"""Envío de correos (sección 13): todos los correos salen de este módulo.

Cada correo tiene versión de texto y HTML (`templates/emails/<plantilla>.txt|.html`).
En desarrollo EMAIL_BACKEND es el de consola: el correo, con su enlace, se imprime en
`docker compose logs svc-usuarios`. En pruebas Django usa locmem (`mail.outbox`).

Quien llama lo hace dentro de `transaction.on_commit`, para que solo se envíe si los
cambios se guardaron. Si el envío falla se registra el error y la petición sigue: el
usuario puede pedir el correo otra vez.
"""

import logging
from urllib.parse import quote

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from apps.usuarios import tokens
from apps.usuarios.models import Usuario

logger = logging.getLogger(__name__)


def enviar_correo(destinatario: str, asunto: str, plantilla: str, contexto: dict) -> bool:
    contexto = {"asunto": asunto, "frontend_url": settings.FRONTEND_URL, **contexto}
    texto = render_to_string(f"emails/{plantilla}.txt", contexto)
    html = render_to_string(f"emails/{plantilla}.html", contexto)
    mensaje = EmailMultiAlternatives(asunto, texto, settings.DEFAULT_FROM_EMAIL, [destinatario])
    mensaje.attach_alternative(html, "text/html")
    try:
        mensaje.send()
    except Exception as error:  # SMTP caído, credenciales malas, tiempo agotado...
        # Sin el destinatario ni el contenido: el correo lleva enlaces con tokens.
        logger.error("No se pudo enviar el correo «%s»: %s", plantilla, type(error).__name__)
        return False
    return True


def enviar_verificacion(usuario: Usuario) -> bool:
    token = quote(tokens.token_de_verificacion(usuario), safe="")
    return enviar_correo(
        usuario.email,
        "Verifica tu correo en AgroIA",
        "verificacion",
        {
            "nombre": usuario.nombre,
            "enlace": f"{settings.FRONTEND_URL}/verificar-correo/?token={token}",
        },
    )


def enviar_recuperacion(usuario: Usuario) -> bool:
    uid, token = tokens.uid_de(usuario), tokens.token_de_recuperacion(usuario)
    return enviar_correo(
        usuario.email,
        "Restablece tu contraseña de AgroIA",
        "recuperacion",
        {"nombre": usuario.nombre, "enlace": f"{settings.FRONTEND_URL}/restablecer/{uid}/{token}/"},
    )


def enviar_aviso_password(usuario: Usuario) -> bool:
    return enviar_correo(
        usuario.email,
        "Tu contraseña de AgroIA fue cambiada",
        "password_cambiada",
        {
            "nombre": usuario.nombre,
            "fecha": timezone.localtime(),
            "enlace": f"{settings.FRONTEND_URL}/recuperar/",
        },
    )
