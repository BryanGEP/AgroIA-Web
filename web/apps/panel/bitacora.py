"""Cómo se lee la bitácora en el panel: nombre de cada tipo de evento y un resumen en una línea.

Solo usa los campos que el evento ya trae (catálogo en docs/eventos.md). Nunca datos
sensibles: los eventos no traen contraseñas, direcciones ni nombres, y aquí no se buscan.
"""

from decimal import Decimal, InvalidOperation

TIPOS = {
    "usuario_registrado": "Cuenta creada",
    "correo_verificado": "Correo verificado",
    "rol_cambiado": "Rol cambiado",
    "password_cambiada": "Contraseña cambiada",
    "sesiones_cerradas": "Sesiones cerradas",
    "pedido_creado": "Pedido creado",
    "pedido_estado_cambiado": "Estado de pedido",
}
ESTADOS = {
    "pendiente": "pendiente",
    "pagado": "pagado",
    "enviado": "enviado",
    "entregado": "entregado",
    "cancelado": "cancelado",
}
ROLES = {"cliente": "cliente", "administrador": "administrador"}
METODOS = {
    "tarjeta": "tarjeta",
    "transferencia": "transferencia",
    "contra_entrega": "contra entrega",
}
VIAS = {"enlace": "por el enlace del correo", "recuperacion": "al recuperar la contraseña"}
MOTIVOS = {"cambio": "desde su cuenta", "recuperacion": "con la recuperación"}


def _pesos(valor) -> str:
    try:
        return f"${Decimal(str(valor)):,.2f}"
    except (InvalidOperation, ValueError):
        return ""


def _texto(tabla: dict, valor) -> str:
    return tabla.get(valor, str(valor) if valor not in (None, "") else "?")


def nombre_de_tipo(tipo: str) -> str:
    return TIPOS.get(tipo, tipo.replace("_", " ").capitalize())


def resumir(evento: dict) -> str:
    """«Pedido #12: pendiente → pagado», «Rol: cliente → administrador»…"""
    tipo = evento.get("tipo", "")
    datos = evento.get("datos") or {}
    if tipo == "pedido_estado_cambiado":
        anterior = _texto(ESTADOS, datos.get("estado_anterior"))
        nuevo = _texto(ESTADOS, datos.get("estado_nuevo"))
        return f"Pedido #{datos.get('pedido_id', '?')}: {anterior} → {nuevo}"
    if tipo == "pedido_creado":
        partes = [f"Pedido #{datos.get('pedido_id', '?')} creado"]
        if datos.get("total") is not None:
            partes.append(f"por {_pesos(datos['total'])}")
        if datos.get("unidades") is not None:
            unidades = datos["unidades"]
            partes.append(f"({unidades} unidad{'es' if unidades != 1 else ''})")
        if datos.get("metodo_pago"):
            partes.append(f"· {_texto(METODOS, datos['metodo_pago'])}")
        return " ".join(partes)
    if tipo == "rol_cambiado":
        anterior = _texto(ROLES, datos.get("rol_anterior"))
        return f"Rol: {anterior} → {_texto(ROLES, datos.get('rol_nuevo'))}"
    if tipo == "usuario_registrado":
        return f"Cuenta nueva ({_texto(ROLES, datos.get('rol'))})"
    if tipo == "correo_verificado":
        via = VIAS.get(datos.get("via"))
        return f"Correo verificado {via}" if via else "Correo verificado"
    if tipo == "password_cambiada":
        motivo = MOTIVOS.get(datos.get("motivo"))
        return f"Contraseña cambiada {motivo}" if motivo else "Contraseña cambiada"
    if tipo == "sesiones_cerradas":
        return "Cerró todas sus sesiones"
    return nombre_de_tipo(tipo)


def actor(evento: dict) -> str | None:
    """Quién hizo el cambio, si el evento lo trae (`cambiado_por`)."""
    return (evento.get("datos") or {}).get("cambiado_por")
