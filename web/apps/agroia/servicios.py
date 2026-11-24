"""Chat con AgroIA: la pregunta va por eventos (Entrega 4) y la pantalla consulta su estado.

1. Al preguntar, el gateway llama a svc-contenido (`POST conversaciones/<id>/preguntar/`):
   guarda la pregunta, deja una solicitud `pendiente` en la conversación y publica
   `ia_pregunta_solicitada`. Responde de inmediato.
2. El worker de svc-ia (contenedor svc-ia-worker) llama al agente y publica la respuesta o
   la fallida; el consumidor de svc-contenido la guarda en la conversación.
3. La pantalla consulta el estado (`GET conversaciones/<id>/solicitud/`) con HTMX: cada 2 s
   al principio y cada 5 s después de 20 s, hasta `listo` o `fallido`.

Una solicitud fallida (el agente no respondió, tardó más de 180 s...) ofrece «Reintentar»,
que pide otra respuesta a la última pregunta sin repetirla. El gateway no toca Redis: todo
pasa por svc-contenido, dueño de la conversación. Nunca se inventa una respuesta.
"""

from datetime import UTC, datetime

from django.http import HttpRequest

from apps.cuentas.servicios import con_sesion

# Polling: cada 2 s los primeros 20 s; después, cada 5 s.
INTERVALO_INICIAL = 2
INTERVALO_DESPUES = 5
SEGUNDOS_INICIALES = 20

MENSAJES_DE_FALLO = {
    "agente_no_disponible": "AgroIA no pudo responder en este momento.",
    "vencida": "AgroIA tardó demasiado en responder.",
    "servicio_no_disponible": "No pudimos enviar tu pregunta a AgroIA.",
    "pregunta_invalida": "AgroIA no pudo procesar esta pregunta.",
}
SE_PUEDE_REINTENTAR = set(MENSAJES_DE_FALLO)

# 429 de svc-contenido: el límite de solicitudes a la IA por usuario.
DEMASIADAS = "Hiciste muchas preguntas seguidas. Espera un momento y vuelve a preguntar."


def mensaje_de_error(error) -> str:
    """El mensaje para un ErrorApi al preguntar o reintentar."""
    if error.codigo == "demasiados_intentos":
        if error.espera:
            return (
                "Hiciste muchas preguntas seguidas. Espera "
                f"{_espera_legible(error.espera)} y vuelve a preguntar."
            )
        return DEMASIADAS
    return error.mensaje


def _espera_legible(segundos: int) -> str:
    if segundos < 90:
        return f"{segundos} segundos"
    return f"{-(-segundos // 60)} minutos"


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


def preguntar(request: HttpRequest, conversacion_id: str, pregunta: str) -> dict:
    """La solicitud (`pendiente`, o `fallido` si no se pudo enviar). Lanza ErrorApi con
    `conversacion_llena` o `solicitud_en_curso`."""
    return con_sesion(
        request,
        "contenido",
        "POST",
        f"conversaciones/{conversacion_id}/preguntar/",
        json={"texto": pregunta},
    )


def reintentar(request: HttpRequest, conversacion_id: str) -> dict:
    return con_sesion(request, "contenido", "POST", f"conversaciones/{conversacion_id}/reintentar/")


def solicitud(request: HttpRequest, conversacion_id: str) -> dict:
    return con_sesion(request, "contenido", "GET", f"conversaciones/{conversacion_id}/solicitud/")


def intervalo(datos: dict) -> int:
    """Segundos hasta la siguiente consulta: crece después de los primeros 20 s."""
    try:
        creada = datetime.fromisoformat(datos["creada_en"])
    except (KeyError, TypeError, ValueError):
        return INTERVALO_INICIAL
    transcurrido = (datetime.now(UTC) - creada).total_seconds()
    return INTERVALO_INICIAL if transcurrido < SEGUNDOS_INICIALES else INTERVALO_DESPUES


def mensaje_de_fallo(codigo: str | None) -> str:
    return MENSAJES_DE_FALLO.get(codigo or "", "AgroIA no pudo responder.")


def sin_respuesta_heredada(mensajes: list[dict], datos_solicitud: dict | None) -> bool:
    """Conversaciones de antes de los eventos: la última pregunta quedó sin respuesta y no
    hay solicitud. Se ofrece reintentar."""
    return not datos_solicitud and bool(mensajes) and mensajes[-1].get("rol") == "usuario"
