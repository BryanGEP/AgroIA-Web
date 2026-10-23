"""Fixtures compartidas: MongoDB simulado y clientes de API con tokens de cada usuario."""

import mongomock
import pytest
from django.conf import settings
from rest_framework.test import APIClient

from agroia_comun.pruebas import firmar_token
from config import mongo
from tests.datos import ADMIN_ID, CLIENTE_ID, OTRO_CLIENTE_ID


@pytest.fixture(autouse=True)
def mongo_simulado(monkeypatch):
    """Cada prueba usa una base mongomock nueva y vacía."""
    cliente = mongomock.MongoClient(settings.MONGO_URL, tz_aware=True)
    monkeypatch.setattr(mongo, "obtener_cliente", lambda: cliente)
    return cliente.get_default_database()


def token(usuario_id: int, rol: str | None = "cliente", **extra) -> str:
    return firmar_token(settings.LLAVE_PRIVADA_PRUEBAS, usuario_id=usuario_id, rol=rol, **extra)


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
def admin() -> APIClient:
    return api_con(token(ADMIN_ID, rol="administrador"))


@pytest.fixture
def sin_rol() -> APIClient:
    return api_con(token(CLIENTE_ID, rol=None))
