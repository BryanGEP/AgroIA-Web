from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction

from apps.catalogo.models import Producto
from apps.catalogo.tests.factories import CategoriaFactory, ProductoFactory

pytestmark = pytest.mark.django_db


def test_stock_no_puede_ser_negativo():
    producto = ProductoFactory()
    producto.stock = -1

    with pytest.raises(IntegrityError), transaction.atomic():
        producto.save()


def test_precio_debe_ser_positivo():
    with pytest.raises(IntegrityError), transaction.atomic():
        ProductoFactory(precio=Decimal("0.00"))


def test_slug_de_producto_es_unico():
    ProductoFactory(slug="caldo-bordeles")

    with pytest.raises(IntegrityError), transaction.atomic():
        ProductoFactory(slug="caldo-bordeles")


def test_precio_se_guarda_como_decimal():
    producto = ProductoFactory(precio=Decimal("349.90"))
    producto.refresh_from_db()

    assert producto.precio == Decimal("349.90")
    assert isinstance(producto.precio, Decimal)


def test_ficha_tecnica_guarda_datos_variables():
    ficha = {"ingrediente_activo": "Oxicloruro de cobre 50%", "dosis": "2-3 kg/ha"}
    producto = ProductoFactory(ficha_tecnica=ficha)
    producto.refresh_from_db()

    assert producto.ficha_tecnica == ficha


def test_no_se_puede_borrar_una_categoria_con_productos():
    categoria = CategoriaFactory()
    ProductoFactory(categoria=categoria)

    with pytest.raises(Exception, match=r"[Pp]rotected"), transaction.atomic():
        categoria.delete()


def test_imagen_con_extension_no_permitida_es_invalida():
    producto = ProductoFactory.build(categoria=CategoriaFactory())
    producto.imagen = SimpleUploadedFile("ficha.pdf", b"%PDF", content_type="application/pdf")

    with pytest.raises(ValidationError) as error:
        producto.full_clean()
    assert "imagen" in error.value.message_dict


def test_str_es_legible():
    categoria = CategoriaFactory(nombre="Fungicidas")
    producto = ProductoFactory(nombre="Caldo bordelés", categoria=categoria)

    assert str(categoria) == "Fungicidas"
    assert str(producto) == "Caldo bordelés"
    assert Producto.Unidad.COSTAL == "costal"
