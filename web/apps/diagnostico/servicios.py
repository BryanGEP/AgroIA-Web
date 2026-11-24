"""Diagnóstico por imagen, asíncrono (Entrega 4): el gateway manda la foto a svc-contenido
(`POST diagnosticos/solicitar/`), que la guarda y publica `diagnostico_solicitado`; el worker
de svc-ia clasifica y publica el resultado, y la pantalla consulta el estado
(`GET diagnosticos/<id>/`) con HTMX hasta `listo` o `fallido`.

Mientras no haya modelo de visión, el worker publica `diagnostico_fallido` con
`modelo_no_disponible`: se muestra «estará disponible pronto» y no queda la foto. Un
resultado del clasificador de prueba (solo en desarrollo) trae `es_prueba` y la pantalla
avisa que no es un diagnóstico real.
"""

from dataclasses import dataclass, field

from clientes import tienda
from django.http import HttpRequest

from apps.cuentas.servicios import con_sesion, con_sesion_crudo

TAMANO_MAXIMO = 5 * 1024 * 1024
TIPOS = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG\r\n\x1a\n"}
NOMBRES = {"sano": "Sano", "rona": "Roña", "antracnosis": "Antracnosis"}
# Productos sugeridos por clase: los fungicidas cúpricos sirven para roña y antracnosis.
SUGERENCIAS = {
    "rona": {"categoria": "fungicidas", "disponible": "true"},
    "antracnosis": {"categoria": "fungicidas", "disponible": "true"},
}
MAX_SUGERIDOS = 4


@dataclass
class Resultado:
    diagnostico: dict
    guardado: bool = True
    sugeridos: list[dict] = field(default_factory=list)


def validar_foto(archivo) -> str | None:
    """Mensaje de error si la foto no es JPG o PNG de hasta 5 MB (también revisa la firma
    del archivo, no solo su nombre)."""
    if archivo.size > TAMANO_MAXIMO:
        return "La foto pesa más de 5 MB."
    inicio = archivo.read(8)
    archivo.seek(0)
    if not any(inicio.startswith(firma) for firma in TIPOS.values()):
        return "Elige una foto JPG o PNG."
    return None


def _tipo(archivo) -> str:
    archivo.seek(0)
    inicio = archivo.read(8)
    archivo.seek(0)
    return next(tipo for tipo, firma in TIPOS.items() if inicio.startswith(firma))


def sugeridos(clase: str) -> list[dict]:
    filtros = SUGERENCIAS.get(clase)
    if not filtros:
        return []
    try:
        return tienda.obtener_cliente().productos(filtros).get("results", [])[:MAX_SUGERIDOS]
    except (tienda.TiendaNoDisponible, tienda.NoEncontrado):
        return []


def solicitar(request: HttpRequest, archivo) -> dict:
    """Manda la foto a svc-contenido, que la guarda y pide el diagnóstico al worker de svc-ia
    por eventos. Devuelve el diagnóstico `pendiente` (o `fallido` si no se pudo pedir)."""
    tipo = _tipo(archivo)
    contenido = archivo.read()
    return con_sesion(
        request,
        "contenido",
        "POST",
        "diagnosticos/solicitar/",
        files={"imagen": (archivo.name or "foto", contenido, tipo)},
    )


def intervalo(diagnostico: dict) -> int:
    """Igual que el chat: cada 2 s los primeros 20 s, después cada 5 s."""
    from apps.agroia.servicios import intervalo as intervalo_del_chat

    return intervalo_del_chat({"creada_en": diagnostico.get("creado_en")})


def historial(request: HttpRequest, pagina: int = 1) -> dict:
    return con_sesion(request, "contenido", "GET", "diagnosticos/", params={"page": pagina})


def detalle(request: HttpRequest, diagnostico_id: str) -> dict:
    return con_sesion(request, "contenido", "GET", f"diagnosticos/{diagnostico_id}/")


def imagen(request: HttpRequest, diagnostico_id: str):
    """La foto, pedida a svc-contenido con el token del usuario: svc-contenido comprueba que
    sea del dueño o de un administrador. El gateway no conoce la ruta del archivo."""
    respuesta = con_sesion_crudo(
        request, "contenido", "GET", f"diagnosticos/{diagnostico_id}/imagen/"
    )
    return respuesta.content, respuesta.headers.get("content-type", "")
