"""Filtros de fecha por día completo en la zona del servidor (agroia_comun.filtros)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.test import override_settings
from django.utils import timezone

from agroia_comun.filtros import FechaDesde, FechaHasta, inicio_del_dia

MEXICO = ZoneInfo("America/Mexico_City")


class ConsultaFalsa:
    """Guarda los argumentos de filter() en lugar de consultar una base."""

    def __init__(self):
        self.filtros = None

    def filter(self, **filtros):
        self.filtros = filtros
        return self


@override_settings(TIME_ZONE="America/Mexico_City", USE_TZ=True)
def test_inicio_del_dia_en_hora_de_mexico():
    with timezone.override(MEXICO):
        inicio = inicio_del_dia(date(2026, 11, 26))

    assert inicio == datetime(2026, 11, 26, tzinfo=MEXICO)
    # 00:00 en México son las 06:00 UTC.
    assert inicio.astimezone(ZoneInfo("UTC")).hour == 6


def test_desde_incluye_el_dia_completo():
    consulta = ConsultaFalsa()
    with timezone.override(MEXICO):
        FechaDesde(field_name="creado_en").filter(consulta, date(2026, 11, 26))

    assert consulta.filtros == {"creado_en__gte": datetime(2026, 11, 26, tzinfo=MEXICO)}


def test_hasta_llega_al_inicio_del_dia_siguiente():
    consulta = ConsultaFalsa()
    with timezone.override(MEXICO):
        FechaHasta(field_name="date_joined").filter(consulta, date(2026, 11, 30))

    assert consulta.filtros == {"date_joined__lt": datetime(2026, 12, 1, tzinfo=MEXICO)}


def test_sin_valor_no_filtra():
    consulta = ConsultaFalsa()

    assert FechaDesde(field_name="x").filter(consulta, None) is consulta
    assert FechaHasta(field_name="x").filter(consulta, "") is consulta
    assert consulta.filtros is None
