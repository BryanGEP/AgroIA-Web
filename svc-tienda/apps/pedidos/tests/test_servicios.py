"""Lógica de negocio del carrito y los pedidos."""

from decimal import Decimal

import pytest

from agroia_comun.errores import ErrorDeNegocio
from apps.catalogo.tests.factories import CategoriaFactory, ProductoFactory
from apps.pedidos import servicios
from apps.pedidos.models import Carrito, ItemCarrito, Pedido
from apps.pedidos.tests.factories import ItemPedidoFactory, PedidoFactory
from tests.datos import DIRECCION

pytestmark = pytest.mark.django_db

USUARIO = 10


def codigo_de(error) -> str:
    return error.value.codigo


# --- Carrito ------------------------------------------------------------------


def test_obtener_carrito_lo_crea_una_sola_vez():
    primero = servicios.obtener_carrito(USUARIO)
    segundo = servicios.obtener_carrito(USUARIO)

    assert primero.pk == segundo.pk
    assert Carrito.objects.filter(usuario_id=USUARIO).count() == 1


def test_agregar_producto_al_carrito():
    producto = ProductoFactory(stock=5)

    item = servicios.agregar_al_carrito(USUARIO, producto, 2)

    assert item.cantidad == 2
    assert item.carrito.usuario_id == USUARIO


def test_agregar_el_mismo_producto_suma_la_cantidad():
    producto = ProductoFactory(stock=5)
    servicios.agregar_al_carrito(USUARIO, producto, 2)

    item = servicios.agregar_al_carrito(USUARIO, producto, 3)

    assert item.cantidad == 5
    assert ItemCarrito.objects.count() == 1


def test_agregar_mas_que_el_stock_falla():
    producto = ProductoFactory(stock=3)
    servicios.agregar_al_carrito(USUARIO, producto, 2)

    with pytest.raises(ErrorDeNegocio) as error:
        servicios.agregar_al_carrito(USUARIO, producto, 2)

    assert codigo_de(error) == "stock_insuficiente"
    assert ItemCarrito.objects.get().cantidad == 2


@pytest.mark.parametrize(
    "producto_factory",
    [
        lambda: ProductoFactory(activo=False),
        lambda: ProductoFactory(categoria=CategoriaFactory(activa=False)),
    ],
)
def test_no_se_puede_agregar_un_producto_no_disponible(producto_factory):
    with pytest.raises(ErrorDeNegocio) as error:
        servicios.agregar_al_carrito(USUARIO, producto_factory(), 1)

    assert codigo_de(error) == "producto_no_disponible"


def test_cambiar_cantidad_valida_el_stock():
    producto = ProductoFactory(stock=4)
    item = servicios.agregar_al_carrito(USUARIO, producto, 1)

    servicios.cambiar_cantidad(item, 4)
    item.refresh_from_db()
    assert item.cantidad == 4

    with pytest.raises(ErrorDeNegocio) as error:
        servicios.cambiar_cantidad(item, 5)
    assert codigo_de(error) == "stock_insuficiente"


def test_vaciar_carrito():
    servicios.agregar_al_carrito(USUARIO, ProductoFactory(), 1)
    servicios.agregar_al_carrito(USUARIO, ProductoFactory(), 1)

    servicios.vaciar_carrito(USUARIO)

    assert not ItemCarrito.objects.exists()


def test_totales_del_carrito():
    servicios.agregar_al_carrito(USUARIO, ProductoFactory(precio=Decimal("120.50")), 2)
    carrito = servicios.obtener_carrito(USUARIO)

    subtotal, envio, total = servicios.totales_del_carrito(carrito)

    assert (subtotal, envio, total) == (Decimal("241.00"), Decimal("150.00"), Decimal("391.00"))


# --- Envío --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("subtotal", "envio"),
    [
        (Decimal("100.00"), Decimal("150.00")),
        (Decimal("1500.00"), Decimal("150.00")),
        (Decimal("1500.01"), Decimal("0.00")),
    ],
)
def test_envio_gratis_solo_si_el_subtotal_supera_el_limite(subtotal, envio):
    assert servicios.calcular_envio(subtotal) == envio


def test_envio_usa_la_configuracion(settings):
    settings.COSTO_ENVIO = Decimal("99.00")
    settings.ENVIO_GRATIS_DESDE = Decimal("500.00")

    assert servicios.calcular_envio(Decimal("400.00")) == Decimal("99.00")
    assert servicios.calcular_envio(Decimal("600.00")) == Decimal("0.00")


# --- Crear pedido -------------------------------------------------------------


def test_crear_pedido_desde_el_carrito():
    fungicida = ProductoFactory(nombre="Caldo bordelés", precio=Decimal("185.00"), stock=10)
    tijera = ProductoFactory(nombre="Tijera de poda", precio=Decimal("320.50"), stock=3)
    servicios.agregar_al_carrito(USUARIO, fungicida, 2)
    servicios.agregar_al_carrito(USUARIO, tijera, 1)

    pedido = servicios.crear_pedido_desde_carrito(USUARIO, DIRECCION, "tarjeta")

    assert pedido.estado == Pedido.Estado.PENDIENTE
    assert pedido.usuario_id == USUARIO
    assert pedido.metodo_pago == "tarjeta"
    assert pedido.direccion_envio == DIRECCION
    assert pedido.subtotal == Decimal("690.50")
    assert pedido.envio == Decimal("150.00")
    assert pedido.total == Decimal("840.50")
    items = {i.nombre_producto: i for i in pedido.items.all()}
    assert items["Caldo bordelés"].precio_unitario == Decimal("185.00")
    assert items["Caldo bordelés"].importe == Decimal("370.00")
    assert items["Tijera de poda"].cantidad == 1
    fungicida.refresh_from_db()
    tijera.refresh_from_db()
    assert (fungicida.stock, tijera.stock) == (8, 2)
    assert not ItemCarrito.objects.filter(carrito__usuario_id=USUARIO).exists()


