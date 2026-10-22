"""Lógica de negocio del catálogo."""

from django.db.models import Model, QuerySet
from django.utils.text import slugify

from apps.catalogo.models import Categoria, Producto


def generar_slug_unico(modelo: type[Model], nombre: str, excluir_pk: int | None = None) -> str:
    """Slug a partir del nombre; si ya existe, agrega -2, -3..."""
    base = slugify(nombre)[:160] or "sin-nombre"
    existentes = modelo.objects.filter(slug__startswith=base)
    if excluir_pk is not None:
        existentes = existentes.exclude(pk=excluir_pk)
    ocupados = set(existentes.values_list("slug", flat=True))
    slug, numero = base, 2
    while slug in ocupados:
        slug = f"{base}-{numero}"
        numero += 1
    return slug


def categorias_visibles(es_admin: bool) -> QuerySet[Categoria]:
    """El administrador ve todas; el público, solo las activas."""
    categorias = Categoria.objects.all()
    return categorias if es_admin else categorias.filter(activa=True)


def productos_visibles(es_admin: bool) -> QuerySet[Producto]:
    """El administrador ve todos; el público, solo activos de categorías activas."""
    productos = Producto.objects.select_related("categoria")
    if es_admin:
        return productos
    return productos.filter(activo=True, categoria__activa=True)


def desactivar_categoria(categoria: Categoria) -> None:
    """Borrado lógico: los productos la referencian y los pedidos a ellos."""
    categoria.activa = False
    categoria.save(update_fields=["activa"])


def desactivar_producto(producto: Producto) -> None:
    """Borrado lógico: los pedidos conservan la referencia al producto."""
    producto.activo = False
    producto.save(update_fields=["activo"])
