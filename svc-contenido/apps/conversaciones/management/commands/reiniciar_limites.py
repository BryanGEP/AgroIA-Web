"""Borra los contadores del límite de solicitudes a la IA. Solo en desarrollo.

    docker compose exec svc-contenido python manage.py reiniciar_limites

Para empezar una corrida de Postman, la matriz o la prueba de eventos sin esperar a que
venzan las ventanas de 1 minuto o 1 hora. No cambia los límites: solo vacía lo contado.
Los contadores de svc-usuarios (login, registro, recuperación) los borra el suyo.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from agroia_comun.limites import borrar_contadores


class Command(BaseCommand):
    help = "Vacía los contadores del límite de la IA (solo con DJANGO_DEBUG=True)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "reiniciar_limites solo corre con DJANGO_DEBUG=True: quitar los límites es "
                "solo para pruebas en desarrollo."
            )
        contadores = borrar_contadores()
        self.stdout.write(f"Contadores del límite de la IA borrados: {contadores}.")
