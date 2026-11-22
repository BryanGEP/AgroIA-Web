"""La correlación de lo que se está atendiendo ahora (una petición o un evento).

Vive en una ContextVar: cada petición y cada evento tienen la suya, también con hilos.

- En los servicios Django, `agroia_comun.correlacion.CorrelacionMiddleware` la pone al
  empezar cada petición (del encabezado X-Correlacion-Id si es un UUID válido; si no, una
  nueva) y la restablece al terminar, aunque haya un error.
- El consumidor la pone con la `correlacion_id` del sobre mientras procesa cada evento,
  así un manejador que publica otro evento conserva la cadena.
- `publicar()` la usa cuando no se le pasa una.

No importa Django: también la puede usar svc-ia.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from agroia_comun.eventos.sobre import correlacion_valida

_actual: ContextVar[str | None] = ContextVar("correlacion_id", default=None)


def actual() -> str | None:
    return _actual.get()


def establecer(valor) -> tuple[str, Token]:
    """Pone la correlación (validada: un UUID o una nueva) y devuelve el token para
    restablecerla."""
    correlacion = correlacion_valida(valor)
    return correlacion, _actual.set(correlacion)


def restablecer(token: Token) -> None:
    _actual.reset(token)


@contextmanager
def con_correlacion(valor) -> Iterator[str]:
    correlacion, token = establecer(valor)
    try:
        yield correlacion
    finally:
        restablecer(token)
