"""Consumidor de correos de svc-usuarios. Corre en su propio contenedor:

    docker compose up svc-usuarios-eventos      (comando: python manage.py consumir_eventos)

Consume `correo_solicitado` con el grupo svc-usuarios hasta recibir SIGTERM. Reintentos,
fallidos y apagado limpio: agroia_comun.eventos.
"""

from django.core.management.base import BaseCommand

from agroia_comun.eventos import Consumidor
from apps.usuarios.eventos import GRUPO, MANEJADORES


class Command(BaseCommand):
    help = "Envía los correos que piden los eventos correo_solicitado."

    def handle(self, *args, **options):
        Consumidor(GRUPO, MANEJADORES).correr()
