"""Comandos para correr las pruebas de seguridad: limpiar_datos_prueba y reiniciar_limites."""

from io import StringIO

import pytest
from axes.models import AccessAttempt
from django.core.cache import cache
from django.core.management import CommandError, call_command
from rest_framework.test import APIClient

from apps.usuarios.management.commands.reiniciar_limites import borrar_contadores
from apps.usuarios.models import CambioRol, Usuario
from apps.usuarios.tests.factories import PASSWORD_DE_PRUEBA, UsuarioFactory

pytestmark = pytest.mark.django_db

DEMO = ["cliente@demo.agroia.test", "sin-verificar@demo.agroia.test", "admin@demo.agroia.test"]
DE_PRUEBA = ["maria.1795210681119@example.com", "flujo.1795108796@example.com"]
REALES = ["lucia@example.com", "ana.2026@example.com", "maria.1795210681119@ejemplo.mx"]


def correr(comando, *args) -> str:
    salida = StringIO()
    call_command(comando, *args, stdout=salida)
    return salida.getvalue()


@pytest.fixture
def con_debug(settings):
    settings.DEBUG = True


@pytest.fixture
def usuarios(con_debug):
    correr("cargar_usuarios_demo")
    prueba = [UsuarioFactory(email=e) for e in DE_PRUEBA]
    reales = [UsuarioFactory(email=e) for e in REALES]
    return prueba, reales


# --- limpiar_datos_prueba --------------------------------------------------------------


def test_borra_los_usuarios_de_prueba_y_conserva_demo_y_reales(usuarios):
    prueba, _ = usuarios
    prueba[0].direcciones.create(
        calle="Camino", numero="1", colonia="Centro", municipio="Jiquilpan",
        estado="Michoacán", codigo_postal="59510",
    )  # fmt: skip
    CambioRol.objects.create(usuario=prueba[1], rol_anterior="cliente", rol_nuevo="administrador")

    salida = correr("limpiar_datos_prueba")

    assert "Usuarios de prueba borrados: 2" in salida
    restantes = set(Usuario.objects.values_list("email", flat=True))
    assert restantes == set(DEMO + REALES)
    assert not CambioRol.objects.exists()


def test_se_puede_correr_varias_veces(usuarios):
    correr("limpiar_datos_prueba")

    assert "Usuarios de prueba borrados: 0" in correr("limpiar_datos_prueba")
    assert Usuario.objects.count() == len(DEMO + REALES)


def test_listar_ids_no_borra_y_trae_demo_y_prueba(usuarios):
    prueba, reales = usuarios

    ids = set(correr("limpiar_datos_prueba", "--listar-ids").strip().split(","))

    esperados = {str(u.pk) for u in Usuario.objects.filter(email__in=DEMO)}
    esperados |= {str(u.pk) for u in prueba}
    assert ids == esperados
    assert not ids & {str(u.pk) for u in reales}
    assert Usuario.objects.count() == len(DEMO + DE_PRUEBA + REALES)


@pytest.mark.parametrize("argumentos", [[], ["--listar-ids"]])
def test_limpiar_se_niega_sin_debug(settings, argumentos):
    settings.DEBUG = False
    UsuarioFactory(email=DE_PRUEBA[0])

    with pytest.raises(CommandError, match="DJANGO_DEBUG=True"):
        correr("limpiar_datos_prueba", *argumentos)
    assert Usuario.objects.filter(email=DE_PRUEBA[0]).exists()


# --- reiniciar_limites -----------------------------------------------------------------


def login(email, password="incorrecta", ip="10.0.0.1"):
    return APIClient().post(
        "/api/v1/auth/login/", {"email": email, "password": password}, format="json",
        REMOTE_ADDR=ip,
    )  # fmt: skip


def test_reinicia_el_limite_de_logins(con_debug):
    for i in range(10):
        login(f"nadie{i}@example.com")
    assert login("otro@example.com").status_code == 429

    salida = correr("reiniciar_limites")

    assert "Contadores de límite borrados: 0." not in salida
    assert login("otro@example.com").status_code == 401


def test_quita_el_bloqueo_de_axes(con_debug):
    usuario = UsuarioFactory(email="bloqueada@example.com")
    for _ in range(5):
        login(usuario.email)
    assert login(usuario.email, PASSWORD_DE_PRUEBA).status_code == 403
    assert AccessAttempt.objects.exists()

    salida = correr("reiniciar_limites")

    assert "Intentos de axes borrados: 1." in salida
    assert not AccessAttempt.objects.exists()
    assert login(usuario.email, PASSWORD_DE_PRUEBA).status_code == 200


def test_solo_borra_los_contadores(con_debug):
    cache.set("throttle_login_10.0.0.1", [1.0])
    cache.set("otra_cosa", "se queda")

    assert borrar_contadores() == 1
    assert cache.get("throttle_login_10.0.0.1") is None
    assert cache.get("otra_cosa") == "se queda"


def test_en_redis_busca_con_el_prefijo_de_la_cache():
    """En Docker la caché es Redis: busca las llaves con KEY_PREFIX y versión."""

    class ClienteFalso:
        def __init__(self):
            self.llaves = {b"svc-usuarios:1:throttle_login_1.2.3.4", b"svc-usuarios:1:sesion"}
            self.patron = None

        def scan_iter(self, match):
            self.patron = match
            return [llave for llave in self.llaves if b"throttle_" in llave]

        def delete(self, *llaves):
            self.llaves -= set(llaves)

    from django.core.cache.backends.redis import RedisCache

    redis = RedisCache("redis://redis:6379/0", {"KEY_PREFIX": "svc-usuarios"})
    cliente = ClienteFalso()
    redis._cache.get_client = lambda write=False: cliente

    assert borrar_contadores(redis) == 1
    assert cliente.patron == "svc-usuarios:1:throttle_*"
    assert cliente.llaves == {b"svc-usuarios:1:sesion"}


def test_reiniciar_se_niega_sin_debug(settings):
    settings.DEBUG = False
    cache.set("throttle_login_10.0.0.1", [1.0])

    with pytest.raises(CommandError, match="DJANGO_DEBUG=True"):
        correr("reiniciar_limites")
    assert cache.get("throttle_login_10.0.0.1") is not None
