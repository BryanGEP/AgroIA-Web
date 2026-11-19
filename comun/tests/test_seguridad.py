"""Log de seguridad: una línea JSON por evento, sin contraseñas ni tokens."""

import json
import logging

import pytest
from django.test import RequestFactory
from rest_framework.test import APIClient

from agroia_comun.pruebas import firmar_token
from agroia_comun.seguridad import ip_cliente, registrar_evento

USUARIO = "3f8e1d2c-4b5a-4c6d-8e7f-9a0b1c2d3e4f"


def eventos(caplog) -> list[dict]:
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "seguridad"]


@pytest.fixture
def log(caplog):
    caplog.set_level(logging.INFO, logger="seguridad")
    return caplog


def test_evento_con_datos_de_la_peticion(log):
    request = RequestFactory().post("/api/v1/auth/login/", REMOTE_ADDR="10.0.0.7")

    registrar_evento("login_fallido", request, email="ana@example.com")

    (evento,) = eventos(log)
    assert evento["evento"] == "login_fallido"
    assert evento["ip"] == "10.0.0.7"
    assert evento["metodo"] == "POST"
    assert evento["ruta"] == "/api/v1/auth/login/"
    assert evento["email"] == "ana@example.com"
    assert "fecha" in evento


def test_nunca_registra_contrasenas_ni_tokens(log):
    registrar_evento(
        "prueba",
        password="Secreta-123",
        password_nueva="Otra-456",
        refresh="eyJ...",
        access="eyJ...",
        token="abc",
        uid="MTA",
        email="ana@example.com",
    )

    (evento,) = eventos(log)
    assert evento["email"] == "ana@example.com"
    texto = json.dumps(evento)
    for valor in ("Secreta-123", "Otra-456", "eyJ", "abc", "MTA"):
        assert valor not in texto


def test_ip_del_gateway_en_x_forwarded_for():
    # Un proxy de confianza: vale el último valor, el que agregó el gateway.
    request = RequestFactory().get(
        "/", REMOTE_ADDR="172.18.0.5", HTTP_X_FORWARDED_FOR="1.2.3.4, 200.10.20.30"
    )

    assert ip_cliente(request) == "200.10.20.30"
    assert ip_cliente(RequestFactory().get("/", REMOTE_ADDR="10.0.0.7")) == "10.0.0.7"


def test_401_se_registra_como_acceso_denegado(log):
    APIClient().get("/protegida/")

    (evento,) = eventos(log)
    assert evento["evento"] == "acceso_denegado"
    assert evento["estado"] == 401
    assert evento["error"] == "no_autenticado"
    assert evento["usuario_id"] is None


def test_403_registra_al_usuario_y_el_codigo(log, llave_privada):
    cliente = APIClient()
    token = firmar_token(llave_privada, usuario_id=USUARIO, email_verificado=False)
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    cliente.get("/cliente/")

    (evento,) = eventos(log)
    assert evento["estado"] == 403
    assert evento["error"] == "email_no_verificado"
    assert evento["usuario_id"] == USUARIO
    assert token not in log.text


def test_token_invalido_se_registra_sin_el_token(log):
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION="Bearer no-es-un-jwt")

    cliente.get("/protegida/")

    (evento,) = eventos(log)
    assert evento["error"] == "token_invalido"
    assert "no-es-un-jwt" not in log.text


def test_los_errores_de_negocio_no_se_duplican_en_el_log(log):
    APIClient().post("/errores/", {"caso": "negocio"}, format="json")

    assert eventos(log) == []
