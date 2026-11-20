"""Reglas del proxy /api/<servicio>/<ruta>: qué rutas son públicas, qué encabezados pasan y
cómo se traduce la respuesta.

El proxy es la primera capa de autenticación: valida el access antes de reenviar. Cada
servicio lo vuelve a validar y decide los roles (segunda capa). Ver
docs/contrato-identidad.md#dos-capas-de-validación.
"""

import re

import httpx

# Rutas que pasan sin token: el login y el resto de la identidad, y el catálogo.
RUTAS_PUBLICAS = {
    "usuarios": [
        (
            {"POST"},
            re.compile(
                r"^auth/(login|registro|token/renovar|verificar-correo|"
                r"reenviar-verificacion|recuperar|restablecer)/$"
            ),
        ),
    ],
    "tienda": [({"GET", "HEAD"}, re.compile(r"^(categorias|productos)(/.*)?$"))],
}

# Lista cerrada: solo estos encabezados del cliente llegan al servicio. Nunca Cookie, Host,
# los de salto (Connection, Keep-Alive, Transfer-Encoding...) ni un X-Forwarded-For del
# cliente: ese lo pone el cliente común con la IP real (clientes/api.py).
ENCABEZADOS_DE_ENTRADA = ("Authorization", "Content-Type", "Accept", "Accept-Language")
# Y solo estos vuelven al cliente (sin Set-Cookie, Server ni los de salto).
ENCABEZADOS_DE_SALIDA = ("Content-Type", "Retry-After", "WWW-Authenticate", "Content-Disposition")


def es_publica(servicio: str, metodo: str, ruta: str) -> bool:
    return any(
        metodo in metodos and patron.match(ruta)
        for metodos, patron in RUTAS_PUBLICAS.get(servicio, [])
    )


def ruta_segura(ruta: str) -> bool:
    """Sin `.` ni `..` (Django ya decodificó %2e) ni barras invertidas: el proxy no debe
    alcanzar rutas del servicio fuera de su API, como /admin/."""
    if "\\" in ruta or ruta.startswith("/"):
        return False
    return all(segmento not in (".", "..") for segmento in ruta.split("/"))


def token_bearer(encabezado: str) -> str | None:
    """El token de `Authorization: Bearer <token>`, o None si el formato no es ese."""
    partes = encabezado.split()
    if len(partes) != 2 or partes[0].lower() != "bearer":
        return None
    return partes[1]


def encabezados_de_entrada(encabezados) -> dict[str, str]:
    return {
        nombre: encabezados[nombre] for nombre in ENCABEZADOS_DE_ENTRADA if nombre in encabezados
    }


def encabezados_de_salida(respuesta: httpx.Response) -> dict[str, str]:
    return {
        nombre: respuesta.headers[nombre]
        for nombre in ENCABEZADOS_DE_SALIDA
        if nombre in respuesta.headers
    }


def location_externa(location: str, url_interna: str, servicio: str, prefijo: str) -> str | None:
    """Una redirección del servicio (por ejemplo, la barra final que agrega Django) apunta
    a su dirección interna; se traduce a la ruta del proxy. Si no es del servicio, se quita."""
    base = url_interna.rstrip("/") + prefijo
    for inicio in (base, prefijo):
        if location.startswith(inicio):
            return f"/api/{servicio}/" + location.removeprefix(inicio)
    return None
