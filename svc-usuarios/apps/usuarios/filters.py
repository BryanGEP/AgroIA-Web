import django_filters
from django.db.models import Q, QuerySet

from apps.usuarios.models import Usuario


class UsuarioFilter(django_filters.FilterSet):
    rol = django_filters.ChoiceFilter(choices=Usuario.Rol.choices)
    q = django_filters.CharFilter(method="buscar", help_text="Busca en correo, nombre y apellidos.")

    class Meta:
        model = Usuario
        fields = ["rol", "q"]

    def buscar(self, queryset: QuerySet, name: str, valor: str) -> QuerySet:
        return queryset.filter(
            Q(email__icontains=valor) | Q(nombre__icontains=valor) | Q(apellidos__icontains=valor)
        )
