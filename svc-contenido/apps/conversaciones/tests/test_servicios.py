"""Lógica de negocio de las conversaciones (MongoDB simulado con mongomock)."""

from datetime import timedelta

import pytest
from bson import ObjectId
from django.http import Http404

from agroia_comun.errores import ErrorDeNegocio
from apps.conversaciones import servicios
from config import mongo
from tests.datos import CLIENTE_ID, OTRO_CLIENTE_ID


def test_crear_conversacion():
    conversacion = servicios.crear(CLIENTE_ID, "Manchas en hojas")

    assert isinstance(conversacion["_id"], ObjectId)
    assert conversacion["usuario_id"] == CLIENTE_ID
    assert conversacion["titulo"] == "Manchas en hojas"
    assert conversacion["mensajes"] == []
    assert conversacion["creada_en"] == conversacion["actualizada_en"]


def test_listar_solo_las_propias_mas_recientes_primero(mongo_simulado):
    vieja = servicios.crear(CLIENTE_ID, "Vieja")
    nueva = servicios.crear(CLIENTE_ID, "Nueva")
    servicios.crear(OTRO_CLIENTE_ID, "De otro")
    hace_una_hora = mongo.ahora() - timedelta(hours=1)
    mongo_simulado["conversaciones"].update_many({}, {"$set": {"actualizada_en": hace_una_hora}})
    servicios.agregar_mensaje(CLIENTE_ID, str(vieja["_id"]), "usuario", "Hola", None)

    consulta = servicios.consulta_propias(CLIENTE_ID)

    assert consulta.count() == 2
    titulos = [c["titulo"] for c in consulta[0:20]]
    assert titulos == ["Vieja", "Nueva"]  # la vieja recibió un mensaje después
    assert "mensajes" not in consulta[0:1][0]
    assert nueva["_id"]


def test_obtener_conversacion_de_otro_es_404():
    conversacion = servicios.crear(CLIENTE_ID, "Privada")

    with pytest.raises(Http404):
        servicios.obtener_propia(OTRO_CLIENTE_ID, str(conversacion["_id"]))


@pytest.mark.parametrize("id_texto", ["no-es-un-id", "123", str(ObjectId())])
def test_id_mal_formado_o_inexistente_es_404(id_texto):
    with pytest.raises(Http404):
        servicios.obtener_propia(CLIENTE_ID, id_texto)


def test_agregar_mensajes_de_usuario_y_agente():
    conversacion = servicios.crear(CLIENTE_ID, "Riego")
    id_texto = str(conversacion["_id"])

    servicios.agregar_mensaje(CLIENTE_ID, id_texto, "usuario", "¿Cada cuándo riego?", None)
    actualizada = servicios.agregar_mensaje(
        CLIENTE_ID, id_texto, "agente", "Cada 3 a 5 días.", ["Guía de riego"]
    )

    assert [m["rol"] for m in actualizada["mensajes"]] == ["usuario", "agente"]
    assert actualizada["mensajes"][1]["fuentes"] == ["Guía de riego"]
    assert "fuentes" not in actualizada["mensajes"][0]
    assert actualizada["actualizada_en"] >= conversacion["actualizada_en"]


def test_no_se_agrega_mensaje_a_conversacion_de_otro():
    conversacion = servicios.crear(CLIENTE_ID, "Privada")

    with pytest.raises(Http404):
        servicios.agregar_mensaje(OTRO_CLIENTE_ID, str(conversacion["_id"]), "usuario", "x", None)


def test_limite_de_200_mensajes(mongo_simulado):
    conversacion = servicios.crear(CLIENTE_ID, "Larga")
    mensajes = [{"rol": "usuario", "texto": str(i)} for i in range(servicios.LIMITE_MENSAJES - 1)]
    mongo_simulado["conversaciones"].update_one(
        {"_id": conversacion["_id"]}, {"$set": {"mensajes": mensajes}}
    )
    id_texto = str(conversacion["_id"])

    servicios.agregar_mensaje(CLIENTE_ID, id_texto, "usuario", "el 200", None)
    with pytest.raises(ErrorDeNegocio) as error:
        servicios.agregar_mensaje(CLIENTE_ID, id_texto, "usuario", "el 201", None)

    assert error.value.codigo == "conversacion_llena"
    assert len(servicios.obtener_propia(CLIENTE_ID, id_texto)["mensajes"]) == 200


def test_borrar_conversacion():
    conversacion = servicios.crear(CLIENTE_ID, "Borrar")
    id_texto = str(conversacion["_id"])

    with pytest.raises(Http404):
        servicios.borrar(OTRO_CLIENTE_ID, id_texto)
    servicios.borrar(CLIENTE_ID, id_texto)
    with pytest.raises(Http404):
        servicios.obtener_propia(CLIENTE_ID, id_texto)
