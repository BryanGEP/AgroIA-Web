"""Publicar eventos.

    publicar("usuario_registrado", {"usuario_id": "…", "rol": "cliente"}, origen="svc-usuarios")

- Valida el tipo y los datos contra el catálogo: un error ahí sí se lanza (`ErrorEvento`),
  porque es un error de programación.
- Si Redis no responde, **no** lanza: registra `evento_no_publicado` con el sobre (sin los
  campos no registrables) y devuelve None. La operación de negocio ya se confirmó y no se
  debe romper por el bróker. El riesgo (el evento se pierde) y la mejora pendiente
  (outbox) están en docs/eventos.md.
- En los servicios Django se publica después del commit: ver `agroia_comun.eventos.en_django`.
"""

import logging
import time

import redis

from agroia_comun.eventos import conexion, correlacion
from agroia_comun.eventos.catalogo import MAXLEN, STREAM_FALLIDOS, obtener_tipo, politica
from agroia_comun.eventos.registro import motivo_de, registrar
from agroia_comun.eventos.sobre import Sobre, crear_sobre


def _agregar(cliente: redis.Redis, stream: str, sobre: Sobre) -> str:
    """XADD con el recorte del stream: por largo (MAXLEN ~) y, si su política tiene
    retención, también por antigüedad (MINID exacto, los mensajes más viejos que la
    retención).
    El de fallidos no se recorta."""
    if stream == STREAM_FALLIDOS:
        return cliente.xadd(stream, {"sobre": sobre.a_json()})
    retencion = politica(stream).retencion_segundos
    if retencion is None:
        return cliente.xadd(stream, {"sobre": sobre.a_json()}, maxlen=MAXLEN, approximate=True)
    minimo = f"{int((time.time() - retencion) * 1000)}-0"
    transaccion = cliente.pipeline(transaction=True)
    # Exacto: con «~» Redis solo borra nodos completos (unos 100 mensajes) y en un stream
    # chico los datos se quedarían más tiempo que la retención.
    transaccion.xadd(stream, {"sobre": sobre.a_json()}, minid=minimo, approximate=False)
    transaccion.xtrim(stream, maxlen=MAXLEN, approximate=True)
    return transaccion.execute()[0]


def publicar(
    tipo: str,
    datos: dict,
    *,
    origen: str,
    correlacion_id=None,
    cliente: redis.Redis | None = None,
) -> Sobre | None:
    """Publica y devuelve el sobre, o None si Redis no respondió. Sin `correlacion_id`, usa
    la de la petición o el evento en curso (ver correlacion.py)."""
    if correlacion_id is None:
        correlacion_id = correlacion.actual()
    sobre = crear_sobre(tipo, datos, origen, correlacion_id)
    return publicar_sobre(sobre, cliente=cliente)


def publicar_sobre(
    sobre: Sobre, *, cliente: redis.Redis | None = None, suceso: str = "evento_publicado"
) -> Sobre | None:
    """Publica un sobre ya armado en el stream de su tipo, con su mismo id. Lo usa
    también el reproceso de fallidos."""
    definicion = obtener_tipo(sobre.tipo)
    cliente = cliente or conexion.cliente()
    try:
        id_mensaje = _agregar(cliente, definicion.stream, sobre)
    except redis.RedisError as error:
        registrar(
            "evento_no_publicado",
            logging.ERROR,
            **sobre.para_log(),
            stream=definicion.stream,
            motivo=motivo_de(error),
            fecha_evento=sobre.fecha,
            datos=definicion.registrable(sobre.datos),
        )
        return None
    registrar(suceso, **sobre.para_log(), stream=definicion.stream, id_mensaje=id_mensaje)
    return sobre
