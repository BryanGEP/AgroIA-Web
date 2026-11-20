"""Diagnóstico por imagen: el gateway manda la foto a svc-ia y guarda el resultado en
svc-contenido (síncrono; en la Entrega 4 pasará a eventos, como el chat).

Mientras svc-ia no tenga modelo de visión responde 503 `modelo_no_disponible` y no se guarda
nada. El flujo completo (clasificar, guardar, sugerir productos) ya está listo para cuando
devuelva un resultado.
"""

import json
import logging
from dataclasses import dataclass, field

from clientes import tienda
from django.http import HttpRequest

from agroia_comun.seguridad import registrar_evento
from apps.cuentas.servicios import ErrorApi, con_sesion, con_sesion_crudo

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


def diagnosticar(request: HttpRequest, archivo) -> Resultado:
    """Lanza ErrorApi 503 `modelo_no_disponible` mientras no haya modelo."""
    tipo = _tipo(archivo)
    contenido = archivo.read()
    nombre = archivo.name or "foto"
    diagnostico = con_sesion(
        request, "ia", "POST", "diagnostico/", files={"imagen": (nombre, contenido, tipo)}
    )
    resultado = Resultado(diagnostico=diagnostico, sugeridos=sugeridos(diagnostico.get("clase")))
    try:
        guardado = con_sesion(
            request,
            "contenido",
            "POST",
            "diagnosticos/",
            files={"imagen": (nombre, contenido, tipo)},
            data={
                "clase": diagnostico["clase"],
                "confianza": str(diagnostico["confianza"]),
                "probabilidades": json.dumps(diagnostico["probabilidades"]),
                "modelo_version": diagnostico["modelo_version"],
            },
        )
        resultado.diagnostico = {**diagnostico, "id": guardado.get("id")}
    except ErrorApi as error:
        # El resultado existe: se muestra igual, pero no quedó en el historial.
        resultado.guardado = False
        registrar_evento(
            "diagnostico_no_guardado", request, nivel=logging.WARNING, error=error.codigo
        )
    return resultado


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
