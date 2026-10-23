"""Lógica de negocio de las conversaciones con el agente.

Documento en la colección `conversaciones`:
    {_id, usuario_id, titulo, creada_en, actualizada_en,
     mensajes: [{rol: "usuario"|"agente", texto, fuentes?, fecha}]}

Los mensajes van dentro de su conversación porque siempre se leen juntos. Cada usuario
solo ve sus conversaciones, también el administrador (son privadas).
"""

from django.http import Http404
from pymongo import ASCENDING, DESCENDING, ReturnDocument

from agroia_comun.errores import ErrorDeNegocio
from config import mongo
from config.paginacion import ConsultaMongo

COLECCION = "conversaciones"
LIMITE_MENSAJES = 200
INDICES = [[("usuario_id", ASCENDING), ("actualizada_en", DESCENDING)]]


def _coleccion():
    return mongo.coleccion(COLECCION)


def crear(usuario_id: int, titulo: str) -> dict:
    ahora = mongo.ahora()
    conversacion = {
        "usuario_id": usuario_id,
        "titulo": titulo,
        "creada_en": ahora,
        "actualizada_en": ahora,
        "mensajes": [],
    }
    conversacion["_id"] = _coleccion().insert_one(conversacion).inserted_id
    return conversacion


def consulta_propias(usuario_id: int) -> ConsultaMongo:
    """Conversaciones del usuario, las más recientes primero, sin los mensajes."""
    return ConsultaMongo(
        _coleccion(),
        {"usuario_id": usuario_id},
        [("actualizada_en", DESCENDING), ("_id", DESCENDING)],
        {"mensajes": 0},
    )


def obtener_propia(usuario_id: int, id_texto: str) -> dict:
    """La conversación con sus mensajes; 404 si no existe o es de otro usuario."""
    conversacion = _coleccion().find_one(
        {"_id": mongo.object_id_o_404(id_texto), "usuario_id": usuario_id}
    )
    if conversacion is None:
        raise Http404
    return conversacion


def borrar(usuario_id: int, id_texto: str) -> None:
    resultado = _coleccion().delete_one(
        {"_id": mongo.object_id_o_404(id_texto), "usuario_id": usuario_id}
    )
    if resultado.deleted_count == 0:
        raise Http404


def agregar_mensaje(
    usuario_id: int, id_texto: str, rol: str, texto: str, fuentes: list[str] | None
) -> dict:
    """Agrega un mensaje y devuelve la conversación actualizada.

    El límite de 200 mensajes va en el mismo filtro del update, así se respeta aunque
    lleguen dos mensajes al mismo tiempo. Al llegar al límite hay que iniciar otra.
    """
    id_conversacion = mongo.object_id_o_404(id_texto)
    ahora = mongo.ahora()
    mensaje = {"rol": rol, "texto": texto, "fecha": ahora}
    if fuentes:
        mensaje["fuentes"] = fuentes

    actualizada = _coleccion().find_one_and_update(
        {
            "_id": id_conversacion,
            "usuario_id": usuario_id,
            f"mensajes.{LIMITE_MENSAJES - 1}": {"$exists": False},
        },
        {"$push": {"mensajes": mensaje}, "$set": {"actualizada_en": ahora}},
        return_document=ReturnDocument.AFTER,
    )
    if actualizada is not None:
        return actualizada

    obtener_propia(usuario_id, id_texto)  # 404 si no existe o no es suya
    raise ErrorDeNegocio(
        "conversacion_llena",
        f"La conversación llegó al límite de {LIMITE_MENSAJES} mensajes; inicia una nueva.",
    )
