"""Lógica de negocio de las conversaciones con el agente.

Documento en la colección `conversaciones`:
    {_id, usuario_id, titulo, creada_en, actualizada_en,
     mensajes: [{rol: "usuario"|"agente", texto, fuentes?, fecha, solicitud_id?}],
     solicitud?: {id, estado: "pendiente"|"listo"|"fallido", codigo?, creada_en,
                  vence_en, actualizada_en}}

Los mensajes van dentro de su conversación porque siempre se leen juntos. Cada usuario
solo ve sus conversaciones, también el administrador (son privadas).

Preguntas a la IA (asíncronas, Entrega 4; docs/eventos.md):
- `preguntar` guarda la pregunta, deja la solicitud `pendiente` en la conversación (una a
  la vez) y publica `ia_pregunta_solicitada` con el historial guardado. El worker de svc-ia
  publica la respuesta y `guardar_respuesta` (consumidor) la agrega una sola vez.
- `reintentar` pide otra vez la respuesta a la última pregunta, sin repetirla.
- Una solicitud pendiente que pasa de `vence_en` se marca `fallido` con el código
  `vencida`; una respuesta que llegue después se descarta (`respuesta_tardia` en el log).
"""

import logging
import uuid
from datetime import datetime, timedelta

from bson import ObjectId
from bson.errors import InvalidId
from django.conf import settings
from django.http import Http404
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from rest_framework import status

from agroia_comun.errores import ErrorDeNegocio
from agroia_comun.eventos import Sobre, publicar
from agroia_comun.eventos.registro import registrar
from config import mongo
from config.paginacion import ConsultaMongo

COLECCION = "conversaciones"
LIMITE_MENSAJES = 200
INDICES = [[("usuario_id", ASCENDING), ("actualizada_en", DESCENDING)]]
MAX_HISTORIAL = 10  # lo que svc-ia manda al agente
MAX_FUENTES = 20
LARGO_FUENTE = 500


def _coleccion():
    return mongo.coleccion(COLECCION)


def crear(usuario_id: uuid.UUID | str, titulo: str) -> dict:
    ahora = mongo.ahora()
    conversacion = {
        "usuario_id": str(usuario_id),
        "titulo": titulo,
        "creada_en": ahora,
        "actualizada_en": ahora,
        "mensajes": [],
    }
    conversacion["_id"] = _coleccion().insert_one(conversacion).inserted_id
    return conversacion


def consulta_propias(usuario_id: uuid.UUID | str) -> ConsultaMongo:
    """Conversaciones del usuario, las más recientes primero, sin los mensajes."""
    return ConsultaMongo(
        _coleccion(),
        {"usuario_id": str(usuario_id)},
        [("actualizada_en", DESCENDING), ("_id", DESCENDING)],
        {"mensajes": 0},
    )


def obtener_propia(usuario_id: uuid.UUID | str, id_texto: str) -> dict:
    """La conversación con sus mensajes; 404 si no existe o es de otro usuario."""
    conversacion = _coleccion().find_one(
        {"_id": mongo.object_id_o_404(id_texto), "usuario_id": str(usuario_id)}
    )
    if conversacion is None:
        raise Http404
    return conversacion


def borrar(usuario_id: uuid.UUID | str, id_texto: str) -> None:
    resultado = _coleccion().delete_one(
        {"_id": mongo.object_id_o_404(id_texto), "usuario_id": str(usuario_id)}
    )
    if resultado.deleted_count == 0:
        raise Http404


