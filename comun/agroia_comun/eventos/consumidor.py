"""Consumir eventos con un grupo de consumidores de Redis Streams.

    Consumidor("svc-contenido", {"usuario_registrado": guardar_en_bitacora}).correr()

Cada servicio que reacciona a eventos tiene un grupo con su nombre; cada evento llega una
vez a cada grupo (varios servicios pueden escuchar el mismo stream).

Por mensaje:
1. Si el sobre no se puede leer, o trae una versión más nueva que la del catálogo de este
   servicio, va directo a fallidos (reintentar no lo arregla).
2. Si el tipo no tiene manejador en este grupo, se confirma y se registra como ignorado.
3. Si la llave `agroia:procesados:<grupo>:<evento_id>` existe, ya se aplicó: se confirma
   sin volver a llamar al manejador (`evento_duplicado`).
4. Se llama al manejador. Si termina bien, en una transacción se escribe la llave de
   procesado (vence en 7 días) y se confirma el mensaje (XACK). La llave se escribe solo
   después de que el manejador terminó bien.
5. Si el manejador falla, el mensaje no se confirma y queda en la lista de pendientes del
   grupo. Se vuelve a intentar cuando lleva sin confirmarse `espera_base * 2 ** (entregas - 1)`
   segundos (espera creciente). Al pasar de `max_reintentos` reintentos, se copia al
   stream de fallidos con el motivo y se confirma.

La misma revisión de pendientes recupera los mensajes que dejó colgados un consumidor que
murió a la mitad: después de la espera, cualquier consumidor del grupo los reclama.

Si el proceso muere entre el manejador y la llave de procesado, el mensaje se vuelve a
entregar y el manejador se llama otra vez: **todo manejador debe ser idempotente por sí
mismo** (por ejemplo, un índice único de `evento_id`). La llave solo evita el trabajo
repetido, y además vence.

Con SIGTERM o SIGINT (docker compose stop) termina el mensaje en curso y sale.
"""

import logging
import os
import signal
import socket
import time
from collections.abc import Callable

import redis

from agroia_comun.eventos import conexion
from agroia_comun.eventos.catalogo import PREFIJO, STREAM_FALLIDOS, ErrorEvento, obtener_tipo
from agroia_comun.eventos.registro import motivo_de, registrar
from agroia_comun.eventos.sobre import Sobre

Manejador = Callable[[Sobre], None]

TTL_PROCESADOS = 7 * 24 * 3600
PENDIENTES_POR_VUELTA = 50


def _entero(variable: str, por_defecto: int) -> int:
    return int(os.environ.get(variable, por_defecto))


def _decimal(variable: str, por_defecto: float) -> float:
    return float(os.environ.get(variable, por_defecto))


