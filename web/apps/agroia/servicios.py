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
from urllib.parse import urlsplit

from django.http import HttpRequest
from django.urls import Resolver404, resolve
from django.utils.http import url_has_allowed_host_and_scheme

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


# --- Widget flotante (Entrega 4, fase 3) ---------------------------------------------------
#
# El widget usa el mismo flujo que /agroia/. Su conversación se guarda en la sesión del
# gateway y se crea con el primer mensaje; «Reiniciar» solo olvida cuál era (la anterior
# sigue en /agroia/). La marca de pendiente le dice a base.html, sin pedir nada a
# svc-contenido, que hay una pregunta esperando: así el polling sigue al cambiar de página.

SESION_CONVERSACION = "agroia_widget_conversacion"
SESION_PENDIENTE = "agroia_widget_pendiente"
LARGO_PRODUCTO = 80

# Dónde no aparece: el chat completo, las pantallas de acceso y el panel de administración.
APPS_SIN_WIDGET = {"agroia", "panel", "proxy"}
VISTAS_SIN_WIDGET = {
    ("cuentas", "iniciar_sesion"),
    ("cuentas", "registro"),
    ("cuentas", "recuperar"),
    ("cuentas", "restablecer"),
    ("cuentas", "verificar_correo"),
    ("cuentas", "reenviar_verificacion"),
}

SUGERENCIAS_GENERALES = [
    "¿Cada cuánto debo regar mi aguacate?",
    "¿Qué es la antracnosis?",
    "Consejos para el suelo",
    "¿Cómo detecto la roña?",
]
SUGERENCIAS = {
    "catalogo": [
        "¿Qué fungicida conviene contra la antracnosis?",
        "¿Qué fertilizante uso antes de la floración?",
        "¿Cómo elijo un insumo para mi huerta?",
    ],
    "diagnostico": [
        "¿Cómo distingo la roña de la antracnosis?",
        "¿Qué hago si mi aguacate tiene antracnosis?",
        "¿Cómo prevengo la roña?",
        "¿Qué daño causa el trips en el fruto?",
    ],
    "tienda": [
        "¿Qué insumos necesito para la temporada de lluvias?",
        "¿Cuánto fungicida necesito por hectárea?",
        "¿Cada cuánto debo regar mi aguacate?",
        "¿Cómo detecto la roña?",
    ],
}
SUGERENCIAS_PRODUCTO = [
    "¿Cómo y cuándo se aplica {producto}?",
    "¿Qué precauciones debo tener con {producto}?",
    "¿Para qué problemas del aguacate sirve {producto}?",
]


def mostrar_widget(app: str | None, vista: str | None) -> bool:
    if not app and not vista:
        return False  # sin vista resuelta (por ejemplo, una ruta que no existe)
    return app not in APPS_SIN_WIDGET and (app, vista) not in VISTAS_SIN_WIDGET


def nombre_de_producto(valor) -> str:
    """El nombre que manda la página de detalle. Viene del navegador: se normaliza y se
    recorta. El HTML lo escapa el autoescape de Django al mostrarlo."""
    if not isinstance(valor, str):
        return ""
    return " ".join(valor.split())[:LARGO_PRODUCTO]


def sugerencias(ruta: str, producto: str = "") -> list[str]:
    """Preguntas sugeridas según la sección de la página donde está el widget."""
    try:
        coincidencia = resolve(ruta or "/")
    except Resolver404:
        return SUGERENCIAS_GENERALES
    producto = nombre_de_producto(producto)
    if coincidencia.app_name == "catalogo" and coincidencia.url_name == "detalle" and producto:
        return [s.format(producto=producto) for s in SUGERENCIAS_PRODUCTO]
    return SUGERENCIAS.get(coincidencia.app_name, SUGERENCIAS_GENERALES)


def ruta_actual(request: HttpRequest) -> str:
    """La página donde está el widget (HTMX manda HX-Current-URL). Solo la ruta y la query,
    y solo si es de este sitio: sirve para las sugerencias y para el ?next= del login."""
    actual = request.headers.get("HX-Current-URL", "")
    if not url_has_allowed_host_and_scheme(
        actual, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return "/"
    partes = urlsplit(actual)
    return partes.path + (f"?{partes.query}" if partes.query else "") or "/"


def conversacion_del_widget(request: HttpRequest) -> str | None:
    return request.session.get(SESION_CONVERSACION)


def usar_en_widget(request: HttpRequest, conversacion_id: str) -> None:
    request.session[SESION_CONVERSACION] = conversacion_id


def olvidar_widget(request: HttpRequest) -> None:
    request.session.pop(SESION_CONVERSACION, None)
    request.session.pop(SESION_PENDIENTE, None)


def marcar_pendiente(request: HttpRequest, conversacion_id: str, pendiente: bool) -> None:
    """Solo para la conversación del widget: las de /agroia/ no le importan."""
    if conversacion_id != conversacion_del_widget(request):
        return
    if pendiente:
        request.session[SESION_PENDIENTE] = True
    else:
        request.session.pop(SESION_PENDIENTE, None)
