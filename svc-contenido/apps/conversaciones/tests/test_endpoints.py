"""Endpoints de conversaciones: caso correcto, validación, 401, 403 y recursos ajenos."""

import pytest
from bson import ObjectId

from apps.conversaciones import servicios
from tests.datos import ADMIN_ID, CLIENTE_ID, OTRO_CLIENTE_ID

URL = "/api/v1/conversaciones/"


def crear(usuario_id: int = CLIENTE_ID, titulo: str = "Manchas en hojas") -> str:
    return str(servicios.crear(usuario_id, titulo)["_id"])


def test_crear_conversacion(cliente):
    respuesta = cliente.post(URL, {"titulo": "Manchas en hojas"}, format="json")

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["titulo"] == "Manchas en hojas"
    assert cuerpo["usuario_id"] == CLIENTE_ID
    assert cuerpo["mensajes"] == []
    assert ObjectId.is_valid(cuerpo["id"])


def test_crear_sin_titulo_usa_uno_por_defecto(cliente):
    respuesta = cliente.post(URL, {}, format="json")

    assert respuesta.status_code == 201
    assert respuesta.json()["titulo"] == "Nueva conversación"


def test_titulo_demasiado_largo_400(cliente):
    respuesta = cliente.post(URL, {"titulo": "x" * 121}, format="json")

    assert respuesta.status_code == 400
    assert "titulo" in respuesta.json()["campos"]


def test_crear_401_y_403(anonimo, sin_rol):
    assert anonimo.post(URL, {}, format="json").status_code == 401
    assert sin_rol.post(URL, {}, format="json").status_code == 403


def test_listar_propias_paginado(cliente):
    for i in range(23):
        crear(titulo=f"Conversación {i}")
    crear(OTRO_CLIENTE_ID, "De otro")

    primera = cliente.get(URL).json()
    segunda = cliente.get(URL, {"page": 2}).json()

    assert primera["count"] == 23
    assert len(primera["results"]) == 20
    assert len(segunda["results"]) == 3
    assert primera["next"] is not None
    assert primera["results"][0]["titulo"] == "Conversación 22"
    assert "mensajes" not in primera["results"][0]


def test_pagina_inexistente_404(cliente):
    respuesta = cliente.get(URL, {"page": 5})

    assert respuesta.status_code == 404
    assert respuesta.json()["error"] == "no_encontrado"


def test_admin_solo_ve_sus_propias_conversaciones(admin):
    crear(CLIENTE_ID)
    crear(ADMIN_ID, "Del admin")

    resultados = admin.get(URL).json()["results"]

    assert [c["titulo"] for c in resultados] == ["Del admin"]


def test_listar_401_y_403(anonimo, sin_rol):
    assert anonimo.get(URL).status_code == 401
    assert sin_rol.get(URL).status_code == 403


def test_ver_detalle_con_mensajes(cliente):
    id_texto = crear()
    servicios.agregar_mensaje(CLIENTE_ID, id_texto, "usuario", "Hola", None)

    respuesta = cliente.get(f"{URL}{id_texto}/")

    assert respuesta.status_code == 200
    assert respuesta.json()["mensajes"][0]["texto"] == "Hola"


def test_ver_conversacion_ajena_404(otro_cliente, admin):
    id_texto = crear()

    assert otro_cliente.get(f"{URL}{id_texto}/").status_code == 404
    # Las conversaciones son privadas: tampoco el administrador las ve.
    assert admin.get(f"{URL}{id_texto}/").status_code == 404


@pytest.mark.parametrize("id_texto", ["abc", str(ObjectId())])
def test_id_invalido_o_inexistente_404(cliente, id_texto):
    respuesta = cliente.get(f"{URL}{id_texto}/")

    assert respuesta.status_code == 404
    assert respuesta.json()["error"] == "no_encontrado"


def test_ver_detalle_401_y_403(anonimo, sin_rol):
    id_texto = crear()

    assert anonimo.get(f"{URL}{id_texto}/").status_code == 401
    assert sin_rol.get(f"{URL}{id_texto}/").status_code == 403


def test_borrar(cliente, otro_cliente, anonimo, sin_rol):
    id_texto = crear()
    url = f"{URL}{id_texto}/"

    assert anonimo.delete(url).status_code == 401
    assert sin_rol.delete(url).status_code == 403
    assert otro_cliente.delete(url).status_code == 404
    assert cliente.delete(url).status_code == 204
    assert cliente.get(url).status_code == 404


def test_agregar_mensaje(cliente):
    id_texto = crear()
    url = f"{URL}{id_texto}/mensajes/"

    cliente.post(url, {"rol": "usuario", "texto": "¿Qué es la roña?"}, format="json")
    respuesta = cliente.post(
        url,
        {"rol": "agente", "texto": "Es una enfermedad por hongos.", "fuentes": ["Manual SENASICA"]},
        format="json",
    )

    assert respuesta.status_code == 201
    mensajes = respuesta.json()["mensajes"]
    assert [m["rol"] for m in mensajes] == ["usuario", "agente"]
    assert mensajes[1]["fuentes"] == ["Manual SENASICA"]
    assert "fecha" in mensajes[0]


@pytest.mark.parametrize(
    ("datos", "campo"),
    [
        ({"rol": "sistema", "texto": "x"}, "rol"),
        ({"rol": "usuario", "texto": ""}, "texto"),
        ({"rol": "usuario"}, "texto"),
        ({"rol": "usuario", "texto": "x", "fuentes": ["no aplica"]}, "fuentes"),
    ],
)
def test_mensaje_invalido_400(cliente, datos, campo):
    respuesta = cliente.post(f"{URL}{crear()}/mensajes/", datos, format="json")

    assert respuesta.status_code == 400
    assert campo in respuesta.json()["campos"]


def test_mensaje_en_conversacion_ajena_404(otro_cliente):
    respuesta = otro_cliente.post(
        f"{URL}{crear()}/mensajes/", {"rol": "usuario", "texto": "x"}, format="json"
    )

    assert respuesta.status_code == 404


def test_mensaje_al_llegar_al_limite_409(cliente, mongo_simulado):
    id_texto = crear()
    mongo_simulado["conversaciones"].update_one(
        {"_id": ObjectId(id_texto)},
        {"$set": {"mensajes": [{"rol": "usuario", "texto": "x"}] * servicios.LIMITE_MENSAJES}},
    )

    respuesta = cliente.post(
        f"{URL}{id_texto}/mensajes/", {"rol": "usuario", "texto": "uno más"}, format="json"
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["error"] == "conversacion_llena"


def test_mensaje_401_y_403(anonimo, sin_rol):
    url = f"{URL}{crear()}/mensajes/"

    assert anonimo.post(url, {"rol": "usuario", "texto": "x"}, format="json").status_code == 401
    assert sin_rol.post(url, {"rol": "usuario", "texto": "x"}, format="json").status_code == 403
