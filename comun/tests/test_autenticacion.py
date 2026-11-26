"""Validación del JWT RS256 con la llave pública, sin consultar svc-usuarios."""

import pytest
from django.core.exceptions import ImproperlyConfigured
from rest_framework.test import APIClient

from agroia_comun.configuracion import (
    SECRET_KEY_DE_EJEMPLO,
    configurar_jwt,
    leer_llave_publica,
    validar_backend_de_correo,
    validar_modo_auth,
    validar_secret_key,
)
from agroia_comun.pruebas import firmar_token, generar_par_de_llaves

USUARIO = "7c4e2a9b-5d1f-4e3a-b8c6-0d9e8f7a6b54"


def con_token(token: str) -> APIClient:
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return cliente


def test_token_valido_se_acepta(llave_privada):
    respuesta = con_token(firmar_token(llave_privada, usuario_id=USUARIO)).get("/protegida/")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"usuario_id": USUARIO}


@pytest.mark.parametrize("user_id", [10, "diez", ""], ids=["entero", "texto", "vacio"])
def test_user_id_que_no_es_uuid_se_rechaza(llave_privada, user_id):
    # Los tokens de antes de la Entrega 3 traían un id entero.
    respuesta = con_token(firmar_token(llave_privada, user_id=user_id)).get("/protegida/")

    assert respuesta.status_code == 401
    assert respuesta.json()["error"] == "token_invalido"


def test_token_sin_user_id_se_rechaza(llave_privada):
    import jwt

    claims = jwt.decode(
        firmar_token(llave_privada), options={"verify_signature": False}, algorithms=["RS256"]
    )
    del claims["user_id"]
    token = jwt.encode(claims, llave_privada, algorithm="RS256")

    assert con_token(token).get("/protegida/").status_code == 401


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
    token = firmar_token(llave_privada, emisor="otro-emisor")

    assert con_token(token).get("/protegida/").status_code == 401


def test_el_emisor_se_configura():
    # Se lee de JWT_ISSUER al arrancar; simplejwt no lo recarga en caliente.
    assert configurar_jwt("llave")["ISSUER"] == "agroia-usuarios"
    assert configurar_jwt("llave", issuer="svc-usuarios")["ISSUER"] == "svc-usuarios"


def test_emisor_vacio_no_arranca():
    with pytest.raises(ImproperlyConfigured):
        configurar_jwt("llave", issuer="")


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


CLAVE_FUERTE = "x7Kp2-Qm9vL4_tR8sW1zN6bY3cF5hJ0dG-aE7uI2oP9lK4mB8nV1"


@pytest.mark.parametrize(
    "clave",
    [
        SECRET_KEY_DE_EJEMPLO,
        "corta-pero-con-varios-caracteres",
        "a" * 60,
        "django-insecure-" + "k" * 50,
    ],
    ids=["la-de-env-example", "corta", "pocos-caracteres-distintos", "django-insecure"],
)
def test_secret_key_insegura_no_arranca_sin_debug(clave):
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        validar_secret_key(clave, debug=False)


def test_secret_key_fuerte_arranca_y_con_debug_no_se_revisa():
    validar_secret_key(CLAVE_FUERTE, debug=False)
    validar_secret_key(SECRET_KEY_DE_EJEMPLO, debug=True)


@pytest.mark.parametrize("backend", ["console", "locmem", "dummy", "filebased"])
def test_correo_que_no_se_envia_no_arranca_sin_debug(backend):
    with pytest.raises(ImproperlyConfigured, match="EMAIL_BACKEND"):
        validar_backend_de_correo(f"django.core.mail.backends.{backend}.EmailBackend", debug=False)


def test_correo_smtp_arranca_y_consola_con_debug_tambien():
    validar_backend_de_correo("django.core.mail.backends.smtp.EmailBackend", debug=False)
    validar_backend_de_correo("django.core.mail.backends.console.EmailBackend", debug=True)
