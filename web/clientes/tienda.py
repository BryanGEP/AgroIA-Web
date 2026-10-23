"""Cliente HTTP de svc-tienda para el gateway.

web no lee la base de otros servicios: todo pasa por la API, siempre con timeout. El
catálogo y el detalle son públicos, así que por ahora no se envía token.

Las imágenes que devuelve svc-tienda apuntan a su dirección interna
(`http://svc-tienda:8000/media/...`), que el navegador no alcanza; el cliente las
reescribe a `/media/tienda/...`, una ruta del gateway que reenvía el archivo.
"""

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

PREFIJO_IMAGENES = "/media/tienda/"


class TiendaNoDisponible(Exception):
    """svc-tienda no respondió, tardó demasiado o devolvió un error del servidor."""


class NoEncontrado(Exception):
    """El producto (o la página del listado) no existe o no está activo."""


@dataclass
class Archivo:
    contenido: bytes
    tipo: str


class ClienteTienda:
    def __init__(
        self,
        base_url: str,
        timeout: float,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    def _get(self, ruta: str, params: dict | None = None) -> httpx.Response:
        try:
            with httpx.Client(
                base_url=self.base_url, timeout=self.timeout, transport=self.transport
            ) as http:
                respuesta = http.get(ruta, params=params)
        except httpx.HTTPError as error:
            logger.warning("svc-tienda no respondió (%s): %s", ruta, type(error).__name__)
            raise TiendaNoDisponible from error
        if respuesta.status_code == 404:
            raise NoEncontrado
        if respuesta.status_code >= 400:
            logger.warning("svc-tienda respondió %s en %s", respuesta.status_code, ruta)
            raise TiendaNoDisponible
        return respuesta

    def _json(self, ruta: str, params: dict | None = None) -> dict:
        try:
            return self._get(ruta, params).json()
        except ValueError as error:
            raise TiendaNoDisponible from error

    def _reescribir_imagen(self, producto: dict) -> dict:
        url = producto.get("imagen")
        if url:
            partes, interna = urlsplit(url), urlsplit(self.base_url)
            if partes.netloc == interna.netloc and partes.path.startswith("/media/"):
                producto["imagen"] = PREFIJO_IMAGENES + partes.path.removeprefix("/media/")
        return producto

    def categorias(self) -> list[dict]:
        """Categorías activas (svc-tienda pagina de 20; hoy hay 5)."""
        return self._json("/api/v1/categorias/").get("results", [])

    def productos(self, params: dict | None = None) -> dict:
        """Página de productos: {"count", "next", "previous", "results"}."""
        datos = self._json("/api/v1/productos/", params)
        datos["results"] = [self._reescribir_imagen(p) for p in datos.get("results", [])]
        return datos

    def producto(self, slug: str) -> dict:
        return self._reescribir_imagen(self._json(f"/api/v1/productos/{slug}/"))

    def imagen(self, ruta: str) -> Archivo:
        respuesta = self._get(f"/media/{ruta}")
        return Archivo(respuesta.content, respuesta.headers.get("content-type", ""))


def obtener_cliente() -> ClienteTienda:
    """Cliente configurado; las pruebas lo sustituyen por uno con httpx.MockTransport."""
    return ClienteTienda(settings.URL_SVC_TIENDA, settings.TIENDA_TIMEOUT)
