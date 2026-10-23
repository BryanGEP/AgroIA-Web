"""Filtros de plantilla del gateway: precios, ficha técnica y categorías."""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()

# Tinte y nombre de la ilustración por categoría (las clases están en static/css/fuente.css).
CATEGORIAS = {"fungicidas", "fertilizantes", "herramientas", "riego", "proteccion"}

UNIDADES = {"pieza": "pieza", "kg": "kg", "litro": "litro", "costal": "costal"}

ETIQUETAS = {
    "ingrediente_activo": "Ingrediente activo",
    "intervalo_seguridad": "Intervalo de seguridad",
    "categoria_toxicologica": "Categoría toxicológica",
    "materia_organica": "Materia orgánica",
    "proteccion_uv": "Protección UV",
    "corte_maximo": "Corte máximo",
    "longitud_hoja": "Longitud de la hoja",
    "longitud_garrocha": "Longitud de la garrocha",
    "separacion_goteros": "Separación de goteros",
    "caudal_maximo": "Caudal máximo",
    "presion_maxima": "Presión máxima",
    "composicion": "Composición",
    "presentacion": "Presentación",
    "formulacion": "Formulación",
    "aplicacion": "Aplicación",
    "certificacion": "Certificación",
    "conexion": "Conexión",
    "diametro": "Diámetro",
    "incluye_cartuchos": "Incluye cartuchos",
}


@register.filter
def pesos(valor) -> str:
    """Precio en pesos con formato es-MX: 1250.5 → $1,250.50."""
    try:
        cantidad = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    return f"${cantidad:,.2f}"


@register.filter
def unidad(valor: str) -> str:
    return UNIDADES.get(valor, valor or "")


@register.filter
def tinte(slug: str) -> str:
    """Nombre de la categoría para su tinte e ilustración; 'general' si no se conoce."""
    return slug if slug in CATEGORIAS else "general"


@register.simple_tag
def nombre_categoria(slug: str, categorias: list[dict] | None) -> str:
    for categoria in categorias or []:
        if categoria.get("slug") == slug:
            return categoria.get("nombre", slug)
    return (slug or "").replace("-", " ").capitalize()


def _etiqueta(clave: str) -> str:
    if clave in ETIQUETAS:
        return ETIQUETAS[clave]
    if any(letra.isupper() or letra.isdigit() for letra in clave):
        return clave  # símbolos como N, K2O o P2O5
    return clave.replace("_", " ").capitalize()


def _valor(valor) -> str:
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, list):
        return ", ".join(_valor(v) for v in valor)
    return str(valor)


@register.filter
def ficha_filas(ficha) -> list[dict]:
    """La ficha técnica (JSON) como filas legibles; los objetos anidados, como sublista."""
    if not isinstance(ficha, dict):
        return []
    filas = []
    for clave, valor in ficha.items():
        if isinstance(valor, dict):
            filas.append(
                {
                    "etiqueta": _etiqueta(clave),
                    "lista": [(_etiqueta(k), _valor(v)) for k, v in valor.items()],
                }
            )
        else:
            filas.append({"etiqueta": _etiqueta(clave), "valor": _valor(valor)})
    return filas
