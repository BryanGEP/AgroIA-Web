"""Evento usuario_registrado: se publica después del commit y nunca rompe el registro."""

import json
import logging
import uuid

import fakeredis
import pytest
import redis
from django.db import transaction
from rest_framework.test import APIClient

from agroia_comun.eventos import conexion
from agroia_comun.eventos.catalogo import STREAM_USUARIOS
from apps.usuarios import servicios
from apps.usuarios.models import Usuario
from tests.datos import REGISTRO

pytestmark = pytest.mark.django_db

REGISTRO_URL = "/api/v1/auth/registro/"


def eventos(redis_simulado) -> list[dict]:
    return [json.loads(c["sobre"]) for _, c in redis_simulado.xrange(STREAM_USUARIOS)]


def registrar(captura, **encabezados):
    with captura(execute=True):
        return APIClient().post(REGISTRO_URL, REGISTRO, format="json", **encabezados)


def test_el_registro_publica_usuario_registrado_sin_datos_personales(
    redis_de_eventos, django_capture_on_commit_callbacks
):
    correlacion = str(uuid.uuid4())

    respuesta = registrar(django_capture_on_commit_callbacks, HTTP_X_CORRELACION_ID=correlacion)

    assert respuesta.status_code == 201
    [sobre] = eventos(redis_de_eventos)
    usuario = Usuario.objects.get(email=REGISTRO["email"])
    assert sobre["tipo"] == "usuario_registrado"
    assert sobre["origen"] == "svc-usuarios"
    assert sobre["version"] == 1
    assert sobre["correlacion_id"] == correlacion
    assert sobre["datos"] == {"usuario_id": str(usuario.id), "rol": "cliente"}
    texto = json.dumps(sobre)
    assert REGISTRO["email"] not in texto and REGISTRO["nombre"] not in texto


def test_una_correlacion_que_no_es_uuid_se_reemplaza(
    redis_de_eventos, django_capture_on_commit_callbacks
):
    registrar(django_capture_on_commit_callbacks, HTTP_X_CORRELACION_ID="<script>alert(1)")

    [sobre] = eventos(redis_de_eventos)
    assert uuid.UUID(sobre["correlacion_id"])


def test_un_registro_invalido_no_publica(redis_de_eventos, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        respuesta = APIClient().post(
            REGISTRO_URL, {**REGISTRO, "password_confirmacion": "otra"}, format="json"
        )

    assert respuesta.status_code == 400
    assert eventos(redis_de_eventos) == []


def test_si_la_transaccion_se_revierte_no_publica(
    redis_de_eventos, django_capture_on_commit_callbacks
):
    with (
        django_capture_on_commit_callbacks(execute=True) as pendientes,
        pytest.raises(RuntimeError),
        transaction.atomic(),
    ):
        servicios.registrar_usuario("ana@example.com", "Aguacate-Hass-2026", "Ana", "")
        raise RuntimeError("algo falló después de crear al usuario")

    assert pendientes == []
    assert eventos(redis_de_eventos) == []
    assert not Usuario.objects.filter(email="ana@example.com").exists()


class RedisCaido(fakeredis.FakeRedis):
    def xadd(self, *args, **kwargs):
        raise redis.ConnectionError("Error 111 connecting to redis:6379. Connection refused.")


def test_con_redis_caido_el_registro_responde_201_y_queda_evento_no_publicado(
    caplog, django_capture_on_commit_callbacks
):
    caplog.set_level(logging.INFO, logger="eventos")
    conexion.usar(RedisCaido(decode_responses=True))

    respuesta = registrar(django_capture_on_commit_callbacks)

    assert respuesta.status_code == 201
    assert Usuario.objects.filter(email=REGISTRO["email"]).exists()
    [linea] = [json.loads(r.getMessage()) for r in caplog.records if r.name == "eventos"]
    assert linea["evento"] == "evento_no_publicado"
    assert linea["tipo"] == "usuario_registrado"
    assert "Connection refused" in linea["motivo"]
    assert REGISTRO["email"] not in caplog.text
