"""Manejadores de eventos de svc-contenido (grupo `svc-contenido`). Ver docs/eventos.md.

Cada manejador es idempotente por sí mismo: la bitácora tiene un índice único de
`evento_id`, así que el mismo evento entregado dos veces se guarda una sola vez.
"""

from agroia_comun.eventos import Sobre
from apps.bitacora import servicios

GRUPO = "svc-contenido"


def a_bitacora(sobre: Sobre) -> None:
    servicios.registrar_desde_evento(sobre)


# Fase 1: solo usuario_registrado. Los demás eventos de negocio llegan en la fase 2.
MANEJADORES = {
    "usuario_registrado": a_bitacora,
}
