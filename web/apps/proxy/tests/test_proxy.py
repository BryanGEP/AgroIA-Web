"""Proxy /api/<servicio>/<ruta>: valida el JWT en el gateway y reenvía al servicio."""

import json
import logging

import httpx
import pytest

from agroia_comun.pruebas import generar_par_de_llaves
from tests.servicios_falsos import error, token

PRODUCTOS = {"count": 0, "next": None, "previous": None, "results": []}


def bearer(valor: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {valor}"}


# --- Rutas públicas y token ---------------------------------------------------------------


def test_ruta_publica_pasa_sin_token(client, servicios):
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/productos/", httpx.Response(200, json=PRODUCTOS)
    )

    respuesta = client.get("/api/tienda/productos/?q=cobre&page=2")

    assert respuesta.status_code == 200
    assert respuesta.json() == PRODUCTOS
    (peticion,) = servicios.de("svc-tienda")
    assert peticion.url.query == b"q=cobre&page=2"
    assert "authorization" not in peticion.headers


def test_login_es_publico(client, servicios):
    servicios.responder(
        "POST", "svc-usuarios", "/api/v1/auth/login/", httpx.Response(200, json={"access": "a"})
    )

    respuesta = client.post(
        "/api/usuarios/auth/login/",
        {"email": "a@b.mx", "password": "x"},
        content_type="application/json",
    )

    assert respuesta.status_code == 200


@pytest.mark.parametrize(
    ("metodo", "ruta"),
    [
        ("get", "/api/tienda/carrito/"),
        ("post", "/api/tienda/productos/"),
        ("get", "/api/usuarios/usuarios/yo/"),
        ("post", "/api/ia/agente/preguntar/"),
        ("get", "/api/contenido/conversaciones/"),
    ],
)
def test_ruta_privada_sin_token_401_sin_llegar_al_servicio(client, servicios, metodo, ruta):
    respuesta = getattr(client, metodo)(ruta)

    assert respuesta.status_code == 401
    assert respuesta.json() == {
        "error": "no_autenticado",
        "detalle": "No se enviaron las credenciales de autenticación.",
    }
    assert respuesta["WWW-Authenticate"].startswith("Bearer")
    assert servicios.peticiones == []


@pytest.mark.parametrize(
    "valor",
    [
        pytest.param(lambda: "Bearer no-es-un-jwt", id="basura"),
        pytest.param(lambda: f"Bearer {token(minutos=-1)}", id="vencido"),
        pytest.param(lambda: f"Bearer {token(emisor='otro')}", id="otro-emisor"),
        pytest.param(lambda: f"Bearer {token(token_type='refresh')}", id="refresh"),
        pytest.param(lambda: "Token abc", id="otro-esquema"),
        pytest.param(lambda: "Bearer", id="sin-valor"),
    ],
)
def test_token_invalido_401_sin_llegar_al_servicio(client, servicios, valor):
    respuesta = client.get("/api/tienda/carrito/", HTTP_AUTHORIZATION=valor())

    assert respuesta.status_code == 401
    assert respuesta.json()["error"] == "token_invalido"
    assert servicios.peticiones == []


def test_token_firmado_con_otra_llave_401(client, servicios):
    from agroia_comun.pruebas import firmar_token

    ajeno = firmar_token(generar_par_de_llaves()[0], rol="administrador")

    assert client.get("/api/tienda/carrito/", **bearer(ajeno)).status_code == 401
    assert servicios.peticiones == []


def test_token_invalido_en_ruta_publica_tambien_401(client, servicios):
    assert client.get("/api/tienda/productos/", **bearer("no-es-un-jwt")).status_code == 401


def test_el_proxy_nunca_toma_el_token_de_la_sesion(client, servicios, con_sesion):
    # La sesión del navegador tiene un access válido, pero el proxy solo acepta
    # Authorization: una petición sin ese encabezado es anónima.
    con_sesion()

    respuesta = client.get("/api/tienda/carrito/")

    assert respuesta.status_code == 401
    assert respuesta.json()["error"] == "no_autenticado"
    assert servicios.peticiones == []


def test_el_401_del_gateway_queda_en_el_log(client, servicios, caplog):
    caplog.set_level(logging.INFO, logger="seguridad")

    client.get("/api/tienda/carrito/", **bearer("no-es-un-jwt"))

    eventos = [json.loads(r.getMessage()) for r in caplog.records if r.name == "seguridad"]
    assert eventos[-1]["evento"] == "acceso_denegado"
    assert eventos[-1]["capa"] == "gateway"
    assert "no-es-un-jwt" not in caplog.text


# --- Reenvío ----------------------------------------------------------------------------------


def test_reenvia_metodo_cuerpo_y_token_y_devuelve_la_respuesta(client, servicios):
    servicios.responder(
        "POST",
        "svc-tienda",
        "/api/v1/carrito/items/",
        httpx.Response(201, json={"id": 7}, headers={"X-Interno": "no", "Set-Cookie": "a=b"}),
    )
    acceso = token()

    respuesta = client.post(
        "/api/tienda/carrito/items/",
        {"producto": "caldo", "cantidad": 2},
        content_type="application/json",
        **bearer(acceso),
    )

    assert respuesta.status_code == 201
    assert respuesta.json() == {"id": 7}
    assert "Set-Cookie" not in respuesta and "X-Interno" not in respuesta
    (peticion,) = servicios.de("svc-tienda")
    assert peticion.method == "POST"
    assert peticion.headers["authorization"] == f"Bearer {acceso}"
    assert peticion.headers["content-type"] == "application/json"
    assert servicios.cuerpo(peticion) == {"producto": "caldo", "cantidad": 2}


