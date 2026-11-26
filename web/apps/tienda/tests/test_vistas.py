"""Carrito, checkout y mis pedidos en el gateway (svc-tienda y svc-usuarios simulados)."""

import httpx
import pytest

from tests.servicios_falsos import error

pytestmark = pytest.mark.django_db

PRODUCTO = {
    "slug": "caldo",
    "nombre": "Caldo bordelés",
    "precio": "250.00",
    "unidad": "kg",
    "imagen": "http://svc-tienda:8000/media/productos/caldo.png",
    "stock": 10,
}
CARRITO = {
    "id": 1,
    "items": [{"id": 4, "producto": PRODUCTO, "cantidad": 3, "importe": "750.00"}],
    "subtotal": "750.00",
    "envio": "150.00",
    "total": "900.00",
}
VACIO = {"id": 1, "items": [], "subtotal": "0.00", "envio": "0.00", "total": "0.00"}
DIRECCION = {
    "id": 7,
    "alias": "Huerta",
    "calle": "Camino a La Palma",
    "numero": "km 3",
    "colonia": "La Palma",
    "municipio": "Jiquilpan",
    "estado": "Michoacán",
    "codigo_postal": "59510",
    "referencias": "",
    "predeterminada": True,
}
PEDIDO = {
    "id": 12,
    "estado": "pendiente",
    "direccion_envio": DIRECCION,
    "items": [
        {
            "id": 1,
            "producto": "caldo",
            "nombre_producto": "Caldo bordelés",
            "precio_unitario": "250.00",
            "cantidad": 3,
            "importe": "750.00",
        }
    ],
    "subtotal": "750.00",
    "envio": "150.00",
    "total": "900.00",
    "metodo_pago": "tarjeta",
    "pago_simulado": True,
    "creado_en": "2026-11-20T10:00:00-06:00",
    "transiciones_permitidas": [],
}


def con_carrito(servicios, carrito=CARRITO):
    servicios.responder("GET", "svc-tienda", "/api/v1/carrito/", httpx.Response(200, json=carrito))


def con_direcciones(servicios, direcciones=(DIRECCION,)):
    servicios.responder(
        "GET",
        "svc-usuarios",
        "/api/v1/usuarios/yo/direcciones/",
        httpx.Response(200, json={"count": len(direcciones), "results": list(direcciones)}),
    )


# --- Agregar al carrito ------------------------------------------------------------------


def test_agregar_sin_sesion_lleva_al_login(client):
    respuesta = client.post("/carrito/agregar/caldo/")

    assert respuesta.status_code == 302
    assert respuesta["Location"].startswith("/iniciar-sesion/?next=")


def test_agregar_con_htmx_actualiza_el_contador(client, servicios, con_sesion):
    con_sesion()
    servicios.responder(
        "POST", "svc-tienda", "/api/v1/carrito/items/", httpx.Response(201, json={})
    )
    con_carrito(servicios)

    respuesta = client.post("/carrito/agregar/caldo/", {"cantidad": "1"}, HTTP_HX_REQUEST="true")

    html = respuesta.content.decode()
    assert "Lo agregamos" in html
    assert 'id="contador-carrito" hx-swap-oob="true"' in html and ">3<" in html
    assert client.session["carrito_cantidad"] == 3
    (peticion,) = servicios.de("svc-tienda", "/api/v1/carrito/items/")
    assert servicios.cuerpo(peticion) == {"producto": "caldo", "cantidad": 1}


def test_agregar_sin_stock_muestra_el_mensaje(client, servicios, con_sesion):
    con_sesion()
    servicios.responder(
        "POST",
        "svc-tienda",
        "/api/v1/carrito/items/",
        error(409, "stock_insuficiente", "Solo quedan 2 piezas."),
    )

    html = client.post("/carrito/agregar/caldo/", HTTP_HX_REQUEST="true").content.decode()

    assert "Solo quedan 2 piezas." in html


def test_agregar_sin_javascript_regresa_al_producto(client, servicios, con_sesion):
    con_sesion()
    servicios.responder(
        "POST", "svc-tienda", "/api/v1/carrito/items/", httpx.Response(201, json={})
    )
    con_carrito(servicios)

    respuesta = client.post("/carrito/agregar/caldo/", {"next": "/catalogo/caldo/"})

    assert respuesta["Location"] == "/catalogo/caldo/"