def test_pedido_mayor_al_limite_tiene_envio_gratis():
    servicios.agregar_al_carrito(USUARIO, ProductoFactory(precio=Decimal("800.00")), 2)

    pedido = servicios.crear_pedido_desde_carrito(USUARIO, DIRECCION, "transferencia")

    assert pedido.envio == Decimal("0.00")
    assert pedido.total == Decimal("1600.00")


def test_crear_pedido_con_carrito_vacio_falla():
    servicios.obtener_carrito(USUARIO)

    with pytest.raises(ErrorDeNegocio) as error:
        servicios.crear_pedido_desde_carrito(USUARIO, DIRECCION, "tarjeta")

    assert codigo_de(error) == "carrito_vacio"
    assert error.value.status_code == 400


def test_crear_pedido_sin_carrito_falla():
    with pytest.raises(ErrorDeNegocio) as error:
        servicios.crear_pedido_desde_carrito(USUARIO, DIRECCION, "tarjeta")

    assert codigo_de(error) == "carrito_vacio"


def test_stock_insuficiente_no_cambia_nada():
    suficiente = ProductoFactory(stock=10)
    escaso = ProductoFactory(nombre="Malla sombra", stock=5)
    servicios.agregar_al_carrito(USUARIO, suficiente, 2)
    servicios.agregar_al_carrito(USUARIO, escaso, 5)
    escaso.stock = 1  # otro cliente compró mientras tanto
    escaso.save()

    with pytest.raises(ErrorDeNegocio) as error:
        servicios.crear_pedido_desde_carrito(USUARIO, DIRECCION, "tarjeta")

    assert codigo_de(error) == "stock_insuficiente"
    assert "Malla sombra" in str(error.value.detail)
    suficiente.refresh_from_db()
    assert suficiente.stock == 10
    assert not Pedido.objects.exists()
    assert ItemCarrito.objects.filter(carrito__usuario_id=USUARIO).count() == 2


def test_producto_desactivado_despues_de_agregarlo_no_se_puede_comprar():
    producto = ProductoFactory()
    servicios.agregar_al_carrito(USUARIO, producto, 1)
    producto.activo = False
    producto.save()

    with pytest.raises(ErrorDeNegocio) as error:
        servicios.crear_pedido_desde_carrito(USUARIO, DIRECCION, "tarjeta")

    assert codigo_de(error) == "producto_no_disponible"


def test_cambio_de_precio_posterior_no_afecta_el_pedido():
    producto = ProductoFactory(precio=Decimal("100.00"))
    servicios.agregar_al_carrito(USUARIO, producto, 1)
    pedido = servicios.crear_pedido_desde_carrito(USUARIO, DIRECCION, "tarjeta")

    producto.precio = Decimal("250.00")
    producto.save()

    item = pedido.items.get()
    assert item.precio_unitario == Decimal("100.00")


# --- Pago y estados -----------------------------------------------------------


def test_pagar_pedido_pendiente():
    pedido = PedidoFactory()

    pagado = servicios.pagar_pedido(pedido)

    assert pagado.estado == Pedido.Estado.PAGADO


def test_no_se_paga_dos_veces():
    pedido = PedidoFactory(estado=Pedido.Estado.PAGADO)

    with pytest.raises(ErrorDeNegocio) as error:
        servicios.pagar_pedido(pedido)

    assert codigo_de(error) == "transicion_invalida"


@pytest.mark.parametrize(
    ("actual", "nuevo"),
    [
        ("pendiente", "pagado"),
        ("pagado", "enviado"),
        ("enviado", "entregado"),
        ("pendiente", "cancelado"),
        ("pagado", "cancelado"),
    ],
)
def test_transiciones_validas(actual, nuevo):
    pedido = PedidoFactory(estado=actual)

    assert servicios.cambiar_estado(pedido, nuevo).estado == nuevo


@pytest.mark.parametrize(
    ("actual", "nuevo"),
    [
        ("pendiente", "enviado"),
        ("pendiente", "entregado"),
        ("pagado", "pendiente"),
        ("enviado", "cancelado"),
        ("entregado", "cancelado"),
        ("cancelado", "pagado"),
        ("pagado", "pagado"),
    ],
)
def test_transiciones_invalidas(actual, nuevo):
    pedido = PedidoFactory(estado=actual)

    with pytest.raises(ErrorDeNegocio) as error:
        servicios.cambiar_estado(pedido, nuevo)

    assert codigo_de(error) == "transicion_invalida"
    pedido.refresh_from_db()
    assert pedido.estado == actual


@pytest.mark.parametrize("estado", ["pendiente", "pagado"])
def test_cancelar_devuelve_el_stock(estado):
    producto = ProductoFactory(stock=4)
    pedido = PedidoFactory(estado=estado)
    ItemPedidoFactory(pedido=pedido, producto=producto, cantidad=3)

    servicios.cambiar_estado(pedido, "cancelado")

    producto.refresh_from_db()
    assert producto.stock == 7


def test_flujo_completo_conserva_el_stock_correcto():
    producto = ProductoFactory(stock=5)
    servicios.agregar_al_carrito(USUARIO, producto, 2)
    pedido = servicios.crear_pedido_desde_carrito(USUARIO, DIRECCION, "contra_entrega")
    servicios.pagar_pedido(pedido)
    servicios.cambiar_estado(pedido, "enviado")
    servicios.cambiar_estado(pedido, "entregado")

    producto.refresh_from_db()
    pedido.refresh_from_db()
    assert producto.stock == 3
    assert pedido.estado == "entregado"
