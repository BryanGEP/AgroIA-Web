"""Bitácora de actividad del sistema.

Documento en la colección `bitacora`:
    {_id, tipo, usuario_id, servicio, datos, fecha}
y, si vino de un evento por Redis, además {evento_id, correlacion_id}.

La llenan los eventos que publican los servicios (consumidor `consumir_eventos`, ver
docs/eventos.md) y, a mano, un administrador con POST.
"""

import uuid
from datetime import UTC, datetime

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from agroia_comun.eventos import Sobre, conexion, operacion
from config import mongo
from config.paginacion import ConsultaMongo

COLECCION = "bitacora"
INDICES = [
    [("tipo", ASCENDING), ("fecha", DESCENDING)],
    [("fecha", DESCENDING)],
    [("usuario_id", ASCENDING), ("fecha", DESCENDING)],
    [("correlacion_id", ASCENDING)],
    # Línea de tiempo de un pedido en el panel (filtro pedido_id).
    [("datos.pedido_id", ASCENDING), ("fecha", DESCENDING)],
]
# Un evento se guarda una sola vez aunque llegue dos veces (idempotencia del consumidor).
# sparse: los eventos registrados a mano con POST no llevan evento_id.
INDICES_UNICOS = [[("evento_id", ASCENDING)]]


def _coleccion():
    return mongo.coleccion(COLECCION)


def registrar(tipo: str, usuario_id: uuid.UUID | str | None, servicio: str, datos: dict) -> dict:
    evento = {
        "tipo": tipo,
        "usuario_id": str(usuario_id) if usuario_id is not None else None,
        "servicio": servicio,
        "datos": datos,
        "fecha": mongo.ahora(),
    }
    evento["_id"] = _coleccion().insert_one(evento).inserted_id
    return evento


def registrar_desde_evento(sobre: Sobre) -> bool:
    """Guarda un evento de negocio en la bitácora. Devuelve False si ya estaba (el mismo
    evento_id): se puede llamar varias veces con el mismo sobre sin duplicarlo."""
    datos = dict(sobre.datos)
    usuario_id = datos.pop("usuario_id", None)
    documento = {
        "tipo": sobre.tipo,
        "usuario_id": str(usuario_id) if usuario_id is not None else None,
        "servicio": sobre.origen,
        "datos": datos,
        "fecha": mongo.ahora(),
        "evento_id": sobre.id,
        "correlacion_id": sobre.correlacion_id,
    }
    try:
        _coleccion().insert_one(documento)
    except DuplicateKeyError:
        return False
    return True


def consulta(
    tipo: str | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    usuario_id: uuid.UUID | None = None,
    correlacion_id: uuid.UUID | None = None,
    pedido_id: int | None = None,
) -> ConsultaMongo:
    """Eventos filtrados por tipo, usuario, correlación y rango de fechas [desde, hasta),
    más recientes primero."""
    filtro: dict = {}
    if tipo:
        filtro["tipo"] = tipo
    if usuario_id:
        filtro["usuario_id"] = str(usuario_id)
    if correlacion_id:
        filtro["correlacion_id"] = str(correlacion_id)
    if pedido_id is not None:
        filtro["datos.pedido_id"] = pedido_id
    rango = {}
    if desde is not None:
        rango["$gte"] = desde
    if hasta is not None:
        rango["$lt"] = hasta
    if rango:
        filtro["fecha"] = rango
    return ConsultaMongo(_coleccion(), filtro, [("fecha", DESCENDING), ("_id", DESCENDING)])


# --- Estado de los eventos para el panel -------------------------------------------------------


def nombre_de_excepcion(motivo: str | None) -> str | None:
    """«ConnectionError: texto» → «ConnectionError». El texto puede traer datos del evento:
    en el panel solo va el nombre; el motivo completo se ve con el comando `estado`."""
    if not motivo:
        return None
    return motivo.split(":", 1)[0].strip() or None


def _fecha_de_id(id_mensaje: str) -> str | None:
    """El id de un mensaje de Redis empieza con los milisegundos de cuando se agregó."""
    try:
        milisegundos = int(str(id_mensaje).split("-", 1)[0])
    except ValueError:
        return None
    return datetime.fromtimestamp(milisegundos / 1000, tz=UTC).isoformat()


def estado_de_eventos() -> dict:
    """Lo mismo que `python -m agroia_comun.eventos estado`, para el panel: streams, grupos,
    consumidores y los últimos fallidos con su fecha, sin el sobre ni sus datos. Lanza
    redis.RedisError si Redis no responde."""
    datos = operacion.estado(conexion.cliente())
    ultimos = []
    for fallido in datos["fallidos"]["ultimos"]:
        ultimos.append(
            {
                "id": fallido["id"],
                "fecha": _fecha_de_id(fallido["id"]),
                "tipo": fallido.get("tipo"),
                "grupo": fallido.get("grupo"),
                "stream": fallido.get("stream"),
                "intentos": int(fallido["intentos"]) if fallido.get("intentos") else None,
                "motivo": nombre_de_excepcion(fallido.get("motivo")),
                "datos_omitidos": fallido.get("datos_omitidos") or None,
            }
        )
    return {
        "streams": datos["streams"],
        "fallidos": {"total": datos["fallidos"]["total"], "ultimos": ultimos},
    }
