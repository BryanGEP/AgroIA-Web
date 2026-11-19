"""Límite de intentos por correo (sección 9).

`ScopedRateThrottle` de DRF ya cuenta por IP (o por usuario si hay token). Esta clase
cuenta además por el correo del cuerpo, para que nadie pida cientos de correos para la
misma cuenta cambiando de IP. Usa la tasa `<throttle_scope>_correo` de
DEFAULT_THROTTLE_RATES. En la caché se guarda un hash del correo, no el correo.
"""

import hashlib

from rest_framework.throttling import SimpleRateThrottle

from apps.usuarios.managers import normalizar_email


class LimitePorCorreo(SimpleRateThrottle):
    def __init__(self):
        # La tasa depende de la vista; se resuelve en allow_request.
        pass

    def allow_request(self, request, view):
        self.scope = f"{view.throttle_scope}_correo"
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        datos = request.data if hasattr(request.data, "get") else {}
        correo = datos.get("email")
        if not isinstance(correo, str) or not correo.strip():
            return None  # sin correo no hay qué contar; el límite por IP sigue activo
        huella = hashlib.sha256(normalizar_email(correo).encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": huella}
