"""Registro de solicitudes recientes, para responder GET /solicitudes/<id>/.

En la Entrega 2 todo se resuelve en la misma petición, así que cada solicitud nace
`listo`. Se guardan en la memoria del proceso (las últimas 1000) y se pierden al
reiniciar. En la Entrega 4 pasará a Redis, cuando svc-ia responda `pendiente` y publique
el resultado como evento.
"""

import threading
import uuid
from collections import OrderedDict
from datetime import UTC, datetime

from app.seguridad import Usuario

MAXIMO = 1000


class RegistroSolicitudes:
    def __init__(self, maximo: int = MAXIMO):
        self.maximo = maximo
        self._datos: OrderedDict[str, dict] = OrderedDict()
        self._candado = threading.Lock()

    def guardar(self, tipo: str, usuario: Usuario, resultado: dict) -> dict:
        solicitud = {
            "id": uuid.uuid4().hex,
            "estado": "listo",
            "tipo": tipo,
            "creada_en": datetime.now(UTC),
            "resultado": resultado,
        }
        with self._candado:
            self._datos[solicitud["id"]] = {**solicitud, "usuario_id": usuario.id}
            while len(self._datos) > self.maximo:
                self._datos.popitem(last=False)
        return solicitud

    def obtener(self, id_solicitud: str, usuario: Usuario) -> dict | None:
        """La solicitud si es del usuario o si es administrador; si no, None (404)."""
        with self._candado:
            guardada = self._datos.get(id_solicitud)
        if guardada is None or not (
            usuario.es_administrador or guardada["usuario_id"] == usuario.id
        ):
            return None
        return {clave: valor for clave, valor in guardada.items() if clave != "usuario_id"}

    def limpiar(self) -> None:
        with self._candado:
            self._datos.clear()


registro = RegistroSolicitudes()