def agregar_mensaje(
    usuario_id: uuid.UUID | str, id_texto: str, rol: str, texto: str, fuentes: list[str] | None
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
            "usuario_id": str(usuario_id),
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


# --- Preguntas a la IA (asíncronas) -------------------------------------------------------


def _ahora() -> datetime:
    return mongo.ahora()


def _nueva_solicitud() -> dict:
    ahora = _ahora()
    return {
        "id": str(uuid.uuid4()),
        "estado": "pendiente",
        "codigo": None,
        "creada_en": ahora,
        "vence_en": ahora + timedelta(seconds=settings.IA_SOLICITUD_VENCE_SEGUNDOS),
        "actualizada_en": ahora,
    }


def _marcar(conversacion_id, solicitud_id: str, estado: str, codigo: str | None) -> bool:
    """Cambia una solicitud que sigue pendiente. False si ya no lo estaba."""
    resultado = _coleccion().update_one(
        {"_id": conversacion_id, "solicitud.id": solicitud_id, "solicitud.estado": "pendiente"},
        {
            "$set": {
                "solicitud.estado": estado,
                "solicitud.codigo": codigo,
                "solicitud.actualizada_en": _ahora(),
            }
        },
    )
    return resultado.modified_count == 1


def vencer_si_toca(conversacion: dict) -> dict:
    """Si la solicitud sigue pendiente y ya pasó su `vence_en`, la marca fallida
    (`vencida`). Devuelve la conversación al día."""
    solicitud = conversacion.get("solicitud")
    if (
        solicitud
        and solicitud["estado"] == "pendiente"
        and _ahora() > solicitud["vence_en"]
        and _marcar(conversacion["_id"], solicitud["id"], "fallido", "vencida")
    ):
        solicitud.update(estado="fallido", codigo="vencida")
    return conversacion


def _historial(mensajes: list[dict]) -> list[dict]:
    return [{"rol": m["rol"], "texto": m["texto"]} for m in mensajes][-MAX_HISTORIAL:]


def _publicar_pregunta(conversacion: dict, solicitud: dict, pregunta: str, historial) -> dict:
    sobre = publicar(
        "ia_pregunta_solicitada",
        {
            "solicitud_id": solicitud["id"],
            "usuario_id": conversacion["usuario_id"],
            "conversacion_id": str(conversacion["_id"]),
            "pregunta": pregunta,
            "historial": historial,
            "vence_en": solicitud["vence_en"].isoformat(),
        },
        origen=settings.NOMBRE_SERVICIO,
    )
    if sobre is None:
        # Redis no respondió: la pregunta quedó guardada y el usuario puede reintentar.
        _marcar(conversacion["_id"], solicitud["id"], "fallido", "servicio_no_disponible")
        solicitud.update(estado="fallido", codigo="servicio_no_disponible")
    return solicitud


def _en_curso() -> ErrorDeNegocio:
    return ErrorDeNegocio(
        "solicitud_en_curso",
        "AgroIA todavía está respondiendo tu pregunta anterior.",
        status.HTTP_409_CONFLICT,
    )


def preguntar(usuario_id: uuid.UUID | str, id_texto: str, texto: str) -> dict:
    """Guarda la pregunta, deja la solicitud pendiente y la publica. Devuelve la solicitud."""
    conversacion = vencer_si_toca(obtener_propia(usuario_id, id_texto))
    if (conversacion.get("solicitud") or {}).get("estado") == "pendiente":
        raise _en_curso()
    historial = _historial(conversacion.get("mensajes", []))
    solicitud = _nueva_solicitud()
    ahora = solicitud["creada_en"]
    # En un solo update: el límite de mensajes y que no haya otra solicitud pendiente.
    resultado = _coleccion().update_one(
        {
            "_id": conversacion["_id"],
            "usuario_id": str(usuario_id),
            f"mensajes.{LIMITE_MENSAJES - 1}": {"$exists": False},
            "solicitud.estado": {"$ne": "pendiente"},
        },
        {
            "$push": {"mensajes": {"rol": "usuario", "texto": texto, "fecha": ahora}},
            "$set": {"solicitud": solicitud, "actualizada_en": ahora},
        },
    )
    if resultado.modified_count == 0:
        actual = obtener_propia(usuario_id, id_texto)
        if (actual.get("solicitud") or {}).get("estado") == "pendiente":
            raise _en_curso()
        raise ErrorDeNegocio(
            "conversacion_llena",
            f"La conversación llegó al límite de {LIMITE_MENSAJES} mensajes; inicia una nueva.",
        )
    return _publicar_pregunta(conversacion, solicitud, texto, historial)


def reintentar(usuario_id: uuid.UUID | str, id_texto: str) -> dict:
    """Pide otra vez la respuesta a la última pregunta, sin volver a guardarla."""
    conversacion = vencer_si_toca(obtener_propia(usuario_id, id_texto))
    if (conversacion.get("solicitud") or {}).get("estado") == "pendiente":
        raise _en_curso()
    mensajes = conversacion.get("mensajes", [])
    if not mensajes or mensajes[-1]["rol"] != "usuario":
        raise ErrorDeNegocio(
            "sin_pregunta_pendiente",
            "No hay una pregunta sin respuesta en esta conversación.",
            status.HTTP_409_CONFLICT,
        )
    solicitud = _nueva_solicitud()
    resultado = _coleccion().update_one(
        {"_id": conversacion["_id"], "solicitud.estado": {"$ne": "pendiente"}},
        {"$set": {"solicitud": solicitud}},
    )
    if resultado.modified_count == 0:
        raise _en_curso()
    return _publicar_pregunta(
        conversacion, solicitud, mensajes[-1]["texto"], _historial(mensajes[:-1])
    )


def solicitud_actual(usuario_id: uuid.UUID | str, id_texto: str) -> dict:
    """La solicitud de la conversación (404 si no hay o la conversación no es suya). En
    `listo` trae también la respuesta y sus fuentes."""
    conversacion = vencer_si_toca(obtener_propia(usuario_id, id_texto))
    solicitud = conversacion.get("solicitud")
    if not solicitud:
        raise Http404
    datos = {**solicitud, "conversacion_id": str(conversacion["_id"])}
    if solicitud["estado"] == "listo":
        respuesta = next(
            (m for m in conversacion["mensajes"] if m.get("solicitud_id") == solicitud["id"]),
            None,
        )
        if respuesta:
            datos.update(respuesta=respuesta["texto"], fuentes=respuesta.get("fuentes", []))
    return datos


# --- Consumidor: resultados del worker de svc-ia --------------------------------------------


def _conversacion_del_evento(datos: dict) -> dict | None:
    """La conversación de la solicitud, solo si coinciden la conversación, el usuario y la
    solicitud del evento. Si no, None: el evento no se aplica (no se reintenta)."""
    try:
        id_conversacion = ObjectId(datos["conversacion_id"])
    except (InvalidId, TypeError):
        return None
    return _coleccion().find_one(
        {
            "_id": id_conversacion,
            "usuario_id": datos["usuario_id"],
            "solicitud.id": datos["solicitud_id"],
        }
    )


def _registrar(suceso: str, sobre: Sobre, nivel=logging.INFO, **extra) -> None:
    """Sin la pregunta ni la respuesta: solo los ids."""
    registrar(
        suceso,
        nivel,
        evento_id=sobre.id,
        tipo=sobre.tipo,
        correlacion_id=sobre.correlacion_id,
        solicitud_id=sobre.datos.get("solicitud_id"),
        conversacion_id=sobre.datos.get("conversacion_id"),
        **extra,
    )


def guardar_respuesta(sobre: Sobre) -> None:
    """ia_respuesta_generada: agrega la respuesta una sola vez y marca la solicitud lista."""
    datos = sobre.datos
    conversacion = _conversacion_del_evento(datos)
    if conversacion is None:
        _registrar("solicitud_no_coincide", sobre, logging.WARNING)
        return
    conversacion = vencer_si_toca(conversacion)
    solicitud = conversacion["solicitud"]
    if solicitud["estado"] == "listo":
        return  # ya se guardó (evento repetido)
    if solicitud["estado"] == "fallido":
        _registrar("respuesta_tardia", sobre, codigo=solicitud.get("codigo"))
        return
    ahora = _ahora()
    fuentes = [str(f)[:LARGO_FUENTE] for f in datos.get("fuentes", [])][:MAX_FUENTES]
    mensaje = {"rol": "agente", "texto": datos["respuesta"], "fecha": ahora,
               "solicitud_id": solicitud["id"]}  # fmt: skip
    if fuentes:
        mensaje["fuentes"] = fuentes
    # Un solo update: solo si sigue pendiente, no tiene ya la respuesta y cabe.
    resultado = _coleccion().update_one(
        {
            "_id": conversacion["_id"],
            "solicitud.id": solicitud["id"],
            "solicitud.estado": "pendiente",
            "mensajes.solicitud_id": {"$ne": solicitud["id"]},
            f"mensajes.{LIMITE_MENSAJES - 1}": {"$exists": False},
        },
        {
            "$push": {"mensajes": mensaje},
            "$set": {
                "solicitud.estado": "listo",
                "solicitud.actualizada_en": ahora,
                "actualizada_en": ahora,
            },
        },
    )
    if resultado.modified_count == 0 and _marcar(
        conversacion["_id"], solicitud["id"], "fallido", "conversacion_llena"
    ):
        _registrar("respuesta_no_cabe", sobre, logging.WARNING)


def guardar_fallida(sobre: Sobre) -> None:
    """ia_respuesta_fallida: la solicitud queda fallida con su código (la interfaz ofrece
    «Reintentar»)."""
    conversacion = _conversacion_del_evento(sobre.datos)
    if conversacion is None:
        _registrar("solicitud_no_coincide", sobre, logging.WARNING)
        return
    _marcar(conversacion["_id"], sobre.datos["solicitud_id"], "fallido", sobre.datos["codigo"])