def test_las_tarjetas_con_sesion_tienen_el_boton(client, tienda_falsa, con_sesion):
    con_sesion()

    html = client.get("/catalogo/").content.decode()

    assert 'action="/carrito/agregar/caldo-bordeles/"' in html and "csrfmiddlewaretoken" in html


# --- Carrito -------------------------------------------------------------------------------


def test_carrito_pide_sesion(client):
    assert client.get("/carrito/")["Location"].startswith("/iniciar-sesion/?next=%2Fcarrito%2F")


def test_ver_carrito_recalcula_el_contador(client, servicios, con_sesion):
    con_sesion()
    con_carrito(servicios)

    html = client.get("/carrito/").content.decode()

    assert "Caldo bordelés" in html and "$900.00" in html
    assert 'src="/media/tienda/productos/caldo.png"' in html  # imagen por el gateway
    assert client.session["carrito_cantidad"] == 3


def test_cambiar_cantidad_con_htmx(client, servicios, con_sesion):
    con_sesion()
    servicios.responder(
        "PATCH", "svc-tienda", "/api/v1/carrito/items/4/", httpx.Response(200, json={})
    )
    con_carrito(servicios)

    respuesta = client.post("/carrito/items/4/cantidad/", {"cantidad": "3"}, HTTP_HX_REQUEST="true")

    html = respuesta.content.decode()
    assert 'id="carrito"' in html and "<html" not in html
    assert servicios.cuerpo(servicios.de("svc-tienda", "/api/v1/carrito/items/4/")[0]) == {
        "cantidad": 3
    }


def test_cambiar_cantidad_sin_stock_muestra_el_error_junto_al_producto(
    client, servicios, con_sesion
):
    con_sesion()
    servicios.responder(
        "PATCH",
        "svc-tienda",
        "/api/v1/carrito/items/4/",
        error(409, "stock_insuficiente", "No hay suficiente stock."),
    )
    con_carrito(servicios)

    html = client.post(
        "/carrito/items/4/cantidad/", {"cantidad": "99"}, HTTP_HX_REQUEST="true"
    ).content.decode()

    assert "No hay suficiente stock." in html


