"""Lógica de las pantallas de cuenta: llama a svc-usuarios y traduce sus respuestas.

Las vistas solo validan el formulario y muestran el resultado. Los errores de la API
(`{"error", "detalle", "campos"}`) llegan como ErrorApi; `campos` se muestra junto a cada
campo del formulario.
"""

import contextlib
import math
from dataclasses import dataclass, field

from clientes.api import (
    ClienteServicios,
    ServicioNoDisponible,
    SesionApi,
    SesionExpirada,
    actualizar_tokens,
    guardar_sesion,
    ip_del_navegador,
)
from django.http import HttpRequest

# Los códigos que svc-usuarios manda como mensaje de un campo, en palabras.
MENSAJES_DE_CAMPO = {
    "email_registrado": "Ya existe una cuenta con este correo.",
    "password_no_coincide": "Las contraseñas no coinciden.",
    "privacidad_no_aceptada": "Para crear tu cuenta debes aceptar el aviso de privacidad.",
}
NO_DISPONIBLE = "El servicio de cuentas no está disponible. Intenta de nuevo en unos minutos."


@dataclass
class ErrorApi(Exception):
    estado: int
    codigo: str
    detalle: str
    campos: dict[str, list[str]] = field(default_factory=dict)
    espera: int | None = None  # segundos de Retry-After (429)

    @property
    def mensaje(self) -> str:
        """Mensaje general para mostrar arriba del formulario."""
        if self.codigo == "demasiados_intentos":
            if self.espera:
                minutos = math.ceil(self.espera / 60)
                cuando = f"{self.espera} segundos" if self.espera < 120 else f"{minutos} minutos"
                return f"Hiciste demasiados intentos. Espera {cuando} y vuelve a intentarlo."
            return "Hiciste demasiados intentos. Espera un momento y vuelve a intentarlo."
        if self.codigo == "validacion" and self.campos:
            return "Revisa los datos marcados."
        return self.detalle


def _error_de(respuesta) -> ErrorApi:
    try:
        datos = respuesta.json()
    except ValueError:
        datos = {}
    espera = respuesta.headers.get("Retry-After")
    return ErrorApi(
        estado=respuesta.status_code,
        codigo=datos.get("error", "error"),
        detalle=datos.get("detalle") or NO_DISPONIBLE,
        campos=datos.get("campos") or {},
        espera=int(espera) if espera and espera.isdigit() else None,
    )


def _sin_servicio() -> ErrorApi:
    return ErrorApi(estado=503, codigo="servicio_no_disponible", detalle=NO_DISPONIBLE)


def _publico(request: HttpRequest, metodo: str, ruta: str, **datos) -> dict:
    """Llamada sin sesión (login, registro, recuperación), con la IP real del navegador."""
    try:
        respuesta = ClienteServicios().enviar(
            "usuarios", metodo, ruta, ip=ip_del_navegador(request), json=datos
        )
    except ServicioNoDisponible as error:
        raise _sin_servicio() from error
    if respuesta.status_code >= 400:
        raise _error_de(respuesta)
    return respuesta.json() if respuesta.content else {}


def _con_sesion(request: HttpRequest, metodo: str, ruta: str, **opciones) -> dict | list:
    """Llamada con el token de la sesión; renueva sola si venció (SesionExpirada si no)."""
    try:
        respuesta = SesionApi(request).llamar("usuarios", metodo, ruta, **opciones)
    except ServicioNoDisponible as error:
        raise _sin_servicio() from error
    if respuesta.status_code >= 400:
        raise _error_de(respuesta)
    return respuesta.json() if respuesta.content else {}


def mensajes_de_campo(mensajes) -> list[str]:
    if isinstance(mensajes, str):
        mensajes = [mensajes]
    return [MENSAJES_DE_CAMPO.get(str(m), str(m)) for m in mensajes]


# --- Sesión ---------------------------------------------------------------------------


def iniciar_sesion(request: HttpRequest, email: str, password: str) -> dict:
    datos = _publico(request, "POST", "auth/login/", email=email, password=password)
    # Llave de sesión nueva al entrar: evita la fijación de sesión.
    request.session.cycle_key()
    guardar_sesion(request, datos["access"], datos["refresh"], datos["usuario"])
    return datos["usuario"]


def cerrar_sesion(request: HttpRequest) -> None:
    """Mete el refresh a la blacklist y vacía la sesión, aunque svc-usuarios no responda."""
    refresh = request.session.get("refresh")
    if refresh:
        with contextlib.suppress(ServicioNoDisponible, SesionExpirada):
            SesionApi(request).llamar("usuarios", "POST", "auth/logout/", json={"refresh": refresh})
    request.session.flush()


# --- Registro y correo ----------------------------------------------------------------


def registrar(request: HttpRequest, **datos) -> dict:
    return _publico(request, "POST", "auth/registro/", **datos)


def verificar_correo(request: HttpRequest, token: str) -> dict:
    datos = _publico(request, "POST", "auth/verificar-correo/", token=token)
    if request.session.get("refresh"):
        # El token de la sesión todavía dice email_verificado=false: se renueva para que el
        # banner desaparezca. Si ya no se puede, se queda como estaba hasta el próximo login.
        with contextlib.suppress(SesionExpirada, ServicioNoDisponible):
            SesionApi(request).renovar()
    return datos


def reenviar_verificacion(request: HttpRequest, email: str) -> dict:
    return _publico(request, "POST", "auth/reenviar-verificacion/", email=email)


def recuperar(request: HttpRequest, email: str) -> dict:
    return _publico(request, "POST", "auth/recuperar/", email=email)


def restablecer(request: HttpRequest, uid: str, token: str, password: str, confirmacion: str):
    return _publico(
        request,
        "POST",
        "auth/restablecer/",
        uid=uid,
        token=token,
        password=password,
        password_confirmacion=confirmacion,
    )


# --- Mi cuenta ------------------------------------------------------------------------


def perfil(request: HttpRequest) -> dict:
    return _con_sesion(request, "GET", "usuarios/yo/")


def actualizar_perfil(request: HttpRequest, **datos) -> dict:
    perfil_nuevo = _con_sesion(request, "PATCH", "usuarios/yo/", json=datos)
    usuario = dict(request.session.get("usuario") or {})
    usuario["nombre"] = perfil_nuevo.get("nombre", usuario.get("nombre"))
    request.session["usuario"] = usuario
    return perfil_nuevo


def direcciones(request: HttpRequest) -> list[dict]:
    datos = _con_sesion(request, "GET", "usuarios/yo/direcciones/")
    return datos.get("results", []) if isinstance(datos, dict) else datos


def crear_direccion(request: HttpRequest, **datos) -> dict:
    return _con_sesion(request, "POST", "usuarios/yo/direcciones/", json=datos)


def borrar_direccion(request: HttpRequest, direccion_id: int) -> None:
    _con_sesion(request, "DELETE", f"usuarios/yo/direcciones/{direccion_id}/")


def marcar_predeterminada(request: HttpRequest, direccion_id: int) -> dict:
    return _con_sesion(
        request,
        "PATCH",
        f"usuarios/yo/direcciones/{direccion_id}/",
        json={"predeterminada": True},
    )


def cambiar_password(request: HttpRequest, actual: str, nueva: str, confirmacion: str) -> None:
    datos = _con_sesion(
        request,
        "POST",
        "auth/cambiar-password/",
        json={
            "password_actual": actual,
            "password_nueva": nueva,
            "password_confirmacion": confirmacion,
        },
    )
    # Las demás sesiones se cerraron; esta sigue con el par nuevo.
    actualizar_tokens(request, datos["access"], datos["refresh"])
