"""El sobre común de todos los eventos.

    {"id", "tipo", "version", "fecha", "origen", "correlacion_id", "datos"}

En el stream se guarda como un solo campo, `sobre`, con el JSON. `id` lo genera quien
publica y se conserva al reprocesar: es lo que usa la idempotencia de los consumidores.
`correlacion_id` sigue un flujo entre servicios; solo se acepta si es un UUID válido.
"""

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from agroia_comun.eventos.catalogo import ErrorEvento, obtener_tipo

ENCABEZADO_CORRELACION = "X-Correlacion-Id"


def correlacion_valida(valor) -> str:
    """El valor si es un UUID válido (normalizado); si no, uno nuevo."""
    if valor:
        try:
            return str(uuid.UUID(str(valor).strip()))
        except ValueError:
            pass
    return str(uuid.uuid4())


@dataclass(frozen=True)
class Sobre:
    id: str
    tipo: str
    version: int
    fecha: str
    origen: str
    correlacion_id: str
    datos: dict

    def a_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def de_json(cls, texto: str | bytes) -> "Sobre":
        try:
            crudo = json.loads(texto)
            return cls(
                id=str(crudo["id"]),
                tipo=str(crudo["tipo"]),
                version=int(crudo["version"]),
                fecha=str(crudo["fecha"]),
                origen=str(crudo["origen"]),
                correlacion_id=str(crudo["correlacion_id"]),
                datos=dict(crudo["datos"]),
            )
        except (ValueError, KeyError, TypeError) as error:
            raise ErrorEvento(f"Sobre inválido: {type(error).__name__}.") from error

    def para_log(self) -> dict:
        """Lo que sí se puede registrar: todo menos los datos."""
        return {
            "evento_id": self.id,
            "tipo": self.tipo,
            "version": self.version,
            "origen": self.origen,
            "correlacion_id": self.correlacion_id,
        }


def crear_sobre(tipo: str, datos: dict, origen: str, correlacion_id=None) -> Sobre:
    definicion = obtener_tipo(tipo)
    definicion.validar_datos(datos)
    if not origen:
        raise ErrorEvento("Falta el servicio de origen del evento.")
    return Sobre(
        id=str(uuid.uuid4()),
        tipo=tipo,
        version=definicion.version,
        fecha=datetime.now(UTC).isoformat(timespec="milliseconds"),
        origen=origen,
        correlacion_id=correlacion_valida(correlacion_id),
        datos=dict(datos),
    )
