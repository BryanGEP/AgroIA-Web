"""Bitácora de actividad del sistema.

Documento en la colección `bitacora`:
    {_id, tipo, usuario_id, servicio, datos, fecha}
y, si vino de un evento por Redis, además {evento_id, correlacion_id}.

La llenan los eventos que publican los servicios (consumidor `consumir_eventos`, ver
docs/eventos.md) y, a mano, un administrador con POST.
"""

import uuid
from datetime import datetime

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from agroia_comun.eventos import Sobre
from config import mongo
from config.paginacion import ConsultaMongo

COLECCION = "bitacora"
INDICES = [[("tipo", ASCENDING), ("fecha", DESCENDING)], [("fecha", DESCENDING)]]
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
    tipo: str | None = None, desde: datetime | None = None, hasta: datetime | None = None
) -> ConsultaMongo:
    """Eventos filtrados por tipo y rango de fechas [desde, hasta), más recientes primero."""
    filtro: dict = {}
    if tipo:
        filtro["tipo"] = tipo
    rango = {}
    if desde is not None:
        rango["$gte"] = desde
    if hasta is not None:
        rango["$lt"] = hasta
    if rango:
        filtro["fecha"] = rango
    return ConsultaMongo(_coleccion(), filtro, [("fecha", DESCENDING), ("_id", DESCENDING)])
