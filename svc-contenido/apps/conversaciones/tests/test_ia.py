"""Preguntas asíncronas a la IA: solicitud, evento, respuesta del worker, vencimiento y
reintento."""

import json
import logging
import uuid

import fakeredis
import pytest
import redis

from agroia_comun.eventos import Sobre, conexion, publicar
from agroia_comun.eventos.catalogo import STREAM_IA_SOLICITUDES
from apps.conversaciones import servicios
from config import mongo
from tests.datos import CLIENTE_ID, OTRO_CLIENTE_ID

PREGUNTA = "¿Cada cuánto aplico el fungicida en mi huerta de Tacámbaro?"
RESPUESTA = "Cada 21 días en temporada de lluvias, según el manual."


def url(conversacion_id: str, accion: str = "") -> str:
    return f"/api/v1/conversaciones/{conversacion_id}/{accion}"


@pytest.fixture
def conversacion(cliente) -> str:
    return cliente.post("/api/v1/conversaciones/", {"titulo": "Riego"}, format="json").json()["id"]


def solicitudes(redis_de_eventos) -> list[dict]:
    return [json.loads(c["sobre"]) for _, c in redis_de_eventos.xrange(STREAM_IA_SOLICITUDES)]


def resultado(tipo: str, sobre_pedido: dict, **datos) -> Sobre:
    base = {k: sobre_pedido["datos"][k] for k in ("solicitud_id", "usuario_id", "conversacion_id")}
    return publicar(tipo, {**base, **datos}, origen="svc-ia",
                    cliente=fakeredis.FakeRedis(decode_responses=True))  # fmt: skip


# --- Pedir --------------------------------------------------------------------------------


def test_preguntar_guarda_la_pregunta_y_publica_la_solicitud(
    cliente, conversacion, redis_de_eventos
):
    cliente.post(url(conversacion, "mensajes/"), {"rol": "usuario", "texto": "Hola"}, format="json")
    correlacion = str(uuid.uuid4())

    respuesta = cliente.post(
        url(conversacion, "preguntar/"), {"texto": PREGUNTA}, format="json",
        HTTP_X_CORRELACION_ID=correlacion,
    )  # fmt: skip

    assert respuesta.status_code == 202
    solicitud = respuesta.json()
    assert solicitud["estado"] == "pendiente"
    [sobre] = solicitudes(redis_de_eventos)
    assert sobre["tipo"] == "ia_pregunta_solicitada"
    assert sobre["origen"] == "svc-contenido"
    assert sobre["correlacion_id"] == correlacion
    assert sobre["datos"]["solicitud_id"] == solicitud["id"]
    assert sobre["datos"]["usuario_id"] == str(CLIENTE_ID)
    assert sobre["datos"]["pregunta"] == PREGUNTA
    assert sobre["datos"]["historial"] == [{"rol": "usuario", "texto": "Hola"}]  # sin la nueva
    mensajes = cliente.get(url(conversacion)).json()["mensajes"]
    assert [m["texto"] for m in mensajes] == ["Hola", PREGUNTA]


def test_la_pregunta_no_aparece_en_ningun_log(cliente, conversacion, caplog):
    caplog.set_level(logging.DEBUG)

    cliente.post(url(conversacion, "preguntar/"), {"texto": PREGUNTA}, format="json")

    assert "Tacámbaro" not in caplog.text
    assert "evento_publicado" in caplog.text


def test_una_sola_solicitud_pendiente_por_conversacion(cliente, conversacion):
    cliente.post(url(conversacion, "preguntar/"), {"texto": PREGUNTA}, format="json")

    segunda = cliente.post(url(conversacion, "preguntar/"), {"texto": "Otra"}, format="json")

    assert segunda.status_code == 409
    assert segunda.json()["error"] == "solicitud_en_curso"


def test_preguntar_en_una_conversacion_ajena_responde_404(otro_cliente, conversacion):
    respuesta = otro_cliente.post(url(conversacion, "preguntar/"), {"texto": "x"}, format="json")

    assert respuesta.status_code == 404


@pytest.mark.parametrize("accion", ["preguntar/", "reintentar/", "solicitud/"])
def test_sin_token_401_y_sin_rol_403(anonimo, sin_rol, conversacion, accion):
    metodo = "get" if accion == "solicitud/" else "post"
    assert getattr(anonimo, metodo)(url(conversacion, accion)).status_code == 401
    assert getattr(sin_rol, metodo)(url(conversacion, accion)).status_code == 403


def test_preguntar_sin_texto_400(cliente, conversacion):
    respuesta = cliente.post(url(conversacion, "preguntar/"), {"texto": ""}, format="json")
    assert respuesta.status_code == 400


def test_con_redis_caido_la_solicitud_queda_fallida_y_se_puede_reintentar(
    cliente, conversacion, monkeypatch
):
    class Caido(fakeredis.FakeRedis):
        def pipeline(self, *a, **k):
            raise redis.ConnectionError("Connection refused")

        def xadd(self, *a, **k):
            raise redis.ConnectionError("Connection refused")

    conexion.usar(Caido(decode_responses=True))

    respuesta = cliente.post(url(conversacion, "preguntar/"), {"texto": PREGUNTA}, format="json")

    assert respuesta.status_code == 202
    assert respuesta.json()["estado"] == "fallido"
    assert respuesta.json()["codigo"] == "servicio_no_disponible"


# --- Respuesta del worker ---------------------------------------------------------------------


