"""Catálogo: página completa y parcial HTMX, filtros, detalle, 404, errores e imágenes."""

import pytest

from tests.tienda_falsa import producto


def test_catalogo_pagina_completa(client, tienda_falsa):
    respuesta = client.get("/catalogo/")

    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert "<html" in html
    assert 'id="filtros"' in html
    assert "Caldo bordelés 1 kg" in html
    assert "$1,250.50" in html
    assert "HX-Request" in respuesta["Vary"]


def test_catalogo_parcial_con_htmx(client, tienda_falsa):
    respuesta = client.get("/catalogo/", {"q": "caldo"}, HTTP_HX_REQUEST="true")

    html = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert "<html" not in html
    assert 'id="filtros"' not in html
    assert "Caldo bordelés 1 kg" in html
    assert "HX-Request" in respuesta["Vary"]


def test_restaurar_historial_devuelve_la_pagina_completa(client, tienda_falsa):
    respuesta = client.get(
        "/catalogo/", HTTP_HX_REQUEST="true", HTTP_HX_HISTORY_RESTORE_REQUEST="true"
    )

    assert "<html" in respuesta.content.decode()


def test_los_filtros_llegan_a_svc_tienda(client, tienda_falsa):
    client.get(
        "/catalogo/",
        {
            "q": "cobre",
            "categoria": "fungicidas",
            "precio_min": "100",
            "precio_max": "500.5",
            "disponible": "on",
            "orden": "-precio",
            "page": "1",
        },
    )

    assert tienda_falsa.parametros() == {
        "q": "cobre",
        "categoria": "fungicidas",
        "precio_min": "100",
        "precio_max": "500.5",
        "disponible": "true",
        "ordering": "-precio",
        "page": "1",
    }


def test_filtros_invalidos_no_se_envian_y_se_explican(client, tienda_falsa):
    respuesta = client.get(
        "/catalogo/", {"precio_min": "500", "precio_max": "100", "categoria": "inventada"}
    )

    html = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert "mayor o igual que el precio mínimo" in html
    assert 'aria-invalid="true"' in html
    enviados = tienda_falsa.parametros()
    assert "precio_max" not in enviados
    assert "categoria" not in enviados


def test_los_filtros_quedan_marcados_en_el_formulario(client, tienda_falsa):
    html = client.get(
        "/catalogo/", {"categoria": "riego", "disponible": "on", "q": "goteo"}
    ).content.decode()

    assert '<option value="riego" selected>' in html
    assert 'value="goteo"' in html
    assert "checked" in html


def test_sin_javascript_los_campos_vacios_se_quitan_de_la_url(client, tienda_falsa):
    respuesta = client.get("/catalogo/?q=&categoria=riego&precio_min=&orden=")

    assert respuesta.status_code == 302
    assert respuesta["Location"] == "/catalogo/?categoria=riego"
    assert client.get("/catalogo/?q=&orden=")["Location"] == "/catalogo/"


def test_con_htmx_no_se_redirige(client, tienda_falsa):
    respuesta = client.get("/catalogo/?q=&categoria=riego", HTTP_HX_REQUEST="true")

    assert respuesta.status_code == 200


def test_catalogo_vacio(client, tienda_falsa):
    tienda_falsa.productos = []

    html = client.get("/catalogo/", {"q": "nada"}).content.decode()

    assert "No hay productos con estos filtros" in html


def test_pagina_inexistente(client, tienda_falsa):
    respuesta = client.get("/catalogo/", {"page": "9"})

    assert respuesta.status_code == 200
    assert "Esa página ya no existe" in respuesta.content.decode()


def test_paginador_conserva_los_filtros(client, tienda_falsa):
    tienda_falsa.productos = [producto(f"p{i}") for i in range(20)]
    tienda_falsa.conteo = 45

    html = client.get("/catalogo/", {"categoria": "fungicidas"}).content.decode()

    assert "página 1 de 3" in html
    assert "categoria=fungicidas&amp;page=2" in html
    assert 'hx-push-url="true"' in html


