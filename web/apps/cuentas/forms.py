"""Formularios de las pantallas de cuenta. Validan lo básico en el gateway; las reglas
(contraseña segura, correo repetido...) las decide svc-usuarios y sus errores se agregan a
cada campo con `agregar_errores_de_api`."""

from django import forms

from apps.cuentas.servicios import ErrorApi, mensajes_de_campo

ENTRADA = "input input-bordered w-full"
CASILLA = "checkbox checkbox-primary"


def _texto(etiqueta: str, autocompletar: str, **extra) -> forms.CharField:
    return forms.CharField(
        label=etiqueta,
        widget=forms.TextInput(attrs={"class": ENTRADA, "autocomplete": autocompletar}),
        **extra,
    )


def _correo() -> forms.EmailField:
    return forms.EmailField(
        label="Correo",
        max_length=254,
        widget=forms.EmailInput(attrs={"class": ENTRADA, "autocomplete": "email"}),
    )


def _clave(etiqueta: str, autocompletar: str) -> forms.CharField:
    return forms.CharField(
        label=etiqueta,
        max_length=128,
        strip=False,
        widget=forms.PasswordInput(attrs={"class": ENTRADA, "autocomplete": autocompletar}),
    )


class FormularioApi(forms.Form):
    # Nombre del campo en la API -> nombre del campo en el formulario, cuando difieren.
    campos_api: dict[str, str] = {}

    def add_error(self, field, error):
        """Además del error, marca el campo para lectores de pantalla y en rojo."""
        super().add_error(field, error)
        for nombre in [field] if field else []:
            if nombre in self.fields:
                atributos = self.fields[nombre].widget.attrs
                atributos["aria-invalid"] = "true"
                atributos["aria-describedby"] = f"id_{nombre}-error"
                if "input-error" not in atributos.get(
                    "class", ""
                ) and "checkbox" not in atributos.get("class", ""):
                    atributos["class"] = atributos.get("class", "") + " input-error"

    def agregar_errores_de_api(self, error: ErrorApi) -> None:
        if not error.campos:
            self.add_error(None, error.mensaje)
            return
        for campo, mensajes in error.campos.items():
            nombre = self.campos_api.get(campo, campo)
            self.add_error(nombre if nombre in self.fields else None, mensajes_de_campo(mensajes))


class IniciarSesion(FormularioApi):
    # CharField y no EmailField: el error de formato también lo responde la API igual que
    # unas credenciales inválidas, para no dar pistas.
    email = forms.CharField(
        label="Correo",
        max_length=254,
        widget=forms.EmailInput(attrs={"class": ENTRADA, "autocomplete": "username"}),
    )
    password = _clave("Contraseña", "current-password")


class Registro(FormularioApi):
    nombre = _texto("Nombre", "given-name", max_length=150)
    apellidos = _texto("Apellidos", "family-name", max_length=150, required=False)
    email = _correo()
    password = _clave("Contraseña", "new-password")
    password_confirmacion = _clave("Repite la contraseña", "new-password")
    acepto_privacidad = forms.BooleanField(
        label="Leí y acepto el aviso de privacidad",
        required=True,
        error_messages={"required": "Para crear tu cuenta debes aceptar el aviso de privacidad."},
        widget=forms.CheckboxInput(attrs={"class": CASILLA}),
    )


class Correo(FormularioApi):
    email = _correo()


class Restablecer(FormularioApi):
    password = _clave("Contraseña nueva", "new-password")
    password_confirmacion = _clave("Repite la contraseña nueva", "new-password")


class CambiarPassword(FormularioApi):
    password_actual = _clave("Contraseña actual", "current-password")
    password_nueva = _clave("Contraseña nueva", "new-password")
    password_confirmacion = _clave("Repite la contraseña nueva", "new-password")


class Perfil(FormularioApi):
    nombre = _texto("Nombre", "given-name", max_length=150)
    apellidos = _texto("Apellidos", "family-name", max_length=150, required=False)
    telefono = _texto(
        "Teléfono", "tel", max_length=16, required=False, help_text="10 a 15 dígitos."
    )


class Direccion(FormularioApi):
    alias = _texto(
        "Nombre de la dirección",
        "off",
        max_length=50,
        required=False,
        help_text="Por ejemplo, «Huerta» o «Casa».",
    )
    calle = _texto("Calle", "address-line1", max_length=150)
    numero = _texto("Número", "off", max_length=20)
    colonia = _texto("Colonia", "address-level3", max_length=100)
    municipio = _texto("Municipio", "address-level2", max_length=100)
    estado = _texto("Estado", "address-level1", max_length=100)
    codigo_postal = _texto("Código postal", "postal-code", max_length=5)
    referencias = _texto("Referencias", "off", max_length=255, required=False)
    predeterminada = forms.BooleanField(
        label="Usar como dirección predeterminada",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": CASILLA}),
    )
