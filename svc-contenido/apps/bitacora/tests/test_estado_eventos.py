"""GET /api/v1/eventos/estado/: el estado de los streams para el panel, sin datos."""

import pytest
import redis

from agroia_comun.eventos import conexion
from agroia_comun.eventos.catalogo import STREAM_FALLIDOS, STREAM_TIENDA
from agroia_comun.eventos.sobre import crear_sobre

URL = "/api/v1/eventos/estado/"


def test_estado_sin_token_401(anonimo):
    assert anonimo.get(URL).status_code == 401


def test_estado_con_rol_cliente_403(cliente):
    assert cliente.get(URL).status_code == 403


def test_estado_de_streams_grupos_y_fallidos(admin, redis_de_eventos):
    redis_de_eventos.xgroup_create(STREAM_TIENDA, "svc-contenido", id="0", mkstream=True)
    redis_de_eventos.xadd(STREAM_TIENDA, {"sobre": "{}"})
    redis_de_eventos.xreadgroup("svc-contenido", "consumidor-1", {STREAM_TIENDA: ">"}, count=1)
    sobre = crear_sobre(
        "pedido_creado",
        {"pedido_id": 7, "usuario_id": "8d3f6c2a-1b4e-4f7a-9c5d-2e6f8a0b1c3d", "total": "840.50",
         "productos": 1, "unidades": 2, "metodo_pago": "tarjeta"},
        "svc-tienda",
    )  # fmt: skip
    redis_de_eventos.xadd(
        STREAM_FALLIDOS,
        {
            "sobre": sobre.a_json(),
            "grupo": "svc-contenido",
            "stream": STREAM_TIENDA,
            "intentos": "4",
            "motivo": "ConnectionError: no se pudo guardar 840.50 de 8d3f6c2a",
        },
    )

    respuesta = admin.get(URL)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    tienda = next(s for s in cuerpo["streams"] if s["stream"] == STREAM_TIENDA)
    assert tienda["largo"] == 1
    [grupo] = tienda["grupos"]
    assert grupo["grupo"] == "svc-contenido"
    assert grupo["pendientes"] == 1
    assert grupo["consumidores"][0]["nombre"] == "consumidor-1"
    assert cuerpo["fallidos"]["total"] == 1
    [fallido] = cuerpo["fallidos"]["ultimos"]
    assert fallido["tipo"] == "pedido_creado"
    assert fallido["motivo"] == "ConnectionError"  # solo el nombre de la excepción
    assert fallido["intentos"] == 4
    assert fallido["fecha"]
    texto = respuesta.content.decode()
    assert "840.50" not in texto and "8d3f6c2a" not in texto and "sobre" not in fallido


def test_estado_sin_redis_503(admin, monkeypatch):
    def caido():
        raise redis.ConnectionError("sin conexión")

    monkeypatch.setattr(conexion, "cliente", caido)
    conexion.usar(None)

    respuesta = admin.get(URL)

    assert respuesta.status_code == 503
    assert respuesta.json()["error"] == "eventos_no_disponible"


@pytest.mark.parametrize(
    "motivo, esperado",
    [("ConnectionError: algo", "ConnectionError"), ("TimeoutError", "TimeoutError"), (None, None),
     ("redis.exceptions.ResponseError: x", "redis.exceptions.ResponseError")],
)  # fmt: skip
def test_nombre_de_la_excepcion(motivo, esperado):
    from apps.bitacora.servicios import nombre_de_excepcion

    assert nombre_de_excepcion(motivo) == esperado
