"""Consumidor de correos (svc-usuarios-eventos): genera el token al procesar, no manda dos
veces el mismo correo, revisa si todavía toca, reintenta y manda a fallidos."""

import json
import re
import time
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from freezegun import freeze_time

from agroia_comun.eventos import Consumidor, Sobre, publicar
from agroia_comun.eventos.catalogo import STREAM_CORREOS, STREAM_FALLIDOS
from apps.usuarios import tokens
from apps.usuarios.correos import ErrorDeEnvio
from apps.usuarios.eventos import GRUPO, MANEJADORES, enviar_correo_solicitado
from apps.usuarios.models import CorreoEnviado

pytestmark = pytest.mark.django_db


def solicitud(usuario, tipo_correo: str, fecha: str | None = None) -> Sobre:
    return Sobre(
        id=str(uuid.uuid4()),
        tipo="correo_solicitado",
        version=1,
        fecha=fecha or datetime.now(UTC).isoformat(timespec="milliseconds"),
        origen="svc-usuarios",
        correlacion_id=str(uuid.uuid4()),
        datos={"usuario_id": str(usuario.pk), "tipo_correo": tipo_correo},
    )


def enlace(correo) -> str:
    return re.search(r"https?://\S+", correo.body).group(0)


def token_de_verificacion(correo) -> str:
    return unquote(parse_qs(urlparse(enlace(correo)).query)["token"][0])


def test_genera_el_token_al_procesar_y_no_viaja_en_el_evento(usuario_cliente):
    usuario_cliente.email_verificado = False
    usuario_cliente.save()
    sobre = solicitud(usuario_cliente, "verificacion")

    enviar_correo_solicitado(sobre)

    [correo] = mail.outbox
    token = token_de_verificacion(correo)
    assert token not in sobre.a_json()
    assert tokens.leer_token_de_verificacion(token) == str(usuario_cliente.pk)


def test_un_reproceso_tardio_genera_un_token_nuevo_y_vigente(usuario_cliente):
    """El enlace de verificación vence a las 24 h; un evento reprocesado tres días después
    trae un token nuevo, que sigue sirviendo."""
    usuario_cliente.email_verificado = False
    usuario_cliente.save()
    primero = solicitud(usuario_cliente, "verificacion")
    enviar_correo_solicitado(primero)
    viejo = token_de_verificacion(mail.outbox[0])

    with freeze_time(datetime.now(UTC) + timedelta(days=3)):
        enviar_correo_solicitado(solicitud(usuario_cliente, "verificacion"))
        nuevo = token_de_verificacion(mail.outbox[1])
        assert nuevo != viejo
        assert tokens.leer_token_de_verificacion(nuevo) == str(usuario_cliente.pk)


def test_la_recuperacion_lleva_un_enlace_valido(usuario_cliente):
    enviar_correo_solicitado(solicitud(usuario_cliente, "recuperacion"))

    uid, token = enlace(mail.outbox[0]).rstrip("/").split("/")[-2:]
    assert tokens.usuario_del_enlace(uid, token) == usuario_cliente


def test_el_mismo_evento_dos_veces_manda_un_solo_correo(usuario_cliente):
    sobre = solicitud(usuario_cliente, "recuperacion")

    enviar_correo_solicitado(sobre)
    enviar_correo_solicitado(sobre)

    assert len(mail.outbox) == 1
    assert CorreoEnviado.objects.filter(evento_id=sobre.id, omitido=False).count() == 1


def test_no_manda_la_verificacion_si_ya_verifico(usuario_cliente):
    usuario_cliente.email_verificado = True
    usuario_cliente.save()
    sobre = solicitud(usuario_cliente, "verificacion")

    enviar_correo_solicitado(sobre)

    assert mail.outbox == []
    assert CorreoEnviado.objects.get(evento_id=sobre.id).omitido is True


