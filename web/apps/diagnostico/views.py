"""Diagnóstico por imagen e historial."""

from django import forms
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_http_methods

from apps.cuentas.decoradores import login_requerido
from apps.cuentas.servicios import ErrorApi
from apps.diagnostico import servicios

NO_DISPONIBLE = "El diagnóstico por imagen estará disponible pronto."


class Foto(forms.Form):
    imagen = forms.FileField(
        label="Foto de la hoja o el fruto",
        help_text="JPG o PNG, máximo 5 MB. Que se vea de cerca y con buena luz.",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "file-input file-input-bordered w-full",
                "accept": "image/jpeg,image/png",
            }
        ),
    )

    def clean_imagen(self):
        archivo = self.cleaned_data["imagen"]
        error = servicios.validar_foto(archivo)
        if error:
            raise forms.ValidationError(error)
        return archivo


@login_requerido
@require_http_methods(["GET", "POST"])
def inicio(request: HttpRequest) -> HttpResponse:
    formulario = Foto(request.POST or None, request.FILES or None)
    contexto = {"formulario": formulario, "nombres": servicios.NOMBRES}
    status = 200
    if request.method == "POST":
        if formulario.is_valid():
            try:
                contexto["resultado"] = servicios.diagnosticar(
                    request, formulario.cleaned_data["imagen"]
                )
            except ErrorApi as error:
                if error.codigo == "modelo_no_disponible":
                    contexto["no_disponible"] = NO_DISPONIBLE
                elif error.codigo == "validacion":
                    formulario.add_error("imagen", "No pudimos leer la foto. Prueba con otra.")
                    status = 400
                else:
                    contexto["error"] = error.mensaje
                    status = 503
        else:
            status = 400
    plantilla = (
        "diagnostico/parciales/_resultado.html" if request.htmx else "diagnostico/inicio.html"
    )
    # Con HTMX los errores responden 200: HTMX 2 no reemplaza el contenido con un 4xx.
    return render(request, plantilla, contexto, status=200 if request.htmx else status)


@login_requerido
@require_GET
def historial(request: HttpRequest) -> HttpResponse:
    try:
        pagina = max(int(request.GET.get("page", 1)), 1)
    except ValueError:
        pagina = 1
    try:
        datos = servicios.historial(request, pagina)
    except ErrorApi as error:
        return render(request, "tienda/no_disponible.html", {"texto": error.mensaje}, status=503)
    return render(
        request,
        "diagnostico/historial.html",
        {"diagnosticos": datos, "pagina": pagina, "nombres": servicios.NOMBRES},
    )


@login_requerido
@require_GET
def detalle(request: HttpRequest, diagnostico_id: str) -> HttpResponse:
    try:
        datos = servicios.detalle(request, diagnostico_id)
    except ErrorApi as error:
        if error.estado == 404:
            raise Http404 from error
        return render(request, "tienda/no_disponible.html", {"texto": error.mensaje}, status=503)
    contexto = {
        "diagnostico": datos,
        "nombres": servicios.NOMBRES,
        "sugeridos": servicios.sugeridos(datos.get("clase")),
    }
    return render(request, "diagnostico/detalle.html", contexto)


@login_requerido
@require_GET
def imagen(request: HttpRequest, diagnostico_id: str) -> HttpResponse:
    try:
        contenido, tipo = servicios.imagen(request, diagnostico_id)
    except ErrorApi as error:
        raise Http404 from error
    if not tipo.startswith("image/"):
        raise Http404
    respuesta = HttpResponse(contenido, content_type=tipo)
    # Dato personal: nunca en cachés compartidas.
    respuesta["Cache-Control"] = "private, max-age=3600"
    return respuesta