@pytest.mark.parametrize(
    ("ruta", "host", "destino"),
    [
        ("/api/usuarios/usuarios/yo/", "svc-usuarios", "/api/v1/usuarios/yo/"),
        ("/api/contenido/conversaciones/", "svc-contenido", "/api/v1/conversaciones/"),
        ("/api/ia/solicitudes/abc/", "svc-ia", "/solicitudes/abc/"),  # svc-ia sin /api/v1/
    ],
)
def test_cada_servicio_con_su_prefijo(client, servicios, ruta, host, destino):
    servicios.responder("GET", host, destino, httpx.Response(200, json={}))

    assert client.get(ruta, **bearer(token())).status_code == 200
    assert servicios.de(host, destino)


def test_no_reenvia_cookie_host_ni_encabezados_de_salto(client, servicios):
    servicios.responder("GET", "svc-tienda", "/api/v1/carrito/", httpx.Response(200, json={}))
    client.cookies["sessionid"] = "una-cookie"

    client.get(
        "/api/tienda/carrito/",
        HTTP_CONNECTION="keep-alive",
        HTTP_KEEP_ALIVE="timeout=5",
        HTTP_X_INTERNO="secreto",
        HTTP_ACCEPT_LANGUAGE="es-MX",
        **bearer(token()),
    )

    (peticion,) = servicios.de("svc-tienda")
    assert "cookie" not in peticion.headers
    assert "keep-alive" not in peticion.headers
    assert "x-interno" not in peticion.headers
    assert peticion.headers["host"] == "svc-tienda:8000"  # el del servicio, no el del cliente
    assert peticion.headers["accept-language"] == "es-MX"


def test_x_forwarded_for_es_la_ip_real_y_no_la_del_cliente(client, servicios):
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/productos/", httpx.Response(200, json=PRODUCTOS)
    )

    client.get(
        "/api/tienda/productos/",
        REMOTE_ADDR="190.10.20.30",
        HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8",
    )

    (peticion,) = servicios.de("svc-tienda")
    assert peticion.headers["x-forwarded-for"] == "190.10.20.30"


def test_retry_after_y_errores_del_servicio_pasan_tal_cual(client, servicios):
    servicios.responder(
        "POST",
        "svc-usuarios",
        "/api/v1/auth/login/",
        error(429, "demasiados_intentos", "Espera.", **{"Retry-After": "42"}),
    )

    respuesta = client.post("/api/usuarios/auth/login/", {}, content_type="application/json")

    assert respuesta.status_code == 429
    assert respuesta["Retry-After"] == "42"
    assert respuesta.json()["error"] == "demasiados_intentos"


def test_redireccion_del_servicio_se_traduce_a_la_ruta_del_proxy(client, servicios):
    servicios.responder(
        "GET",
        "svc-tienda",
        "/api/v1/productos",
        httpx.Response(301, headers={"Location": "http://svc-tienda:8000/api/v1/productos/"}),
    )

    respuesta = client.get("/api/tienda/productos")

    assert respuesta.status_code == 301
    assert respuesta["Location"] == "/api/tienda/productos/"


# --- Errores del proxy ------------------------------------------------------------------------


def test_servicio_caido_502(client, servicios):
    servicios.caidos.add("svc-tienda")

    respuesta = client.get("/api/tienda/productos/")

    assert respuesta.status_code == 502
    assert respuesta.json() == {
        "error": "servicio_no_disponible",
        "detalle": "El servicio no está disponible.",
    }


def test_servicio_lento_504(client, servicios):
    servicios.lentos.add("svc-ia")

    respuesta = client.post(
        "/api/ia/agente/preguntar/", {}, content_type="application/json", **bearer(token())
    )

    assert respuesta.status_code == 504
    assert respuesta.json()["error"] == "tiempo_agotado"


@pytest.mark.parametrize(
    "ruta",
    [
        "/api/pagos/cobrar/",
        "/api/tienda/../admin/",
        "/api/tienda/%2e%2e/admin/",
        "/api/tienda/./x/",
    ],
)
def test_servicio_inexistente_o_ruta_fuera_de_la_api_404(client, servicios, ruta):
    respuesta = client.get(ruta, **bearer(token()))

    assert respuesta.status_code == 404
    assert servicios.peticiones == []


def test_el_proxy_no_pide_csrf(client, servicios):
    # Solo acepta el token en Authorization; sin cookies de por medio no hay CSRF que evitar.
    from django.test import Client

    servicios.responder(
        "POST", "svc-tienda", "/api/v1/carrito/items/", httpx.Response(201, json={})
    )
    estricto = Client(enforce_csrf_checks=True)

    respuesta = estricto.post(
        "/api/tienda/carrito/items/", {}, content_type="application/json", **bearer(token())
    )

    assert respuesta.status_code == 201
