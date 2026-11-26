import django_filters
from django import forms
from django.db.models import Q, QuerySet

from agroia_comun.filtros import FechaDesde
from apps.usuarios.models import Usuario

MAXIMO_IDS = 20


class UUIDsFilter(django_filters.BaseInFilter, django_filters.UUIDFilter):
    """Lista de UUID separados por comas; cada uno se valida (400 si alguno no lo es)."""


class FormularioUsuarios(forms.Form):
    def clean_ids(self):
        ids = self.cleaned_data.get("ids")
        if ids and len(ids) > MAXIMO_IDS:
            raise forms.ValidationError(f"Pide como máximo {MAXIMO_IDS} usuarios a la vez.")
        return ids


class UsuarioFilter(django_filters.FilterSet):
    rol = django_filters.ChoiceFilter(choices=Usuario.Rol.choices)
    q = django_filters.CharFilter(method="buscar", help_text="Busca en correo, nombre y apellidos.")
    email_verificado = django_filters.BooleanFilter(help_text="true o false.")
    desde = FechaDesde(
        field_name="date_joined",
        help_text="Registrados desde ese día (AAAA-MM-DD, inclusive, hora de México).",
    )
    ids = UUIDsFilter(
        field_name="id",
        help_text=f"Hasta {MAXIMO_IDS} UUID separados por comas (para nombrar a los usuarios "
        "de una lista de pedidos o de la bitácora con una sola llamada).",
    )

    class Meta:
        model = Usuario
        fields = ["rol", "q", "email_verificado", "desde", "ids"]
        form = FormularioUsuarios

    def buscar(self, queryset: QuerySet, name: str, valor: str) -> QuerySet:
        return queryset.filter(
            Q(email__icontains=valor) | Q(nombre__icontains=valor) | Q(apellidos__icontains=valor)
        )
