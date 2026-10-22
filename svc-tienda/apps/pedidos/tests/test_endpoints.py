"""Endpoints de carrito y pedidos: caso correcto, validación, 401 y 403."""

from decimal import Decimal

import pytest
from django.test import override_settings

from apps.catalogo.tests.factories import ProductoFactory
from apps.pedidos.models import ItemCarrito, Pedido
from apps.pedidos.tests.factories import ItemCarritoFactory, ItemPedidoFactory, PedidoFactory
from tests.datos import CLIENTE_ID, OTRO_CLIENTE_ID

pytestmark = pytest.mark.django_db

CARRITO = "/api/v1/carrito/"
ITEMS = "/api/v1/carrito/items/"
PEDIDOS = "/api/v1/pedidos/"


def item_de(usuario_id: int, **datos) -> ItemCarrito:
    from apps.pedidos.servicios import obtener_carrito

    return ItemCarritoFactory(carrito=obtener_carrito(usuario_id), **datos)


# --- Carrito ------------------------------------------------------------------


def test_ver_carrito_vacio(cliente):
    respuesta = cliente.get(CARRITO)

    assert respuesta.status_code == 200
    assert respuesta.json()["items"] == []
    assert respuesta.json()["total"] == "0.00"


def test_ver_carrito_con_totales(cliente):
    item_de(CLIENTE_ID, producto=ProductoFactory(precio=Decimal("250.00")), cantidad=2)

    cuerpo = cliente.get(CARRITO).json()

    assert cuerpo["subtotal"] == "500.00"
    assert cuerpo["envio"] == "150.00"
    assert cuerpo["total"] == "650.00"
    assert cuerpo["items"][0]["importe"] == "500.00"


def test_ver_carrito_sin_token_401(anonimo):
    assert anonimo.get(CARRITO).status_code == 401


def test_ver_carrito_sin_rol_403(sin_rol):
    assert sin_rol.get(CARRITO).status_code == 403


def test_agregar_al_carrito(cliente):
    ProductoFactory(slug="urea", stock=5)

    respuesta = cliente.post(ITEMS, {"producto": "urea", "cantidad": 2}, format="json")

    assert respuesta.status_code == 201
    assert respuesta.json()["items"][0]["cantidad"] == 2
    assert respuesta.json()["items"][0]["producto"]["slug"] == "urea"


def test_agregar_mas_que_el_stock_409(cliente):
    ProductoFactory(slug="urea", stock=1)

    respuesta = cliente.post(ITEMS, {"producto": "urea", "cantidad": 2}, format="json")

    assert respuesta.status_code == 409
    assert respuesta.json()["error"] == "stock_insuficiente"


def test_agregar_producto_inactivo_409(cliente):
    ProductoFactory(slug="retirado", activo=False)

    respuesta = cliente.post(ITEMS, {"producto": "retirado", "cantidad": 1}, format="json")

    assert respuesta.status_code == 409
    assert respuesta.json()["error"] == "producto_no_disponible"


@pytest.mark.parametrize(
    "datos",
    [{"producto": "urea", "cantidad": 0}, {"producto": "no-existe", "cantidad": 1}, {}],
)
def test_agregar_con_datos_invalidos_400(cliente, datos):
    ProductoFactory(slug="urea")

    respuesta = cliente.post(ITEMS, datos, format="json")

    assert respuesta.status_code == 400
    assert respuesta.json()["error"] == "validacion"


def test_agregar_sin_token_401(anonimo):
    ProductoFactory(slug="urea")

    assert (
        anonimo.post(ITEMS, {"producto": "urea", "cantidad": 1}, format="json").status_code == 401
    )


def test_agregar_sin_rol_403(sin_rol):
    ProductoFactory(slug="urea")

    assert (
        sin_rol.post(ITEMS, {"producto": "urea", "cantidad": 1}, format="json").status_code == 403
    )


def test_cambiar_cantidad(cliente):
    item = item_de(CLIENTE_ID, producto=ProductoFactory(stock=5))
    url = f"{ITEMS}{item.pk}/"

    assert cliente.patch(url, {"cantidad": 4}, format="json").status_code == 200
    item.refresh_from_db()
    assert item.cantidad == 4
    assert cliente.patch(url, {"cantidad": 6}, format="json").status_code == 409
    assert cliente.patch(url, {"cantidad": 0}, format="json").status_code == 400


def test_no_se_puede_tocar_el_item_de_otro_cliente(otro_cliente):
    item = item_de(CLIENTE_ID)
    url = f"{ITEMS}{item.pk}/"

    assert otro_cliente.patch(url, {"cantidad": 1}, format="json").status_code == 404
    assert otro_cliente.delete(url).status_code == 404


def test_cambiar_cantidad_401_y_403(anonimo, sin_rol):
    url = f"{ITEMS}{item_de(CLIENTE_ID).pk}/"

    assert anonimo.patch(url, {"cantidad": 1}, format="json").status_code == 401
    assert sin_rol.patch(url, {"cantidad": 1}, format="json").status_code == 403