def test_catalogo_sin_svc_tienda_muestra_error_amable(client, tienda_falsa):
    tienda_falsa.caida = True

    respuesta = client.get("/catalogo/")

    html = respuesta.content.decode()
    assert respuesta.status_code == 503
    assert "El catálogo no está disponible en este momento" in html
    assert "Traceback" not in html
    assert "ConnectError" not in html


def test_detalle(client, tienda_falsa):
    respuesta = client.get("/catalogo/caldo-bordeles/")

    html = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert "Caldo bordelés 1 kg" in html
    assert "$1,250.50" in html
    assert "por kg" in html
    assert "Disponible" in html
    assert "Ingrediente activo" in html
    assert "Sulfato de cobre" in html
    assert "Protección UV" in html and "Sí" in html
    assert "Cu" in html and "25%" in html
    assert "M, G" in html
    assert "Agregar al carrito" in html
    assert "Fungicidas" in html


def test_detalle_con_pocas_existencias(client, tienda_falsa):
    assert "Quedan 4" in client.get("/catalogo/manguera/").content.decode()


def test_detalle_agotado(client, tienda_falsa):
    tienda_falsa.productos = [producto(stock=0)]

    html = client.get("/catalogo/caldo-bordeles/").content.decode()

    assert "Agotado" in html


def test_producto_inexistente_o_inactivo_404_amable(client, tienda_falsa):
    respuesta = client.get("/catalogo/no-existe/")

    html = respuesta.content.decode()
    assert respuesta.status_code == 404
    assert "Este producto no está en el catálogo" in html
    assert 'href="/catalogo/"' in html


def test_detalle_sin_svc_tienda(client, tienda_falsa):
    tienda_falsa.caida = True

    assert client.get("/catalogo/caldo-bordeles/").status_code == 503


def test_producto_sin_imagen_muestra_ilustracion(client, tienda_falsa):
    html = client.get("/catalogo/caldo-bordeles/").content.decode()

    assert 'role="img"' in html
    assert "Ilustración de Fungicidas" in html
    assert "<img" not in html


def test_la_imagen_interna_se_reescribe_al_gateway(client, tienda_falsa, settings):
    tienda_falsa.productos = [
        producto(imagen=f"{settings.URL_SVC_TIENDA}/media/productos/caldo.png")
    ]

    html = client.get("/catalogo/caldo-bordeles/").content.decode()

    assert 'src="/media/tienda/productos/caldo.png"' in html
    assert "svc-tienda" not in html


def test_reenvio_de_imagen(client, tienda_falsa):
    tienda_falsa.imagenes["productos/caldo.png"] = (b"\x89PNG...", "image/png")

    respuesta = client.get("/media/tienda/productos/caldo.png")

    assert respuesta.status_code == 200
    assert respuesta["Content-Type"] == "image/png"
    assert respuesta["Cache-Control"] == "public, max-age=3600"
    assert respuesta.content == b"\x89PNG..."


@pytest.mark.parametrize(
    "ruta",
    ["productos/no-existe.png", "otra-carpeta/x.png", "productos/../settings.py"],
)
def test_reenvio_de_imagen_rechaza_rutas_no_validas(client, tienda_falsa, ruta):
    assert client.get(f"/media/tienda/{ruta}").status_code == 404


def test_reenvio_solo_deja_pasar_imagenes(client, tienda_falsa):
    tienda_falsa.imagenes["productos/raro.png"] = (b"<html>", "text/html")

    assert client.get("/media/tienda/productos/raro.png").status_code == 404


def test_reenvio_con_svc_tienda_caido(client, tienda_falsa):
    tienda_falsa.caida = True

    assert client.get("/media/tienda/productos/caldo.png").status_code == 502


def test_solo_get(client, tienda_falsa):
    assert client.post("/catalogo/").status_code == 405
