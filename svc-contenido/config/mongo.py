"""Conexión a MongoDB para svc-contenido.

El cliente se crea la primera vez que se usa, no al importar, para que Django y las
pruebas arranquen aunque MongoDB no esté disponible. En pruebas se reemplaza con
mongomock.
"""

from functools import lru_cache

from django.conf import settings
from pymongo import MongoClient
from pymongo.database import Database


@lru_cache(maxsize=1)
def obtener_cliente() -> MongoClient:
    return MongoClient(settings.MONGO_URL, serverSelectionTimeoutMS=5000, tz_aware=True)


def obtener_base() -> Database:
    """Base indicada al final de MONGO_URL (`contenido`)."""
    return obtener_cliente().get_default_database()
