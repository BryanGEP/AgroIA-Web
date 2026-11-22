"""Fixtures compartidas: usuarios en la base y clientes de API con su token.

El `user_id` del token es el `id` (UUID) del Usuario, así que cada fixture crea al usuario
con un id fijo y firma el token para ese id.
"""

import fakeredis
import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from agroia_comun.eventos import conexion as conexion_eventos
from apps.usuarios.tests.factories import UsuarioFactory
from tests.datos import ADMIN_ID, CLIENTE_ID, OTRO_CLIENTE_ID
from tests.tokens import api_con, token


@pytest.fixture(autouse=True)
def redis_de_eventos():
    """Los eventos usan un Redis simulado y vacío en cada prueba (sin contenedor)."""
    simulado = fakeredis.FakeRedis(decode_responses=True)
    conexion_eventos.usar(simulado)
    yield simulado
    conexion_eventos.usar(None)


@pytest.fixture
def entregar_correos(redis_de_eventos):
    """Corre el consumidor de correos (el mismo de svc-usuarios-eventos) hasta vaciar la
    cola: las acciones ya no envían el correo, publican correo_solicitado."""
    from agroia_comun.eventos import Consumidor
    from apps.usuarios.eventos import GRUPO, MANEJADORES

    consumidor = Consumidor(GRUPO, MANEJADORES, cliente=redis_de_eventos, bloqueo_ms=10)
    consumidor.preparar()

    def entregar() -> int:
        total = 0
        while atendidos := consumidor.una_vuelta():
            total += atendidos
        return total

    return entregar


@pytest.fixture(autouse=True)
def limite_de_intentos_limpio():
    """Cada prueba empieza con los contadores del límite de intentos en cero."""
    cache.clear()
    yield
    cache.clear()


def con_id_fijo(**campos):
    return UsuarioFactory(**campos)


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
