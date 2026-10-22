import pytest
from django.db import IntegrityError, transaction

from apps.catalogo.tests.factories import ProductoFactory
from apps.pedidos.models import Pedido
from apps.pedidos.tests.factories import (
    CarritoFactory,
    ItemCarritoFactory,
    ItemPedidoFactory,
    PedidoFactory,
)

pytestmark = pytest.mark.django_db


def test_un_carrito_por_usuario():
    CarritoFactory(usuario_id=50)

    with pytest.raises(IntegrityError), transaction.atomic():
        CarritoFactory(usuario_id=50)


def test_un_producto_solo_aparece_una_vez_por_carrito():
    item = ItemCarritoFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        ItemCarritoFactory(carrito=item.carrito, producto=item.producto)


def test_cantidad_del_carrito_debe_ser_positiva():
    with pytest.raises(IntegrityError), transaction.atomic():
        ItemCarritoFactory(cantidad=0)


def test_cantidad_del_pedido_debe_ser_positiva():
    with pytest.raises(IntegrityError), transaction.atomic():
        ItemPedidoFactory(cantidad=0)


def test_pedido_nuevo_queda_pendiente():
    assert PedidoFactory().estado == Pedido.Estado.PENDIENTE


def test_item_de_pedido_conserva_nombre_y_precio_copiados():
    producto = ProductoFactory(nombre="Urea 46%")
    item = ItemPedidoFactory(producto=producto)

    producto.nombre = "Urea granulada"
    producto.save()
    item.refresh_from_db()

    assert item.nombre_producto == "Urea 46%"


def test_no_se_puede_borrar_un_producto_con_pedidos():
    item = ItemPedidoFactory()

    with pytest.raises(Exception, match=r"[Pp]rotected"), transaction.atomic():
        item.producto.delete()


def test_estados_y_metodos_de_pago():
    assert set(Pedido.Estado.values) == {"pendiente", "pagado", "enviado", "entregado", "cancelado"}
    assert set(Pedido.MetodoPago.values) == {"tarjeta", "transferencia", "contra_entrega"}
