"""Lógica de negocio del historial de diagnósticos por imagen.

Documento en la colección `diagnosticos`:
    {_id, usuario_id, imagen, clase, confianza, probabilidades, modelo_version, creado_en}

`imagen` es el nombre del archivo en default_storage, no una URL: la URL se calcula al
responder, así sigue funcionando cuando se pase a Cloud Storage (Entrega 5). svc-ia
clasifica y no guarda nada; aquí se guarda el resultado que manda el gateway.
"""

import uuid
from pathlib import Path

from django.core.files.storage import default_storage
from django.http import Http404
from pymongo import ASCENDING, DESCENDING

from config import mongo
from config.paginacion import ConsultaMongo

COLECCION = "diagnosticos"
INDICES = [[("usuario_id", ASCENDING), ("creado_en", DESCENDING)]]


def _coleccion():
    return mongo.coleccion(COLECCION)


def crear(
    usuario_id: int,
    imagen,
    clase: str,
    confianza: float,
    probabilidades: dict[str, float],
    modelo_version: str,
) -> dict:
    """Guarda la imagen con default_storage y el resultado en MongoDB."""
    extension = Path(imagen.name).suffix.lower() or ".jpg"
    nombre = default_storage.save(f"diagnosticos/{uuid.uuid4().hex}{extension}", imagen)
    diagnostico = {
        "usuario_id": usuario_id,
        "imagen": nombre,
        "clase": clase,
        "confianza": confianza,
        "probabilidades": probabilidades,
        "modelo_version": modelo_version,
        "creado_en": mongo.ahora(),
    }
    try:
        diagnostico["_id"] = _coleccion().insert_one(diagnostico).inserted_id
    except Exception:
        default_storage.delete(nombre)
        raise
    return diagnostico


def consulta(usuario_id: int, es_admin: bool) -> ConsultaMongo:
    """El cliente ve los suyos; el administrador, todos. Los más recientes primero."""
    filtro = {} if es_admin else {"usuario_id": usuario_id}
    return ConsultaMongo(_coleccion(), filtro, [("creado_en", DESCENDING), ("_id", DESCENDING)])


def obtener(usuario_id: int, es_admin: bool, id_texto: str) -> dict:
    """Dueño o administrador; para cualquier otro, 404."""
    filtro = {"_id": mongo.object_id_o_404(id_texto)}
    if not es_admin:
        filtro["usuario_id"] = usuario_id
    diagnostico = _coleccion().find_one(filtro)
    if diagnostico is None:
        raise Http404
    return diagnostico
