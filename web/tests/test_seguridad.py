"""Encabezados de seguridad, CSP y CORS del gateway."""

import httpx
import pytest

PRODUCTOS = {"count": 0, "next": None, "previous": None, "results": []}


@pytest.fixture
def catalogo(servicios):
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/productos/", httpx.Response(200, json=PRODUCTOS)
    )
    return servicios


def test_encabezados_de_seguridad(client):
    respuesta = client.get("/aviso-de-privacidad/")

    assert respuesta["X-Content-Type-Options"] == "nosniff"
    assert respuesta["Referrer-Policy"] == "same-origin"
    assert respuesta["X-Frame-Options"] == "DENY"


def test_csp_sin_unsafe_inline_ni_eval(client):
    politica = client.get("/aviso-de-privacidad/")["Content-Security-Policy"]

    assert "script-src 'self'" in politica and "style-src 'self'" in politica
    assert "frame-ancestors 'none'" in politica
    assert "unsafe-inline" not in politica and "unsafe-eval" not in politica


def test_las_paginas_no_tienen_scripts_ni_estilos_en_linea(client, tienda_falsa):
    import re

    for ruta in ("/", "/catalogo/", "/catalogo/caldo-bordeles/", "/iniciar-sesion/", "/registro/"):
        html = client.get(ruta).content.decode()
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), ruta  # sin <script> en línea
        assert " style=" not in html, ruta
        assert not re.search(r"\son[a-z]+=", html), ruta  # sin onclick=...
        assert "hx-on" not in html, ruta


def test_docs_tiene_su_propia_politica(client):
    politica = client.get("/api/docs/")["Content-Security-Policy"]

    assert "cdn.jsdelivr.net" in politica


# --- CORS y origen ---------------------------------------------------------------------------


def test_origen_permitido_recibe_cors_sin_credenciales(client, catalogo):
    respuesta = client.get("/api/tienda/productos/", HTTP_ORIGIN="http://app.agroia.test")

    assert respuesta.status_code == 200
    assert respuesta["Access-Control-Allow-Origin"] == "http://app.agroia.test"
    assert "Access-Control-Allow-Credentials" not in respuesta


def test_preflight_de_un_origen_permitido(client):
    respuesta = client.options(
        "/api/tienda/carrito/",
        HTTP_ORIGIN="http://app.agroia.test",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization, content-type",
    )

    assert respuesta.status_code == 200
    assert "authorization" in respuesta["Access-Control-Allow-Headers"]


def test_origen_no_permitido_403_sin_llegar_al_servicio(client, catalogo):
    respuesta = client.get("/api/tienda/productos/", HTTP_ORIGIN="https://sitio-ajeno.example")

    assert respuesta.status_code == 403
    assert respuesta.json()["error"] == "origen_no_permitido"
    assert "Access-Control-Allow-Origin" not in respuesta
    assert catalogo.peticiones == []


def test_sin_origin_pasa(client, catalogo):
    # Postman, curl y las apps no mandan Origin: el control de acceso es el token.
    assert client.get("/api/tienda/productos/").status_code == 200


def test_el_propio_sitio_es_un_origen_permitido(client, catalogo):
    assert client.get("/api/tienda/productos/", HTTP_ORIGIN="http://testserver").status_code == 200


def test_cors_solo_aplica_a_la_api(client):
    respuesta = client.get("/aviso-de-privacidad/", HTTP_ORIGIN="https://sitio-ajeno.example")

    assert respuesta.status_code == 200
    assert "Access-Control-Allow-Origin" not in respuesta


def test_cookie_de_sesion_segura_sin_debug():
    from django.conf import settings

    from agroia_comun.pruebas import cargar_configuracion

    resultado = cargar_configuracion(
        settings.BASE_DIR,
        DJANGO_DEBUG="False",
        DJANGO_SECRET_KEY="x7Kp2-Qm9vL4_tR8sW1zN6bY3cF5hJ0dG-aE7uI2oP9lK4mB8nV1",
    )
    assert resultado.returncode == 0, resultado.stderr
