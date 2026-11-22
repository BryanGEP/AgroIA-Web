"""Correlación en el gateway y log por petición sin tokens."""

import json
import logging
import uuid

import httpx
import pytest

from agroia_comun.eventos import correlacion as ctx
from tests.servicios_falsos import token

TOKEN_DE_VERIFICACION = "VERIFICA-dXN1YXJpbw:1vZ9Xh:SECRETO-de-verificacion-123"
UID, TOKEN_DE_RECUPERACION = "MTA", "cr1t8k-SECRETO-de-recuperacion-456"


class TodoElLog(logging.Handler):
    """Junta lo que escribe cualquier logger, también los que no propagan."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lineas: list[str] = []

    def emit(self, registro):
        self.lineas.append(registro.getMessage())


@pytest.fixture
def todo_el_log():
    manejador = TodoElLog()
    loggers = [logging.getLogger()] + [
        logging.getLogger(nombre) for nombre in list(logging.root.manager.loggerDict)
    ]
    anteriores = [(lg, lg.level) for lg in loggers]
    for lg in loggers:
        lg.addHandler(manejador)
        lg.setLevel(logging.DEBUG)
    yield manejador
    for lg, nivel in anteriores:
        lg.removeHandler(manejador)
        lg.setLevel(nivel)


def peticiones(log: TodoElLog) -> list[dict]:
    salida = []
    for linea in log.lineas:
        try:
            datos = json.loads(linea)
        except ValueError:
            continue
        if datos.get("evento") == "peticion":
            salida.append(datos)
    return salida


# --- La correlación de cada petición ------------------------------------------------------


def test_genera_una_correlacion_si_el_navegador_no_la_manda(client):
    respuesta = client.get("/")

    assert uuid.UUID(respuesta["X-Correlacion-Id"])


def test_acepta_la_del_navegador_si_es_un_uuid(client):
    valor = str(uuid.uuid4())

    assert client.get("/", HTTP_X_CORRELACION_ID=valor)["X-Correlacion-Id"] == valor


@pytest.mark.parametrize("valor", ["abc", "1; DROP TABLE", "\r\nX-Inyectado: si", "x" * 400])
def test_si_no_es_uuid_genera_una_nueva(client, valor):
    generada = client.get("/", HTTP_X_CORRELACION_ID=valor)["X-Correlacion-Id"]

    assert uuid.UUID(generada) and generada != valor


def test_no_se_arrastra_entre_dos_peticiones(client):
    primera = client.get("/")["X-Correlacion-Id"]
    segunda = client.get("/")["X-Correlacion-Id"]

    assert primera != segunda
    assert ctx.actual() is None


def test_las_llamadas_internas_llevan_la_correlacion_validada(client, servicios):
    servicios.responder(
        "POST", "svc-usuarios", "/api/v1/auth/recuperar/", httpx.Response(200, json={})
    )
    valor = str(uuid.uuid4())

    client.post("/recuperar/", {"email": "ana@example.com"}, HTTP_X_CORRELACION_ID=valor)

    [peticion] = servicios.de("svc-usuarios")
    assert peticion.headers["X-Correlacion-Id"] == valor


def test_el_proxy_reenvia_la_correlacion_validada_y_no_la_del_cliente(client, servicios):
    servicios.responder("GET", "svc-tienda", "/api/v1/productos/", httpx.Response(200, json={}))

    respuesta = client.get("/api/tienda/productos/", HTTP_X_CORRELACION_ID="no-es-uuid")

    [peticion] = servicios.de("svc-tienda")
    reenviada = peticion.headers["X-Correlacion-Id"]
    assert uuid.UUID(reenviada) and reenviada != "no-es-uuid"
    assert respuesta["X-Correlacion-Id"] == reenviada


def test_el_proxy_reenvia_la_misma_si_es_valida(client, servicios):
    servicios.responder("GET", "svc-tienda", "/api/v1/carrito/", httpx.Response(200, json={}))
    valor = str(uuid.uuid4())

    client.get(
        "/api/tienda/carrito/",
        HTTP_AUTHORIZATION=f"Bearer {token()}",
        HTTP_X_CORRELACION_ID=valor,
    )

    assert servicios.de("svc-tienda")[0].headers["X-Correlacion-Id"] == valor


# --- Log por petición ---------------------------------------------------------------------


def test_cada_peticion_deja_una_linea_con_su_patron_y_correlacion(client, todo_el_log):
    valor = str(uuid.uuid4())

    client.get("/catalogo/urea-46/?q=algo", HTTP_X_CORRELACION_ID=valor)

    [linea] = [p for p in peticiones(todo_el_log) if p["ruta"] == "catalogo/<slug:slug>/"]
    assert linea["metodo"] == "GET"
    assert linea["correlacion_id"] == valor
    assert isinstance(linea["duracion_ms"], int)
    assert "urea-46" not in json.dumps(linea) and "q=algo" not in json.dumps(linea)


def test_ningun_log_tiene_los_tokens_de_verificacion_ni_de_recuperacion(
    client, servicios, todo_el_log
):
    servicios.responder(
        "POST", "svc-usuarios", "/api/v1/auth/verificar-correo/",
        httpx.Response(200, json={"mensaje": "Correo verificado."}),
    )  # fmt: skip
    servicios.responder(
        "POST", "svc-usuarios", "/api/v1/auth/restablecer/", httpx.Response(200, json={})
    )

    client.get("/verificar-correo/", {"token": TOKEN_DE_VERIFICACION})
    client.get(f"/restablecer/{UID}/{TOKEN_DE_RECUPERACION}/")
    client.post(
        f"/restablecer/{UID}/{TOKEN_DE_RECUPERACION}/",
        {"password": "Hass-Mendez-2026", "password_confirmacion": "Hass-Mendez-2026"},
    )
    # Una ruta que no existe con un token: django.request registra «Not Found».
    client.get(f"/restablecer-mal/{TOKEN_DE_RECUPERACION}/")

    texto = "\n".join(todo_el_log.lineas)
    assert TOKEN_DE_VERIFICACION not in texto
    assert TOKEN_DE_RECUPERACION not in texto
    rutas = {p["ruta"] for p in peticiones(todo_el_log)}
    assert {"verificar-correo/", "restablecer/<str:uid>/<str:token>/", "(sin ruta)"} <= rutas


def test_el_log_de_runserver_no_escribe_la_ruta_real(todo_el_log):
    logging.getLogger("django.server").info(
        '"%s" %s %s', f"GET /restablecer/{UID}/{TOKEN_DE_RECUPERACION}/ HTTP/1.1", "200", "12"
    )

    assert TOKEN_DE_RECUPERACION not in "\n".join(todo_el_log.lineas)
