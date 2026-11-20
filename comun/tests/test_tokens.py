"""validar_access(): la validación del proxy del gateway, sin DRF."""

import pytest

from agroia_comun.pruebas import USUARIO_ID_PRUEBA, firmar_token, generar_par_de_llaves
from agroia_comun.tokens import TokenInvalido, validar_access
from tests.conftest import LLAVE_PUBLICA

EMISOR = "agroia-usuarios"


def test_token_valido_devuelve_los_claims(llave_privada):
    claims = validar_access(firmar_token(llave_privada, rol="administrador"), LLAVE_PUBLICA, EMISOR)

    assert claims["user_id"] == str(USUARIO_ID_PRUEBA)
    assert claims["rol"] == "administrador"


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(lambda llave: firmar_token(generar_par_de_llaves()[0]), id="otra-llave"),
        pytest.param(lambda llave: firmar_token(llave, minutos=-1), id="vencido"),
        pytest.param(lambda llave: firmar_token(llave, emisor="otro"), id="otro-emisor"),
        pytest.param(lambda llave: firmar_token(llave, token_type="refresh"), id="refresh"),
        pytest.param(lambda llave: firmar_token(llave, user_id=10), id="user-id-entero"),
        pytest.param(lambda llave: firmar_token(llave, user_id="diez"), id="user-id-texto"),
        pytest.param(lambda llave: "no-es-un-jwt", id="basura"),
        pytest.param(lambda llave: "", id="vacio"),
    ],
)
def test_token_invalido(llave_privada, token):
    with pytest.raises(TokenInvalido):
        validar_access(token(llave_privada), LLAVE_PUBLICA, EMISOR)


def test_sin_llave_publica_nunca_es_valido(llave_privada):
    with pytest.raises(TokenInvalido):
        validar_access(firmar_token(llave_privada), "", EMISOR)
