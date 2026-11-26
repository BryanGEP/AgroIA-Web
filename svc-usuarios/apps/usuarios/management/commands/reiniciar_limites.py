"""Borra los contadores de límite de intentos y los bloqueos de axes. Solo en desarrollo.

    docker compose exec svc-usuarios python manage.py reiniciar_limites

Sirve para empezar una corrida de las pruebas de seguridad (Postman, la matriz) sin
esperar a que venzan las ventanas de 1 minuto o 1 hora. No cambia los límites: solo
vacía lo que ya se contó.

- Contadores de DRF (`ScopedRateThrottle` y `LimitePorCorreo`): las llaves `throttle_*`
  de la caché (Redis en Docker).
- Bloqueos de django-axes: todos los intentos fallidos guardados (`AccessAttempt`).

Los contadores de svc-contenido (límite de preguntas a la IA) los borra su propio
`reiniciar_limites`: cada servicio vacía solo los suyos.
"""

from axes.utils import reset as reiniciar_axes
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from agroia_comun.limites import borrar_contadores


class Command(BaseCommand):
    help = "Vacía los contadores de intentos y los bloqueos de axes (solo con DJANGO_DEBUG=True)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "reiniciar_limites solo corre con DJANGO_DEBUG=True: quitar los límites y "
                "los bloqueos es solo para pruebas en desarrollo."
            )
        contadores = borrar_contadores()
        bloqueos = reiniciar_axes()
        self.stdout.write(
            f"Contadores de límite borrados: {contadores}. Intentos de axes borrados: {bloqueos}."
        )
