"""Lógica de negocio del historial de diagnósticos por imagen.

Documento en la colección `diagnosticos`:
    {_id, usuario_id, imagen, clase, confianza, probabilidades, modelo_version, creado_en,
     estado?: "pendiente"|"listo"|"fallido", codigo?, solicitud?: {id, vence_en}}

`imagen` es el nombre del archivo en default_storage, no una URL: la URL se calcula al
responder, así sigue funcionando cuando se pase a Cloud Storage (Entrega 5). svc-ia
clasifica y no guarda nada.

Diagnóstico asíncrono (Entrega 4; docs/eventos.md): `solicitar` guarda la foto, deja el
diagnóstico `pendiente`, pone una copia temporal de la imagen en Redis
(`agroia:ia:imagen:<solicitud_id>`, vence con la solicitud) y publica
`diagnostico_solicitado`, que lleva solo los ids. El worker de svc-ia clasifica y publica el
resultado; `guardar_resultado` lo guarda. Si falla, el diagnóstico queda `fallido` y se
borra la foto (como antes, cuando un 503 no guardaba nada). Los diagnósticos sin `estado`
son de antes (síncronos) y cuentan como listos. El historial solo muestra los listos.
"""

import logging
import mimetypes
import uuid
from datetime import timedelta
from pathlib import Path

import redis
from bson import ObjectId
from bson.errors import InvalidId
from django.conf import settings
from django.core.files.storage import default_storage
from django.http import Http404
from pymongo import ASCENDING, DESCENDING

from agroia_comun.eventos import Sobre, conexion, publicar
from agroia_comun.eventos.registro import registrar
from config import mongo
from config.paginacion import ConsultaMongo

COLECCION = "diagnosticos"
INDICES = [[("usuario_id", ASCENDING), ("creado_en", DESCENDING)]]
# Los de antes no tienen estado: cuentan como listos.
SOLO_LISTOS = {"$or": [{"estado": "listo"}, {"estado": {"$exists": False}}]}


def llave_de_imagen(solicitud_id: str) -> str:
    """Copia temporal de la imagen para el worker de svc-ia (la lee y la borra)."""
    return f"agroia:ia:imagen:{solicitud_id}"


def _coleccion():
    return mongo.coleccion(COLECCION)


