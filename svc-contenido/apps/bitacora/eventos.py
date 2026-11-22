"""Manejadores de eventos de svc-contenido (grupo `svc-contenido`). Ver docs/eventos.md.

Cada manejador es idempotente por sí mismo: la bitácora tiene un índice único de
`evento_id`, así que el mismo evento entregado dos veces se guarda una sola vez.
"""

from agroia_comun.eventos import Sobre
from apps.bitacora import servicios

GRUPO = "svc-contenido"


def a_bitacora(sobre: Sobre) -> None:
    servicios.registrar_desde_evento(sobre)


# Todos los eventos de negocio van a la bitácora con el mismo manejador. correo_solicitado
# no: es una cola de trabajo interna de svc-usuarios (otro stream).
TIPOS_A_BITACORA = (
    "usuario_registrado",
    "correo_verificado",
    "rol_cambiado",
    "password_cambiada",
    "sesiones_cerradas",
    "pedido_creado",
    "pedido_estado_cambiado",
)
MANEJADORES = dict.fromkeys(TIPOS_A_BITACORA, a_bitacora)
