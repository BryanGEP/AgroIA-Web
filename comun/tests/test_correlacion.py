"""Correlación: ContextVar, middleware, publicar con la de la petición y la cadena en el
consumidor."""

import json
import logging
import uuid

import fakeredis
import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from agroia_comun.correlacion import CorrelacionMiddleware
from agroia_comun.eventos import Consumidor, ErrorEvento, publicar
from agroia_comun.eventos import correlacion as ctx
from agroia_comun.eventos.catalogo import STREAM_USUARIOS, obtener_tipo
from agroia_comun.seguridad import registrar_evento

USUARIO = str(uuid.uuid4())


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


def sobres(r, stream=STREAM_USUARIOS) -> list[dict]:
    return [json.loads(c["sobre"]) for _, c in r.xrange(stream)]


# --- ContextVar -------------------------------------------------------------------------


def test_con_correlacion_la_pone_y_la_restablece():
    assert ctx.actual() is None
    valor = str(uuid.uuid4())
    with ctx.con_correlacion(valor) as puesta:
        assert puesta == valor == ctx.actual()
    assert ctx.actual() is None


def test_con_correlacion_la_restablece_aunque_falle():
    with pytest.raises(RuntimeError), ctx.con_correlacion(str(uuid.uuid4())):
        raise RuntimeError
    assert ctx.actual() is None


def test_publicar_sin_correlacion_usa_la_actual(r):
    valor = str(uuid.uuid4())
    with ctx.con_correlacion(valor):
        publicar("usuario_registrado", {"usuario_id": USUARIO, "rol": "cliente"},
                 origen="svc-usuarios", cliente=r)  # fmt: skip
    assert sobres(r)[0]["correlacion_id"] == valor


def test_el_consumidor_conserva_la_cadena_y_la_limpia(r):
    """Un manejador que publica otro evento le pasa la correlación del sobre."""
    original = publicar(
        "usuario_registrado", {"usuario_id": USUARIO, "rol": "cliente"},
        origen="svc-usuarios", correlacion_id=str(uuid.uuid4()), cliente=r,
    )  # fmt: skip
    vista = []

    def manejador(sobre):
        vista.append(ctx.actual())
        publicar("sesiones_cerradas", {"usuario_id": USUARIO}, origen="svc-prueba", cliente=r)

    c = Consumidor(
        "svc-prueba", {"usuario_registrado": manejador}, cliente=r, bloqueo_ms=10, latido=0.005
    )
    c.preparar()
    c.una_vuelta()

    assert vista == [original.correlacion_id]
    encadenado = sobres(r)[-1]
    assert encadenado["tipo"] == "sesiones_cerradas"
    assert encadenado["correlacion_id"] == original.correlacion_id
    assert ctx.actual() is None


# --- Middleware ---------------------------------------------------------------------------


def atender(encabezado=None, vista=None):
    vista = vista or (lambda request: HttpResponse(ctx.actual()))
    extra = {"HTTP_X_CORRELACION_ID": encabezado} if encabezado is not None else {}
    request = RequestFactory().get("/", **extra)
    return request, CorrelacionMiddleware(vista)(request)


def test_el_middleware_acepta_un_uuid_y_lo_devuelve():
    valor = str(uuid.uuid4())
    request, respuesta = atender(valor.upper())

    assert respuesta.content.decode() == valor  # la vista la ve normalizada
    assert respuesta["X-Correlacion-Id"] == valor
    assert request.correlacion_id == valor


@pytest.mark.parametrize("encabezado", [None, "", "no-es-uuid", "1' OR '1'='1", "x" * 300])
def test_el_middleware_genera_una_si_no_viene_o_no_es_uuid(encabezado):
    _, respuesta = atender(encabezado)

    generada = respuesta["X-Correlacion-Id"]
    assert uuid.UUID(generada)
    assert generada != encabezado


def test_no_se_arrastra_entre_dos_peticiones_seguidas():
    _, primera = atender()
    _, segunda = atender()

    assert primera["X-Correlacion-Id"] != segunda["X-Correlacion-Id"]
    assert ctx.actual() is None


def test_se_restablece_aunque_la_vista_lance_una_excepcion():
    def falla(request):
        raise RuntimeError("error de la vista")

    with pytest.raises(RuntimeError):
        atender(str(uuid.uuid4()), falla)
    assert ctx.actual() is None


def test_el_log_de_seguridad_lleva_la_correlacion(caplog):
    caplog.set_level(logging.INFO, logger="seguridad")
    valor = str(uuid.uuid4())

    with ctx.con_correlacion(valor):
        registrar_evento("prueba")

    linea = json.loads(caplog.records[-1].getMessage())
    assert linea["correlacion_id"] == valor


# --- Catálogo de la fase 2 ----------------------------------------------------------------


@pytest.mark.parametrize(
    "tipo, datos",
    [
        ("correo_solicitado", {"usuario_id": USUARIO, "tipo_correo": "codigo_2fa"}),
        (
            "correo_solicitado",
            {"usuario_id": USUARIO, "tipo_correo": "verificacion", "token": "abc"},
        ),
        (
            "pedido_estado_cambiado",
            {
                "pedido_id": 1,
                "usuario_id": USUARIO,
                "estado_anterior": "pendiente",
                "estado_nuevo": "robado",
                "total": "10.00",
                "cambiado_por": USUARIO,
            },
        ),
        (
            "pedido_creado",
            {
                "pedido_id": 1,
                "usuario_id": USUARIO,
                "total": "10.00",
                "productos": 1,
                "unidades": 1,
                "metodo_pago": "tarjeta",
                "direccion": "Calle 1",
            },
        ),
        (
            "rol_cambiado",
            {
                "usuario_id": USUARIO,
                "rol_anterior": "cliente",
                "rol_nuevo": "operativo",
                "cambiado_por": USUARIO,
            },
        ),
    ],
)
def test_el_catalogo_rechaza_valores_y_campos_que_no_son_suyos(tipo, datos):
    with pytest.raises(ErrorEvento):
        obtener_tipo(tipo).validar_datos(datos)
