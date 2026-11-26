import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.usuarios.models import Direccion, Usuario
from apps.usuarios.tests.factories import DireccionFactory, UsuarioFactory

pytestmark = pytest.mark.django_db


def test_create_user_normaliza_el_correo_y_aplica_hash():
    usuario = Usuario.objects.create_user(
        "  Maria.Lopez@Example.COM ", "Aguacate-Hass-2026", nombre="María"
    )

    assert usuario.email == "maria.lopez@example.com"
    assert usuario.password != "Aguacate-Hass-2026"
    assert usuario.check_password("Aguacate-Hass-2026")


def test_valores_iniciales_del_usuario():
    usuario = Usuario.objects.create_user("juan@example.com", "Aguacate-Hass-2026", nombre="Juan")

    assert usuario.rol == Usuario.Rol.CLIENTE
    assert usuario.email_verificado is False
    assert usuario.token_version == 0
    assert usuario.tiene_2fa is False
    assert usuario.is_active is True
    assert usuario.is_staff is False
    assert usuario.acepto_privacidad_en is None


def test_create_superuser_es_administrador():
    admin = Usuario.objects.create_superuser(
        "admin@example.com", "Aguacate-Hass-2026", nombre="Admin"
    )

    assert admin.rol == Usuario.Rol.ADMINISTRADOR
    assert admin.is_staff and admin.is_superuser
    assert admin.email_verificado is True


def test_superusuario_sin_is_staff_falla():
    with pytest.raises(ValueError):
        Usuario.objects.create_superuser("x@example.com", "Aguacate-Hass-2026", is_staff=False)


def test_correo_obligatorio():
    with pytest.raises(ValueError):
        Usuario.objects.create_user("", "Aguacate-Hass-2026")


def test_no_hay_username():
    assert Usuario.USERNAME_FIELD == "email"
    assert not hasattr(Usuario(), "username") or Usuario().username is None
    assert "username" not in [campo.name for campo in Usuario._meta.fields]


def test_correo_unico():
    UsuarioFactory(email="repetido@example.com")

    with pytest.raises(IntegrityError), transaction.atomic():
        UsuarioFactory(email="repetido@example.com")


def test_telefono_invalido():
    usuario = UsuarioFactory.build(telefono="123")

    with pytest.raises(ValidationError) as error:
        usuario.full_clean(exclude=["password"])
    assert "telefono" in error.value.message_dict


def test_nombre_completo():
    usuario = UsuarioFactory.build(nombre="María", apellidos="López")

    assert usuario.get_full_name() == "María López"
    assert str(UsuarioFactory(email="maria@example.com")) == "maria@example.com"


def test_solo_una_direccion_predeterminada_por_usuario():
    usuario = UsuarioFactory()
    DireccionFactory(usuario=usuario, predeterminada=True)

    with pytest.raises(IntegrityError), transaction.atomic():
        DireccionFactory(usuario=usuario, predeterminada=True)


def test_usuarios_distintos_pueden_tener_su_predeterminada():
    DireccionFactory(predeterminada=True)
    DireccionFactory(predeterminada=True)

    assert Direccion.objects.filter(predeterminada=True).count() == 2


def test_codigo_postal_invalido():
    direccion = DireccionFactory.build(usuario=UsuarioFactory(), codigo_postal="5951")

    with pytest.raises(ValidationError) as error:
        direccion.full_clean()
    assert "codigo_postal" in error.value.message_dict


def test_borrar_usuario_borra_sus_direcciones():
    direccion = DireccionFactory()

    direccion.usuario.delete()

    assert not Direccion.objects.exists()
