"""Validación del JWT con PyJWT: mismas reglas que agroia_comun en los servicios Django."""

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
        pytest.param(lambda: firmar_token(user_id="diez"), id="user-id-no-entero"),
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
