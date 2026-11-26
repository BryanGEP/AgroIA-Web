"""POST /diagnostico/: validación de la imagen y 503 mientras no haya modelo de visión."""

import pytest

from app.main import TAMANO_MAXIMO_IMAGEN, app
from app.vision import ResultadoClasificacion, obtener_clasificador

URL = "/diagnostico/"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


class ClasificadorDePrueba:
    """Solo para pruebas: devuelve siempre el mismo resultado."""

    modelo_version = "prueba-1"

    def __init__(self):
        self.recibido: bytes | None = None

    def clasificar(self, imagen: bytes) -> ResultadoClasificacion:
        self.recibido = imagen
        return ResultadoClasificacion(
            clase="antracnosis",
            confianza=0.91,
            probabilidades={"sano": 0.03, "rona": 0.06, "antracnosis": 0.91},
        )


def subir(cliente_http, encabezados, contenido=PNG, nombre="hoja.png", tipo="image/png"):
    return cliente_http.post(URL, files={"imagen": (nombre, contenido, tipo)}, headers=encabezados)


def test_sin_modelo_responde_503(cliente_http, como_cliente):
    respuesta = subir(cliente_http, como_cliente)

    assert respuesta.status_code == 503
    assert respuesta.json() == {
        "error": "modelo_no_disponible",
        "detalle": "El modelo de diagnóstico se integrará en una entrega posterior.",
    }


def test_hoy_no_hay_clasificador_configurado():
    assert obtener_clasificador() is None


def test_con_clasificador_devuelve_el_formato_del_contrato(cliente_http, como_cliente):
    clasificador = ClasificadorDePrueba()
    app.dependency_overrides[obtener_clasificador] = lambda: clasificador

    respuesta = subir(cliente_http, como_cliente, JPG, "hoja.jpg", "image/jpeg")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "listo"
    assert cuerpo["clase"] == "antracnosis"
    assert cuerpo["confianza"] == 0.91
    assert cuerpo["probabilidades"] == {"sano": 0.03, "rona": 0.06, "antracnosis": 0.91}
    assert cuerpo["modelo_version"] == "prueba-1"
    assert len(cuerpo["id"]) == 32
    assert clasificador.recibido == JPG


@pytest.mark.parametrize(
    ("contenido", "nombre", "tipo"),
    [
        (b"GIF89a" + b"\x00" * 10, "hoja.gif", "image/gif"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "hoja.webp", "image/webp"),
        (b"%PDF-1.7", "hoja.png", "image/png"),  # extensión engañosa
        (b"", "vacia.png", "image/png"),
    ],
)
def test_formato_no_permitido_400(cliente_http, como_cliente, contenido, nombre, tipo):
    respuesta = subir(cliente_http, como_cliente, contenido, nombre, tipo)

    assert respuesta.status_code == 400
    assert respuesta.json()["campos"]["imagen"] == ["Solo se aceptan imágenes JPG o PNG."]


def test_imagen_de_mas_de_5_mb_400(cliente_http, como_cliente):
    grande = b"\x89PNG\r\n\x1a\n" + b"\x00" * TAMANO_MAXIMO_IMAGEN

    respuesta = subir(cliente_http, como_cliente, grande)

    assert respuesta.status_code == 400
    assert "5 MB" in respuesta.json()["campos"]["imagen"][0]


def test_sin_imagen_400(cliente_http, como_cliente):
    respuesta = cliente_http.post(URL, headers=como_cliente)

    assert respuesta.status_code == 400
    assert "imagen" in respuesta.json()["campos"]


def test_la_imagen_se_valida_antes_de_revisar_el_modelo(cliente_http, como_cliente):
    respuesta = subir(cliente_http, como_cliente, b"no es imagen", "x.png", "image/png")

    assert respuesta.status_code == 400


def test_401_y_403(cliente_http, sin_rol):
    assert subir(cliente_http, {}).status_code == 401
    assert subir(cliente_http, sin_rol).status_code == 403
