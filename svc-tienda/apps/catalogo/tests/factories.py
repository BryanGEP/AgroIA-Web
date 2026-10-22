from decimal import Decimal

import factory

from apps.catalogo.models import Categoria, Producto


class CategoriaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Categoria

    nombre = factory.Sequence(lambda n: f"Categoría {n}")
    slug = factory.Sequence(lambda n: f"categoria-{n}")
    descripcion = "Insumos para el cultivo del aguacate."


class ProductoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Producto

    categoria = factory.SubFactory(CategoriaFactory)
    nombre = factory.Sequence(lambda n: f"Producto {n}")
    slug = factory.Sequence(lambda n: f"producto-{n}")
    descripcion = "Producto para huertas de aguacate."
    precio = Decimal("100.00")
    stock = 10
    unidad = Producto.Unidad.PIEZA
    ficha_tecnica = factory.LazyFunction(lambda: {"presentacion": "1 kg"})