def test_quitar_producto(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("DELETE", "svc-tienda", "/api/v1/carrito/items/4/", httpx.Response(204))
    con_carrito(servicios, VACIO)

    html = client.post("/carrito/items/4/quitar/", HTTP_HX_REQUEST="true").content.decode()

    assert "Tu carrito está vacío" in html
    assert client.session["carrito_cantidad"] == 0


# --- Checkout ------------------------------------------------------------------------------


def test_checkout_con_carrito_vacio_regresa_al_carrito(client, servicios, con_sesion):
    con_sesion()
    con_carrito(servicios, VACIO)

    assert client.get("/checkout/")["Location"] == "/carrito/"


def test_checkout_muestra_direcciones_y_pago_simulado(client, servicios, con_sesion):
    con_sesion()
    con_carrito(servicios)
    con_direcciones(servicios)

    html = client.get("/checkout/").content.decode()

    assert "Camino a La Palma" in html and "Pago simulado" in html
    assert 'value="7"' in html and "checked" in html


def test_confirmar_pedido_manda_la_direccion_en_el_cuerpo(client, servicios, con_sesion):
    con_sesion()
    con_carrito(servicios)
    con_direcciones(servicios)
    servicios.responder("POST", "svc-tienda", "/api/v1/pedidos/", httpx.Response(201, json=PEDIDO))

    respuesta = client.post("/checkout/", {"direccion": "7", "metodo_pago": "tarjeta"})

    assert respuesta["Location"] == "/mis-pedidos/12/"
    enviado = servicios.cuerpo(servicios.de("svc-tienda", "/api/v1/pedidos/")[0])
    assert enviado["metodo_pago"] == "tarjeta"
    assert enviado["direccion_envio"] == {
        k: v for k, v in DIRECCION.items() if k not in ("id", "predeterminada", "referencias")
    }
    assert client.session["carrito_cantidad"] == 0


def test_correo_sin_verificar_muestra_el_aviso_con_reenvio(client, servicios, con_sesion):
    con_sesion(verificado=False)
    con_carrito(servicios)
    con_direcciones(servicios)
    servicios.responder("POST", "svc-tienda", "/api/v1/pedidos/", error(403, "email_no_verificado"))

    respuesta = client.post("/checkout/", {"direccion": "7", "metodo_pago": "tarjeta"})

    html = respuesta.content.decode()
    assert respuesta.status_code == 200  # el aviso, no una página de error
    assert "Para comprar necesitas verificar tu correo" in html
    assert "Reenviar el enlace" in html
    assert "email_no_verificado" not in html


def test_checkout_sin_stock(client, servicios, con_sesion):
    con_sesion()
    con_carrito(servicios)
    con_direcciones(servicios)
    servicios.responder(
        "POST",
        "svc-tienda",
        "/api/v1/pedidos/",
        error(409, "stock_insuficiente", "No hay suficiente stock de «Caldo bordelés»."),
    )

    html = client.post("/checkout/", {"direccion": "7", "metodo_pago": "tarjeta"}).content.decode()

    assert "No hay suficiente stock de «Caldo bordelés»." in html


def test_checkout_con_direccion_ajena_no_llega_a_svc_tienda(client, servicios, con_sesion):
    con_sesion()
    con_carrito(servicios)
    con_direcciones(servicios)

    respuesta = client.post("/checkout/", {"direccion": "999", "metodo_pago": "tarjeta"})

    assert respuesta.status_code == 400
    assert servicios.de("svc-tienda", "/api/v1/pedidos/") == []


# --- Mis pedidos ---------------------------------------------------------------------------


def test_mis_pedidos_y_detalle(client, servicios, con_sesion):
    con_sesion()
    servicios.responder(
        "GET",
        "svc-tienda",
        "/api/v1/pedidos/",
        httpx.Response(200, json={"count": 1, "next": None, "previous": None, "results": [PEDIDO]}),
    )
    servicios.responder(
        "GET", "svc-tienda", "/api/v1/pedidos/12/", httpx.Response(200, json=PEDIDO)
    )

    lista = client.get("/mis-pedidos/").content.decode()
    detalle = client.get("/mis-pedidos/12/").content.decode()

    assert "Pedido #12" in lista and "Pendiente de pago" in lista
    assert (
        "Pago simulado" in detalle and "Pagar $900.00" in detalle and "Camino a La Palma" in detalle
    )


def test_pagar_pedido(client, servicios, con_sesion):
    con_sesion()
    servicios.responder(
        "POST", "svc-tienda", "/api/v1/pedidos/12/pagar/", httpx.Response(200, json=PEDIDO)
    )
    servicios.responder(
        "GET",
        "svc-tienda",
        "/api/v1/pedidos/12/",
        httpx.Response(200, json={**PEDIDO, "estado": "pagado"}),
    )

    respuesta = client.post("/mis-pedidos/12/pagar/", follow=True)

    html = respuesta.content.decode()
    assert "Es un pago simulado" in html and "Pagado" in html


def test_pedido_ajeno_404(client, servicios, con_sesion):
    con_sesion()
    servicios.responder("GET", "svc-tienda", "/api/v1/pedidos/99/", error(404, "no_encontrado"))

    assert client.get("/mis-pedidos/99/").status_code == 404


def test_el_contador_se_calcula_al_iniciar_sesion(client, servicios):
    from tests.servicios_falsos import USUARIO_ID, par

    servicios.responder(
        "POST",
        "svc-usuarios",
        "/api/v1/auth/login/",
        httpx.Response(
            200,
            json={
                **par(),
                "usuario": {
                    "id": USUARIO_ID,
                    "nombre": "Juan",
                    "rol": "cliente",
                    "email_verificado": True,
                },
            },
        ),
    )
    con_carrito(servicios)

    client.post("/iniciar-sesion/", {"email": "a@b.mx", "password": "x"})

    assert client.session["carrito_cantidad"] == 3
