"""Integración con django-axes: bloqueo temporal por intentos fallidos (sección 9).

axes cuenta los intentos fallidos por la combinación correo + IP (AXES_LOCKOUT_PARAMETERS)
y los guarda en `AccessAttempt` (visible en /admin/). Para desbloquear a mano:

    docker compose exec svc-usuarios python manage.py axes_reset_username <correo>
"""

from django.http import JsonResponse

from apps.usuarios.managers import normalizar_email

CODIGO = "cuenta_bloqueada_temporalmente"
MENSAJE = "Demasiados intentos fallidos. Intenta de nuevo en 15 minutos o restablece tu contraseña."


def correo_del_intento(request, credentials) -> str | None:
    """AXES_USERNAME_CALLABLE: el correo normalizado, venga del login de la API (`email`) o
    del admin de Django (`username`)."""
    credenciales = credentials or {}
    correo = credenciales.get("email") or credenciales.get("username")
    return normalizar_email(correo) if isinstance(correo, str) else None


def respuesta_de_bloqueo(request, response=None, credentials=None, *args, **kwargs):
    """AXES_LOCKOUT_CALLABLE: 403 con el formato común de errores."""
    return JsonResponse({"error": CODIGO, "detalle": MENSAJE}, status=403)
