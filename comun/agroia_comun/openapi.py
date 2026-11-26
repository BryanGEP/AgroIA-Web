"""Documentación OpenAPI de las respuestas de error, común a los servicios Django.

Las vistas declaran sus errores solo con una descripción, por ejemplo
`409: OpenApiResponse(description="`stock_insuficiente` o `producto_no_disponible`.")`.
Este hook de drf-spectacular completa cada respuesta 4xx/5xx que no trae contenido con:

- el esquema común `Error` (`{"error", "detalle", "campos"?}`, ver errores.py), y
- un ejemplo por cada código de error: los que la descripción menciona entre comillas
  invertidas, o el código por omisión de ese estado HTTP.

Así el formato y los ejemplos de error viven en un solo lugar.

Uso en config/settings.py:

    SPECTACULAR_SETTINGS = {
        ...,
        "POSTPROCESSING_HOOKS": [
            "drf_spectacular.hooks.postprocess_schema_enums",
            "agroia_comun.openapi.documentar_errores",
        ],
    }
"""

import re

ESQUEMA_ERROR = {
    "type": "object",
    "description": "Formato común de errores de AgroIA-Web.",
    "properties": {
        "error": {"type": "string", "description": "Código corto del error."},
        "detalle": {"type": "string", "description": "Mensaje para el usuario."},
        "campos": {
            "type": "object",
            "description": "Solo en `validacion`: mensajes por campo.",
            "additionalProperties": True,
        },
    },
    "required": ["error", "detalle"],
}

# Código por omisión de cada estado HTTP cuando la descripción no menciona uno.
CODIGO_POR_ESTADO = {
    "400": "validacion",
    "401": "no_autenticado",
    "403": "sin_permiso",
    "404": "no_encontrado",
    "405": "metodo_no_permitido",
    "429": "demasiados_intentos",
}
# Para un 409 sin código en la descripción no hay un código genérico; se usa este texto.
DETALLE_GENERICO = "No se pudo completar la acción."

# Mensajes de ejemplo. Los de negocio son los que lanzan los servicios.py.
DETALLES = {
    "validacion": "Revisa los datos enviados.",
    "json_invalido": "El cuerpo de la petición no es válido.",
    "no_autenticado": "No se proporcionaron las credenciales de autenticación.",
    "token_invalido": "El token no es válido o ya venció.",
    "sin_permiso": "No tienes permiso para realizar esta acción.",
    "no_encontrado": "No se encontró el recurso solicitado.",
    "metodo_no_permitido": "Método no permitido en esta ruta.",
    "demasiados_intentos": "Demasiados intentos. Intenta de nuevo en 60 segundos.",
    "email_no_verificado": "Verifica tu correo para poder hacer esta acción.",
    "credenciales_invalidas": "Correo o contraseña incorrectos.",
    "refresh_invalido": "La sesión no es válida o ya venció. Inicia sesión de nuevo.",
    "cuenta_bloqueada_temporalmente": (
        "Demasiados intentos fallidos. Intenta de nuevo en 15 minutos o restablece tu contraseña."
    ),
    "token_expirado": "El enlace de verificación ya venció. Pide uno nuevo.",
    "enlace_invalido": "El enlace no es válido o ya expiró. Solicita uno nuevo.",
    "password_actual_incorrecta": "La contraseña actual no es correcta.",
    "password_repetida": "La nueva contraseña debe ser distinta de la actual.",
    "auto_degradacion": "No puedes quitarte tu propio rol de administrador.",
    "carrito_vacio": "Tu carrito está vacío.",
    "stock_insuficiente": (
        "No hay suficiente stock de «Oxicloruro de cobre 50% PH 1 kg»: pediste 40 y quedan 30."
    ),
    "producto_no_disponible": (
        "El producto «Oxicloruro de cobre 50% PH 1 kg» ya no está disponible."
    ),
    "transicion_invalida": "Un pedido entregado no puede pasar a «cancelado».",
    "conversacion_llena": "La conversación llegó al límite de 200 mensajes; inicia una nueva.",
}

# Solo estos códigos se toman de las descripciones: entre comillas invertidas también
# aparecen nombres de campos (`nombre`, `precio_min`...), que no son errores.
_CODIGO_EN_TEXTO = re.compile(r"`([a-z][a-z_]+)`")


def _ejemplo(codigo: str) -> dict:
    valor = {"error": codigo, "detalle": DETALLES.get(codigo, DETALLE_GENERICO)}
    if codigo == "validacion":
        valor["campos"] = {"campo": ["Este campo es requerido."]}
    return {"summary": codigo, "value": valor}


def _codigos(estado: str, descripcion: str) -> list[str]:
    """Códigos mencionados en la descripción (sin repetir); si no hay, el del estado."""
    vistos: list[str] = []
    for codigo in _CODIGO_EN_TEXTO.findall(descripcion or ""):
        if codigo in DETALLES and codigo not in vistos:
            vistos.append(codigo)
    if not vistos:
        vistos.append(CODIGO_POR_ESTADO.get(estado, "error_" + estado))
    return vistos


def documentar_errores(result, generator, request, public):
    """Hook de drf-spectacular: esquema `Error` y ejemplos en las respuestas de error."""
    esquemas = result.setdefault("components", {}).setdefault("schemas", {})
    esquemas.setdefault("Error", ESQUEMA_ERROR)
    for operaciones in result.get("paths", {}).values():
        for operacion in operaciones.values():
            if not isinstance(operacion, dict):
                continue
            for estado, respuesta in operacion.get("responses", {}).items():
                if str(estado)[:1] not in ("4", "5") or respuesta.get("content"):
                    continue
                codigos = _codigos(str(estado), respuesta.get("description", ""))
                ejemplos = {c: _ejemplo(c) for c in codigos}
                respuesta["content"] = {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Error"},
                        "examples": ejemplos,
                    }
                }
    return result
