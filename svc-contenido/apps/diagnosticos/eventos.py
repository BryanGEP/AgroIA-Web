"""Manejadores de svc-contenido para los resultados del diagnóstico (grupo svc-contenido).

Idempotentes: el resultado solo se guarda si el diagnóstico sigue pendiente, y solo si el
diagnóstico, el usuario y la solicitud del evento coinciden.
"""

from apps.diagnosticos import servicios

MANEJADORES = {
    "diagnostico_generado": servicios.guardar_resultado,
    "diagnostico_fallido": servicios.guardar_fallido,
}
