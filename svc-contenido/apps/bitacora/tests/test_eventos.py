"""Consumidor de svc-contenido: usuario_registrado llega a la bitácora una sola vez."""

import uuid

import pytest
from django.core.management import call_command

from agroia_comun.eventos import Consumidor, publicar
from apps.bitacora import servicios
from apps.bitacora.eventos import GRUPO, MANEJADORES
from config import mongo

USUARIO = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def indices():
    call_command("crear_indices", verbosity=0)


def bitacora() -> list[dict]:
    return list(mongo.coleccion(servicios.COLECCION).find({}, {"_id": 0}))


def consumidor(redis_de_eventos) -> Consumidor:
    c = Consumidor(GRUPO, MANEJADORES, cliente=redis_de_eventos, bloqueo_ms=10)
    c.preparar()
    return c


def test_usuario_registrado_llega_a_la_bitacora(redis_de_eventos):
    sobre = publicar(
        "usuario_registrado",
        {"usuario_id": USUARIO, "rol": "cliente"},
        origen="svc-usuarios",
        cliente=redis_de_eventos,
    )

    assert consumidor(redis_de_eventos).una_vuelta() == 1

    [evento] = bitacora()
    assert evento["tipo"] == "usuario_registrado"
    assert evento["usuario_id"] == USUARIO
    assert evento["servicio"] == "svc-usuarios"
    assert evento["datos"] == {"rol": "cliente"}
    assert evento["evento_id"] == sobre.id
    assert evento["correlacion_id"] == sobre.correlacion_id


def test_el_manejador_es_idempotente_aunque_se_llame_dos_veces(redis_de_eventos):
    """Si el consumidor muere después de guardar y antes de confirmar, el evento se vuelve a
    entregar: el índice único de evento_id evita el duplicado."""
    sobre = publicar(
        "usuario_registrado",
        {"usuario_id": USUARIO, "rol": "cliente"},
        origen="svc-usuarios",
        cliente=redis_de_eventos,
    )

    assert servicios.registrar_desde_evento(sobre) is True
    assert servicios.registrar_desde_evento(sobre) is False

    assert len(bitacora()) == 1


def test_los_eventos_manuales_sin_evento_id_no_chocan_con_el_indice():
    servicios.registrar("pedido_creado", USUARIO, "svc-tienda", {"pedido_id": 1})
    servicios.registrar("pedido_creado", USUARIO, "svc-tienda", {"pedido_id": 2})

    assert len(bitacora()) == 2


def test_crear_indices_crea_el_indice_unico_de_evento_id(mongo_simulado):
    indices = mongo_simulado[servicios.COLECCION].index_information().values()

    [unico] = [i for i in indices if i["key"] == [("evento_id", 1)]]
    assert unico["unique"] and unico["sparse"]