class Consumidor:
    def __init__(
        self,
        grupo: str,
        manejadores: dict[str, Manejador],
        *,
        nombre: str | None = None,
        cliente: redis.Redis | None = None,
        cliente_de_lectura: redis.Redis | None = None,
        max_reintentos: int | None = None,
        espera_base: float | None = None,
        bloqueo_ms: int | None = None,
    ):
        if not manejadores:
            raise ErrorEvento("Un consumidor necesita al menos un manejador.")
        self.grupo = grupo
        self.manejadores = dict(manejadores)
        self.streams = sorted({obtener_tipo(tipo).stream for tipo in manejadores})
        self.nombre = nombre or f"{grupo}-{socket.gethostname()}"
        self.redis = cliente or conexion.cliente()
        self.lectura = cliente_de_lectura or cliente or conexion.cliente_de_lectura()
        self.max_reintentos = (
            _entero("EVENTOS_MAX_REINTENTOS", 5) if max_reintentos is None else max_reintentos
        )
        self.espera_base = (
            _decimal("EVENTOS_ESPERA_BASE", 2.0) if espera_base is None else espera_base
        )
        self.bloqueo_ms = conexion.BLOQUEO_MS if bloqueo_ms is None else bloqueo_ms
        self.detener = False

    # --- utilidades ----------------------------------------------------------------------

    def espera(self, entregas: int) -> float:
        """Segundos que debe llevar un mensaje sin confirmarse antes del siguiente intento."""
        return self.espera_base * 2 ** max(entregas - 1, 0)

    def clave_procesado(self, evento_id: str) -> str:
        return f"{PREFIJO}procesados:{self.grupo}:{evento_id}"

    def preparar(self) -> None:
        """Crea los grupos si no existen. Desde el inicio del stream (id 0): lo que se
        publicó antes de que existiera el grupo también se procesa."""
        for stream in self.streams:
            try:
                self.redis.xgroup_create(stream, self.grupo, id="0", mkstream=True)
            except redis.ResponseError as error:
                if "BUSYGROUP" not in str(error):
                    raise

    # --- un mensaje ----------------------------------------------------------------------

    def procesar(self, stream: str, id_mensaje: str, campos: dict, entregas: int) -> str:
        """Procesa un mensaje y devuelve qué pasó: procesado, duplicado, ignorado,
        reintento o fallido."""
        base = {"grupo": self.grupo, "stream": stream, "id_mensaje": id_mensaje}
        try:
            sobre = Sobre.de_json(campos.get("sobre", ""))
        except ErrorEvento as error:
            self._a_fallidos(stream, id_mensaje, campos.get("sobre", ""), entregas, error, {})
            return "fallido"
        datos_log = {**base, **sobre.para_log(), "intento": entregas}

        manejador = self.manejadores.get(sobre.tipo)
        if manejador is None:
            self.redis.xack(stream, self.grupo, id_mensaje)
            registrar("evento_ignorado", **datos_log)
            return "ignorado"

        version = obtener_tipo(sobre.tipo).version
        if sobre.version > version:
            # Un productor más nuevo: aplicarlo con el manejador de una versión vieja podría
            # guardarlo mal. Va a fallidos hasta que este servicio se actualice.
            error = ErrorEvento(f"Versión {sobre.version} no soportada (este grupo: {version}).")
            self._a_fallidos(stream, id_mensaje, sobre.a_json(), entregas, error, datos_log)
            return "fallido"

        if self.redis.exists(self.clave_procesado(sobre.id)):
            self.redis.xack(stream, self.grupo, id_mensaje)
            registrar("evento_duplicado", **datos_log)
            return "duplicado"

        try:
            manejador(sobre)
        except Exception as error:  # cualquier error del manejador cuenta como intento
            if entregas > self.max_reintentos:
                self._a_fallidos(stream, id_mensaje, sobre.a_json(), entregas, error, datos_log)
                return "fallido"
            registrar(
                "evento_reintentado",
                logging.WARNING,
                **datos_log,
                motivo=motivo_de(error),
                siguiente_en_segundos=self.espera(entregas),
            )
            return "reintento"

        # Solo después de que el manejador terminó bien.
        transaccion = self.redis.pipeline(transaction=True)
        transaccion.set(self.clave_procesado(sobre.id), 1, ex=TTL_PROCESADOS)
        transaccion.xack(stream, self.grupo, id_mensaje)
        transaccion.execute()
        registrar("evento_procesado", **datos_log)
        return "procesado"

    def _a_fallidos(self, stream, id_mensaje, sobre_json, entregas, error, datos_log) -> None:
        motivo = motivo_de(error)
        transaccion = self.redis.pipeline(transaction=True)
        # Sin MAXLEN: los fallidos no se recortan (ver docs/eventos.md).
        transaccion.xadd(
            STREAM_FALLIDOS,
            {
                "sobre": sobre_json or "",
                "stream": stream,
                "grupo": self.grupo,
                "id_mensaje": id_mensaje,
                "intentos": entregas,
                "motivo": motivo,
            },
        )
        transaccion.xack(stream, self.grupo, id_mensaje)
        transaccion.execute()
        registrar(
            "evento_fallido",
            logging.ERROR,
            **(datos_log or {"grupo": self.grupo, "stream": stream, "id_mensaje": id_mensaje}),
            intentos=entregas,
            motivo=motivo,
        )

    # --- una vuelta del ciclo ------------------------------------------------------------

    def reclamar_pendientes(self) -> int:
        """Reintenta los mensajes del grupo cuya espera ya pasó: los que fallaron y los
        que dejó colgados otro consumidor."""
        atendidos = 0
        for stream in self.streams:
            pendientes = self.redis.xpending_range(
                stream, self.grupo, min="-", max="+", count=PENDIENTES_POR_VUELTA
            )
            for pendiente in pendientes:
                if self.detener:
                    return atendidos
                entregas = pendiente["times_delivered"]
                espera_ms = int(self.espera(entregas) * 1000)
                if pendiente["time_since_delivered"] < espera_ms:
                    continue
                reclamados = self.redis.xclaim(
                    stream,
                    self.grupo,
                    self.nombre,
                    min_idle_time=espera_ms,
                    message_ids=[pendiente["message_id"]],
                )
                for id_mensaje, campos in reclamados:
                    if campos is None:  # ya no está en el stream (recortado)
                        self.redis.xack(stream, self.grupo, id_mensaje)
                        continue
                    self.procesar(stream, id_mensaje, campos, entregas + 1)
                    atendidos += 1
        return atendidos

    def leer_nuevos(self) -> int:
        """Lee de a un mensaje nuevo, para no dejar leídos sin empezar al detenerse."""
        respuesta = self.lectura.xreadgroup(
            self.grupo,
            self.nombre,
            dict.fromkeys(self.streams, ">"),
            count=1,
            block=self.bloqueo_ms,
        )
        atendidos = 0
        for stream, mensajes in respuesta or []:
            for id_mensaje, campos in mensajes:
                self.procesar(stream, id_mensaje, campos, 1)
                atendidos += 1
        return atendidos

    def una_vuelta(self) -> int:
        atendidos = self.reclamar_pendientes()
        if not self.detener:
            atendidos += self.leer_nuevos()
        return atendidos

    # --- proceso -------------------------------------------------------------------------

    def pedir_detener(self, *_):
        self.detener = True
        registrar("consumidor_deteniendo", grupo=self.grupo, consumidor=self.nombre)

    def correr(self) -> None:
        signal.signal(signal.SIGTERM, self.pedir_detener)
        signal.signal(signal.SIGINT, self.pedir_detener)
        fallos = 0
        preparado = False
        registrar(
            "consumidor_iniciado", grupo=self.grupo, consumidor=self.nombre, streams=self.streams
        )
        while not self.detener:
            try:
                if not preparado:
                    self.preparar()
                    preparado = True
                self.una_vuelta()
                fallos = 0
            except redis.RedisError as error:
                fallos += 1
                espera = min(30.0, 2.0**fallos)
                registrar(
                    "consumidor_sin_redis",
                    logging.ERROR,
                    grupo=self.grupo,
                    motivo=motivo_de(error),
                    reintento_en_segundos=espera,
                )
                self._dormir(espera)
        registrar("consumidor_detenido", grupo=self.grupo, consumidor=self.nombre)

    def _dormir(self, segundos: float) -> None:
        limite = time.monotonic() + segundos
        while not self.detener and time.monotonic() < limite:
            time.sleep(0.2)
