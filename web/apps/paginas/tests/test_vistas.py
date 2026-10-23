"""Inicio, aviso de privacidad, 404 y la base común de todas las páginas."""


def test_inicio_con_categorias_y_productos(client, tienda_falsa):
    respuesta = client.get("/")

    html = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert "Insumos, asesoría y diagnóstico para tu huerta de aguacate" in html
    assert "Fungicidas" in html and "Riego" in html
    assert "Caldo bordelés 1 kg" in html
    assert 'action="/catalogo/"' in html
    assert tienda_falsa.parametros() == {"disponible": "true"}


def test_inicio_sin_svc_tienda_se_muestra_igual(client, tienda_falsa):
    tienda_falsa.caida = True

    respuesta = client.get("/")

    html = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert "Insumos, asesoría y diagnóstico" in html
    assert "El catálogo no está disponible en este momento" in html


def test_base_comun(client, tienda_falsa):
    html = client.get("/").content.decode()

    assert 'lang="es-MX"' in html
    assert "hx-headers" in html and "X-CSRFToken" in html
    assert "vendor/htmx-2.0.11.min.js" in html
    assert "vendor/alpine-3.17.4.min.js" in html
    assert "cdn." not in html  # sin CDN
    assert "Saltar al contenido" in html
    assert 'href="/aviso-de-privacidad/"' in html
    assert html.count("Próximamente") >= 4  # chat, diagnóstico e iniciar sesión


def test_sin_lenguaje_del_proyecto_escolar(client, tienda_falsa):
    for url in ("/", "/catalogo/", "/catalogo/caldo-bordeles/"):
        html = client.get(url).content.decode().lower()
        assert "entrega" not in html
        assert "fase " not in html


def test_ningun_comentario_de_plantilla_se_ve_en_la_pagina(client, tienda_falsa):
    for url in ("/", "/catalogo/", "/catalogo/caldo-bordeles/", "/aviso-de-privacidad/"):
        html = client.get(url).content.decode()
        assert "{#" not in html and "#}" not in html


def test_aviso_de_privacidad(client):
    respuesta = client.get("/aviso-de-privacidad/")

    html = respuesta.content.decode()
    assert respuesta.status_code == 200
    for apartado in (
        "Quién es responsable de tus datos",
        "Qué datos recabamos",
        "Para qué los usamos",
        "Con quién los compartimos",
        "derechos ARCO",
        "Última actualización",
        "proyecto académico",
    ):
        assert apartado in html


def test_pagina_inexistente_404_amable(client, settings):
    settings.DEBUG = False

    respuesta = client.get("/no-existe/")

    assert respuesta.status_code == 404
    assert "No encontramos esta página" in respuesta.content.decode()
