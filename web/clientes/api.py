"""Cliente HTTP común del gateway hacia los cuatro servicios internos.

Todo lo que web pide a un servicio pasa por aquí: las pantallas (con la sesión), el proxy
`/api/<servicio>/` (con el token del encabezado) y el catálogo. Siempre con timeout.

`X-Forwarded-For` (condición B4 de la revisión de seguridad, docs/contrato-identidad.md):
web es el borde, así que pone la `REMOTE_ADDR` de la conexión que recibe y nunca reenvía
el `X-Forwarded-For` que mande el cliente. Los servicios confían en el último valor de
ese encabezado para el límite de intentos, el bloqueo de axes y el log de seguridad.
"""

import logging
from dataclasses import dataclass

import httpx
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpRequest

from agroia_comun.eventos import correlacion
from agroia_comun.eventos.sobre import ENCABEZADO_CORRELACION
from agroia_comun.tokens import TokenInvalido, validar_access

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Servicio:
    url: str
    prefijo: str  # se antepone a la ruta: /api/v1/ en los servicios Django, / en svc-ia
    timeout: float


def servicios() -> dict[str, Servicio]:
    return {
        "usuarios": Servicio(settings.URL_SVC_USUARIOS, "/api/v1/", settings.SERVICIOS_TIMEOUT),
        "tienda": Servicio(settings.URL_SVC_TIENDA, "/api/v1/", settings.SERVICIOS_TIMEOUT),
        "contenido": Servicio(settings.URL_SVC_CONTENIDO, "/api/v1/", settings.SERVICIOS_TIMEOUT),
        # El agente puede tardar hasta AGENTE_TIMEOUT (45 s); se deja margen (IA_TIMEOUT, 50 s).
        "ia": Servicio(settings.URL_SVC_IA, "/", settings.IA_TIMEOUT),
    }


class ServicioNoDisponible(Exception):
    """El servicio no respondió o tardó más que su timeout."""

    def __init__(self, servicio: str, tiempo_agotado: bool):
        super().__init__(servicio)
        self.servicio = servicio
        self.tiempo_agotado = tiempo_agotado


class SesionExpirada(Exception):
    """No se pudo renovar el token: la sesión ya se vació. El middleware manda al login."""


def ip_del_navegador(request: HttpRequest) -> str:
    """La IP de la conexión. Nunca se lee el X-Forwarded-For que mande el cliente."""
    return request.META.get("REMOTE_ADDR", "")


def obtener_transporte() -> httpx.BaseTransport | None:
    """Transporte de httpx; las pruebas lo sustituyen por un httpx.MockTransport."""
    return None


