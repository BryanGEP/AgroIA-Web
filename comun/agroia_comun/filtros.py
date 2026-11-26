"""Filtros de django-filter por día completo en la zona del servidor (extra [django]).

La base guarda en UTC; «desde 2026-11-26» quiere decir desde las 00:00 de ese día en la zona
de `TIME_ZONE` (America/Mexico_City en todos los servicios) y «hasta 2026-11-26», antes de las
00:00 del día siguiente: los dos inclusive. Los usan svc-tienda (pedidos) y svc-usuarios
(fecha de registro) para el panel de administración.

    from agroia_comun.filtros import FechaDesde, FechaHasta

    class PedidoFilter(django_filters.FilterSet):
        desde = FechaDesde(field_name="creado_en")
        hasta = FechaHasta(field_name="creado_en")

Importa Django: no es parte del núcleo (svc-ia no lo instala).
"""

from datetime import date, datetime, time, timedelta

import django_filters
from django.utils import timezone


def inicio_del_dia(dia: date) -> datetime:
    """Las 00:00 de `dia` en la zona actual de Django, con su zona horaria."""
    return datetime.combine(dia, time.min, tzinfo=timezone.get_current_timezone())


class FechaDesde(django_filters.DateFilter):
    """`campo >= 00:00 del día` (inclusive)."""

    def filter(self, qs, value):
        if value in (None, ""):
            return qs
        return qs.filter(**{f"{self.field_name}__gte": inicio_del_dia(value)})


class FechaHasta(django_filters.DateFilter):
    """`campo < 00:00 del día siguiente`: incluye todo el día."""

    def filter(self, qs, value):
        if value in (None, ""):
            return qs
        return qs.filter(**{f"{self.field_name}__lt": inicio_del_dia(value + timedelta(days=1))})
