"""Filtros de plantilla del panel: resumen legible de la bitácora, fechas y ids cortos."""

from datetime import datetime

from django import template
from django.utils import timezone

from apps.panel import bitacora

register = template.Library()


@register.filter
def resumen_evento(evento: dict) -> str:
    return bitacora.resumir(evento)


@register.filter
def nombre_tipo(tipo: str) -> str:
    return bitacora.nombre_de_tipo(tipo or "")


@register.filter
def fecha(valor):
    """Texto ISO 8601 de un servicio → datetime en la hora local (para |date)."""
    if not valor:
        return None
    try:
        momento = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    if timezone.is_naive(momento):
        return momento
    return timezone.localtime(momento)


@register.filter
def id_corto(valor) -> str:
    return str(valor or "")[:8]


@register.filter
def segundos(milisegundos) -> str:
    """Tiempo inactivo de un consumidor en palabras cortas."""
    try:
        total = int(milisegundos) // 1000
    except (TypeError, ValueError):
        return "?"
    if total < 60:
        return f"{total} s"
    if total < 3600:
        return f"{total // 60} min"
    if total < 86400:
        return f"{total // 3600} h {total % 3600 // 60} min"
    return f"{total // 86400} d"


@register.simple_tag
def elegir_usuario(nombres: dict, usuario_id):
    return (nombres or {}).get(str(usuario_id or ""))


@register.simple_tag
def secciones_panel() -> list[tuple[str, str]]:
    from django.urls import reverse

    return [
        ("Resumen", reverse("panel:inicio")),
        ("Pedidos", reverse("panel:pedidos")),
        ("Productos", reverse("panel:productos")),
        ("Categorías", reverse("panel:categorias")),
        ("Usuarios", reverse("panel:usuarios")),
        ("Bitácora", reverse("panel:bitacora")),
        ("Eventos", reverse("panel:eventos")),
    ]
