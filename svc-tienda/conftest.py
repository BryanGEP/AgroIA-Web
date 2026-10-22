"""Fixtures compartidas: clientes de API con tokens de cada tipo de usuario."""

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from agroia_comun.pruebas import firmar_token
from tests.datos import ADMIN_ID, CLIENTE_ID, DIRECCION, OTRO_CLIENTE_ID, SIN_VERIFICAR_ID


def token(usuario_id: int, rol: str | None = "cliente", verificado: bool = True, **extra) -> str:
    return firmar_token(
        settings.LLAVE_PRIVADA_PRUEBAS,
        usuario_id=usuario_id,
        rol=rol,
        email_verificado=verificado,
        **extra,
    )


def api_con(token_jwt: str) -> APIClient:
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {token_jwt}")
    return cliente


@pytest.fixture
def anonimo() -> APIClient:
    return APIClient()


@pytest.fixture
def cliente() -> APIClient:
    return api_con(token(CLIENTE_ID))


@pytest.fixture
def otro_cliente() -> APIClient:
    return api_con(token(OTRO_CLIENTE_ID))


@pytest.fixture
def sin_verificar() -> APIClient:
    return api_con(token(SIN_VERIFICAR_ID, verificado=False))


@pytest.fixture
def admin() -> APIClient:
    return api_con(token(ADMIN_ID, rol="administrador"))


@pytest.fixture
def sin_rol() -> APIClient:
    return api_con(token(CLIENTE_ID, rol=None))


@pytest.fixture
def direccion() -> dict:
    return dict(DIRECCION)
