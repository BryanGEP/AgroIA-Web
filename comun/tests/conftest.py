"""Configuración mínima de Django para probar comun sin ningún servicio."""

import pytest
from django.conf import settings

from agroia_comun.configuracion import configurar_jwt
from agroia_comun.pruebas import generar_par_de_llaves

LLAVE_PRIVADA, LLAVE_PUBLICA = generar_par_de_llaves()


def pytest_configure():
    settings.configure(
        SECRET_KEY="clave-solo-para-pruebas-no-es-secreta",
        DEBUG=False,
        ALLOWED_HOSTS=["testserver"],
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "django.contrib.auth",
            "rest_framework",
        ],
        DATABASES={},
        ROOT_URLCONF="tests.urls_prueba",
        LANGUAGE_CODE="es-mx",
        USE_TZ=True,
        AUTH_ACTIVA=True,
        SIMPLE_JWT=configurar_jwt(LLAVE_PUBLICA),
        REST_FRAMEWORK={
            "DEFAULT_AUTHENTICATION_CLASSES": ["agroia_comun.autenticacion.AutenticacionJWT"],
            "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
            "EXCEPTION_HANDLER": "agroia_comun.errores.manejador_de_excepciones",
            "UNAUTHENTICATED_USER": None,
        },
    )


@pytest.fixture
def llave_privada() -> str:
    return LLAVE_PRIVADA
