"""Bitácora de actividad del sistema.

Documento en la colección `bitacora`:
    {_id, tipo, usuario_id, servicio, datos, fecha}

Por ahora la llena un administrador con POST; en la Entrega 4 la llenarán los eventos
que publiquen los servicios por Redis.
"""

from datetime import datetime

from pymongo import ASCENDING, DESCENDING

from config import mongo
from config.paginacion import ConsultaMongo

COLECCION = "bitacora"
INDICES = [[("tipo", ASCENDING), ("fecha", DESCENDING)], [("fecha", DESCENDING)]]


def _coleccion():
    return mongo.coleccion(COLECCION)


def registrar(tipo: str, usuario_id: int | None, servicio: str, datos: dict) -> dict:
    evento = {
        "tipo": tipo,
        "usuario_id": usuario_id,
        "servicio": servicio,
        "datos": datos,
        "fecha": mongo.ahora(),
    }
    evento["_id"] = _coleccion().insert_one(evento).inserted_id
    return evento


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
