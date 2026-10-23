"""Endpoints de diagnósticos: guardar el resultado con la imagen, listar y ver."""

import json

import pytest
from bson import ObjectId
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.diagnosticos import servicios
from tests.datos import ADMIN_ID, CLIENTE_ID, OTRO_CLIENTE_ID, PROBABILIDADES, imagen

URL = "/api/v1/diagnosticos/"


def datos(**cambios) -> dict:
    base = {
        "imagen": imagen(),
        "clase": "antracnosis",
        "confianza": "0.91",
        "probabilidades": json.dumps(PROBABILIDADES),
        "modelo_version": "v1",
    }
    base.update(cambios)
    return base


def guardar(usuario_id: int = CLIENTE_ID) -> str:
    diagnostico = servicios.crear(
        usuario_id, imagen(), "sano", 0.8, {"sano": 0.8, "rona": 0.1, "antracnosis": 0.1}, "v1"
    )
    return str(diagnostico["_id"])


def test_crear_diagnostico(cliente, mongo_simulado):
    respuesta = cliente.post(URL, datos(), format="multipart")

    assert respuesta.status_code == 201, respuesta.json()
    cuerpo = respuesta.json()
    assert cuerpo["clase"] == "antracnosis"
    assert cuerpo["confianza"] == 0.91
    assert cuerpo["probabilidades"] == PROBABILIDADES
    assert cuerpo["usuario_id"] == CLIENTE_ID
    assert cuerpo["imagen_url"].startswith("http://testserver/media/diagnosticos/")
    documento = mongo_simulado["diagnosticos"].find_one({"_id": ObjectId(cuerpo["id"])})
    assert default_storage.exists(documento["imagen"])


@pytest.mark.parametrize(("nombre", "formato"), [("hoja.jpg", "JPEG"), ("hoja.webp", "WEBP")])
def test_acepta_jpg_y_webp(cliente, nombre, formato):
    respuesta = cliente.post(URL, datos(imagen=imagen(nombre, formato)), format="multipart")

    assert respuesta.status_code == 201


@pytest.mark.parametrize(
    ("cambio", "campo"),
    [
        ({"clase": "mildiu"}, "clase"),
        ({"confianza": "1.5"}, "confianza"),
        ({"probabilidades": "no es json"}, "probabilidades"),
        ({"probabilidades": json.dumps({"sano": 0.5, "rona": 0.5})}, "probabilidades"),
        (
            {"probabilidades": json.dumps({"sano": 0.5, "rona": 0.4, "antracnosis": 0.4})},
            "probabilidades",
        ),
        ({"confianza": "0.50"}, "confianza"),
        ({"modelo_version": ""}, "modelo_version"),
    ],
)
def test_resultado_invalido_400(cliente, cambio, campo):
    respuesta = cliente.post(URL, datos(**cambio), format="multipart")

    assert respuesta.status_code == 400
    assert campo in respuesta.json()["campos"]


def test_archivo_que_no_es_imagen_400(cliente):
    falso = SimpleUploadedFile("hoja.png", b"no soy una imagen", content_type="image/png")

    respuesta = cliente.post(URL, datos(imagen=falso), format="multipart")

    assert respuesta.status_code == 400
    assert "imagen" in respuesta.json()["campos"]


def test_imagen_de_mas_de_5_mb_400(cliente, monkeypatch):
    monkeypatch.setattr("apps.diagnosticos.serializers.TAMANO_MAXIMO_IMAGEN", 10)

    respuesta = cliente.post(URL, datos(), format="multipart")

    assert respuesta.status_code == 400
    assert "5 MB" in respuesta.json()["campos"]["imagen"][0]


def test_sin_imagen_400(cliente):
    sin_imagen = datos()
    sin_imagen.pop("imagen")

    respuesta = cliente.post(URL, sin_imagen, format="multipart")

    assert respuesta.status_code == 400
    assert "imagen" in respuesta.json()["campos"]


def test_crear_401_y_403(anonimo, sin_rol):
    assert anonimo.post(URL, datos(), format="multipart").status_code == 401
    assert sin_rol.post(URL, datos(), format="multipart").status_code == 403


def test_cliente_lista_solo_los_suyos(cliente):
    propio = guardar(CLIENTE_ID)
    guardar(OTRO_CLIENTE_ID)

    resultados = cliente.get(URL).json()["results"]

    assert [d["id"] for d in resultados] == [propio]


def test_admin_lista_todos(admin):
    guardar(CLIENTE_ID)
    guardar(OTRO_CLIENTE_ID)
    guardar(ADMIN_ID)

    assert admin.get(URL).json()["count"] == 3


def test_listar_paginado_mas_recientes_primero(cliente):
    ids = [guardar() for _ in range(21)]

    primera = cliente.get(URL).json()

    assert primera["count"] == 21
    assert len(primera["results"]) == 20
    assert primera["results"][0]["id"] == ids[-1]


def test_listar_401_y_403(anonimo, sin_rol):
    assert anonimo.get(URL).status_code == 401
    assert sin_rol.get(URL).status_code == 403


def test_ver_detalle(cliente, admin, otro_cliente):
    id_texto = guardar(CLIENTE_ID)
    url = f"{URL}{id_texto}/"

    assert cliente.get(url).status_code == 200
    assert admin.get(url).status_code == 200
    assert otro_cliente.get(url).status_code == 404


@pytest.mark.parametrize("id_texto", ["xyz", str(ObjectId())])
def test_detalle_id_invalido_o_inexistente_404(cliente, id_texto):
    assert cliente.get(f"{URL}{id_texto}/").status_code == 404


def test_detalle_401_y_403(anonimo, sin_rol):
    url = f"{URL}{guardar()}/"

    assert anonimo.get(url).status_code == 401
    assert sin_rol.get(url).status_code == 403
