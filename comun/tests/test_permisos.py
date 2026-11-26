"""Permisos por rol leídos del token."""

from django.test import override_settings
from rest_framework.test import APIClient

from agroia_comun.pruebas import firmar_token

DUENO = "5d2a6f0e-1c3b-4a7e-8f90-1a2b3c4d5e01"
OTRO = "6e3b7a1f-2d4c-4b8f-9a01-2b3c4d5e6f02"
ADMIN = "1a9c5e7b-3f2d-4c6a-8b10-3c4d5e6f7a03"


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
    assert respuesta.json() == {
        "error": "email_no_verificado",
        "detalle": "Verifica tu correo para poder hacer esta acción.",
    }
    assert con_token(admin).get("/cliente/").status_code == 403


def test_dueno_o_admin(llave_privada):
    dueno = firmar_token(llave_privada, usuario_id=DUENO, rol="cliente")
    otro = firmar_token(llave_privada, usuario_id=OTRO, rol="cliente")
    admin = firmar_token(llave_privada, usuario_id=ADMIN, rol="administrador")
    sin_rol = firmar_token(llave_privada, usuario_id=DUENO, rol=None)
    ruta = f"/dueno/{DUENO}/"

    assert con_token(dueno).get(ruta).status_code == 200
    respuesta = con_token(otro).get(ruta)
    assert respuesta.status_code == 403
    assert respuesta.json()["error"] == "sin_permiso"
    assert con_token(admin).get(ruta).status_code == 200
    assert con_token(sin_rol).get(ruta).status_code == 403


def test_rol_desconocido_no_tiene_permisos(llave_privada):
    token = firmar_token(llave_privada, rol="superusuario")

    assert con_token(token).get("/admin/").status_code == 403
    assert con_token(token).get(f"/dueno/{ADMIN}/").status_code == 403


@override_settings(AUTH_ACTIVA=False)
def test_auth_apagada_no_revisa_roles(llave_privada):
    cliente = firmar_token(llave_privada, rol="cliente", email_verificado=False)

    assert APIClient().get("/admin/").status_code == 200
    assert con_token(cliente).get("/cliente/").status_code == 200


@override_settings(AUTH_ACTIVA=False)
def test_auth_apagada_sigue_pidiendo_usuario_donde_se_necesita(llave_privada):
    assert APIClient().get("/protegida/").status_code == 401
    assert APIClient().get("/cliente/").status_code == 401
    otra = firmar_token(llave_privada, usuario_id=OTRO)
    assert con_token(otra).get("/protegida/").json() == {"usuario_id": OTRO}
