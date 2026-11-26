"""Diagnóstico asíncrono: solicitar, copia temporal de la imagen, resultado del worker,
fallo (borra la foto) y vencimiento."""

import json

import fakeredis
import pytest
from django.core.files.storage import default_storage

from agroia_comun.eventos import conexion, publicar
from agroia_comun.eventos.catalogo import STREAM_IA_SOLICITUDES
from apps.diagnosticos import servicios
from config import mongo
from tests.datos import CLIENTE_ID, OTRO_CLIENTE_ID, imagen

SOLICITAR = "/api/v1/diagnosticos/solicitar/"
PROBABILIDADES = {"sano": 0.1, "rona": 0.2, "antracnosis": 0.7}


def pedidos(redis_de_eventos) -> list[dict]:
    return [json.loads(c["sobre"]) for _, c in redis_de_eventos.xrange(STREAM_IA_SOLICITUDES)]


def resultado(tipo: str, pedido: dict, **datos):
    base = {k: pedido["datos"][k] for k in ("solicitud_id", "diagnostico_id", "usuario_id")}
    return publicar(tipo, {**base, **datos}, origen="svc-ia",
                    cliente=fakeredis.FakeRedis(decode_responses=True))  # fmt: skip


@pytest.fixture
def solicitado(cliente, redis_de_eventos) -> tuple[dict, dict]:
    respuesta = cliente.post(SOLICITAR, {"imagen": imagen()}, format="multipart")
    assert respuesta.status_code == 202
    [pedido] = pedidos(redis_de_eventos)
    return respuesta.json(), pedido


def test_solicitar_deja_el_diagnostico_pendiente_y_la_imagen_en_redis(solicitado):
    diagnostico, pedido = solicitado

    assert diagnostico["estado"] == "pendiente" and diagnostico["clase"] is None
    assert pedido["tipo"] == "diagnostico_solicitado"
    assert pedido["datos"]["diagnostico_id"] == diagnostico["id"]
    assert pedido["datos"]["usuario_id"] == str(CLIENTE_ID)
    assert "imagen" not in json.dumps(pedido["datos"])  # la imagen no viaja en el evento
    llave = servicios.llave_de_imagen(pedido["datos"]["solicitud_id"])
    copia = conexion.cliente_binario().get(llave)
    assert copia.startswith(b"\x89PNG")
    assert 0 < conexion.cliente_binario().ttl(llave) <= 180


def test_solicitar_rechaza_lo_que_no_es_jpg_ni_png(cliente):
    respuesta = cliente.post(SOLICITAR, {"imagen": imagen("hoja.webp", "WEBP")},
                             format="multipart")  # fmt: skip
    assert respuesta.status_code == 400


def test_sin_token_401(anonimo):
    assert anonimo.post(SOLICITAR, {"imagen": imagen()}, format="multipart").status_code == 401


def test_el_resultado_queda_guardado_una_sola_vez(cliente, solicitado):
    diagnostico, pedido = solicitado
    sobre = resultado("diagnostico_generado", pedido, clase="antracnosis", confianza=0.7,
                      probabilidades=PROBABILIDADES, modelo_version="v1")  # fmt: skip

    servicios.guardar_resultado(sobre)
    servicios.guardar_resultado(sobre)

    guardado = cliente.get(f"/api/v1/diagnosticos/{diagnostico['id']}/").json()
    assert guardado["estado"] == "listo"
    assert guardado["clase"] == "antracnosis" and guardado["es_prueba"] is False
    assert cliente.get("/api/v1/diagnosticos/").json()["count"] == 1


def test_un_resultado_del_clasificador_de_prueba_se_marca(cliente, solicitado):
    diagnostico, pedido = solicitado
    servicios.guardar_resultado(
        resultado("diagnostico_generado", pedido, clase="sano", confianza=0.8,
                  probabilidades={"sano": 0.8, "rona": 0.1, "antracnosis": 0.1},
                  modelo_version="prueba-no-es-un-modelo")
    )  # fmt: skip

    assert cliente.get(f"/api/v1/diagnosticos/{diagnostico['id']}/").json()["es_prueba"] is True


def test_un_fallo_borra_la_foto_y_lo_oculta_del_historial(cliente, solicitado):
    diagnostico, pedido = solicitado
    nombre = mongo.coleccion("diagnosticos").find_one({})["imagen"]
    assert default_storage.exists(nombre)

    servicios.guardar_fallido(resultado("diagnostico_fallido", pedido,
                                        codigo="modelo_no_disponible"))  # fmt: skip

    guardado = cliente.get(f"/api/v1/diagnosticos/{diagnostico['id']}/").json()
    assert (guardado["estado"], guardado["codigo"]) == ("fallido", "modelo_no_disponible")
    assert guardado["imagen_url"] is None
    assert not default_storage.exists(nombre)
    assert cliente.get("/api/v1/diagnosticos/").json()["count"] == 0


def test_un_resultado_de_otro_usuario_no_se_guarda(cliente, solicitado):
    diagnostico, pedido = solicitado
    pedido["datos"]["usuario_id"] = str(OTRO_CLIENTE_ID)

    servicios.guardar_resultado(
        resultado("diagnostico_generado", pedido, clase="sano", confianza=0.8,
                  probabilidades={"sano": 0.8, "rona": 0.1, "antracnosis": 0.1},
                  modelo_version="v1")
    )  # fmt: skip

    assert cliente.get(f"/api/v1/diagnosticos/{diagnostico['id']}/").json()["estado"] == (
        "pendiente"
    )


def test_un_diagnostico_vencido_queda_fallido(cliente, settings, redis_de_eventos):
    settings.IA_SOLICITUD_VENCE_SEGUNDOS = -1
    diagnostico = cliente.post(SOLICITAR, {"imagen": imagen()}, format="multipart").json()

    guardado = cliente.get(f"/api/v1/diagnosticos/{diagnostico['id']}/").json()

    assert (guardado["estado"], guardado["codigo"]) == ("fallido", "vencida")
    assert guardado["imagen_url"] is None


def test_el_diagnostico_ajeno_responde_404(otro_cliente, solicitado):
    diagnostico, _ = solicitado
    assert otro_cliente.get(f"/api/v1/diagnosticos/{diagnostico['id']}/").status_code == 404


def test_cien_consultas_de_estado_sin_429(cliente, solicitado):
    diagnostico, _ = solicitado
    estados = {cliente.get(f"/api/v1/diagnosticos/{diagnostico['id']}/").status_code
               for _ in range(100)}  # fmt: skip
    assert estados == {200}
