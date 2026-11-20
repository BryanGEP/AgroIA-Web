"""Pantallas de cuenta: iniciar sesión, registro, verificación, recuperación, mi cuenta y
cambio de contraseña. Los enlaces de los correos de svc-usuarios (FRONTEND_URL) llegan a
/verificar-correo/?token=..., /restablecer/<uid>/<token>/ y /recuperar/."""

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from apps.cuentas import servicios
from apps.cuentas.decoradores import login_requerido, redirigir
from apps.cuentas.forms import (
    CambiarPassword,
    Correo,
    Direccion,
    IniciarSesion,
    Perfil,
    Registro,
    Restablecer,
)
from apps.cuentas.servicios import ErrorApi


def _destino_seguro(request: HttpRequest, destino: str | None) -> str:
    """El ?next= solo si es una ruta de este sitio (evita redirecciones a otro dominio)."""
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return destino
    return reverse("paginas:inicio")


@require_http_methods(["GET", "POST"])
def iniciar_sesion(request: HttpRequest) -> HttpResponse:
    siguiente = request.POST.get("next") or request.GET.get("next", "")
    if request.session.get("access"):
        return redirect(_destino_seguro(request, siguiente))
    formulario = IniciarSesion(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        try:
            usuario = servicios.iniciar_sesion(
                request, formulario.cleaned_data["email"], formulario.cleaned_data["password"]
            )
        except ErrorApi as error:
            formulario.agregar_errores_de_api(error)
        else:
            messages.success(request, f"Hola, {usuario['nombre']}.")
            return redirect(_destino_seguro(request, siguiente))
    return render(
        request, "cuentas/iniciar_sesion.html", {"formulario": formulario, "next": siguiente}
    )


@require_POST
def cerrar_sesion(request: HttpRequest) -> HttpResponse:
    servicios.cerrar_sesion(request)
    messages.success(request, "Cerraste sesión.")
    return redirect("paginas:inicio")


@require_http_methods(["GET", "POST"])
def registro(request: HttpRequest) -> HttpResponse:
    formulario = Registro(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        try:
            servicios.registrar(request, **formulario.cleaned_data)
        except ErrorApi as error:
            formulario.agregar_errores_de_api(error)
        else:
            return render(
                request,
                "cuentas/aviso.html",
                {
                    "titulo": "Revisa tu correo",
                    "texto": (
                        f"Te enviamos un enlace a {formulario.cleaned_data['email']} para "
                        "verificar tu cuenta. Mientras tanto ya puedes iniciar sesión."
                    ),
                    "enlace": reverse("cuentas:iniciar_sesion"),
                    "accion": "Iniciar sesión",
                },
                status=201,
            )
    return render(request, "cuentas/registro.html", {"formulario": formulario})


@require_http_methods(["GET"])
def verificar_correo(request: HttpRequest) -> HttpResponse:
    token = request.GET.get("token", "")
    contexto = {"enlace": reverse("cuentas:reenviar_verificacion"), "accion": "Pedir otro enlace"}
    if not token:
        contexto.update(titulo="Enlace incompleto", texto="Abre el enlace completo del correo.")
        return render(request, "cuentas/aviso.html", contexto, status=400)
    try:
        datos = servicios.verificar_correo(request, token)
    except ErrorApi as error:
        if error.codigo == "token_expirado":
            contexto.update(
                titulo="El enlace ya venció",
                texto="Los enlaces de verificación duran 24 horas. Pide uno nuevo.",
            )
        elif error.estado >= 500:
            contexto.update(
                titulo="No pudimos verificar tu correo",
                texto=error.mensaje,
                enlace=request.get_full_path(),
                accion="Intentar de nuevo",
            )
        else:
            contexto.update(
                titulo="El enlace no es válido",
                texto="Puede que esté incompleto o que ya no sirva. Pide uno nuevo.",
            )
        return render(request, "cuentas/aviso.html", contexto, status=error.estado)
    contexto.update(
        titulo="¡Listo!" if datos.get("mensaje") == "Correo verificado." else "Todo en orden",
        texto=datos.get("mensaje", "Tu correo está verificado.") + " Ya puedes comprar.",
        enlace=reverse("catalogo:lista"),
        accion="Ir al catálogo",
    )
    return render(request, "cuentas/aviso.html", contexto)


def _formulario_de_correo(request: HttpRequest, plantilla: str, accion) -> HttpResponse:
    inicial = {"email": request.GET.get("email", "")}
    formulario = Correo(request.POST or None, initial=inicial)
    if request.method == "POST" and formulario.is_valid():
        try:
            datos = accion(request, formulario.cleaned_data["email"])
        except ErrorApi as error:
            formulario.agregar_errores_de_api(error)
        else:
            messages.success(request, datos.get("mensaje", "Listo."))
            return redirect(request.path)
    return render(request, plantilla, {"formulario": formulario})


@require_http_methods(["GET", "POST"])
def reenviar_verificacion(request: HttpRequest) -> HttpResponse:
    if (
        request.method == "POST"
        and request.POST.get("desde_banner")
        and request.session.get("usuario")
    ):
        # El botón del banner: reenvía al correo de la cuenta sin pedirlo otra vez.
        return _reenviar_desde_banner(request)
    return _formulario_de_correo(
        request, "cuentas/reenviar_verificacion.html", servicios.reenviar_verificacion
    )


def _reenviar_desde_banner(request: HttpRequest) -> HttpResponse:
    try:
        perfil = servicios.perfil(request)
        datos = servicios.reenviar_verificacion(request, perfil["email"])
    except ErrorApi as error:
        messages.error(request, error.mensaje)
    else:
        messages.success(request, datos.get("mensaje", "Te enviamos un enlace nuevo."))
    return redirigir(request, _destino_seguro(request, request.POST.get("next")))


@require_http_methods(["GET", "POST"])
def recuperar(request: HttpRequest) -> HttpResponse:
    return _formulario_de_correo(request, "cuentas/recuperar.html", servicios.recuperar)


@require_http_methods(["GET", "POST"])
def restablecer(request: HttpRequest, uid: str, token: str) -> HttpResponse:
    formulario = Restablecer(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        try:
            servicios.restablecer(
                request,
                uid,
                token,
                formulario.cleaned_data["password"],
                formulario.cleaned_data["password_confirmacion"],
            )
        except ErrorApi as error:
            if error.codigo == "enlace_invalido":
                return render(
                    request,
                    "cuentas/aviso.html",
                    {
                        "titulo": "El enlace ya no sirve",
                        "texto": error.detalle,
                        "enlace": reverse("cuentas:recuperar"),
                        "accion": "Pedir otro enlace",
                    },
                    status=400,
                )
            formulario.agregar_errores_de_api(error)
        else:
            # Se cerraron todas las sesiones, también la de este navegador si había.
            request.session.flush()
            messages.success(request, "Contraseña restablecida. Inicia sesión con la nueva.")
            return redirect("cuentas:iniciar_sesion")
    return render(request, "cuentas/restablecer.html", {"formulario": formulario})


# --- Mi cuenta --------------------------------------------------------------------------


def _mi_cuenta(request: HttpRequest, perfil_form=None, direccion_form=None, status=200):
    perfil = servicios.perfil(request)
    contexto = {
        "perfil": perfil,
        "formulario_perfil": perfil_form
        or Perfil(initial={c: perfil.get(c, "") for c in ("nombre", "apellidos", "telefono")}),
        "formulario_direccion": direccion_form or Direccion(),
        "direcciones": servicios.direcciones(request),
    }
    return render(request, "cuentas/mi_cuenta.html", contexto, status=status)


@login_requerido
@require_http_methods(["GET", "POST"])
def mi_cuenta(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return _mi_cuenta(request)
    formulario = Perfil(request.POST)
    if formulario.is_valid():
        try:
            servicios.actualizar_perfil(request, **formulario.cleaned_data)
        except ErrorApi as error:
            formulario.agregar_errores_de_api(error)
        else:
            messages.success(request, "Guardamos tus datos.")
            return redirect("cuentas:mi_cuenta")
    return _mi_cuenta(request, perfil_form=formulario, status=400)


def _lista_de_direcciones(request: HttpRequest, formulario=None, status=200) -> HttpResponse:
    """Con HTMX solo la sección de direcciones; sin JavaScript, la página completa.

    Con HTMX los errores del formulario responden 200: HTMX 2 no reemplaza el contenido
    cuando la respuesta es 4xx, y el formulario con sus errores debe verse.
    """
    if request.htmx:
        contexto = {
            "direcciones": servicios.direcciones(request),
            "formulario_direccion": formulario or Direccion(),
        }
        return render(request, "cuentas/parciales/_direcciones.html", contexto)
    if status == 200:
        return redirect(reverse("cuentas:mi_cuenta") + "#direcciones")
    return _mi_cuenta(request, direccion_form=formulario, status=status)


@login_requerido
@require_POST
def agregar_direccion(request: HttpRequest) -> HttpResponse:
    formulario = Direccion(request.POST)
    if formulario.is_valid():
        try:
            servicios.crear_direccion(request, **formulario.cleaned_data)
        except ErrorApi as error:
            formulario.agregar_errores_de_api(error)
        else:
            if not request.htmx:  # con HTMX el cambio ya se ve en la lista
                messages.success(request, "Agregamos la dirección.")
            return _lista_de_direcciones(request)
    return _lista_de_direcciones(request, formulario, status=400)


@login_requerido
@require_POST
def borrar_direccion(request: HttpRequest, direccion_id: int) -> HttpResponse:
    try:
        servicios.borrar_direccion(request, direccion_id)
    except ErrorApi as error:
        messages.error(request, error.mensaje)
    else:
        if not request.htmx:
            messages.success(request, "Borramos la dirección.")
    return _lista_de_direcciones(request)


@login_requerido
@require_POST
def predeterminada(request: HttpRequest, direccion_id: int) -> HttpResponse:
    try:
        servicios.marcar_predeterminada(request, direccion_id)
    except ErrorApi as error:
        messages.error(request, error.mensaje)
    return _lista_de_direcciones(request)


@login_requerido
@require_http_methods(["GET", "POST"])
def cambiar_password(request: HttpRequest) -> HttpResponse:
    formulario = CambiarPassword(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        try:
            servicios.cambiar_password(
                request,
                formulario.cleaned_data["password_actual"],
                formulario.cleaned_data["password_nueva"],
                formulario.cleaned_data["password_confirmacion"],
            )
        except ErrorApi as error:
            formulario.agregar_errores_de_api(error)
        else:
            messages.success(
                request, "Cambiamos tu contraseña y cerramos la sesión en tus otros dispositivos."
            )
            return redirect("cuentas:mi_cuenta")
    return render(request, "cuentas/cambiar_password.html", {"formulario": formulario})
