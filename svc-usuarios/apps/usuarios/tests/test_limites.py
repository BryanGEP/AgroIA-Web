"""Límite de intentos (sección 9): throttling de DRF y bloqueo de django-axes."""

import json
import logging
from datetime import timedelta

import pytest
from axes.models import AccessAttempt
from freezegun import freeze_time
from rest_framework.test import APIClient

from apps.usuarios.tests.factories import PASSWORD_DE_PRUEBA
from tests.datos import REGISTRO

pytestmark = pytest.mark.django_db

AUTH = "/api/v1/auth/"
BLOQUEO = {
    "error": "cuenta_bloqueada_temporalmente",
    "detalle": (
        "Demasiados intentos fallidos. Intenta de nuevo en 15 minutos o restablece tu contraseña."
    ),
}


def login(password=PASSWORD_DE_PRUEBA, ip="10.0.0.1", email="cliente@example.com"):
    return APIClient().post(
        f"{AUTH}login/", {"email": email, "password": password}, format="json", REMOTE_ADDR=ip
    )


def assert_429(respuesta):
    assert respuesta.status_code == 429
    assert respuesta.json()["error"] == "demasiados_intentos"
    assert int(respuesta.headers["Retry-After"]) > 0


# --- Throttling de DRF -----------------------------------------------------------------


def test_login_10_por_minuto_por_ip(usuario_cliente):
    # Un correo distinto cada vez, para que axes no bloquee antes del límite por IP.
    for i in range(10):
        assert login(email=f"nadie{i}@example.com").status_code == 401

    assert_429(login())
    assert login(ip="10.0.0.2").status_code == 200  # otra IP sigue entrando


def test_registro_5_por_hora_por_ip(anonimo):
    for i in range(5):
        datos = {**REGISTRO, "email": f"persona{i}@example.com"}
        assert anonimo.post(f"{AUTH}registro/", datos, format="json").status_code == 201

    assert_429(anonimo.post(f"{AUTH}registro/", REGISTRO, format="json"))


@pytest.mark.parametrize("ruta", ["recuperar/", "reenviar-verificacion/"])
def test_correos_3_por_hora_por_ip(ruta, usuario_cliente):
    cliente = APIClient()
    for i in range(3):
        datos = {"email": f"persona{i}@example.com"}
        assert cliente.post(f"{AUTH}{ruta}", datos, format="json").status_code == 200

    assert_429(cliente.post(f"{AUTH}{ruta}", {"email": "otra@example.com"}, format="json"))


@pytest.mark.parametrize("ruta", ["recuperar/", "reenviar-verificacion/"])
def test_correos_3_por_hora_por_correo_aunque_cambie_la_ip(ruta, usuario_cliente):
    for i in range(3):
        respuesta = APIClient().post(
            f"{AUTH}{ruta}",
            {"email": "cliente@example.com"},
            format="json",
            REMOTE_ADDR=f"10.0.1.{i}",
        )
        assert respuesta.status_code == 200

    respuesta = APIClient().post(
        f"{AUTH}{ruta}", {"email": " Cliente@Example.com "}, format="json", REMOTE_ADDR="10.0.1.9"
    )
    assert_429(respuesta)


def test_la_ip_sale_del_gateway(usuario_cliente):
    # NUM_PROXIES = 1: cuenta el último valor de X-Forwarded-For.
    for i in range(10):
        APIClient().post(
            f"{AUTH}login/",
            {"email": f"nadie{i}@example.com", "password": "x"},
            format="json",
            HTTP_X_FORWARDED_FOR="200.1.1.1",
        )

    bloqueado = APIClient().post(
        f"{AUTH}login/",
        {"email": "x", "password": "x"},
        format="json",
        HTTP_X_FORWARDED_FOR="200.1.1.1",
    )
    otro = APIClient().post(
        f"{AUTH}login/",
        {"email": "x", "password": "x"},
        format="json",
        HTTP_X_FORWARDED_FOR="200.2.2.2",
    )
    assert bloqueado.status_code == 429
    assert otro.status_code == 401


# --- Bloqueo con django-axes -----------------------------------------------------------


def test_al_quinto_fallo_queda_bloqueado_y_la_correcta_tampoco_entra(usuario_cliente):
    for _ in range(4):
        assert login(password="Mala-2026").status_code == 401

    quinto = login(password="Mala-2026")
    sexto_con_la_correcta = login()

    assert quinto.status_code == 403 and quinto.json() == BLOQUEO
    assert sexto_con_la_correcta.status_code == 403
    assert sexto_con_la_correcta.json() == BLOQUEO
    intento = AccessAttempt.objects.get()
    assert intento.username == "cliente@example.com"
    assert intento.ip_address == "10.0.0.1"


def test_el_bloqueo_es_por_correo_e_ip(usuario_cliente):
    for _ in range(5):
        login(password="Mala-2026")

    assert login().status_code == 403
    # Desde otra IP, el dueño de la cuenta sigue entrando.
    assert login(ip="10.0.0.2").status_code == 200


def test_despues_del_enfriamiento_vuelve_a_entrar(usuario_cliente):
    with freeze_time("2026-11-19 12:00:00") as reloj:
        for _ in range(5):
            login(password="Mala-2026")
        assert login().status_code == 403
        reloj.tick(timedelta(minutes=15, seconds=1))
        assert login().status_code == 200


def test_entrar_bien_reinicia_los_intentos(usuario_cliente):
    for _ in range(4):
        login(password="Mala-2026")
    assert login().status_code == 200

    for _ in range(4):
        assert login(password="Mala-2026").status_code == 401


def test_el_bloqueo_queda_en_el_log(usuario_cliente, caplog):
    caplog.set_level(logging.INFO, logger="seguridad")

    for _ in range(5):
        login(password="Mala-2026")

    eventos = [json.loads(r.getMessage()) for r in caplog.records if r.name == "seguridad"]
    assert [e["evento"] for e in eventos] == ["login_fallido"] * 4 + ["cuenta_bloqueada"]
    assert "Mala-2026" not in caplog.text
