"""Validación del JWT RS256 con la llave pública, sin consultar svc-usuarios."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from rest_framework.test import APIClient

from agroia_comun.configuracion import leer_llave_publica, validar_modo_auth
from agroia_comun.pruebas import firmar_token, generar_par_de_llaves


def con_token(token: str) -> APIClient:
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return cliente


def test_token_valido_se_acepta(llave_privada):
    respuesta = con_token(firmar_token(llave_privada, usuario_id=7)).get("/protegida/")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"usuario_id": 7}


def test_sin_token_responde_401():
    respuesta = APIClient().get("/protegida/")

    assert respuesta.status_code == 401
    assert respuesta.json()["error"] == "no_autenticado"
    assert respuesta.headers["WWW-Authenticate"].startswith("Bearer")


def test_token_firmado_con_otra_llave_se_rechaza():
    otra_privada, _ = generar_par_de_llaves()

    respuesta = con_token(firmar_token(otra_privada)).get("/protegida/")

    assert respuesta.status_code == 401
    assert respuesta.json()["error"] == "token_invalido"


def test_token_vencido_se_rechaza(llave_privada):
    respuesta = con_token(firmar_token(llave_privada, minutos=-1)).get("/protegida/")

    assert respuesta.status_code == 401
    assert respuesta.json()["error"] == "token_invalido"


def test_token_de_otro_emisor_se_rechaza(llave_privada):
    token = firmar_token(llave_privada, iss="otro-emisor")

    assert con_token(token).get("/protegida/").status_code == 401


def test_token_de_renovacion_no_sirve_como_acceso(llave_privada):
    token = firmar_token(llave_privada, token_type="refresh")

    assert con_token(token).get("/protegida/").status_code == 401


def test_token_sin_rol_se_rechaza_donde_se_pide_rol(llave_privada):
    token = firmar_token(llave_privada, rol=None)

    assert con_token(token).get("/protegida/").status_code == 200
    respuesta = con_token(token).get("/cliente/")
    assert respuesta.status_code == 403
    assert respuesta.json()["error"] == "sin_permiso"


def test_el_detalle_del_token_invalido_no_expone_datos_internos():
    respuesta = con_token("no-es-un-jwt").get("/protegida/")

    cuerpo = respuesta.json()
    assert set(cuerpo) == {"error", "detalle"}
    assert isinstance(cuerpo["detalle"], str)


def test_sin_llave_con_auth_activa_no_arranca(tmp_path):
    with pytest.raises(ImproperlyConfigured):
        leer_llave_publica(str(tmp_path / "no-existe.pem"), auth_activa=True)


def test_sin_llave_con_auth_apagada_arranca(tmp_path):
    assert leer_llave_publica(str(tmp_path / "no-existe.pem"), auth_activa=False) == ""


def test_lee_la_llave_del_archivo(tmp_path):
    _, publica = generar_par_de_llaves()
    ruta = tmp_path / "publica.pem"
    ruta.write_text(publica)

    assert leer_llave_publica(str(ruta), auth_activa=True) == publica


def test_auth_apagada_sin_debug_no_arranca():
    with pytest.raises(ImproperlyConfigured):
        validar_modo_auth(auth_activa=False, debug=False)


@pytest.mark.parametrize(("auth_activa", "debug"), [(True, False), (True, True), (False, True)])
def test_combinaciones_permitidas_de_auth_y_debug(auth_activa, debug):
    validar_modo_auth(auth_activa=auth_activa, debug=debug)