@pytest.mark.parametrize("tipo_correo", ["verificacion", "recuperacion", "aviso_password"])
def test_no_manda_nada_a_una_cuenta_desactivada(usuario_cliente, tipo_correo):
    usuario_cliente.is_active = False
    usuario_cliente.email_verificado = False
    usuario_cliente.save()

    enviar_correo_solicitado(solicitud(usuario_cliente, tipo_correo))

    assert mail.outbox == []


def test_el_aviso_usa_la_fecha_del_evento(usuario_cliente, settings):
    settings.TIME_ZONE = "America/Mexico_City"
    fecha = "2026-11-03T15:20:00.000+00:00"  # 09:20 en la Ciudad de México

    with freeze_time("2026-11-10 12:00:00"):
        enviar_correo_solicitado(solicitud(usuario_cliente, "aviso_password", fecha))

    cuerpo = mail.outbox[0].body.lower()
    assert "el 3 de noviembre de 2026 a las 09:20" in cuerpo
    assert "10 de noviembre" not in cuerpo


class FallaSiempre(BaseEmailBackend):
    def send_messages(self, mensajes):
        raise TimeoutError("el servidor de correo no responde")


def test_un_envio_que_falla_lanza_el_error_y_no_marca(usuario_cliente, settings):
    settings.EMAIL_BACKEND = f"{__name__}.FallaSiempre"
    sobre = solicitud(usuario_cliente, "recuperacion")

    with pytest.raises(ErrorDeEnvio) as error:
        enviar_correo_solicitado(sobre)

    assert "cliente@example.com" not in str(error.value)  # sin destinatario en el log
    assert not CorreoEnviado.objects.filter(evento_id=sobre.id).exists()


class FallaUnaVez(BaseEmailBackend):
    llamadas = 0

    def send_messages(self, mensajes):
        FallaUnaVez.llamadas += 1
        if FallaUnaVez.llamadas == 1:
            raise TimeoutError("el servidor de correo no responde")
        mail.outbox.extend(mensajes)
        return len(mensajes)


def consumidor(redis, **opciones) -> Consumidor:
    c = Consumidor(GRUPO, MANEJADORES, cliente=redis, bloqueo_ms=10, espera_base=0.02, **opciones)
    c.preparar()
    return c


def publicar_solicitud(redis, usuario, tipo_correo="recuperacion"):
    return publicar(
        "correo_solicitado",
        {"usuario_id": str(usuario.pk), "tipo_correo": tipo_correo},
        origen="svc-usuarios",
        cliente=redis,
    )


def test_el_reintento_no_manda_dos_correos(usuario_cliente, redis_de_eventos, settings):
    settings.EMAIL_BACKEND = f"{__name__}.FallaUnaVez"
    FallaUnaVez.llamadas = 0
    publicar_solicitud(redis_de_eventos, usuario_cliente)
    c = consumidor(redis_de_eventos, max_reintentos=3)

    c.una_vuelta()  # falla el envío: queda pendiente
    assert mail.outbox == []

    time.sleep(0.05)
    c.una_vuelta()  # reintento: sale
    time.sleep(0.1)
    c.una_vuelta()  # nada más que hacer

    assert len(mail.outbox) == 1
    assert redis_de_eventos.xpending(STREAM_CORREOS, GRUPO)["pending"] == 0


def test_un_envio_que_siempre_falla_llega_a_fallidos(usuario_cliente, redis_de_eventos, settings):
    settings.EMAIL_BACKEND = f"{__name__}.FallaSiempre"
    sobre = publicar_solicitud(redis_de_eventos, usuario_cliente)
    c = consumidor(redis_de_eventos, max_reintentos=2)

    for entrega in range(1, 4):
        time.sleep(c.espera(entrega) + 0.02)
        c.una_vuelta()

    [(_, fallido)] = redis_de_eventos.xrange(STREAM_FALLIDOS)
    assert json.loads(fallido["sobre"])["id"] == sobre.id
    assert fallido["grupo"] == "svc-usuarios"
    assert "ErrorDeEnvio" in fallido["motivo"]
    assert "cliente@example.com" not in fallido["motivo"]
    assert mail.outbox == []
