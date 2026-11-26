"""Diagnóstico por imagen (asíncrono): svc-contenido y svc-tienda simulados."""

import base64

import httpx
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from tests.servicios_falsos import error

pytestmark = pytest.mark.django_db

# PNG de 1x1 píxel.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
ID = "6630c1f2a4b5c6d7e8f90123"
RESULTADO = {
    "id": "s1",
    "estado": "listo",
    "clase": "antracnosis",
    "confianza": 0.91,
    "probabilidades": {"sano": 0.03, "rona": 0.06, "antracnosis": 0.91},
    "modelo_version": "v1",
}
RESULTADO_DATOS = {k: v for k, v in RESULTADO.items() if k not in ("id", "estado")}
FUNGICIDA = {
    "slug": "oxicloruro",
    "nombre": "Oxicloruro de cobre",
    "precio": "245.00",
    "imagen": None,
}


def foto(nombre="hoja.png", contenido=PNG, tipo="image/png"):
    return SimpleUploadedFile(nombre, contenido, content_type=tipo)


def test_diagnostico_pide_sesion(client):
    assert client.get("/diagnostico/")["Location"].startswith("/iniciar-sesion/?next=")


def test_pantalla_con_vista_previa_en_alpine(client, con_sesion):
    con_sesion()

    html = client.get("/diagnostico/").content.decode()

    assert 'x-data="vistaPrevia"' in html and 'accept="image/jpeg,image/png"' in html
    assert '<label for="id_imagen"' in html


RUTA_SOLICITAR = "/api/v1/diagnosticos/solicitar/"
RUTA_DIAG = f"/api/v1/diagnosticos/{ID}/"


def diagnostico(estado="pendiente", codigo=None, **extra) -> dict:
    return {"id": ID, "estado": estado, "codigo": codigo, "es_prueba": False,
            "creado_en": "2026-11-22T10:00:00+00:00", "imagen_url": None, **extra}  # fmt: skip


def test_solicitar_manda_la_foto_a_svc_contenido_y_empieza_a_consultar(
    client, servicios, con_sesion
):
    con_sesion()
    servicios.responder("POST", "svc-contenido", RUTA_SOLICITAR,
                        httpx.Response(202, json=diagnostico()))  # fmt: skip

    html = client.post("/diagnostico/", {"imagen": foto()}, HTTP_HX_REQUEST="true").content.decode()

    (pedido,) = servicios.de("svc-contenido", RUTA_SOLICITAR)
    assert b'filename="hoja.png"' in pedido.content and PNG in pedido.content
    assert servicios.de("svc-ia") == []  # el gateway ya no llama a svc-ia
    assert "Analizando la foto" in html
    assert f'hx-get="/diagnostico/{ID}/estado/"' in html and "hx-trigger" in html


