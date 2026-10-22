"""Formato común de errores: {"error", "detalle"} y "campos" en validación."""

from rest_framework.test import APIClient


def test_error_de_validacion_incluye_campos():
    respuesta = APIClient().post("/errores/", {"cantidad": 0}, format="json")

    assert respuesta.status_code == 400
    cuerpo = respuesta.json()
    assert cuerpo["error"] == "validacion"
    assert isinstance(cuerpo["detalle"], str)
    assert "cantidad" in cuerpo["campos"]


def test_error_de_negocio_usa_su_codigo():
    respuesta = APIClient().post("/errores/", {"caso": "negocio"}, format="json")

    assert respuesta.status_code == 409
    assert respuesta.json() == {"error": "stock_insuficiente", "detalle": "Solo quedan 2 piezas."}


def test_no_encontrado():
    respuesta = APIClient().post("/errores/", {"caso": "no_existe"}, format="json")

    assert respuesta.status_code == 404
    assert respuesta.json()["error"] == "no_encontrado"


def test_metodo_no_permitido():
    respuesta = APIClient().get("/errores/")

    assert respuesta.status_code == 405
    assert respuesta.json()["error"] == "metodo_no_permitido"


def test_json_mal_formado():
    respuesta = APIClient().post("/errores/", "{no es json", content_type="application/json")

    assert respuesta.status_code == 400
    assert respuesta.json()["error"] == "json_invalido"
