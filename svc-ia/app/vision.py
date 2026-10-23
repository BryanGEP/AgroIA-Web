"""Clasificación de imágenes de aguacate: sano, rona o antracnosis.

El modelo de visión todavía no existe en ningún repo; se integrará en una entrega
posterior. Mientras tanto `obtener_clasificador()` devuelve None y POST /diagnostico/
responde 503 `modelo_no_disponible`. Nunca se generan resultados aleatorios ni falsos.

Para integrar el modelo: implementar una clase con `modelo_version` y `clasificar()` que
cumpla el protocolo `Clasificador` y devolverla desde `obtener_clasificador()`.
"""

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


def obtener_clasificador() -> Clasificador | None:
    """Clasificador configurado; hoy ninguno (llega en una entrega posterior)."""
    return None
