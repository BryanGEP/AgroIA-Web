"""Fixtures compartidas: usuarios en la base y clientes de API con su token.

El `user_id` del token es el `id` del Usuario, así que cada fixture crea al usuario con
un id fijo y firma el token para ese id.
"""

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.usuarios.tests.factories import UsuarioFactory
from tests.datos import ADMIN_ID, CLIENTE_ID, OTRO_CLIENTE_ID
from tests.tokens import api_con, token


def con_id_fijo(**campos):
    """Crea un usuario con id fijo y adelanta la secuencia de ids de PostgreSQL, para que
    los usuarios que cree el registro después no choquen con él."""
    usuario = UsuarioFactory(**campos)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT setval(pg_get_serial_sequence('usuarios_usuario', 'id'), "
            "(SELECT MAX(id) FROM usuarios_usuario))"
        )
    return usuario


@pytest.fixture
def usuario_cliente(db):
    return con_id_fijo(id=CLIENTE_ID, email="cliente@example.com", nombre="Juan")


@pytest.fixture
def usuario_otro(db):
    return con_id_fijo(id=OTRO_CLIENTE_ID, email="otro@example.com", nombre="Ana")


@pytest.fixture
def usuario_admin(db):
    return con_id_fijo(id=ADMIN_ID, email="admin@example.com", nombre="Admin", rol="administrador")


@pytest.fixture
def anonimo() -> APIClient:
    return APIClient()


@pytest.fixture
def cliente(usuario_cliente) -> APIClient:
    return api_con(token(CLIENTE_ID))


@pytest.fixture
def otro_cliente(usuario_otro) -> APIClient:
    return api_con(token(OTRO_CLIENTE_ID))


@pytest.fixture
def admin(usuario_admin) -> APIClient:
    return api_con(token(ADMIN_ID, rol="administrador"))


@pytest.fixture
def sin_rol(usuario_cliente) -> APIClient:
    return api_con(token(CLIENTE_ID, rol=None))
