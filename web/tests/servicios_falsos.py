"""Los cuatro servicios simulados con httpx.MockTransport, para las pruebas del gateway.

Cada respuesta se registra con `responder(metodo, host, ruta, respuesta)`, donde
`respuesta` es un httpx.Response o una función que recibe el httpx.Request. Las
peticiones quedan en `peticiones` para revisar qué recibió cada servicio.
"""

import json
import uuid

import httpx
from django.conf import settings

from agroia_comun.pruebas import firmar_token

USUARIO_ID = "c1e2a3b4-0000-4000-8000-000000000010"


def token(rol: str = "cliente", verificado: bool = True, usuario_id: str = USUARIO_ID, **extra):
    return firmar_token(
        settings.LLAVE_PRIVADA_PRUEBAS,
        usuario_id=usuario_id,
        rol=rol,
        email_verificado=verificado,
        **extra,
    )


def par(rol: str = "cliente", verificado: bool = True) -> dict:
    return {"access": token(rol, verificado), "refresh": f"refresh-{uuid.uuid4().hex}"}


def error(estado: int, codigo: str, detalle: str = "Detalle.", campos=None, **encabezados):
    cuerpo = {"error": codigo, "detalle": detalle}
    if campos:
        cuerpo["campos"] = campos
    return httpx.Response(estado, json=cuerpo, headers=encabezados)


class ServiciosFalsos:
    def __init__(self):
        self.peticiones: list[httpx.Request] = []
        self.rutas: dict[tuple[str, str, str], object] = {}
        self.caidos: set[str] = set()
        self.lentos: set[str] = set()

    def responder(self, metodo: str, host: str, ruta: str, respuesta) -> None:
        self.rutas[(metodo, host, ruta)] = respuesta

    def de(self, host: str, ruta: str | None = None) -> list[httpx.Request]:
        return [
            p
            for p in self.peticiones
            if p.url.host == host and (ruta is None or p.url.path == ruta)
        ]

    def cuerpo(self, peticion: httpx.Request) -> dict:
        return json.loads(peticion.content or b"{}")

    def __call__(self, peticion: httpx.Request) -> httpx.Response:
        self.peticiones.append(peticion)
        host = peticion.url.host
        if host in self.caidos:
            raise httpx.ConnectError(f"{host} caído")
        if host in self.lentos:
            raise httpx.ReadTimeout(f"{host} lento")
        respuesta = self.rutas.get((peticion.method, host, peticion.url.path))
        if respuesta is None:
            return error(404, "no_encontrado", "No existe en el servicio falso.")
        return respuesta(peticion) if callable(respuesta) else respuesta
