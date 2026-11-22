"""Eventos entre servicios con Redis Streams (Entrega 4). Ver docs/eventos.md.

Este paquete **no importa Django**: lo usan los servicios Django y también svc-ia
(FastAPI), que instala solo el núcleo de `comun`. Lo propio de Django (publicar después
del commit, la correlación de la petición) está en `agroia_comun.eventos.en_django`.
"""

from agroia_comun.eventos.catalogo import CATALOGO, ErrorEvento, TipoEvento, obtener_tipo
from agroia_comun.eventos.consumidor import Consumidor
from agroia_comun.eventos.productor import publicar, publicar_sobre
from agroia_comun.eventos.sobre import ENCABEZADO_CORRELACION, Sobre, correlacion_valida

__all__ = [
    "CATALOGO",
    "ENCABEZADO_CORRELACION",
    "Consumidor",
    "ErrorEvento",
    "Sobre",
    "TipoEvento",
    "correlacion_valida",
    "obtener_tipo",
    "publicar",
    "publicar_sobre",
]