def test_la_respuesta_se_guarda_una_sola_vez(cliente, conversacion, redis_de_eventos):
    cliente.post(url(conversacion, "preguntar/"), {"texto": PREGUNTA}, format="json")
    [pedido] = solicitudes(redis_de_eventos)
    sobre = resultado("ia_respuesta_generada", pedido, respuesta=RESPUESTA, fuentes=["Manual"])

    servicios.guardar_respuesta(sobre)
    servicios.guardar_respuesta(sobre)  # llega repetido

    estado = cliente.get(url(conversacion, "solicitud/")).json()
    assert estado["estado"] == "listo"
    assert estado["respuesta"] == RESPUESTA
    assert estado["fuentes"] == ["Manual"]
    mensajes = cliente.get(url(conversacion)).json()["mensajes"]
    assert [m["rol"] for m in mensajes] == ["usuario", "agente"]


@pytest.mark.parametrize("campo", ["usuario_id", "conversacion_id", "solicitud_id"])
def test_no_guarda_si_el_evento_no_coincide(cliente, conversacion, redis_de_eventos, campo):
    cliente.post(url(conversacion, "preguntar/"), {"texto": PREGUNTA}, format="json")
    [pedido] = solicitudes(redis_de_eventos)
    otro = {
        "usuario_id": str(OTRO_CLIENTE_ID),
        "conversacion_id": "6afe7fe1ae4b683f2b9e996f",
        "solicitud_id": str(uuid.uuid4()),
    }[campo]
    pedido["datos"][campo] = otro

    servicios.guardar_respuesta(resultado("ia_respuesta_generada", pedido, respuesta="x",
                                          fuentes=[]))  # fmt: skip

    assert cliente.get(url(conversacion, "solicitud/")).json()["estado"] == "pendiente"
    assert len(cliente.get(url(conversacion)).json()["mensajes"]) == 1


def test_una_fallida_marca_la_solicitud_y_reintentar_no_repite_la_pregunta(
    cliente, conversacion, redis_de_eventos
):
    cliente.post(url(conversacion, "preguntar/"), {"texto": PREGUNTA}, format="json")
    [pedido] = solicitudes(redis_de_eventos)
    servicios.guardar_fallida(
        resultado("ia_respuesta_fallida", pedido, codigo="agente_no_disponible")
    )
    estado = cliente.get(url(conversacion, "solicitud/")).json()
    assert (estado["estado"], estado["codigo"]) == ("fallido", "agente_no_disponible")

    respuesta = cliente.post(url(conversacion, "reintentar/"))

    assert respuesta.status_code == 202
    nueva = respuesta.json()
    assert nueva["estado"] == "pendiente" and nueva["id"] != estado["id"]
    segunda = solicitudes(redis_de_eventos)[-1]
    assert segunda["datos"]["pregunta"] == PREGUNTA
    assert segunda["datos"]["historial"] == []
    assert len(cliente.get(url(conversacion)).json()["mensajes"]) == 1


def test_reintentar_sin_pregunta_pendiente_o_con_una_en_curso_409(cliente, conversacion):
    assert cliente.post(url(conversacion, "reintentar/")).json()["error"] == (
        "sin_pregunta_pendiente"
    )
    cliente.post(url(conversacion, "preguntar/"), {"texto": PREGUNTA}, format="json")
    assert cliente.post(url(conversacion, "reintentar/")).json()["error"] == "solicitud_en_curso"


# --- Vencimiento ------------------------------------------------------------------------------


def test_una_solicitud_vencida_queda_fallida_y_la_respuesta_tardia_se_descarta(
    cliente, conversacion, redis_de_eventos, settings, caplog
):
    caplog.set_level(logging.INFO, logger="eventos")
    settings.IA_SOLICITUD_VENCE_SEGUNDOS = -1  # vence al instante
    cliente.post(url(conversacion, "preguntar/"), {"texto": PREGUNTA}, format="json")
    [pedido] = solicitudes(redis_de_eventos)

    estado = cliente.get(url(conversacion, "solicitud/")).json()
    assert (estado["estado"], estado["codigo"]) == ("fallido", "vencida")

    servicios.guardar_respuesta(resultado("ia_respuesta_generada", pedido, respuesta=RESPUESTA,
                                          fuentes=[]))  # fmt: skip

    assert len(cliente.get(url(conversacion)).json()["mensajes"]) == 1
    assert "respuesta_tardia" in caplog.text
    assert RESPUESTA not in caplog.text


def test_el_vencimiento_tambien_se_aplica_al_llegar_el_evento(
    cliente, conversacion, redis_de_eventos, settings
):
    settings.IA_SOLICITUD_VENCE_SEGUNDOS = -1
    cliente.post(url(conversacion, "preguntar/"), {"texto": PREGUNTA}, format="json")
    [pedido] = solicitudes(redis_de_eventos)

    servicios.guardar_respuesta(resultado("ia_respuesta_generada", pedido, respuesta=RESPUESTA,
                                          fuentes=[]))  # fmt: skip

    doc = mongo.coleccion("conversaciones").find_one({})
    assert doc["solicitud"]["estado"] == "fallido" and doc["solicitud"]["codigo"] == "vencida"


# --- Polling ----------------------------------------------------------------------------------


def test_una_espera_completa_de_polling_no_recibe_429(cliente, conversacion):
    """La pantalla consulta cada 2 s y luego cada 5 s durante 180 s: menos de 50 consultas.
    Se hacen 100 sin un solo 429."""
    cliente.post(url(conversacion, "preguntar/"), {"texto": PREGUNTA}, format="json")

    estados = {cliente.get(url(conversacion, "solicitud/")).status_code for _ in range(100)}

    assert estados == {200}


def test_la_solicitud_de_otro_usuario_responde_404(otro_cliente, admin, cliente, conversacion):
    cliente.post(url(conversacion, "preguntar/"), {"texto": PREGUNTA}, format="json")

    assert otro_cliente.get(url(conversacion, "solicitud/")).status_code == 404
    assert admin.get(url(conversacion, "solicitud/")).status_code == 404  # son privadas
