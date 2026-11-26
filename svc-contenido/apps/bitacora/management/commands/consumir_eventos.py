"""Consumidor de eventos de svc-contenido. Corre en su propio contenedor:

    docker compose up svc-contenido-eventos      (comando: python manage.py consumir_eventos)

Crea los índices (el único de evento_id incluido) y consume con el grupo svc-contenido
hasta recibir SIGTERM: los eventos de negocio (bitácora) y los resultados de la IA
(respuestas del agente y diagnósticos). Reintentos, fallidos y apagado limpio:
agroia_comun.eventos.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

from agroia_comun.eventos import Consumidor
from apps.bitacora.eventos import GRUPO
from apps.bitacora.eventos import MANEJADORES as BITACORA
from apps.conversaciones.eventos import MANEJADORES as RESPUESTAS
from apps.diagnosticos.eventos import MANEJADORES as DIAGNOSTICOS

MANEJADORES = {**BITACORA, **RESPUESTAS, **DIAGNOSTICOS}


class Command(BaseCommand):
    help = "Consume los eventos de Redis que le tocan a svc-contenido (bitácora e IA)."

    def handle(self, *args, **options):
        call_command("crear_indices", verbosity=0)
        Consumidor(GRUPO, MANEJADORES).correr()
