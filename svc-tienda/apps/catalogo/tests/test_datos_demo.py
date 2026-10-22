from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.catalogo.models import Categoria, Producto

pytestmark = pytest.mark.django_db


def test_carga_categorias_y_productos():
    call_command("cargar_datos_demo", verbosity=0)

    assert Categoria.objects.count() == 5
    assert Producto.objects.count() == 20
    assert all(isinstance(p.precio, Decimal) and p.precio > 0 for p in Producto.objects.all())
    assert all(p.ficha_tecnica for p in Producto.objects.all())


def test_se_puede_correr_varias_veces_sin_duplicar():
    call_command("cargar_datos_demo", verbosity=0)
    producto = Producto.objects.first()
    producto.stock = 0
    producto.save()

    call_command("cargar_datos_demo", verbosity=0)

    assert Categoria.objects.count() == 5
    assert Producto.objects.count() == 20
    producto.refresh_from_db()
    assert producto.stock > 0
