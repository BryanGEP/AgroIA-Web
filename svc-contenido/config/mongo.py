"""Conexión a MongoDB para svc-contenido.

El cliente se crea la primera vez que se usa, no al importar, para que Django y las
pruebas arranquen aunque MongoDB no esté disponible. En pruebas se reemplaza con
mongomock (ver conftest.py).
"""

from datetime import UTC, datetime
from functools import lru_cache

from bson import ObjectId
from django.conf import settings
from django.http import Http404
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database


@lru_cache(maxsize=1)
def obtener_cliente() -> MongoClient:
    return MongoClient(settings.MONGO_URL, serverSelectionTimeoutMS=5000, tz_aware=True)


def obtener_base() -> Database:
    """Base indicada al final de MONGO_URL (`contenido`)."""
    return obtener_cliente().get_default_database()


def coleccion(nombre: str) -> Collection:
    return obtener_base()[nombre]


def ahora() -> datetime:
    """Fecha actual en UTC truncada a milisegundos, la precisión con la que guarda MongoDB."""
    momento = datetime.now(UTC)
    return momento.replace(microsecond=momento.microsecond // 1000 * 1000)


def object_id_o_404(texto: str) -> ObjectId:
    """Convierte el id de la URL; uno mal formado responde 404, igual que uno inexistente."""
    if not ObjectId.is_valid(texto):
        raise Http404
    return ObjectId(texto)
