"""Envío de correos (sección 13): todos los correos salen de este módulo.

Cada correo tiene versión de texto y HTML (`templates/emails/<plantilla>.txt|.html`).
En desarrollo EMAIL_BACKEND es el de consola: el correo, con su enlace, se imprime en
`docker compose logs svc-usuarios`. En pruebas Django usa locmem (`mail.outbox`).

Desde la Entrega 4 nadie los envía dentro de una petición: las acciones publican el evento
`correo_solicitado` (solo `usuario_id` y el tipo) y el consumidor de svc-usuarios
(apps/usuarios/eventos.py, contenedor svc-usuarios-eventos) llama a estas funciones. Por
eso el token del enlace se genera al enviar, nunca viaja en el evento.

Si el envío falla, se lanza `ErrorDeEnvio` (sin destinatario ni contenido: el correo lleva
enlaces con tokens) y el consumidor reintenta; al agotar los reintentos, el evento va al
stream de fallidos y se puede reprocesar.
"""

import logging
from datetime import datetime
from urllib.parse import quote

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from apps.usuarios import tokens
from apps.usuarios.models import Usuario

logger = logging.getLogger(__name__)


class ErrorDeEnvio(Exception):
    """El servidor de correo no aceptó el mensaje. El texto no lleva destinatario ni
    contenido, porque termina en el log del consumidor."""


def enviar_correo(destinatario: str, asunto: str, plantilla: str, contexto: dict) -> None:
    contexto = {"asunto": asunto, "frontend_url": settings.FRONTEND_URL, **contexto}
    texto = render_to_string(f"emails/{plantilla}.txt", contexto)
    html = render_to_string(f"emails/{plantilla}.html", contexto)
    mensaje = EmailMultiAlternatives(asunto, texto, settings.DEFAULT_FROM_EMAIL, [destinatario])
    mensaje.attach_alternative(html, "text/html")
    try:
        mensaje.send()
    except Exception as error:  # SMTP caído, credenciales malas, tiempo agotado...
        # Solo la clase del error: el mensaje de SMTP puede traer el destinatario.
        raise ErrorDeEnvio(
            f"No se pudo enviar el correo «{plantilla}»: {type(error).__name__}"
        ) from None


def enviar_verificacion(usuario: Usuario) -> None:
    token = quote(tokens.token_de_verificacion(usuario), safe="")
    enviar_correo(
        usuario.email,
        "Verifica tu correo en AgroIA",
        "verificacion",
        {
            "nombre": usuario.nombre,
            "enlace": f"{settings.FRONTEND_URL}/verificar-correo/?token={token}",
        },
    )


def enviar_recuperacion(usuario: Usuario) -> None:
    uid, token = tokens.uid_de(usuario), tokens.token_de_recuperacion(usuario)
    enviar_correo(
        usuario.email,
        "Restablece tu contraseña de AgroIA",
        "recuperacion",
        {"nombre": usuario.nombre, "enlace": f"{settings.FRONTEND_URL}/restablecer/{uid}/{token}/"},
    )


def enviar_aviso_password(usuario: Usuario, fecha: datetime | None = None) -> None:
    """`fecha` es cuándo cambió la contraseña (la del evento), no cuándo sale el correo."""
    enviar_correo(
        usuario.email,
        "Tu contraseña de AgroIA fue cambiada",
        "password_cambiada",
        {
            "nombre": usuario.nombre,
            "fecha": timezone.localtime(fecha or timezone.now()),
            "enlace": f"{settings.FRONTEND_URL}/recuperar/",
        },
    )
