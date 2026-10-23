"""Lógica de negocio: registro y direcciones."""

import pytest
from django.utils import timezone

from apps.usuarios import servicios
from apps.usuarios.models import Direccion, Usuario
from apps.usuarios.tests.factories import DireccionFactory, UsuarioFactory
from tests.datos import DIRECCION

pytestmark = pytest.mark.django_db


def test_registrar_usuario_guarda_el_aviso_de_privacidad():
    antes = timezone.now()

    usuario = servicios.registrar_usuario(
        email="maria@example.com", password="Aguacate-Hass-2026", nombre="María", apellidos="López"
    )

    usuario.refresh_from_db()
    assert usuario.rol == Usuario.Rol.CLIENTE
    assert usuario.email_verificado is False
    assert usuario.version_privacidad == "2026-10"
    assert usuario.acepto_privacidad_en >= antes
    assert usuario.check_password("Aguacate-Hass-2026")


def test_la_version_del_aviso_sale_de_la_configuracion(settings):
    settings.VERSION_AVISO_PRIVACIDAD = "2027-01"

    usuario = servicios.registrar_usuario(
        email="ana@example.com", password="Aguacate-Hass-2026", nombre="Ana", apellidos=""
    )

    assert usuario.version_privacidad == "2027-01"


def test_la_primera_direccion_queda_predeterminada():
    usuario = UsuarioFactory()

    primera = servicios.crear_direccion(usuario, {**DIRECCION, "predeterminada": False})
    segunda = servicios.crear_direccion(usuario, DIRECCION)

    assert primera.predeterminada is True
    assert segunda.predeterminada is False


def test_marcar_otra_como_predeterminada_desmarca_las_demas():
    usuario = UsuarioFactory()
    primera = servicios.crear_direccion(usuario, DIRECCION)
    segunda = servicios.crear_direccion(usuario, DIRECCION)

    servicios.actualizar_direccion(segunda, {"predeterminada": True})

    primera.refresh_from_db()
    segunda.refresh_from_db()
    assert (primera.predeterminada, segunda.predeterminada) == (False, True)


def test_crear_una_nueva_predeterminada_desmarca_la_anterior():
    usuario = UsuarioFactory()
    primera = servicios.crear_direccion(usuario, DIRECCION)

    nueva = servicios.crear_direccion(usuario, {**DIRECCION, "predeterminada": True})

    primera.refresh_from_db()
    assert primera.predeterminada is False
    assert nueva.predeterminada is True


def test_no_toca_las_direcciones_de_otro_usuario():
    ajena = DireccionFactory(predeterminada=True)
    usuario = UsuarioFactory()

    servicios.crear_direccion(usuario, {**DIRECCION, "predeterminada": True})

    ajena.refresh_from_db()
    assert ajena.predeterminada is True


def test_borrar_la_predeterminada_pasa_la_marca_a_la_mas_reciente():
    usuario = UsuarioFactory()
    predeterminada = servicios.crear_direccion(usuario, DIRECCION)
    servicios.crear_direccion(usuario, DIRECCION)
    reciente = servicios.crear_direccion(usuario, DIRECCION)

    servicios.borrar_direccion(predeterminada)

    reciente.refresh_from_db()
    assert reciente.predeterminada is True
    assert Direccion.objects.filter(usuario=usuario, predeterminada=True).count() == 1


def test_borrar_la_unica_direccion():
    usuario = UsuarioFactory()
    direccion = servicios.crear_direccion(usuario, DIRECCION)

    servicios.borrar_direccion(direccion)

    assert not Direccion.objects.exists()
