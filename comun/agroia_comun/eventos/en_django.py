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

from agroia_comun.eventos import correlacion
from agroia_comun.eventos.catalogo import obtener_tipo
from agroia_comun.eventos.productor import publicar
from agroia_comun.eventos.sobre import ENCABEZADO_CORRELACION, correlacion_valida


def correlacion_de(request) -> str:
    """La correlación de la petición: la que puso CorrelacionMiddleware o, sin él, la del
    encabezado X-Correlacion-Id si es un UUID válido (si no, una nueva)."""
    ya_puesta = getattr(request, "correlacion_id", None)
    if ya_puesta:
        return ya_puesta
    encabezados = getattr(request, "headers", None) or {}
    return correlacion_valida(encabezados.get(ENCABEZADO_CORRELACION))


def publicar_al_confirmar(tipo: str, datos: dict, correlacion_id=None) -> None:
    """Publica después del commit. Sin `correlacion_id`, usa la de la petición en curso
    (la pone CorrelacionMiddleware); se toma ahora, no al confirmar."""
    # Se valida ya, dentro de la operación: un evento mal armado es un error de código.
    obtener_tipo(tipo).validar_datos(datos)
    if correlacion_id is None:
        correlacion_id = correlacion.actual()
    origen = settings.NOMBRE_SERVICIO
    transaction.on_commit(
        lambda: publicar(tipo, datos, origen=origen, correlacion_id=correlacion_id)
    )
