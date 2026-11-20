"""Comando limpiar_datos_prueba: borra lo que dejan Postman y la matriz de accesos."""

import uuid
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.catalogo.models import Categoria, Producto
from apps.catalogo.tests.factories import CategoriaFactory, ProductoFactory
from apps.pedidos.models import Carrito, ItemCarrito, Pedido
from apps.pedidos.tests.factories import ItemCarritoFactory, ItemPedidoFactory

pytestmark = pytest.mark.django_db

DEMO = uuid.uuid4()  # la cuenta demo que compra en Postman
OTRO = uuid.uuid4()  # alguien que no es de prueba


def limpiar(*usuarios) -> str:
    salida = StringIO()
    call_command("limpiar_datos_prueba", "--usuarios", ",".join(map(str, usuarios)), stdout=salida)
    return salida.getvalue()


@pytest.fixture
def datos(settings):
    settings.DEBUG = True
    call_command("cargar_datos_demo", verbosity=0)
    fertilizantes = Categoria.objects.get(slug="fertilizantes")
    demo = Producto.objects.get(slug="urea-46-costal-50-kg")
    postman = ProductoFactory(
        nombre="Fosfito de potasio 1 L 1795210684",
        slug="fosfito-de-potasio-1-l-1795210684",
        categoria=fertilizantes,
        activo=False,
    )
    matriz = ProductoFactory(slug="matriz-0419f7e0", categoria=fertilizantes)
    CategoriaFactory(nombre="Herbicidas 1795210684", slug="herbicidas-1795210684", activa=False)
    # Pedidos y carritos de la cuenta demo, y de alguien más.
    ItemPedidoFactory(pedido__usuario_id=DEMO, producto=demo)
    ItemPedidoFactory(pedido__usuario_id=DEMO, producto=postman)
    ItemPedidoFactory(pedido__usuario_id=OTRO, producto=demo)
    ItemCarritoFactory(carrito__usuario_id=DEMO, producto=demo)
    ItemCarritoFactory(carrito__usuario_id=OTRO, producto=matriz)  # se queda el carrito
    return {"postman": postman, "matriz": matriz}


def test_borra_lo_de_prueba_y_conserva_el_catalogo_demo(datos):
    salida = limpiar(DEMO)

    assert "Productos de prueba: 2. Categorías de prueba: 1. Pedidos: 2. Carritos: 1" in salida
    assert Producto.objects.count() == 20  # solo el catálogo de demostración
    assert Categoria.objects.count() == 5
    assert set(Pedido.objects.values_list("usuario_id", flat=True)) == {OTRO}
    assert set(Carrito.objects.values_list("usuario_id", flat=True)) == {OTRO}
    assert not ItemCarrito.objects.filter(producto__slug__startswith="matriz-").exists()


def test_se_puede_correr_varias_veces(datos):
    limpiar(DEMO)

    salida = limpiar(DEMO)

    assert "Productos de prueba: 0. Categorías de prueba: 0. Pedidos: 0. Carritos: 0" in salida
    assert Producto.objects.count() == 20


def test_sin_usuarios_solo_limpia_el_catalogo(datos):
    salida = limpiar()

    assert "Productos de prueba: 2" in salida
    assert "Sin --usuarios" in salida
    # Se borró el pedido que tenía el producto de Postman; el otro de la cuenta demo, no.
    assert Pedido.objects.filter(usuario_id=DEMO).count() == 1


def test_no_toca_un_slug_parecido_que_no_es_de_prueba(datos):
    ProductoFactory(slug="manguera-2024", categoria=Categoria.objects.get(slug="riego"))
    ProductoFactory(slug="matriz-de-riego", categoria=Categoria.objects.get(slug="riego"))

    limpiar(DEMO)

    assert Producto.objects.filter(slug__in=["manguera-2024", "matriz-de-riego"]).count() == 2


def test_usuarios_invalidos_falla_con_mensaje_claro(settings):
    settings.DEBUG = True
    with pytest.raises(CommandError, match="lista de UUID"):
        limpiar("no-es-un-uuid")


def test_se_niega_sin_debug(datos, settings):
    settings.DEBUG = False

    with pytest.raises(CommandError, match="DJANGO_DEBUG=True"):
        limpiar(DEMO)
    assert Producto.objects.filter(slug="fosfito-de-potasio-1-l-1795210684").exists()
