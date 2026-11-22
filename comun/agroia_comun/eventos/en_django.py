"""Eventos desde los servicios Django: publicar después de confirmar la transacción.

    from agroia_comun.eventos.en_django import correlacion_de, publicar_al_confirmar

    with transaction.atomic():
        usuario = ...
        publicar_al_confirmar("usuario_registrado", {...}, correlacion_de(request))

- Si la transacción se revierte, no se publica nada.
- Si Redis no responde al publicar, la operación ya se confirmó: se registra
  `evento_no_publicado` y la respuesta al usuario no cambia (ver docs/eventos.md, riesgo y
  outbox pendiente).
"""

from django.conf import settings
from django.db import transaction

from agroia_comun.eventos.catalogo import obtener_tipo
from agroia_comun.eventos.productor import publicar
from agroia_comun.eventos.sobre import ENCABEZADO_CORRELACION, correlacion_valida


def correlacion_de(request) -> str:
    """El X-Correlacion-Id de la petición si es un UUID válido; si no, uno nuevo."""
    encabezados = getattr(request, "headers", None) or {}
    return correlacion_valida(encabezados.get(ENCABEZADO_CORRELACION))


def publicar_al_confirmar(tipo: str, datos: dict, correlacion_id=None) -> None:
    # Se valida ya, dentro de la operación: un evento mal armado es un error de código.
    obtener_tipo(tipo).validar_datos(datos)
    origen = settings.NOMBRE_SERVICIO
    transaction.on_commit(
        lambda: publicar(tipo, datos, origen=origen, correlacion_id=correlacion_id)
    )
