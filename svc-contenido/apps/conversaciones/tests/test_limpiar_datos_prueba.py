"""Comando limpiar_datos_prueba: borra lo que dejan Postman y la matriz de accesos."""

import uuid
from io import StringIO

import pytest
from django.core.files.storage import default_storage
from django.core.management import CommandError, call_command

from apps.bitacora import servicios as bitacora
from apps.conversaciones import servicios as conversaciones
from apps.diagnosticos import servicios as diagnosticos
from config import mongo
from tests.datos import imagen

DEMO = uuid.uuid4()
PRUEBA = uuid.uuid4()  # registrado por Postman
OTRO = uuid.uuid4()  # alguien que no es de prueba
PROBABILIDADES = {"sano": 0.9, "rona": 0.05, "antracnosis": 0.05}


def limpiar(*usuarios) -> str:
    salida = StringIO()
    call_command("limpiar_datos_prueba", "--usuarios", ",".join(map(str, usuarios)), stdout=salida)
    return salida.getvalue()


def contar(coleccion: str, usuario) -> int:
    return mongo.coleccion(coleccion).count_documents({"usuario_id": str(usuario)})


@pytest.fixture
def datos(settings):
    settings.DEBUG = True
    fotos = {}
    for usuario in (DEMO, PRUEBA, OTRO):
        conversaciones.crear(usuario, "Roña desde el gateway")
        d = diagnosticos.crear(usuario, imagen(), "sano", 0.9, PROBABILIDADES, "prueba")
        fotos[usuario] = d["imagen"]
        bitacora.registrar("pedido_creado", usuario, "svc-tienda", {"pedido_id": 7})
    bitacora.registrar("pedido_creado", uuid.UUID(int=10), "svc-tienda", {"pedido_id": 7})
    return fotos


def test_borra_lo_de_las_cuentas_de_prueba_y_conserva_lo_demas(datos):
    salida = limpiar(DEMO, PRUEBA)

    assert "Conversaciones: 2. Diagnósticos: 2 (2 fotos). Eventos de bitácora: 3" in salida
    for coleccion in (conversaciones.COLECCION, diagnosticos.COLECCION, bitacora.COLECCION):
        assert contar(coleccion, DEMO) == contar(coleccion, PRUEBA) == 0
        assert contar(coleccion, OTRO) == 1
    assert not default_storage.exists(datos[DEMO])
    assert not default_storage.exists(datos[PRUEBA])
    assert default_storage.exists(datos[OTRO])


def test_se_puede_correr_varias_veces(datos):
    limpiar(DEMO, PRUEBA)

    salida = limpiar(DEMO, PRUEBA)

    assert "Conversaciones: 0. Diagnósticos: 0 (0 fotos). Eventos de bitácora: 0" in salida


def test_sin_usuarios_solo_borra_los_eventos_de_ejemplo_de_postman(datos):
    salida = limpiar()

    assert "Eventos de bitácora: 1" in salida
    assert "Sin --usuarios" in salida
    assert contar(conversaciones.COLECCION, DEMO) == 1


def test_usuarios_invalidos_falla_con_mensaje_claro(settings):
    settings.DEBUG = True
    with pytest.raises(CommandError, match="lista de UUID"):
        limpiar("10")


def test_se_niega_sin_debug(datos, settings):
    settings.DEBUG = False

    with pytest.raises(CommandError, match="DJANGO_DEBUG=True"):
        limpiar(DEMO)
    assert contar(conversaciones.COLECCION, DEMO) == 1
    assert default_storage.exists(datos[DEMO])
