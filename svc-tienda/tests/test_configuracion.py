"""El servicio no arranca con una configuración insegura (revisión de seguridad, Entrega 3)."""

from django.conf import settings

from agroia_comun.configuracion import SECRET_KEY_DE_EJEMPLO
from agroia_comun.pruebas import cargar_configuracion

CLAVE_FUERTE = "x7Kp2-Qm9vL4_tR8sW1zN6bY3cF5hJ0dG-aE7uI2oP9lK4mB8nV1"


def test_sin_debug_no_arranca_con_la_clave_de_env_example():
    resultado = cargar_configuracion(
        settings.BASE_DIR, DJANGO_DEBUG="False", DJANGO_SECRET_KEY=SECRET_KEY_DE_EJEMPLO
    )

    assert resultado.returncode != 0
    assert "ImproperlyConfigured" in resultado.stderr
    assert "es la de .env.example" in resultado.stderr


def test_sin_debug_arranca_con_una_clave_fuerte():
    resultado = cargar_configuracion(
        settings.BASE_DIR, DJANGO_DEBUG="False", DJANGO_SECRET_KEY=CLAVE_FUERTE
    )

    assert resultado.returncode == 0, resultado.stderr


def test_con_debug_se_permite_la_clave_de_ejemplo():
    resultado = cargar_configuracion(
        settings.BASE_DIR, DJANGO_DEBUG="True", DJANGO_SECRET_KEY=SECRET_KEY_DE_EJEMPLO
    )

    assert resultado.returncode == 0, resultado.stderr
