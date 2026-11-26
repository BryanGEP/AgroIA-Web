"""Límites de intentos compartidos por los servicios Django (DRF + la caché de Django).

- `borrar_contadores()`: vacía los contadores de DRF de la caché del servicio. Lo usa el
  comando `reiniciar_limites` de cada servicio (solo en desarrollo).
- `LimitePorUsuarioPorMinuto` y `LimitePorUsuarioPorHora`: cuentan por el `user_id` del
  token, con la tasa del `scope` en DEFAULT_THROTTLE_RATES. Cada servicio les da su scope.

Cada servicio guarda sus contadores en la caché con su propio `KEY_PREFIX` y solo borra
los suyos: nadie toca los contadores de otro servicio.
"""

from fnmatch import fnmatch

from django.core.cache import caches
from django.core.cache.backends.locmem import LocMemCache
from django.core.cache.backends.redis import RedisCache
from rest_framework.throttling import UserRateThrottle

# DRF guarda cada contador como "throttle_<scope>_<ident>" (SimpleRateThrottle.cache_format).
PATRON = "throttle_*"


def borrar_contadores(cache_=None) -> int:
    """Borra las llaves de los contadores de este servicio y devuelve cuántas había."""
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
    raise ValueError(f"No sé buscar llaves en la caché {type(cache_).__name__}.")


class LimitePorUsuario(UserRateThrottle):
    """Cuenta por usuario autenticado (el `user_id` del token, un UUID). Sin token no
    cuenta: esas peticiones ya responden 401 antes de llegar aquí."""

    def get_cache_key(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}
