"""Manejadores de svc-contenido para las respuestas de la IA (grupo svc-contenido).

Idempotentes por sí mismos: la respuesta se agrega con un update condicionado a que la
solicitud siga pendiente y a que la conversación no tenga ya un mensaje con ese
`solicitud_id`. Antes de guardar se comprueba que la conversación y la solicitud del evento
sean del `usuario_id` del evento.
"""

from apps.conversaciones import servicios

MANEJADORES = {
    "ia_respuesta_generada": servicios.guardar_respuesta,
    "ia_respuesta_fallida": servicios.guardar_fallida,
}