def crear(
    usuario_id: uuid.UUID | str,
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
        "usuario_id": str(usuario_id),
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


def consulta(usuario_id: uuid.UUID | str, es_admin: bool) -> ConsultaMongo:
    """El cliente ve los suyos; el administrador, todos. Los más recientes primero."""
    filtro = dict(SOLO_LISTOS) if es_admin else {**SOLO_LISTOS, "usuario_id": str(usuario_id)}
    return ConsultaMongo(_coleccion(), filtro, [("creado_en", DESCENDING), ("_id", DESCENDING)])


def abrir_imagen(diagnostico: dict):
    """El archivo de la foto y su tipo. 404 si ya no existe en el almacenamiento."""
    nombre = diagnostico.get("imagen")
    if not nombre or not default_storage.exists(nombre):
        raise Http404
    tipo = mimetypes.guess_type(nombre)[0] or "application/octet-stream"
    if not tipo.startswith("image/"):
        raise Http404
    return default_storage.open(nombre, "rb"), tipo


def obtener(usuario_id: uuid.UUID | str, es_admin: bool, id_texto: str) -> dict:
    """Dueño o administrador; para cualquier otro, 404."""
    filtro = {"_id": mongo.object_id_o_404(id_texto)}
    if not es_admin:
        filtro["usuario_id"] = str(usuario_id)
    diagnostico = _coleccion().find_one(filtro)
    if diagnostico is None:
        raise Http404
    return vencer_si_toca(diagnostico)


# --- Diagnóstico asíncrono ----------------------------------------------------------------


def _fallar(diagnostico_id, solicitud_id: str, codigo: str) -> bool:
    """Marca fallido un diagnóstico pendiente y borra su foto. False si ya no estaba
    pendiente."""
    anterior = _coleccion().find_one_and_update(
        {"_id": diagnostico_id, "solicitud.id": solicitud_id, "estado": "pendiente"},
        {"$set": {"estado": "fallido", "codigo": codigo}, "$unset": {"imagen": ""}},
    )
    if anterior is None:
        return False
    if anterior.get("imagen"):
        default_storage.delete(anterior["imagen"])
    return True


def vencer_si_toca(diagnostico: dict) -> dict:
    solicitud = diagnostico.get("solicitud")
    if (
        diagnostico.get("estado") == "pendiente"
        and solicitud
        and mongo.ahora() > solicitud["vence_en"]
        and _fallar(diagnostico["_id"], solicitud["id"], "vencida")
    ):
        diagnostico.update(estado="fallido", codigo="vencida")
        diagnostico.pop("imagen", None)
    return diagnostico


def solicitar(usuario_id: uuid.UUID | str, imagen) -> dict:
    """Guarda la foto, deja el diagnóstico pendiente y lo pide al worker de svc-ia."""
    contenido = imagen.read()
    imagen.seek(0)
    extension = Path(imagen.name).suffix.lower() or ".jpg"
    nombre = default_storage.save(f"diagnosticos/{uuid.uuid4().hex}{extension}", imagen)
    ahora = mongo.ahora()
    vence = ahora + timedelta(seconds=settings.IA_SOLICITUD_VENCE_SEGUNDOS)
    solicitud = {"id": str(uuid.uuid4()), "vence_en": vence}
    diagnostico = {
        "usuario_id": str(usuario_id),
        "imagen": nombre,
        "estado": "pendiente",
        "codigo": None,
        "solicitud": solicitud,
        "creado_en": ahora,
    }
    try:
        diagnostico["_id"] = _coleccion().insert_one(diagnostico).inserted_id
    except Exception:
        default_storage.delete(nombre)
        raise
    try:
        conexion.cliente_binario().set(
            llave_de_imagen(solicitud["id"]),
            contenido,
            ex=max(settings.IA_SOLICITUD_VENCE_SEGUNDOS, 1),  # Redis pide al menos 1 s
        )
        sobre = publicar(
            "diagnostico_solicitado",
            {
                "solicitud_id": solicitud["id"],
                "diagnostico_id": str(diagnostico["_id"]),
                "usuario_id": str(usuario_id),
                "vence_en": vence.isoformat(),
            },
            origen=settings.NOMBRE_SERVICIO,
        )
    except redis.RedisError:
        sobre = None
    if sobre is None:
        _fallar(diagnostico["_id"], solicitud["id"], "servicio_no_disponible")
        diagnostico.update(estado="fallido", codigo="servicio_no_disponible")
        diagnostico.pop("imagen", None)
    return diagnostico


def _del_evento(datos: dict) -> dict | None:
    """El diagnóstico del evento, solo si coinciden el diagnóstico, el usuario y la
    solicitud."""
    try:
        id_diagnostico = ObjectId(datos["diagnostico_id"])
    except (InvalidId, TypeError):
        return None
    return _coleccion().find_one(
        {"_id": id_diagnostico, "usuario_id": datos["usuario_id"],
         "solicitud.id": datos["solicitud_id"]}
    )  # fmt: skip


def _registrar(suceso: str, sobre: Sobre, nivel=logging.INFO, **extra) -> None:
    registrar(
        suceso,
        nivel,
        evento_id=sobre.id,
        tipo=sobre.tipo,
        correlacion_id=sobre.correlacion_id,
        solicitud_id=sobre.datos.get("solicitud_id"),
        diagnostico_id=sobre.datos.get("diagnostico_id"),
        **extra,
    )


def guardar_resultado(sobre: Sobre) -> None:
    """diagnostico_generado: guarda el resultado una sola vez."""
    datos = sobre.datos
    diagnostico = _del_evento(datos)
    if diagnostico is None:
        _registrar("solicitud_no_coincide", sobre, logging.WARNING)
        return
    diagnostico = vencer_si_toca(diagnostico)
    if diagnostico.get("estado") == "fallido":
        _registrar("respuesta_tardia", sobre, codigo=diagnostico.get("codigo"))
        return
    _coleccion().update_one(
        {"_id": diagnostico["_id"], "estado": "pendiente"},
        {
            "$set": {
                "estado": "listo",
                "clase": datos["clase"],
                "confianza": float(datos["confianza"]),
                "probabilidades": {k: float(v) for k, v in datos["probabilidades"].items()},
                "modelo_version": datos["modelo_version"],
            }
        },
    )


def guardar_fallido(sobre: Sobre) -> None:
    """diagnostico_fallido: queda fallido con su código y se borra la foto."""
    diagnostico = _del_evento(sobre.datos)
    if diagnostico is None:
        _registrar("solicitud_no_coincide", sobre, logging.WARNING)
        return
    _fallar(diagnostico["_id"], sobre.datos["solicitud_id"], sobre.datos["codigo"])
