import django_filters
from django.db.models import Q, QuerySet

from apps.catalogo.models import Producto


class ProductoFilter(django_filters.FilterSet):
    categoria = django_filters.CharFilter(
        field_name="categoria__slug", help_text="Slug de la categoría."
    )
    precio_min = django_filters.NumberFilter(field_name="precio", lookup_expr="gte")
    precio_max = django_filters.NumberFilter(field_name="precio", lookup_expr="lte")
    disponible = django_filters.BooleanFilter(
        method="filtrar_disponible", help_text="true: con stock; false: agotados."
    )
    q = django_filters.CharFilter(method="buscar", help_text="Busca en nombre y descripción.")
    activo = django_filters.BooleanFilter(
        help_text="Solo para administradores; el público siempre ve solo productos activos."
    )

    class Meta:
        model = Producto
        fields = ["categoria", "precio_min", "precio_max", "disponible", "q", "activo"]

    def filtrar_disponible(self, queryset: QuerySet, name: str, valor: bool) -> QuerySet:
        return queryset.filter(stock__gt=0) if valor else queryset.filter(stock=0)

    def buscar(self, queryset: QuerySet, name: str, valor: str) -> QuerySet:
        return queryset.filter(Q(nombre__icontains=valor) | Q(descripcion__icontains=valor))
