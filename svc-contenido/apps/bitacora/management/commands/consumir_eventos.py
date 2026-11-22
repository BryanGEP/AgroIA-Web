"""Consumidor de eventos de svc-contenido. Corre en su propio contenedor:

    docker compose up svc-contenido-eventos      (comando: python manage.py consumir_eventos)

Crea los índices (el único de evento_id incluido) y consume con el grupo svc-contenido
hasta recibir SIGTERM. Reintentos, fallidos y apagado limpio: agroia_comun.eventos.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

from agroia_comun.eventos import Consumidor
from apps.bitacora.eventos import GRUPO, MANEJADORES


class Command(BaseCommand):
    help = "Consume los eventos de Redis que le tocan a svc-contenido (bitácora)."

    def handle(self, *args, **options):
        call_command("crear_indices", verbosity=0)
        Consumidor(GRUPO, MANEJADORES).correr()