def test_quitar_item(cliente, anonimo, sin_rol):
    item = item_de(CLIENTE_ID)
    url = f"{ITEMS}{item.pk}/"

    assert anonimo.delete(url).status_code == 401
    assert sin_rol.delete(url).status_code == 403
    assert cliente.delete(url).status_code == 204
    assert not ItemCarrito.objects.exists()


def test_vaciar_carrito(cliente, anonimo, sin_rol):
    item_de(CLIENTE_ID)
    item_de(CLIENTE_ID)

    assert anonimo.delete(CARRITO).status_code == 401
    assert sin_rol.delete(CARRITO).status_code == 403
    assert cliente.delete(CARRITO).status_code == 204
    assert not ItemCarrito.objects.exists()


@override_settings(AUTH_ACTIVA=False)
def test_auth_apagada_el_carrito_sigue_pidiendo_token(anonimo):
    assert anonimo.get(CARRITO).status_code == 401


# --- Crear pedido -------------------------------------------------------------


def test_crear_pedido(cliente, direccion):
    producto = ProductoFactory(nombre="Malla sombra", precio=Decimal("300.00"), stock=4)
    item_de(CLIENTE_ID, producto=producto, cantidad=2)

    respuesta = cliente.post(
        PEDIDOS, {"direccion_envio": direccion, "metodo_pago": "tarjeta"}, format="json"
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "pendiente"
    assert cuerpo["total"] == "750.00"
    assert cuerpo["pago_simulado"] is True
    assert cuerpo["direccion_envio"]["codigo_postal"] == "59510"
    assert cuerpo["items"][0]["nombre_producto"] == "Malla sombra"
    producto.refresh_from_db()
    assert producto.stock == 2
    assert cliente.get(CARRITO).json()["items"] == []


@pytest.mark.parametrize(
    ("cambio", "campo"),
    [
        ({"codigo_postal": "5951"}, "direccion_envio"),
        ({"calle": ""}, "direccion_envio"),
        ({"municipio": None}, "direccion_envio"),
    ],
)
def test_crear_pedido_con_direccion_invalida(cliente, direccion, cambio, campo):
    item_de(CLIENTE_ID)
    direccion.update(cambio)

    respuesta = cliente.post(
        PEDIDOS, {"direccion_envio": direccion, "metodo_pago": "tarjeta"}, format="json"
    )

    assert respuesta.status_code == 400
    assert campo in respuesta.json()["campos"]


def test_crear_pedido_con_metodo_de_pago_invalido(cliente, direccion):
    item_de(CLIENTE_ID)

    respuesta = cliente.post(
        PEDIDOS, {"direccion_envio": direccion, "metodo_pago": "bitcoin"}, format="json"
    )

    assert respuesta.status_code == 400
    assert "metodo_pago" in respuesta.json()["campos"]


def test_crear_pedido_con_carrito_vacio(cliente, direccion):
    respuesta = cliente.post(
        PEDIDOS, {"direccion_envio": direccion, "metodo_pago": "tarjeta"}, format="json"
    )

    assert respuesta.status_code == 400
    assert respuesta.json()["error"] == "carrito_vacio"


def test_crear_pedido_sin_stock(cliente, direccion):
    producto = ProductoFactory(stock=5)
    item_de(CLIENTE_ID, producto=producto, cantidad=5)
    producto.stock = 2
    producto.save()

    respuesta = cliente.post(
        PEDIDOS, {"direccion_envio": direccion, "metodo_pago": "tarjeta"}, format="json"
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["error"] == "stock_insuficiente"


def test_crear_pedido_sin_token_401(anonimo, direccion):
    datos = {"direccion_envio": direccion, "metodo_pago": "tarjeta"}

    assert anonimo.post(PEDIDOS, datos, format="json").status_code == 401


def test_crear_pedido_como_admin_403(admin, direccion):
    datos = {"direccion_envio": direccion, "metodo_pago": "tarjeta"}

    assert admin.post(PEDIDOS, datos, format="json").status_code == 403


def test_crear_pedido_sin_correo_verificado_403(sin_verificar, direccion):
    datos = {"direccion_envio": direccion, "metodo_pago": "tarjeta"}

    respuesta = sin_verificar.post(PEDIDOS, datos, format="json")

    assert respuesta.status_code == 403
    assert "verific" in respuesta.json()["detalle"].lower()


# --- Pagar --------------------------------------------------------------------


def test_pagar_pedido(cliente):
    pedido = PedidoFactory(usuario_id=CLIENTE_ID)

    respuesta = cliente.post(f"{PEDIDOS}{pedido.pk}/pagar/")

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "pagado"
    assert respuesta.json()["pago_simulado"] is True


def test_pagar_dos_veces_409(cliente):
    pedido = PedidoFactory(usuario_id=CLIENTE_ID, estado="pagado")

    respuesta = cliente.post(f"{PEDIDOS}{pedido.pk}/pagar/")

    assert respuesta.status_code == 409
    assert respuesta.json()["error"] == "transicion_invalida"


def test_pagar_pedido_de_otro_404(otro_cliente):
    pedido = PedidoFactory(usuario_id=CLIENTE_ID)

    assert otro_cliente.post(f"{PEDIDOS}{pedido.pk}/pagar/").status_code == 404
    pedido.refresh_from_db()
    assert pedido.estado == "pendiente"


def test_pagar_401_y_403(anonimo, admin):
    pedido = PedidoFactory(usuario_id=CLIENTE_ID)
    url = f"{PEDIDOS}{pedido.pk}/pagar/"

    assert anonimo.post(url).status_code == 401
    assert admin.post(url).status_code == 403


# --- Listar y ver -------------------------------------------------------------


def test_cliente_solo_ve_sus_pedidos(cliente):
    propio = PedidoFactory(usuario_id=CLIENTE_ID)
    PedidoFactory(usuario_id=OTRO_CLIENTE_ID)

    respuesta = cliente.get(PEDIDOS)

    assert respuesta.status_code == 200
    assert [p["id"] for p in respuesta.json()["results"]] == [propio.pk]


def test_admin_ve_todos_y_filtra_por_estado(admin):
    PedidoFactory(usuario_id=CLIENTE_ID)
    pagado = PedidoFactory(usuario_id=OTRO_CLIENTE_ID, estado="pagado")

    assert admin.get(PEDIDOS).json()["count"] == 2
    filtrados = admin.get(PEDIDOS, {"estado": "pagado"}).json()["results"]
    assert [p["id"] for p in filtrados] == [pagado.pk]


def test_filtro_de_estado_invalido_400(admin):
    respuesta = admin.get(PEDIDOS, {"estado": "perdido"})

    assert respuesta.status_code == 400
    assert "estado" in respuesta.json()["campos"]


def test_listar_pedidos_401_y_403(anonimo, sin_rol):
    assert anonimo.get(PEDIDOS).status_code == 401
    assert sin_rol.get(PEDIDOS).status_code == 403


def test_ver_pedido_propio(cliente):
    pedido = PedidoFactory(usuario_id=CLIENTE_ID)
    ItemPedidoFactory(pedido=pedido, cantidad=3)

    respuesta = cliente.get(f"{PEDIDOS}{pedido.pk}/")

    assert respuesta.status_code == 200
    assert respuesta.json()["items"][0]["cantidad"] == 3


def test_cliente_no_puede_ver_el_pedido_de_otro(otro_cliente):
    pedido = PedidoFactory(usuario_id=CLIENTE_ID)

    respuesta = otro_cliente.get(f"{PEDIDOS}{pedido.pk}/")

    # 404 y no 403, para no revelar que el pedido existe.
    assert respuesta.status_code == 404


def test_admin_ve_cualquier_pedido(admin):
    pedido = PedidoFactory(usuario_id=CLIENTE_ID)

    assert admin.get(f"{PEDIDOS}{pedido.pk}/").status_code == 200


def test_ver_pedido_401_y_403(anonimo, sin_rol):
    pedido = PedidoFactory(usuario_id=CLIENTE_ID)
    url = f"{PEDIDOS}{pedido.pk}/"

    assert anonimo.get(url).status_code == 401
    assert sin_rol.get(url).status_code == 403


# --- Cambiar estado -----------------------------------------------------------


def test_admin_cambia_estado(admin):
    pedido = PedidoFactory(estado="pagado")

    respuesta = admin.patch(f"{PEDIDOS}{pedido.pk}/estado/", {"estado": "enviado"}, format="json")

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "enviado"


def test_transicion_invalida_409(admin):
    pedido = PedidoFactory(estado="pendiente")

    respuesta = admin.patch(f"{PEDIDOS}{pedido.pk}/estado/", {"estado": "entregado"}, format="json")

    assert respuesta.status_code == 409
    assert respuesta.json()["error"] == "transicion_invalida"


def test_estado_desconocido_400(admin):
    pedido = PedidoFactory()

    respuesta = admin.patch(f"{PEDIDOS}{pedido.pk}/estado/", {"estado": "perdido"}, format="json")

    assert respuesta.status_code == 400
    assert "estado" in respuesta.json()["campos"]


def test_cancelar_devuelve_stock(admin):
    producto = ProductoFactory(stock=1)
    pedido = PedidoFactory(estado="pagado")
    ItemPedidoFactory(pedido=pedido, producto=producto, cantidad=4)

    respuesta = admin.patch(f"{PEDIDOS}{pedido.pk}/estado/", {"estado": "cancelado"}, format="json")

    assert respuesta.status_code == 200
    producto.refresh_from_db()
    assert producto.stock == 5


def test_cambiar_estado_401_y_403(anonimo, cliente):
    pedido = PedidoFactory(usuario_id=CLIENTE_ID)
    url = f"{PEDIDOS}{pedido.pk}/estado/"

    assert anonimo.patch(url, {"estado": "pagado"}, format="json").status_code == 401
    assert cliente.patch(url, {"estado": "pagado"}, format="json").status_code == 403
    pedido.refresh_from_db()
    assert pedido.estado == Pedido.Estado.PENDIENTE
