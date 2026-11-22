"""Clientes de Redis para los eventos, siempre con timeouts.

Los eventos viven en su propia base lógica (`EVENTOS_REDIS_URL`, por defecto la base 1),
separada de la caché del límite de intentos (base 0).

- `cliente()`: operaciones normales (XADD, XACK, XPENDING...), timeout corto.
- `cliente_de_lectura()`: la lectura bloqueante del consumidor (XREADGROUP BLOCK), con un
  timeout mayor que el bloqueo para que no se corte la espera normal.

Las pruebas inyectan un cliente simulado con `usar()`.
"""

import os

import redis

URL_POR_DEFECTO = "redis://redis:6379/1"


def _segundos(variable: str, por_defecto: float) -> float:
    return float(os.environ.get(variable, por_defecto))


TIMEOUT = _segundos("EVENTOS_REDIS_TIMEOUT", 2.0)
BLOQUEO_MS = int(_segundos("EVENTOS_BLOQUEO_MS", 5000))

_clientes: dict[str, redis.Redis] = {}
_forzado: redis.Redis | None = None


def url() -> str:
    return os.environ.get("EVENTOS_REDIS_URL") or URL_POR_DEFECTO


def _crear(timeout: float) -> redis.Redis:
    return redis.Redis.from_url(
        url(),
        socket_timeout=timeout,
        socket_connect_timeout=TIMEOUT,
        decode_responses=True,
        health_check_interval=30,
    )


def cliente() -> redis.Redis:
    if _forzado is not None:
        return _forzado
    if "normal" not in _clientes:
        _clientes["normal"] = _crear(TIMEOUT)
    return _clientes["normal"]


def cliente_de_lectura() -> redis.Redis:
    if _forzado is not None:
        return _forzado
    if "lectura" not in _clientes:
        _clientes["lectura"] = _crear(TIMEOUT + BLOQUEO_MS / 1000)
    return _clientes["lectura"]


def usar(cliente_simulado: redis.Redis | None) -> None:
    """Pruebas: todos los eventos usan este cliente (None vuelve al real)."""
    global _forzado
    _forzado = cliente_simulado
