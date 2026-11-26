"""Comando asignar_admin: promueve a administrador a un usuario existente."""

import pytest
from django.core.management import CommandError, call_command

from apps.usuarios.tests.factories import UsuarioFactory

pytestmark = pytest.mark.django_db


def test_promueve_a_un_usuario_existente():
    usuario = UsuarioFactory(email="lucia@example.com")

    call_command("asignar_admin", "  LUCIA@example.com ", verbosity=0)

    usuario.refresh_from_db()
    assert usuario.rol == "administrador"


def test_correo_inexistente_falla_con_mensaje_claro():
    with pytest.raises(CommandError, match="No existe ningún usuario"):
        call_command("asignar_admin", "nadie@example.com")


def test_ya_administrador_no_falla():
    usuario = UsuarioFactory(rol="administrador")

    call_command("asignar_admin", usuario.email, verbosity=0)

    usuario.refresh_from_db()
    assert usuario.rol == "administrador"
