"""Log de eventos: una línea JSON por suceso en el logger `eventos`.

Registra el sobre sin sus datos (id, tipo, origen, correlación), más el grupo, el intento
y el motivo de un error. Nunca escribe los datos del evento, salvo en
`evento_no_publicado`, que necesita el sobre completo para poder republicarlo a mano; y
aun ahí quita los campos `no_registrables` de su tipo.
"""

import json
import logging
from datetime import UTC, datetime

logger = logging.getLogger("eventos")

LARGO_MAXIMO_MOTIVO = 300


def motivo_de(error: BaseException) -> str:
    texto = f"{type(error).__name__}: {error}"
    return texto[:LARGO_MAXIMO_MOTIVO]


def registrar(suceso: str, nivel: int = logging.INFO, **campos) -> None:
    linea = {"evento": suceso, "fecha": datetime.now(UTC).isoformat(timespec="seconds")}
    linea.update({k: v for k, v in campos.items() if v is not None})
    logger.log(nivel, json.dumps(linea, ensure_ascii=False, default=str))
