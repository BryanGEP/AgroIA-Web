"""Chat con AgroIA: el gateway orquesta svc-contenido (historial) y svc-ia (agente).

Al preguntar, en este orden y de forma síncrona:
  1. Lee la conversación de svc-contenido, para tener el historial.
  2. Guarda el mensaje del usuario en svc-contenido. Si la conversación llegó al límite
     (409 `conversacion_llena`) no se llama al agente: se ofrece una conversación nueva.
  3. Pide la respuesta a svc-ia con el historial anterior a la pregunta.
  4. Guarda la respuesta del agente con sus fuentes en svc-contenido.

Si el agente no responde (503 o tiempo agotado), la pregunta ya quedó guardada y se puede
reintentar sin volver a guardarla. Si guardar la respuesta falla después de recibirla, la
respuesta se muestra igual y queda en el log (`respuesta_no_guardada`). Nunca se inventa una
respuesta. En la Entrega 4 esto pasará a eventos por Redis: svc-ia responderá `pendiente` y
svc-contenido guardará el resultado al recibir el evento.
"""

import logging
from dataclasses import dataclass, field

from django.http import HttpRequest

from agroia_comun.seguridad import registrar_evento
from apps.cuentas.servicios import ErrorApi, con_sesion

MAX_FUENTES = 20  # lo que acepta svc-contenido por mensaje
LARGO_FUENTE = 500
CODIGOS_DEL_AGENTE = {"agente_no_disponible", "tiempo_agotado", "servicio_no_disponible"}
SIN_RESPUESTA = (
    "AgroIA no pudo responder en este momento. Tu pregunta quedó guardada: puedes reintentar "
    "en unos minutos."
)


@dataclass
class Turno:
    """Lo que pasó al preguntar, para mostrarlo."""

    pregunta: str = ""
    respuesta: str | None = None
    fuentes: list[str] = field(default_factory=list)
    guardada: bool = True  # la respuesta quedó en el historial
    sin_respuesta: bool = False  # el agente no respondió: se puede reintentar
    llena: bool = False  # la conversación llegó al límite de mensajes
    pregunta_guardada: bool = True


def conversaciones(request: HttpRequest) -> list[dict]:
    datos = con_sesion(request, "contenido", "GET", "conversaciones/")
    return datos.get("results", []) if isinstance(datos, dict) else datos


def conversacion(request: HttpRequest, conversacion_id: str) -> dict:
    return con_sesion(request, "contenido", "GET", f"conversaciones/{conversacion_id}/")


def crear(request: HttpRequest, titulo: str) -> dict:
    return con_sesion(
        request, "contenido", "POST", "conversaciones/", json={"titulo": titulo[:120]}
    )


def borrar(request: HttpRequest, conversacion_id: str) -> None:
    con_sesion(request, "contenido", "DELETE", f"conversaciones/{conversacion_id}/")


def _guardar(request, conversacion_id: str, rol: str, texto: str, fuentes=None) -> None:
    cuerpo = {"rol": rol, "texto": texto}
    if fuentes:
        cuerpo["fuentes"] = fuentes
    con_sesion(
        request, "contenido", "POST", f"conversaciones/{conversacion_id}/mensajes/", json=cuerpo
    )


def _historial(mensajes: list[dict]) -> list[dict]:
    return [{"rol": m["rol"], "texto": m["texto"]} for m in mensajes]


def preguntar(request: HttpRequest, conversacion_id: str, pregunta: str) -> Turno:
    mensajes = conversacion(request, conversacion_id).get("mensajes", [])
    try:
        _guardar(request, conversacion_id, "usuario", pregunta)
    except ErrorApi as error:
        if error.codigo == "conversacion_llena":
            return Turno(pregunta=pregunta, llena=True, pregunta_guardada=False)
        raise
    return _responder(request, conversacion_id, pregunta, _historial(mensajes))


def pendiente(mensajes: list[dict]) -> str | None:
    """La pregunta sin respuesta: el último mensaje, si es del usuario."""
    if mensajes and mensajes[-1].get("rol") == "usuario":
        return mensajes[-1]["texto"]
    return None


def reintentar(request: HttpRequest, conversacion_id: str) -> Turno | None:
    """Pide otra vez la respuesta a la última pregunta, sin volver a guardarla."""
    mensajes = conversacion(request, conversacion_id).get("mensajes", [])
    pregunta = pendiente(mensajes)
    if pregunta is None:
        return None
    return _responder(request, conversacion_id, pregunta, _historial(mensajes[:-1]))


def _responder(request, conversacion_id: str, pregunta: str, historial: list[dict]) -> Turno:
    try:
        datos = con_sesion(
            request,
            "ia",
            "POST",
            "agente/preguntar/",
            json={"pregunta": pregunta, "historial": historial},
        )
    except ErrorApi as error:
        if error.estado >= 500 or error.codigo in CODIGOS_DEL_AGENTE:
            return Turno(pregunta=pregunta, sin_respuesta=True)
        raise
    respuesta = datos.get("respuesta", "")
    fuentes = [str(f)[:LARGO_FUENTE] for f in (datos.get("fuentes") or [])][:MAX_FUENTES]
    turno = Turno(pregunta=pregunta, respuesta=respuesta, fuentes=fuentes)
    try:
        _guardar(request, conversacion_id, "agente", respuesta, fuentes)
    except ErrorApi as error:
        # La respuesta ya existe: se muestra igual, pero no quedó en el historial.
        turno.guardada = False
        turno.llena = error.codigo == "conversacion_llena"
        registrar_evento(
            "respuesta_no_guardada",
            request,
            nivel=logging.WARNING,
            conversacion=conversacion_id,
            error=error.codigo,
        )
    return turno
