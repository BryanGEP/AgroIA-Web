"""Borra los contadores de límite de intentos y los bloqueos de axes. Solo en desarrollo.

    docker compose exec svc-usuarios python manage.py reiniciar_limites

Sirve para empezar una corrida de las pruebas de seguridad (Postman, la matriz) sin
esperar a que venzan las ventanas de 1 minuto o 1 hora. No cambia los límites: solo
vacía lo que ya se contó.

- Contadores de DRF (`ScopedRateThrottle` y `LimitePorCorreo`): las llaves `throttle_*`
  de la caché (Redis en Docker).
- Bloqueos de django-axes: todos los intentos fallidos guardados (`AccessAttempt`).
"""

from fnmatch import fnmatch

from axes.utils import reset as reiniciar_axes
from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.locmem import LocMemCache
from django.core.cache.backends.redis import RedisCache
from django.core.management.base import BaseCommand, CommandError

# DRF guarda cada contador como "throttle_<scope>_<ident>" (SimpleRateThrottle.cache_format).
PATRON = "throttle_*"


def borrar_contadores(cache_=None) -> int:
    """Borra las llaves de los contadores y devuelve cuántas había."""
    cache_ = cache_ or caches["default"]
    patron = cache_.make_key(PATRON)  # con KEY_PREFIX y versión, como las guarda Django
    if isinstance(cache_, RedisCache):
        cliente = cache_._cache.get_client(write=True)
        llaves = list(cliente.scan_iter(match=patron))
        if llaves:
            cliente.delete(*llaves)
        return len(llaves)
    if isinstance(cache_, LocMemCache):  # pruebas
        llaves = [llave for llave in list(cache_._cache) if fnmatch(llave, patron)]
        for llave in llaves:
            cache_._cache.pop(llave, None)
            cache_._expire_info.pop(llave, None)
        return len(llaves)
    raise CommandError(f"No sé buscar llaves en la caché {type(cache_).__name__}.")


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
