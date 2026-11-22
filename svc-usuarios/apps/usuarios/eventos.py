"""Consumidor de correos de svc-usuarios (grupo `svc-usuarios`, stream de correos).

Corre en su propio contenedor, svc-usuarios-eventos (`python manage.py consumir_eventos`).
Cada `correo_solicitado` trae solo `usuario_id` y `tipo_correo`; el token del enlace se
genera aquí, al enviar. Si el evento se reprocesa más tarde, el token es nuevo y vigente.

Antes de enviar se vuelve a revisar si todavía toca: la verificación no se manda si el
correo ya está verificado, y ningún correo sale a una cuenta desactivada.

Idempotencia: `CorreoEnviado` guarda el `evento_id` de cada correo procesado (enviado u
omitido); el mismo evento dos veces no manda dos correos. Queda un hueco que SMTP no deja
cerrar: si el proceso muere después de que el servidor aceptó el correo y antes de guardar
la fila, al reentregarse el evento el correo sale otra vez (ver docs/eventos.md).
"""

from datetime import datetime

from django.db import IntegrityError, transaction

from agroia_comun.eventos import Sobre
from apps.usuarios import correos
from apps.usuarios.models import CorreoEnviado, Usuario

GRUPO = "svc-usuarios"

ENVIOS = {
    "verificacion": correos.enviar_verificacion,
    "recuperacion": correos.enviar_recuperacion,
}


def _todavia_toca(usuario: Usuario | None, tipo_correo: str) -> bool:
    if usuario is None or not usuario.is_active:
        return False
    return not (tipo_correo == "verificacion" and usuario.email_verificado)


def enviar_correo_solicitado(sobre: Sobre) -> None:
    datos = sobre.datos
    if CorreoEnviado.objects.filter(evento_id=sobre.id).exists():
        return
    usuario = Usuario.objects.filter(pk=datos["usuario_id"]).first()
    tipo_correo = datos["tipo_correo"]
    omitido = not _todavia_toca(usuario, tipo_correo)
    if usuario is None:
        return  # la cuenta ya no existe: nada que enviar ni registrar
    if not omitido:
        # Si falla, lanza ErrorDeEnvio: no se guarda la fila y el consumidor reintenta.
        if tipo_correo == "aviso_password":
            correos.enviar_aviso_password(usuario, datetime.fromisoformat(sobre.fecha))
        else:
            ENVIOS[tipo_correo](usuario)
    try:
        with transaction.atomic():
            CorreoEnviado.objects.create(
                evento_id=sobre.id, usuario=usuario, tipo_correo=tipo_correo, omitido=omitido
            )
    except IntegrityError:
        pass  # otro consumidor lo registró al mismo tiempo


MANEJADORES = {"correo_solicitado": enviar_correo_solicitado}
