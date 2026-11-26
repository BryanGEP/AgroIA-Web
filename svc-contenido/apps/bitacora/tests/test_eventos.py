"""Consumidor de svc-contenido: usuario_registrado llega a la bitácora una sola vez."""

import uuid

import fakeredis
import pytest
from django.core.management import call_command

from agroia_comun.eventos import Consumidor, obtener_tipo, publicar
from apps.bitacora import servicios
from apps.bitacora.eventos import GRUPO, MANEJADORES
from config import mongo

USUARIO = str(uuid.uuid4())


@pytest.fixture(autouse=True)
def indices():
    call_command("crear_indices", verbosity=0)


def bitacora() -> list[dict]:
    return list(mongo.coleccion(servicios.COLECCION).find({}, {"_id": 0}))


def consumidor(redis_de_eventos) -> Consumidor:
    c = Consumidor(GRUPO, MANEJADORES, cliente=redis_de_eventos, bloqueo_ms=10, latido=0.005)
    c.preparar()
    return c


def test_usuario_registrado_llega_a_la_bitacora(redis_de_eventos):
    sobre = publicar(
        "usuario_registrado",
        {"usuario_id": USUARIO, "rol": "cliente"},
        origen="svc-usuarios",
        cliente=redis_de_eventos,
    )

    assert consumidor(redis_de_eventos).una_vuelta() == 1

    [evento] = bitacora()
    assert evento["tipo"] == "usuario_registrado"
    assert evento["usuario_id"] == USUARIO
    assert evento["servicio"] == "svc-usuarios"
    assert evento["datos"] == {"rol": "cliente"}
    assert evento["evento_id"] == sobre.id
    assert evento["correlacion_id"] == sobre.correlacion_id


def test_el_manejador_es_idempotente_aunque_se_llame_dos_veces(redis_de_eventos):
    """Si el consumidor muere después de guardar y antes de confirmar, el evento se vuelve a
    entregar: el índice único de evento_id evita el duplicado."""
    sobre = publicar(
        "usuario_registrado",
        {"usuario_id": USUARIO, "rol": "cliente"},
        origen="svc-usuarios",
        cliente=redis_de_eventos,
    )

    assert servicios.registrar_desde_evento(sobre) is True
    assert servicios.registrar_desde_evento(sobre) is False

    assert len(bitacora()) == 1


def test_los_eventos_manuales_sin_evento_id_no_chocan_con_el_indice():
    servicios.registrar("pedido_creado", USUARIO, "svc-tienda", {"pedido_id": 1})
    servicios.registrar("pedido_creado", USUARIO, "svc-tienda", {"pedido_id": 2})

    assert len(bitacora()) == 2


def test_crear_indices_crea_el_indice_unico_de_evento_id(mongo_simulado):
    indices = mongo_simulado[servicios.COLECCION].index_information().values()

    [unico] = [i for i in indices if i["key"] == [("evento_id", 1)]]
    assert unico["unique"] and unico["sparse"]


# --- Fase 2: todos los eventos de negocio y los filtros -----------------------------------

OTRO = str(uuid.uuid4())
EJEMPLOS = {
    "correo_verificado": {"usuario_id": USUARIO, "via": "enlace"},
    "rol_cambiado": {"usuario_id": USUARIO, "rol_anterior": "cliente",
                     "rol_nuevo": "administrador", "cambiado_por": OTRO},
    "password_cambiada": {"usuario_id": USUARIO, "motivo": "cambio"},
    "sesiones_cerradas": {"usuario_id": USUARIO},
    "pedido_creado": {"pedido_id": 7, "usuario_id": USUARIO, "total": "750.00",
                      "productos": 1, "unidades": 2, "metodo_pago": "tarjeta"},
    "pedido_estado_cambiado": {"pedido_id": 7, "usuario_id": USUARIO,
                               "estado_anterior": "pendiente", "estado_nuevo": "pagado",
                               "total": "750.00", "cambiado_por": USUARIO},
}  # fmt: skip
ORIGEN = {"pedido_creado": "svc-tienda", "pedido_estado_cambiado": "svc-tienda"}


@pytest.mark.parametrize("tipo", sorted(EJEMPLOS))
def test_cada_evento_de_negocio_llega_una_vez_a_la_bitacora(redis_de_eventos, tipo):
    origen = ORIGEN.get(tipo, "svc-usuarios")
    sobre = publicar(tipo, EJEMPLOS[tipo], origen=origen, cliente=redis_de_eventos)
    c = consumidor(redis_de_eventos)

    c.una_vuelta()
    # Llega repetido (por ejemplo, un reproceso): no se duplica.
    redis_de_eventos.xadd(obtener_tipo(tipo).stream, {"sobre": sobre.a_json()})
    redis_de_eventos.delete(c.clave_procesado(sobre.id))
    c.una_vuelta()

    [evento] = bitacora()
    assert evento["tipo"] == tipo
    assert evento["servicio"] == origen
    assert evento["usuario_id"] == USUARIO
    assert evento["evento_id"] == sobre.id
    assert evento["correlacion_id"] == sobre.correlacion_id
    datos_sin_usuario = {k: v for k, v in EJEMPLOS[tipo].items() if k != "usuario_id"}
    assert evento["datos"] == datos_sin_usuario


def test_correo_solicitado_no_va_a_la_bitacora():
    assert "correo_solicitado" not in MANEJADORES


BITACORA = "/api/v1/bitacora/"


def sembrar():
    correlacion = str(uuid.uuid4())
    for tipo, usuario, corr in [
        ("pedido_creado", USUARIO, correlacion),
        ("pedido_estado_cambiado", USUARIO, correlacion),
        ("pedido_creado", OTRO, str(uuid.uuid4())),
    ]:
        datos = {**EJEMPLOS[tipo], "usuario_id": usuario}
        sobre = publicar(tipo, datos, origen="svc-tienda", correlacion_id=corr,
                         cliente=fakeredis.FakeRedis(decode_responses=True))  # fmt: skip
        servicios.registrar_desde_evento(sobre)
    return correlacion


def test_filtrar_por_usuario(admin):
    sembrar()

    respuesta = admin.get(BITACORA, {"usuario_id": USUARIO})

    assert respuesta.status_code == 200
    assert {e["usuario_id"] for e in respuesta.json()["results"]} == {USUARIO}
    assert respuesta.json()["count"] == 2


def test_filtrar_por_correlacion_sigue_un_flujo(admin):
    correlacion = sembrar()

    respuesta = admin.get(BITACORA, {"correlacion_id": correlacion})

    tipos = sorted(e["tipo"] for e in respuesta.json()["results"])
    assert tipos == ["pedido_creado", "pedido_estado_cambiado"]


def test_filtrar_por_tipo_y_usuario(admin):
    sembrar()

    respuesta = admin.get(BITACORA, {"tipo": "pedido_creado", "usuario_id": OTRO})

    assert respuesta.json()["count"] == 1


@pytest.mark.parametrize("filtro", ["usuario_id", "correlacion_id"])
def test_un_filtro_que_no_es_uuid_responde_400(admin, filtro):
    respuesta = admin.get(BITACORA, {filtro: "no-es-uuid"})

    assert respuesta.status_code == 400
    assert respuesta.json()["error"] == "validacion"
    assert filtro in respuesta.json()["campos"]


def test_los_filtros_nuevos_tambien_son_solo_para_administradores(cliente):
    assert cliente.get(BITACORA, {"usuario_id": USUARIO}).status_code == 403
