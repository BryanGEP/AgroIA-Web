"""Clasificación de imágenes de aguacate: sano, rona o antracnosis.

El modelo de visión todavía no existe en ningún repo; se integrará en una entrega
posterior. Mientras tanto `obtener_clasificador()` devuelve None y POST /diagnostico/
responde 503 `modelo_no_disponible` (el worker publica `diagnostico_fallido` con ese código).
Nunca se presenta un resultado inventado como real: el clasificador de prueba solo existe
en desarrollo, a pedido, y todo lo que da va marcado como prueba.

Para integrar el modelo: implementar una clase con `modelo_version` y `clasificar()` que
cumpla el protocolo `Clasificador` y devolverla desde `obtener_clasificador()`.
"""

import hashlib
from dataclasses import dataclass
from typing import Protocol

CLASES = ("sano", "rona", "antracnosis")


@dataclass(frozen=True)
class ResultadoClasificacion:
    clase: str
    confianza: float
    probabilidades: dict[str, float]


class Clasificador(Protocol):
    modelo_version: str

    def clasificar(self, imagen: bytes) -> ResultadoClasificacion:
        """Clasifica una imagen JPG o PNG ya validada."""
        ...


class ClasificadorDePrueba:
    """SOLO PARA PROBAR EL FLUJO. No mira la imagen como un modelo: reparte las
    probabilidades a partir del hash de los bytes, así la misma foto da siempre lo mismo.
    Se activa con IA_CLASIFICADOR_PRUEBA=1 y solo con DEBUG=True (config.validar). Su
    `modelo_version` empieza con "prueba-": svc-contenido lo marca `es_prueba` y la pantalla
    avisa que no es un diagnóstico real."""

    modelo_version = "prueba-no-es-un-modelo"

    def clasificar(self, imagen: bytes) -> ResultadoClasificacion:
        huella = hashlib.sha256(imagen).digest()
        pesos = [huella[i] + 1 for i in range(len(CLASES))]
        total = sum(pesos)
        probabilidades = {c: round(p / total, 4) for c, p in zip(CLASES, pesos, strict=True)}
        # Que sumen 1 exactamente (svc-contenido lo valida con tolerancia).
        ajuste = round(1 - sum(probabilidades.values()), 4)
        probabilidades[CLASES[0]] = round(probabilidades[CLASES[0]] + ajuste, 4)
        clase = max(probabilidades, key=probabilidades.get)
        return ResultadoClasificacion(clase, probabilidades[clase], probabilidades)


def obtener_clasificador() -> Clasificador | None:
    """Clasificador configurado. Hoy no hay modelo (llega en una entrega posterior): None,
    salvo el de prueba en desarrollo con IA_CLASIFICADOR_PRUEBA=1."""
    from app.config import settings

    if settings.clasificador_prueba and settings.debug:
        return ClasificadorDePrueba()
    return None
