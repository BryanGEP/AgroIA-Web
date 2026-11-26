import pytest

from apps.catalogo import servicios
from apps.catalogo.models import Categoria, Producto
from apps.catalogo.tests.factories import CategoriaFactory, ProductoFactory

pytestmark = pytest.mark.django_db


def test_generar_slug_desde_el_nombre():
    assert servicios.generar_slug_unico(Producto, "Caldo Bordelés 1 kg") == "caldo-bordeles-1-kg"


def test_generar_slug_agrega_sufijo_si_ya_existe():
    ProductoFactory(slug="caldo-bordeles")
    ProductoFactory(slug="caldo-bordeles-2")

    assert servicios.generar_slug_unico(Producto, "Caldo bordelés") == "caldo-bordeles-3"


def test_generar_slug_ignora_el_propio_registro():
    categoria = CategoriaFactory(slug="riego")

    assert servicios.generar_slug_unico(Categoria, "Riego", excluir_pk=categoria.pk) == "riego"


def test_desactivar_producto_es_borrado_logico():
    producto = ProductoFactory()

    servicios.desactivar_producto(producto)

    producto.refresh_from_db()
    assert producto.activo is False


def test_desactivar_categoria_es_borrado_logico():
    categoria = CategoriaFactory()

    servicios.desactivar_categoria(categoria)

    categoria.refresh_from_db()
    assert categoria.activa is False


def test_productos_visibles_para_el_publico():
    visible = ProductoFactory()
    ProductoFactory(activo=False)
    ProductoFactory(categoria=CategoriaFactory(activa=False))

    assert list(servicios.productos_visibles(es_admin=False)) == [visible]
    assert servicios.productos_visibles(es_admin=True).count() == 3


def test_categorias_visibles_para_el_publico():
    activa = CategoriaFactory()
    CategoriaFactory(activa=False)

    assert list(servicios.categorias_visibles(es_admin=False)) == [activa]
    assert servicios.categorias_visibles(es_admin=True).count() == 2
