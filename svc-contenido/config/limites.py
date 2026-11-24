"""Límite de solicitudes a la IA por usuario.

Preguntar, reintentar y solicitar un diagnóstico comparten el mismo presupuesto por usuario:
`IA_SOLICITUDES_POR_MINUTO` (10) y `IA_SOLICITUDES_POR_HORA` (30). El límite de tokens del
LLM es de toda la aplicación; sin esto, un solo usuario podía agotarlo y dejar sin chat a
los demás. Los GET del polling no cuentan.

Cómo cuenta: un contador por usuario y por ventana fija (el minuto y la hora de reloj),
con `incr` de la caché, que en Redis es atómico. Así, varias peticiones simultáneas del
mismo usuario no se pisan (con el historial de DRF, «leer, agregar y guardar», sí: se perdían
cuentas y un usuario con peticiones en paralelo pasaba del límite). Si alguna ventana se
pasa, la petición devuelve su cuenta con `decr`: una rechazada no gasta el presupuesto.
El costo de las ventanas fijas: justo en el cambio de minuto un usuario puede hacer hasta
el doble en pocos segundos (10 al final de uno y 10 al principio del siguiente); la de una
hora lo sigue acotando.

Al pasarse, DRF responde 429 y `agroia_comun.errores` lo convierte en
`{"error": "demasiados_intentos", "detalle": ...}` con `Retry-After`. Se revisa antes de
la vista: una solicitud rechazada no guarda nada (ni la pregunta).
"""

import contextlib

from django.conf import settings
from drf_spectacular.utils import OpenApiResponse

from agroia_comun.limites import LimitePorUsuario


class LimiteIa(LimitePorUsuario):
    scope = "ia"

    def __init__(self):
        # Las tasas se leen de settings en cada petición (las pruebas las pueden cambiar).
        self.espera = None

    def ventanas(self) -> list[tuple[str, int, int]]:
        return [
            ("ia_minuto", settings.IA_SOLICITUDES_POR_MINUTO, 60),
            ("ia_hora", settings.IA_SOLICITUDES_POR_HORA, 3600),
        ]

    def allow_request(self, request, view):
        if self.get_cache_key(request, view) is None:
            return True
        ahora = self.timer()
        self.espera = None
        contadas = []
        for scope, maximo, duracion in self.ventanas():
            numero = int(ahora // duracion)
            llave = self.cache_format % {"scope": scope, "ident": f"{request.user.pk}_{numero}"}
            self.cache.add(llave, 0, duracion + 5)
            try:
                valor = self.cache.incr(llave)
            except ValueError:  # venció entre add e incr
                self.cache.set(llave, 1, duracion + 5)
                valor = 1
            contadas.append(llave)
            if valor > maximo:
                espera = (numero + 1) * duracion - ahora
                self.espera = max(self.espera or 0, espera)
        if self.espera is None:
            return True
        for llave in contadas:  # rechazada: no se cuenta en ninguna ventana
            with contextlib.suppress(ValueError):
                self.cache.decr(llave)
        return False

    def wait(self):
        return self.espera


LIMITES_IA = [LimiteIa]

DEMASIADAS = {
    429: OpenApiResponse(
        description=(
            "`demasiados_intentos`: el usuario pasó el límite de solicitudes a la IA "
            "(`IA_SOLICITUDES_POR_MINUTO`, `IA_SOLICITUDES_POR_HORA`). Trae `Retry-After`. "
            "No se guardó nada."
        )
    )
}
