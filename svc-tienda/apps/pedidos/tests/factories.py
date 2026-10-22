from decimal import Decimal

import factory

from apps.catalogo.tests.factories import ProductoFactory
from apps.pedidos.models import Carrito, ItemCarrito, ItemPedido, Pedido
from tests.datos import DIRECCION


class CarritoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Carrito

    usuario_id = factory.Sequence(lambda n: 1000 + n)


class ItemCarritoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ItemCarrito

    carrito = factory.SubFactory(CarritoFactory)
    producto = factory.SubFactory(ProductoFactory)
    cantidad = 1


class PedidoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Pedido

    usuario_id = 10
    estado = Pedido.Estado.PENDIENTE
    direccion_envio = factory.LazyFunction(lambda: dict(DIRECCION))
    subtotal = Decimal("200.00")
    envio = Decimal("150.00")
    total = Decimal("350.00")
    metodo_pago = Pedido.MetodoPago.TARJETA


class ItemPedidoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ItemPedido

    pedido = factory.SubFactory(PedidoFactory)
    producto = factory.SubFactory(ProductoFactory)
    nombre_producto = factory.SelfAttribute("producto.nombre")
    precio_unitario = factory.SelfAttribute("producto.precio")
    cantidad = 2
    importe = factory.LazyAttribute(lambda o: o.precio_unitario * o.cantidad)
