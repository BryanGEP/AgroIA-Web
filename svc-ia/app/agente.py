"""Cliente del contenedor `agente` (repo BryanGEP/AgroIA, carpeta svc-agente).

Traduce el contrato de AgroIA-Web a la API real del agente:

    AgroIA-Web  POST /agente/preguntar/  {"pregunta", "historial": [{"rol", "texto"}]}
    agente      POST /chat               {"message", "history": [{"role", "content"}]}
                                         -> {"response", "session_id", "fuentes"}

El agente es sin estado cuando recibe `history`: responde con ese contexto y no guarda
nada. Por eso svc-ia siempre manda `history` (aunque sea vacío) y no usa `session_id`:
las conversaciones las guarda svc-contenido. `fuentes` son las referencias de la base de
conocimiento del agente (RAG) que usó para responder; puede venir vacía.
"""

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

MAX_HISTORIAL = 10
ROLES = {"usuario": "user", "agente": "assistant"}


class AgenteNoDisponible(Exception):
    """El agente no respondió, falló o tardó más que AGENTE_TIMEOUT."""


@dataclass
class RespuestaDelAgente:
    respuesta: str
    fuentes: list[str] = field(default_factory=list)


def construir_cuerpo(pregunta: str, historial: list[dict]) -> dict:
    """Cuerpo para `POST /chat`: la pregunta y las últimas entradas del historial."""
    recientes = historial[-MAX_HISTORIAL:]
    return {
        "message": pregunta,
        "history": [{"role": ROLES[m["rol"]], "content": m["texto"]} for m in recientes],
    }


def leer_fuentes(datos: dict) -> list[str]:
    """Las fuentes del agente, solo si son una lista de textos; si no, se ignoran."""
    fuentes = datos.get("fuentes")
    if not isinstance(fuentes, list):
        return []
    return [f for f in fuentes if isinstance(f, str) and f.strip()]


class ClienteAgente:
    def __init__(self, cliente_http: httpx.Client):
        self.http = cliente_http

    def preguntar(self, pregunta: str, historial: list[dict]) -> RespuestaDelAgente:
        try:
            respuesta = self.http.post("/chat", json=construir_cuerpo(pregunta, historial))
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
            datos = respuesta.json()
        except ValueError as error:
            raise AgenteNoDisponible("respuesta_invalida") from error
        texto = datos.get("response") if isinstance(datos, dict) else None
        if not isinstance(texto, str) or not texto.strip():
            raise AgenteNoDisponible("respuesta_vacia")
        return RespuestaDelAgente(respuesta=texto, fuentes=leer_fuentes(datos))


def obtener_agente() -> Iterator[ClienteAgente]:
    """Dependencia de FastAPI: un cliente por petición, cerrado al terminar."""
    with httpx.Client(base_url=settings.url_agente, timeout=settings.agente_timeout) as http:
        yield ClienteAgente(http)
