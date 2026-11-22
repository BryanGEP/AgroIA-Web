"""Catálogo de eventos: cada tipo con su versión, su stream y los campos que puede llevar.

El detalle (productores, consumidores y qué pasa si falla) está en docs/eventos.md. Un
evento solo puede llevar los campos de su tipo: `validar_datos` rechaza los que sobran,
para que no se cuele un dato personal por accidente.

`no_registrables` marca los campos que ningún log escribe (por ejemplo, la pregunta del
usuario en la fase 3). Se guardan en el stream, pero no en `evento_publicado`,
`evento_no_publicado` ni en ningún otro registro.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

PREFIJO = "agroia:"
STREAM_USUARIOS = f"{PREFIJO}eventos:usuarios"
STREAM_TIENDA = f"{PREFIJO}eventos:tienda"
STREAM_CORREOS = f"{PREFIJO}eventos:correos"
STREAM_IA_SOLICITUDES = f"{PREFIJO}eventos:ia-solicitudes"
STREAM_IA_RESULTADOS = f"{PREFIJO}eventos:ia-resultados"
STREAM_FALLIDOS = f"{PREFIJO}eventos:fallidos"

# Largo aproximado de cada stream (XADD MAXLEN ~). El de fallidos no se recorta: se vacía
# con `reprocesar` o a mano después de revisarlo.
MAXLEN = 10_000


class ErrorEvento(ValueError):
    """Tipo desconocido o datos que no cumplen el catálogo. Es un error de programación:
    sí se lanza, a diferencia de un Redis caído."""


def _uuid(valor) -> bool:
    try:
        uuid.UUID(str(valor))
    except ValueError:
        return False
    return True


VALIDADORES: dict[str, Callable[[object], bool]] = {
    "uuid": _uuid,
    "texto": lambda v: isinstance(v, str),
    "entero": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "decimal": lambda v: isinstance(v, str) and v.replace(".", "", 1).lstrip("-").isdigit(),
    "booleano": lambda v: isinstance(v, bool),
    "lista": lambda v: isinstance(v, list),
}


@dataclass(frozen=True)
class TipoEvento:
    nombre: str
    version: int
    stream: str
    # campo -> nombre del validador. Todos son obligatorios salvo los de `opcionales`.
    campos: dict[str, str]
    opcionales: frozenset[str] = field(default_factory=frozenset)
    no_registrables: frozenset[str] = field(default_factory=frozenset)
    # campo -> valores permitidos (para los campos de texto que son una lista cerrada).
    valores: dict[str, frozenset[str]] = field(default_factory=dict)

    def validar_datos(self, datos: dict) -> None:
        if not isinstance(datos, dict):
            raise ErrorEvento(f"{self.nombre}: los datos deben ser un diccionario.")
        sobran = set(datos) - set(self.campos)
        if sobran:
            raise ErrorEvento(f"{self.nombre}: campos no permitidos: {sorted(sobran)}.")
        faltan = set(self.campos) - set(datos) - self.opcionales
        if faltan:
            raise ErrorEvento(f"{self.nombre}: faltan campos: {sorted(faltan)}.")
        for campo, valor in datos.items():
            if not VALIDADORES[self.campos[campo]](valor):
                raise ErrorEvento(f"{self.nombre}: «{campo}» debe ser {self.campos[campo]}.")
            if campo in self.valores and valor not in self.valores[campo]:
                raise ErrorEvento(
                    f"{self.nombre}: «{campo}» debe ser uno de {sorted(self.valores[campo])}."
                )

    def registrable(self, datos: dict) -> dict:
        """Los datos sin los campos que no se escriben en el log."""
        return {k: v for k, v in datos.items() if k not in self.no_registrables}


CATALOGO: dict[str, TipoEvento] = {}


def registrar_tipo(tipo: TipoEvento) -> TipoEvento:
    if tipo.nombre in CATALOGO and CATALOGO[tipo.nombre] != tipo:
        raise ErrorEvento(f"El tipo {tipo.nombre} ya existe con otra definición.")
    for validador in tipo.campos.values():
        if validador not in VALIDADORES:
            raise ErrorEvento(f"{tipo.nombre}: validador desconocido «{validador}».")
    CATALOGO[tipo.nombre] = tipo
    return tipo


def obtener_tipo(nombre: str) -> TipoEvento:
    try:
        return CATALOGO[nombre]
    except KeyError:
        raise ErrorEvento(f"Tipo de evento desconocido: {nombre!r}.") from None


def streams() -> list[str]:
    """Los streams de negocio del catálogo, sin el de fallidos."""
    return sorted({t.stream for t in CATALOGO.values()})


ROLES = frozenset({"cliente", "administrador"})
ESTADOS_DE_PEDIDO = frozenset({"pendiente", "pagado", "enviado", "entregado", "cancelado"})
TIPOS_DE_CORREO = frozenset({"verificacion", "recuperacion", "aviso_password"})

# --- Fase 1 ------------------------------------------------------------------------------

registrar_tipo(
    TipoEvento(
        nombre="usuario_registrado",
        version=1,
        stream=STREAM_USUARIOS,
        campos={"usuario_id": "uuid", "rol": "texto"},
        valores={"rol": ROLES},
    )
)

# --- Fase 2: eventos de negocio ----------------------------------------------------------
# svc-usuarios -> bitácora (svc-contenido)

registrar_tipo(
    TipoEvento(
        nombre="correo_verificado",
        version=1,
        stream=STREAM_USUARIOS,
        campos={"usuario_id": "uuid", "via": "texto"},
        valores={"via": frozenset({"enlace", "recuperacion"})},
    )
)
registrar_tipo(
    TipoEvento(
        nombre="rol_cambiado",
        version=1,
        stream=STREAM_USUARIOS,
        campos={
            "usuario_id": "uuid",
            "rol_anterior": "texto",
            "rol_nuevo": "texto",
            "cambiado_por": "uuid",
        },
        valores={"rol_anterior": ROLES, "rol_nuevo": ROLES},
    )
)
registrar_tipo(
    TipoEvento(
        nombre="password_cambiada",
        version=1,
        stream=STREAM_USUARIOS,
        campos={"usuario_id": "uuid", "motivo": "texto"},
        valores={"motivo": frozenset({"cambio", "recuperacion"})},
    )
)
registrar_tipo(
    TipoEvento(
        nombre="sesiones_cerradas",
        version=1,
        stream=STREAM_USUARIOS,
        campos={"usuario_id": "uuid"},
    )
)

# svc-usuarios -> su propio consumidor de correos. Nunca lleva el token del enlace: lo genera
# el consumidor al enviar.
registrar_tipo(
    TipoEvento(
        nombre="correo_solicitado",
        version=1,
        stream=STREAM_CORREOS,
        campos={"usuario_id": "uuid", "tipo_correo": "texto"},
        valores={"tipo_correo": TIPOS_DE_CORREO},
    )
)

# svc-tienda -> bitácora. Cada transición de estado (también el pago) publica un solo
# pedido_estado_cambiado. Sin dirección ni nombres: `productos` es el número de renglones.
registrar_tipo(
    TipoEvento(
        nombre="pedido_creado",
        version=1,
        stream=STREAM_TIENDA,
        campos={
            "pedido_id": "entero",
            "usuario_id": "uuid",
            "total": "decimal",
            "productos": "entero",
            "unidades": "entero",
            "metodo_pago": "texto",
        },
        valores={"metodo_pago": frozenset({"tarjeta", "transferencia", "contra_entrega"})},
    )
)
registrar_tipo(
    TipoEvento(
        nombre="pedido_estado_cambiado",
        version=1,
        stream=STREAM_TIENDA,
        campos={
            "pedido_id": "entero",
            "usuario_id": "uuid",
            "estado_anterior": "texto",
            "estado_nuevo": "texto",
            "total": "decimal",
            "cambiado_por": "uuid",
        },
        valores={"estado_anterior": ESTADOS_DE_PEDIDO, "estado_nuevo": ESTADOS_DE_PEDIDO},
    )
)
