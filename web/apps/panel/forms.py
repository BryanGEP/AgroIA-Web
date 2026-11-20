"""Formularios del panel. Validan lo básico; las reglas las decide cada servicio."""

import json

from django import forms

from apps.cuentas.forms import CASILLA, ENTRADA, FormularioApi
from apps.panel.servicios import UNIDADES

TIPOS_DE_IMAGEN = {"image/jpeg", "image/png", "image/webp"}


class Producto(FormularioApi):
    nombre = forms.CharField(
        label="Nombre", max_length=150, widget=forms.TextInput(attrs={"class": ENTRADA})
    )
    categoria = forms.ChoiceField(
        label="Categoría", widget=forms.Select(attrs={"class": "select select-bordered w-full"})
    )
    precio = forms.DecimalField(
        label="Precio (pesos)",
        min_value=0,
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": ENTRADA, "step": "0.01"}),
    )
    stock = forms.IntegerField(
        label="Existencias", min_value=0, widget=forms.NumberInput(attrs={"class": ENTRADA})
    )
    unidad = forms.ChoiceField(
        label="Unidad",
        choices=UNIDADES,
        widget=forms.Select(attrs={"class": "select select-bordered w-full"}),
    )
    descripcion = forms.CharField(
        label="Descripción",
        required=False,
        widget=forms.Textarea(attrs={"class": "textarea textarea-bordered w-full", "rows": 3}),
    )
    ficha_tecnica = forms.CharField(
        label="Ficha técnica (JSON)",
        required=False,
        help_text='Un objeto JSON, por ejemplo {"ingrediente_activo": "Oxicloruro de cobre"}.',
        widget=forms.Textarea(
            attrs={"class": "textarea textarea-bordered w-full font-mono text-sm", "rows": 5}
        ),
    )
    imagen = forms.FileField(
        label="Imagen",
        required=False,
        help_text="JPG, PNG o WebP, máximo 5 MB.",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "file-input file-input-bordered w-full",
                "accept": "image/jpeg,image/png,image/webp",
            }
        ),
    )
    activo = forms.BooleanField(
        label="Visible en la tienda",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": CASILLA}),
    )

    def __init__(self, *args, categorias=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].choices = [(c["slug"], c["nombre"]) for c in categorias]

    def clean_ficha_tecnica(self):
        texto = (self.cleaned_data.get("ficha_tecnica") or "").strip()
        if not texto:
            return {}
        try:
            valor = json.loads(texto)
        except json.JSONDecodeError as error:
            raise forms.ValidationError(f"No es JSON válido (línea {error.lineno}).") from error
        if not isinstance(valor, dict):
            raise forms.ValidationError('Debe ser un objeto JSON: {"clave": "valor"}.')
        return valor

    def clean_imagen(self):
        imagen = self.cleaned_data.get("imagen")
        if not imagen:
            return None
        if imagen.size > 5 * 1024 * 1024:
            raise forms.ValidationError("La imagen pesa más de 5 MB.")
        if imagen.content_type not in TIPOS_DE_IMAGEN:
            raise forms.ValidationError("Elige una imagen JPG, PNG o WebP.")
        return imagen

    def datos_para_api(self) -> dict:
        datos = {
            c: self.cleaned_data[c]
            for c in (
                "nombre",
                "categoria",
                "stock",
                "unidad",
                "descripcion",
                "ficha_tecnica",
                "activo",
            )
        }
        datos["precio"] = str(self.cleaned_data["precio"])
        return datos


class Categoria(FormularioApi):
    nombre = forms.CharField(
        label="Nombre", max_length=100, widget=forms.TextInput(attrs={"class": ENTRADA})
    )
    descripcion = forms.CharField(
        label="Descripción",
        required=False,
        widget=forms.Textarea(attrs={"class": "textarea textarea-bordered w-full", "rows": 3}),
    )
    activa = forms.BooleanField(
        label="Visible en la tienda",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": CASILLA}),
    )
