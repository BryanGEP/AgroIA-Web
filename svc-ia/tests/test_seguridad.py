"""Validación del JWT con PyJWT: mismas reglas que agroia_comun en los servicios Django."""

import json
import logging

import pytest

from app import config, seguridad
from tests.tokens import encabezado, firmar_token, generar_par_de_llaves

URL = "/solicitudes/no-existe/"  # cualquier endpoint protegido sirve


def test_token_valido_pasa_la_autenticacion(cliente_http, como_cliente):
    # 404 porque la solicitud no existe: la autenticación sí pasó.
    assert cliente_http.get(URL, headers=como_cliente).status_code == 404


def test_sin_token_401(cliente_http):
    respuesta = cliente_http.get(URL)

    assert respuesta.status_code == 401
    assert respuesta.json()["error"] == "no_autenticado"
    assert respuesta.headers["WWW-Authenticate"].startswith("Bearer")


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(lambda: firmar_token(llave=generar_par_de_llaves()[0]), id="otra-llave"),
        pytest.param(lambda: firmar_token(minutos=-1), id="vencido"),
        pytest.param(lambda: firmar_token(iss="otro-emisor"), id="otro-emisor"),
        pytest.param(lambda: firmar_token(token_type="refresh"), id="de-renovacion"),
        pytest.param(lambda: firmar_token(user_id="diez"), id="user-id-no-uuid"),
        # Los tokens de antes de la Entrega 3 traían un id entero.
        pytest.param(lambda: firmar_token(user_id=10), id="user-id-entero"),
        pytest.param(lambda: "no-es-un-jwt", id="basura"),
    ],
)
def test_token_invalido_401(cliente_http, token):
    respuesta = cliente_http.get(URL, headers=encabezado(token()))

    assert respuesta.status_code == 401
    assert respuesta.json() == {
        "error": "token_invalido",
        "detalle": "El token no es válido o ya venció.",
    }


def test_token_sin_rol_403(cliente_http, sin_rol):
    respuesta = cliente_http.get(URL, headers=sin_rol)

    assert respuesta.status_code == 403
    assert respuesta.json()["error"] == "sin_permiso"


def test_auth_apagada_no_revisa_el_rol_pero_pide_token(cliente_http, sin_rol, monkeypatch):
    monkeypatch.setattr(config.settings, "auth_activa", False)

    assert cliente_http.get(URL, headers=sin_rol).status_code == 404
    assert cliente_http.get(URL).status_code == 401


def test_auth_apagada_sin_debug_no_arranca():
    with pytest.raises(RuntimeError, match="DEBUG"):
        config.validar(config.Settings(auth_activa=False, debug=False))


@pytest.mark.parametrize(("auth_activa", "debug"), [(True, False), (True, True), (False, True)])
def test_combinaciones_permitidas(auth_activa, debug):
    config.validar(config.Settings(auth_activa=auth_activa, debug=debug))


def test_sin_llave_con_auth_activa_no_arranca(monkeypatch, tmp_path):
    monkeypatch.setattr(config.settings, "jwt_public_key_path", str(tmp_path / "no.pem"))
    seguridad.llave_publica.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="llave pública"):
            seguridad.llave_publica()
    finally:
        monkeypatch.undo()
        seguridad.llave_publica.cache_clear()


def test_el_emisor_se_configura(cliente_http, monkeypatch):
    monkeypatch.setattr(config.settings, "jwt_issuer", "svc-usuarios")

    assert (
        cliente_http.get(URL, headers=encabezado(firmar_token(iss="svc-usuarios"))).status_code
        == 404
    )
    assert cliente_http.get(URL, headers=encabezado(firmar_token())).status_code == 401


def test_emisor_vacio_no_arranca():
    with pytest.raises(RuntimeError, match="JWT_ISSUER"):
        config.validar(config.Settings(jwt_issuer=" "))


@pytest.fixture
def log(caplog, monkeypatch):
    # El logger `seguridad` no propaga (escribe su propia línea); caplog escucha en la raíz.
    monkeypatch.setattr(logging.getLogger("seguridad"), "propagate", True)
    caplog.set_level(logging.INFO, logger="seguridad")
    return caplog


def eventos(caplog) -> list[dict]:
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "seguridad"]


def test_401_y_403_se_registran_sin_el_token(cliente_http, sin_rol, log):
    token = "no-es-un-jwt"
    cliente_http.get(URL)
    cliente_http.get(URL, headers=encabezado(token))
    cliente_http.get(URL, headers=sin_rol)

    registrados = eventos(log)
    assert [(e["estado"], e["error"]) for e in registrados] == [
        (401, "no_autenticado"),
        (401, "token_invalido"),
        (403, "sin_permiso"),
    ]
    assert all(e["evento"] == "acceso_denegado" and e["servicio"] == "svc-ia" for e in registrados)
    assert registrados[0]["ruta"] == URL
    assert registrados[2]["usuario_id"] == "c1e2a3b4-0000-4000-8000-000000000010"
    assert token not in log.text
    assert sin_rol["Authorization"].split()[1] not in log.text


def test_la_ip_sale_del_gateway(cliente_http, log):
    cliente_http.get(URL, headers={"X-Forwarded-For": "1.2.3.4, 200.10.20.30"})

    assert eventos(log)[0]["ip"] == "200.10.20.30"
