"""Panel de administración: llama a los servicios con el token del administrador.

También lee la bitácora y el estado de los eventos de svc-contenido. Nunca toca bases ni
Redis: todo por las APIs de los servicios.

Las reglas las aplica cada servicio (roles, transiciones de pedido, auto-degradación); el
panel solo muestra lo que ellos permiten, por ejemplo `transiciones_permitidas` del pedido.
"""

from datetime import date

from clientes.tienda import reescribir_imagen
from django.conf import settings
from django.http import HttpRequest

from apps.cuentas.servicios import ErrorApi, con_sesion

ESTADOS = [
    ("pendiente", "Pendiente de pago"),
    ("pagado", "Pagado"),
    ("enviado", "Enviado"),
    ("entregado", "Entregado"),
    ("cancelado", "Cancelado"),
]
UNIDADES = [("pieza", "Pieza"), ("kg", "Kilogramo"), ("litro", "Litro"), ("costal", "Costal")]


def _limpios(filtros: dict) -> dict:
    return {clave: valor for clave, valor in filtros.items() if valor not in ("", None)}


# --- Productos y categorías ---------------------------------------------------------------


def productos(request: HttpRequest, filtros: dict) -> dict:
    """Incluye los inactivos: svc-tienda los muestra al administrador."""
    datos = con_sesion(request, "tienda", "GET", "productos/", params=_limpios(filtros))
    datos["results"] = [reescribir_imagen(p) for p in datos.get("results", [])]
    return datos


def producto(request: HttpRequest, slug: str) -> dict:
    return reescribir_imagen(con_sesion(request, "tienda", "GET", f"productos/{slug}/"))


def guardar_producto(request: HttpRequest, slug: str | None, datos: dict, imagen=None) -> dict:
    """Los datos van en JSON (la ficha técnica es un objeto). La imagen, si hay, en un
    segundo PATCH multipart: un JSONField no se lee bien dentro de un formulario."""
    if slug:
        producto_guardado = con_sesion(request, "tienda", "PATCH", f"productos/{slug}/", json=datos)
    else:
        producto_guardado = con_sesion(request, "tienda", "POST", "productos/", json=datos)
    if imagen is not None:
        producto_guardado = con_sesion(
            request,
            "tienda",
            "PATCH",
            f"productos/{producto_guardado['slug']}/",
            files={"imagen": (imagen.name, imagen.read(), imagen.content_type)},
        )
    return producto_guardado


def desactivar_producto(request: HttpRequest, slug: str) -> None:
    con_sesion(request, "tienda", "DELETE", f"productos/{slug}/")


def categorias(request: HttpRequest) -> list[dict]:
    datos = con_sesion(request, "tienda", "GET", "categorias/")
    return datos.get("results", []) if isinstance(datos, dict) else datos


def categoria(request: HttpRequest, slug: str) -> dict:
    return con_sesion(request, "tienda", "GET", f"categorias/{slug}/")


def guardar_categoria(request: HttpRequest, slug: str | None, datos: dict) -> dict:
    if slug:
        return con_sesion(request, "tienda", "PATCH", f"categorias/{slug}/", json=datos)
    return con_sesion(request, "tienda", "POST", "categorias/", json=datos)


def desactivar_categoria(request: HttpRequest, slug: str) -> None:
    con_sesion(request, "tienda", "DELETE", f"categorias/{slug}/")


# --- Pedidos ------------------------------------------------------------------------------


def pedidos(request: HttpRequest, filtros: dict) -> dict:
    return con_sesion(request, "tienda", "GET", "pedidos/", params=_limpios(filtros))


def pedido(request: HttpRequest, pedido_id: int) -> dict:
    return con_sesion(request, "tienda", "GET", f"pedidos/{pedido_id}/")


def cambiar_estado(request: HttpRequest, pedido_id: int, estado: str) -> dict:
    """svc-tienda valida la transición y devuelve las nuevas transiciones permitidas."""
    return con_sesion(
        request, "tienda", "PATCH", f"pedidos/{pedido_id}/estado/", json={"estado": estado}
    )


# --- Usuarios -----------------------------------------------------------------------------


def usuarios(request: HttpRequest, filtros: dict) -> dict:
    return con_sesion(request, "usuarios", "GET", "usuarios/", params=_limpios(filtros))


def cambiar_rol(request: HttpRequest, usuario_id: str, rol: str) -> dict:
    return con_sesion(
        request, "usuarios", "PATCH", f"usuarios/{usuario_id}/rol/", json={"rol": rol}
    )


# --- Resumen, usuarios y bitácora (panel ampliado) ------------------------------------------


def umbral_stock_bajo() -> int:
    return settings.PANEL_UMBRAL_STOCK_BAJO


def resumen_tienda(request: HttpRequest) -> dict:
    """Pedidos por atender, ventas, stock y últimos pedidos (GET /resumen/ de svc-tienda)."""
    return con_sesion(request, "tienda", "GET", "resumen/", params={"umbral": umbral_stock_bajo()})


def usuarios_nuevos(request: HttpRequest, desde: date) -> dict:
    """Registrados desde `desde` (hora de México): `count` y la primera página."""
    return con_sesion(
        request,
        "usuarios",
        "GET",
        "usuarios/",
        params={"desde": desde.isoformat(), "ordering": "-date_joined"},
    )


def usuario(request: HttpRequest, usuario_id: str) -> dict:
    return con_sesion(request, "usuarios", "GET", f"usuarios/{usuario_id}/")


def nombres_de_usuarios(request: HttpRequest, ids) -> dict[str, dict]:
    """Los usuarios de una página (pedidos o bitácora) con una sola llamada (`ids`, hasta 20).
    Si svc-usuarios no responde, la página se muestra igual, con el id corto."""
    unicos = list(dict.fromkeys(str(i) for i in ids if i))[:20]
    if not unicos:
        return {}
    try:
        datos = con_sesion(
            request, "usuarios", "GET", "usuarios/", params={"ids": ",".join(unicos)}
        )
    except ErrorApi:
        return {}
    return {u["id"]: u for u in datos.get("results", [])}


def bitacora(request: HttpRequest, filtros: dict) -> dict:
    return con_sesion(request, "contenido", "GET", "bitacora/", params=_limpios(filtros))


def linea_de_tiempo(request: HttpRequest, pedido_id: int) -> list[dict]:
    """Los eventos de un pedido, del más viejo al más nuevo (filtro `pedido_id`)."""
    datos = con_sesion(request, "contenido", "GET", "bitacora/", params={"pedido_id": pedido_id})
    return list(reversed(datos.get("results", [])))


def estado_eventos(request: HttpRequest) -> dict:
    return con_sesion(request, "contenido", "GET", "eventos/estado/")