class ClienteServicios:
    def __init__(
        self,
        urls: dict[str, Servicio] | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.servicios = urls or servicios()
        self.transport = transport

    def url(self, servicio: str, ruta: str) -> str:
        datos = self.servicios[servicio]
        return datos.url.rstrip("/") + datos.prefijo + ruta.lstrip("/")

    def enviar(
        self,
        servicio: str,
        metodo: str,
        ruta: str,
        *,
        ip: str = "",
        token: str | None = None,
        encabezados: dict[str, str] | None = None,
        **opciones,
    ) -> httpx.Response:
        """Petición a un servicio. `opciones` pasa a httpx (json, content, params...)."""
        datos = self.servicios[servicio]
        cabeceras = dict(encabezados or {})
        if token:
            cabeceras["Authorization"] = f"Bearer {token}"
        if ip:
            cabeceras["X-Forwarded-For"] = ip
        # La correlación de la petición del navegador (ya validada por CorrelacionMiddleware),
        # para seguir el flujo en los servicios y en sus eventos.
        if correlacion.actual():
            cabeceras[ENCABEZADO_CORRELACION] = correlacion.actual()
        try:
            transporte = self.transport or obtener_transporte()
            with httpx.Client(timeout=datos.timeout, transport=transporte) as http:
                return http.request(metodo, self.url(servicio, ruta), headers=cabeceras, **opciones)
        except httpx.TimeoutException as error:
            logger.warning("%s tardó más de %s s", servicio, datos.timeout)
            raise ServicioNoDisponible(servicio, tiempo_agotado=True) from error
        except httpx.HTTPError as error:
            logger.warning("%s no respondió: %s", servicio, type(error).__name__)
            raise ServicioNoDisponible(servicio, tiempo_agotado=False) from error


# --- Sesión del navegador ---------------------------------------------------------------

CLAVES_DE_SESION = ("access", "refresh", "usuario")


def usuario_de_los_claims(claims: dict, nombre: str) -> dict:
    return {
        "id": claims["user_id"],
        "nombre": nombre,
        "rol": claims.get("rol"),
        "email_verificado": claims.get("email_verificado") is True,
    }


def guardar_sesion(request: HttpRequest, access: str, refresh: str, usuario: dict) -> None:
    """Guarda los tokens en la sesión del servidor (web_db). El navegador solo recibe la
    cookie de sesión; los JWT nunca llegan al HTML ni a una cookie."""
    request.session["access"] = access
    request.session["refresh"] = refresh
    request.session["usuario"] = usuario


def actualizar_tokens(request: HttpRequest, access: str, refresh: str) -> None:
    """Par nuevo tras renovar o cambiar la contraseña: los claims del access nuevo
    actualizan el rol y la verificación del correo que muestra el menú."""
    usuario = dict(request.session.get("usuario") or {})
    try:
        claims = validar_access(access, settings.JWT_LLAVE_PUBLICA, settings.JWT_ISSUER)
    except TokenInvalido:
        claims = None
    if claims is not None:
        usuario = usuario_de_los_claims(claims, usuario.get("nombre", ""))
    guardar_sesion(request, access, refresh, usuario)


class SesionApi:
    """Llamadas en nombre del usuario de la sesión, con renovación automática.

    Si un servicio responde 401, renueva una sola vez con el refresh y repite la petición.
    Si la renovación falla, vacía la sesión y lanza SesionExpirada.
    """

    def __init__(self, request: HttpRequest, cliente: ClienteServicios | None = None):
        self.request = request
        self.cliente = cliente or ClienteServicios()

    @property
    def ip(self) -> str:
        return ip_del_navegador(self.request)

    def llamar(self, servicio: str, metodo: str, ruta: str, **opciones) -> httpx.Response:
        access = self.request.session.get("access")
        respuesta = self.cliente.enviar(
            servicio, metodo, ruta, ip=self.ip, token=access, **opciones
        )
        if respuesta.status_code != 401 or not access:
            return respuesta
        self.renovar()
        respuesta = self.cliente.enviar(
            servicio, metodo, ruta, ip=self.ip, token=self.request.session["access"], **opciones
        )
        if respuesta.status_code == 401:
            self.expirar()
        return respuesta

    def renovar(self) -> None:
        refresh = self.request.session.get("refresh")
        if not refresh:
            self.expirar()
        respuesta = self.cliente.enviar(
            "usuarios", "POST", "auth/token/renovar/", ip=self.ip, json={"refresh": refresh}
        )
        if respuesta.status_code == 200:
            datos = respuesta.json()
            actualizar_tokens(self.request, datos["access"], datos["refresh"])
            return
        # Dos peticiones a la vez (por ejemplo, HTMX): la otra ya rotó el refresh y lo
        # guardó en la base. Se adopta el par que guardó en lugar de cerrar la sesión.
        guardada = SessionStore(session_key=self.request.session.session_key).load()
        if guardada.get("refresh") and guardada.get("refresh") != refresh:
            for clave in CLAVES_DE_SESION:
                self.request.session[clave] = guardada.get(clave)
            return
        self.expirar()

    def expirar(self) -> None:
        self.request.session.flush()
        raise SesionExpirada