def test_sin_modelo_muestra_el_aviso_sin_errores_tecnicos(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("GET", "svc-contenido", RUTA_DIAG, httpx.Response(
        200, json=diagnostico("fallido", "modelo_no_disponible")))  # fmt: skip

    html = client.get(f"/diagnostico/{ID}/estado/", HTTP_HX_REQUEST="true").content.decode()

    assert "El diagnóstico por imagen estará disponible pronto." in html
    assert "modelo_no_disponible" not in html
    assert "hx-trigger" not in html


def test_con_resultado_muestra_la_clase_y_sugiere_productos(client, servicios, con_sesion):
    con_sesion()
    servicios.responder(
        "GET",
        "svc-contenido",
        RUTA_DIAG,
        httpx.Response(200, json=diagnostico("listo", **RESULTADO_DATOS)),
    )
    servicios.responder(
        "GET",
        "svc-tienda",
        "/api/v1/productos/",
        httpx.Response(200, json={"count": 1, "results": [FUNGICIDA]}),
    )

    html = client.get(f"/diagnostico/{ID}/estado/", HTTP_HX_REQUEST="true").content.decode()

    assert "Antracnosis" in html and "91 %" in html
    assert '<progress class="progress progress-primary w-full" value="91"' in html
    assert "Oxicloruro de cobre" in html
    assert "Resultado de prueba" not in html and "hx-trigger" not in html
    (sugeridos,) = servicios.de("svc-tienda")
    assert sugeridos.url.params["categoria"] == "fungicidas"


def test_un_resultado_de_prueba_lo_dice_claramente(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("GET", "svc-contenido", RUTA_DIAG, httpx.Response(200, json=diagnostico(
        "listo", **{**RESULTADO_DATOS, "clase": "sano",
                    "modelo_version": "prueba-no-es-un-modelo"}, es_prueba=True)))  # fmt: skip

    html = client.get(f"/diagnostico/{ID}/estado/", HTTP_HX_REQUEST="true").content.decode()

    assert "Resultado de prueba: no es un diagnóstico real." in html


def test_pendiente_sigue_consultando_sin_429(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("GET", "svc-contenido", RUTA_DIAG, httpx.Response(200, json=diagnostico()))

    estados = set()
    for _ in range(90):
        respuesta = client.get(f"/diagnostico/{ID}/estado/", HTTP_HX_REQUEST="true")
        estados.add(respuesta.status_code)
        assert "hx-trigger" in respuesta.content.decode()

    assert estados == {200}


def test_la_pagina_de_un_diagnostico_pendiente_sigue_consultando(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("GET", "svc-contenido", RUTA_DIAG, httpx.Response(200, json=diagnostico()))

    html = client.get(f"/diagnostico/{ID}/").content.decode()

    assert "Analizando la foto" in html and f'hx-get="/diagnostico/{ID}/estado/"' in html
    assert "Foto analizada" not in html  # sin imagen_url no se pide la foto


@pytest.mark.parametrize(
    ("archivo", "mensaje"),
    [
        (lambda: foto("hoja.png", b"no es una imagen", "image/png"), "Elige una foto JPG o PNG."),
        (lambda: foto("hoja.gif", b"GIF89a....", "image/gif"), "Elige una foto JPG o PNG."),
        (
            lambda: foto("grande.png", PNG + b"0" * (5 * 1024 * 1024), "image/png"),
            "La foto pesa más de 5 MB.",
        ),
    ],
    ids=["no-es-imagen", "gif", "mas-de-5-mb"],
)
def test_foto_invalida_no_llega_a_svc_ia(client, servicios, con_sesion, archivo, mensaje):
    con_sesion()

    respuesta = client.post("/diagnostico/", {"imagen": archivo()})

    assert respuesta.status_code == 400
    assert mensaje in respuesta.content.decode()
    assert servicios.peticiones == []


def test_historial(client, servicios, con_sesion):
    con_sesion()
    servicios.responder(
        "GET",
        "svc-contenido",
        "/api/v1/diagnosticos/",
        httpx.Response(
            200,
            json={
                "count": 1,
                "next": None,
                "previous": None,
                "results": [{**RESULTADO, "id": ID, "creado_en": "2026-11-20T10:00:00-06:00"}],
            },
        ),
    )

    html = client.get("/diagnostico/historial/").content.decode()

    assert "Antracnosis" in html and f'src="/diagnostico/{ID}/imagen/"' in html
    assert "svc-contenido" not in html  # nunca la dirección interna


def test_la_foto_se_pide_a_svc_contenido_con_el_token_del_usuario(client, servicios, con_sesion):
    tokens = con_sesion()
    servicios.responder(
        "GET",
        "svc-contenido",
        f"/api/v1/diagnosticos/{ID}/imagen/",
        httpx.Response(200, content=PNG, headers={"Content-Type": "image/png"}),
    )

    respuesta = client.get(f"/diagnostico/{ID}/imagen/")

    assert respuesta.status_code == 200
    assert respuesta["Content-Type"] == "image/png"
    assert respuesta["Cache-Control"] == "private, max-age=3600"
    assert respuesta.content == PNG
    (peticion,) = servicios.de("svc-contenido")
    assert peticion.headers["authorization"] == f"Bearer {tokens['access']}"


def test_la_foto_de_otro_usuario_da_404(client, servicios, con_sesion):
    con_sesion()
    servicios.responder(
        "GET", "svc-contenido", f"/api/v1/diagnosticos/{ID}/imagen/", error(404, "no_encontrado")
    )

    assert client.get(f"/diagnostico/{ID}/imagen/").status_code == 404


def test_la_foto_pide_sesion(client, servicios):
    assert client.get(f"/diagnostico/{ID}/imagen/").status_code == 302
    assert servicios.peticiones == []


def test_muchos_analisis_seguidos_muestra_el_mensaje(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("POST", "svc-contenido", RUTA_SOLICITAR,
                        error(429, "demasiados_intentos", "Demasiados intentos."))  # fmt: skip

    html = client.post("/diagnostico/", {"imagen": foto()}, HTTP_HX_REQUEST="true").content.decode()

    assert "Hiciste muchos análisis seguidos" in html
    assert "demasiados_intentos" not in html and "hx-trigger" not in html
