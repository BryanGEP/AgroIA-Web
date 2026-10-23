"""Cliente del contenedor `agente` (repo BryanGEP/AgroIA, carpeta svc-agente).

Traduce el contrato de AgroIA-Web a la API real del agente:

    AgroIA-Web  POST /agente/preguntar/  {"pregunta", "historial": [{"rol", "texto"}]}
    agente      POST /chat               {"message", "session_id"} -> {"response", "session_id"}

El agente guarda memoria propia por `session_id` y no recibe historial. Como las
conversaciones las guarda svc-contenido y svc-ia no guarda nada, cada petición usa un
`session_id` nuevo y las últimas entradas del historial viajan como un bloque de
contexto dentro del mensaje. Cuando el agente acepte historial, solo cambia
`construir_mensaje`.

Pendiente en el repo AgroIA (antes de la Entrega 5): el agente nunca borra las sesiones
de su memoria, así que con un `session_id` por petición esa memoria crece sin límite
mientras el contenedor siga vivo.
"""

import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

MAX_HISTORIAL = 10
ETIQUETAS = {"usuario": "Productor", "agente": "AgroIA"}


class AgenteNoDisponible(Exception):
    """El agente no respondió, falló o tardó más que AGENTE_TIMEOUT."""


@dataclass
class RespuestaDelAgente:
    respuesta: str
    fuentes: list[str] = field(default_factory=list)


def construir_mensaje(pregunta: str, historial: list[dict]) -> str:
    """Mensaje para el agente: la pregunta, precedida del contexto reciente si lo hay."""
    recientes = historial[-MAX_HISTORIAL:]
    if not recientes:
        return pregunta
    lineas = [f"{ETIQUETAS[m['rol']]}: {m['texto']}" for m in recientes]
    return (
        "Contexto de la conversación anterior:\n"
        + "\n".join(lineas)
        + f"\n\nPregunta actual: {pregunta}"
    )


class ClienteAgente:
    def __init__(self, cliente_http: httpx.Client):
        self.http = cliente_http

    def preguntar(self, pregunta: str, historial: list[dict]) -> RespuestaDelAgente:
        cuerpo = {"message": construir_mensaje(pregunta, historial), "session_id": uuid.uuid4().hex}
        try:
            respuesta = self.http.post("/chat", json=cuerpo)
        except httpx.TimeoutException as error:
            logger.warning("El agente tardó más de %s s", settings.agente_timeout)
            raise AgenteNoDisponible("tiempo_agotado") from error
        except httpx.HTTPError as error:
            logger.warning("No se pudo conectar con el agente: %s", type(error).__name__)
            raise AgenteNoDisponible("sin_conexion") from error

        if respuesta.status_code != 200:
            logger.warning("El agente respondió %s", respuesta.status_code)
            raise AgenteNoDisponible("error_del_agente")
        try:
            texto = respuesta.json().get("response")
        except ValueError as error:
            raise AgenteNoDisponible("respuesta_invalida") from error
        if not isinstance(texto, str) or not texto.strip():
            raise AgenteNoDisponible("respuesta_vacia")
        # El agente todavía no tiene RAG: no devuelve fuentes.
        return RespuestaDelAgente(respuesta=texto, fuentes=[])


def obtener_agente() -> Iterator[ClienteAgente]:
    """Dependencia de FastAPI: un cliente por petición, cerrado al terminar."""
    with httpx.Client(base_url=settings.url_agente, timeout=settings.agente_timeout) as http:
        yield ClienteAgente(http)
