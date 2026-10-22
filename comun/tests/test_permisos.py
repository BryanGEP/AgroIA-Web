"""Permisos por rol leídos del token."""

from django.test import override_settings
from rest_framework.test import APIClient

from agroia_comun.pruebas import firmar_token


def con_token(token: str) -> APIClient:
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return cliente


def test_es_administrador(llave_privada):
    assert (
        con_token(firmar_token(llave_privada, rol="administrador")).get("/admin/").status_code
        == 200
    )
    assert con_token(firmar_token(llave_privada, rol="cliente")).get("/admin/").status_code == 403
    assert APIClient().get("/admin/").status_code == 401


def test_cliente_con_correo_verificado(llave_privada):
    verificado = firmar_token(llave_privada, rol="cliente", email_verificado=True)
    sin_verificar = firmar_token(llave_privada, rol="cliente", email_verificado=False)
    admin = firmar_token(llave_privada, rol="administrador")

    assert con_token(verificado).get("/cliente/").status_code == 200
    respuesta = con_token(sin_verificar).get("/cliente/")
    assert respuesta.status_code == 403
    assert "verific" in respuesta.json()["detalle"].lower()
    assert con_token(admin).get("/cliente/").status_code == 403


def test_dueno_o_admin(llave_privada):
    dueno = firmar_token(llave_privada, usuario_id=5, rol="cliente")
    otro = firmar_token(llave_privada, usuario_id=6, rol="cliente")
    admin = firmar_token(llave_privada, usuario_id=1, rol="administrador")
    sin_rol = firmar_token(llave_privada, usuario_id=5, rol=None)

    assert con_token(dueno).get("/dueno/5/").status_code == 200
    assert con_token(otro).get("/dueno/5/").status_code == 403
    assert con_token(admin).get("/dueno/5/").status_code == 200
    assert con_token(sin_rol).get("/dueno/5/").status_code == 403


def test_rol_desconocido_no_tiene_permisos(llave_privada):
    token = firmar_token(llave_privada, rol="superusuario")

    assert con_token(token).get("/admin/").status_code == 403
    assert con_token(token).get("/dueno/1/").status_code == 403


@override_settings(AUTH_ACTIVA=False)
def test_auth_apagada_no_revisa_roles(llave_privada):
    cliente = firmar_token(llave_privada, rol="cliente", email_verificado=False)

    assert APIClient().get("/admin/").status_code == 200
    assert con_token(cliente).get("/cliente/").status_code == 200


@override_settings(AUTH_ACTIVA=False)
def test_auth_apagada_sigue_pidiendo_usuario_donde_se_necesita(llave_privada):
    assert APIClient().get("/protegida/").status_code == 401
    assert APIClient().get("/cliente/").status_code == 401
    otra = firmar_token(llave_privada, usuario_id=3)
    assert con_token(otra).get("/protegida/").json() == {"usuario_id": 3}
