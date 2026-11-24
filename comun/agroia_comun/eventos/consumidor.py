"""Consumir eventos con un grupo de consumidores de Redis Streams.

    Consumidor("svc-contenido", {"usuario_registrado": guardar_en_bitacora}).correr()
    correr_en_hilos(lambda nombre: Consumidor("svc-ia", MANEJADORES, nombre=nombre), 3)

Cada servicio que reacciona a eventos tiene un grupo con su nombre; cada evento llega una
vez a cada grupo (varios servicios pueden escuchar el mismo stream). Dentro de un grupo,
varios consumidores (hilos o réplicas) se reparten los eventos.

Por mensaje:
1. Si el sobre no se puede leer, o trae una versión más nueva que la del catálogo de este
   servicio, va directo a fallidos (reintentar no lo arregla).
2. Si el tipo no tiene manejador en este grupo, se confirma y se registra como ignorado.
3. Si la llave `agroia:procesados:<grupo>:<evento_id>` existe, ya se aplicó: se confirma
   sin volver a llamar al manejador (`evento_duplicado`).
4. Se llama al manejador. **Mientras trabaja, un latido renueva la posesión del mensaje**
   (XCLAIM a sí mismo con JUSTID, que no suma entregas) cada `latido` segundos: ningún
   otro consumidor lo puede reclamar aunque tarde más que la espera de reintento.
5. Si termina bien, en una transacción se escribe la llave de procesado (vence en 7 días)
   y se confirma el mensaje (XACK). La llave se escribe solo después del manejador.
6. Si el manejador falla, cuenta un fallo (contador propio por mensaje en Redis; no se
   usan las entregas de Redis, que también suben al reclamar) y la posesión se renueva en
   ese momento: la espera del siguiente intento se mide **desde el fallo**. Esa espera es
   `espera_base * 2 ** (fallos - 1)` segundos, y nunca menos que `plazo_sin_latido`. Al
   pasar de `max_reintentos` fallos se llama al `al_agotar` de su tipo (si hay) y el
   evento se copia a fallidos con el motivo, sin sus campos no registrables.
7. Si el manejador lanza `Ocupado` (otro consumidor ya lo está atendiendo, por ejemplo
   con el candado de una solicitud de IA), **no cuenta como fallo**: queda pendiente y se
   revisa después.

Un mensaje pendiente se reclama cuando lleva sin latido más de `plazo_sin_latido` (su
consumidor murió a la mitad) o, si ya falló, cuando pasó su espera. Los reintentos y la
espera salen de la política de cada stream (catalogo.politica): la IA tiene los suyos.

Si el proceso muere entre el manejador y la llave de procesado, el mensaje se vuelve a
entregar y el manejador se llama otra vez: **todo manejador debe ser idempotente por sí
mismo**. La llave solo evita el trabajo repetido, y además vence.

Al arrancar se quitan del grupo los consumidores viejos: sin pendientes y con más de
`inactivo_para_borrar` segundos sin actividad (por ejemplo, los de un contenedor recreado).

Con SIGTERM o SIGINT (docker compose stop) termina el mensaje en curso y sale.
"""

import contextlib
import logging
import os
import signal
import socket
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

import redis

from agroia_comun.eventos import conexion, correlacion
from agroia_comun.eventos.catalogo import (
    PREFIJO,
    STREAM_FALLIDOS,
    ErrorEvento,
    obtener_tipo,
    politica,
)
from agroia_comun.eventos.registro import motivo_de, registrar
from agroia_comun.eventos.sobre import Sobre

Manejador = Callable[[Sobre], None]
AlAgotar = Callable[[Sobre, BaseException], None]

TTL_PROCESADOS = 7 * 24 * 3600
TTL_FALLOS = 7 * 24 * 3600
PENDIENTES_POR_VUELTA = 50


class Ocupado(Exception):
    """El manejador no puede atender el evento ahora porque otro ya lo está atendiendo.
    No cuenta como fallo: el evento queda pendiente y se revisa después."""


def _decimal(variable: str, por_defecto: float) -> float:
    return float(os.environ.get(variable, por_defecto))


class _Latido:
    """Renueva la posesión de un mensaje mientras el manejador trabaja."""

    def __init__(self, consumidor: "Consumidor", stream: str, id_mensaje: str):
        self.c, self.stream, self.id_mensaje = consumidor, stream, id_mensaje
        self.fin = threading.Event()
        self.hilo = threading.Thread(target=self._latir, daemon=True)

    def _latir(self) -> None:
        while not self.fin.wait(self.c.latido):
            with contextlib.suppress(redis.RedisError):  # el siguiente latido lo reintenta
                self.c.renovar(self.stream, self.id_mensaje)

    def __enter__(self):
        self.hilo.start()
        return self

    def __exit__(self, *_):
        self.fin.set()
        self.hilo.join()


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
        latido: float | None = None,
        al_agotar: dict[str, AlAgotar] | None = None,
        inactivo_para_borrar: float | None = None,
    ):
        if not manejadores:
            raise ErrorEvento("Un consumidor necesita al menos un manejador.")
        self.grupo = grupo
        self.manejadores = dict(manejadores)
        self.al_agotar = dict(al_agotar or {})
        self.streams = sorted({obtener_tipo(tipo).stream for tipo in manejadores})
        self.nombre = nombre or f"{grupo}-{socket.gethostname()}"
        self.redis = cliente or conexion.cliente()
        self.lectura = cliente_de_lectura or cliente or conexion.cliente_de_lectura()
        # Si se pasan, valen para todos los streams (pruebas); si no, la política de cada uno.
        self._max_reintentos = max_reintentos
        self._espera_base = espera_base
        self.bloqueo_ms = conexion.BLOQUEO_MS if bloqueo_ms is None else bloqueo_ms
        self.latido = _decimal("EVENTOS_LATIDO", 1.0) if latido is None else latido
        # Tres latidos sin renovar: el consumidor que lo tenía ya no lo está procesando.
        self.plazo_sin_latido = 3 * self.latido
        self.inactivo_para_borrar = (
            _decimal("EVENTOS_INACTIVO_PARA_BORRAR", 600)
            if inactivo_para_borrar is None
            else inactivo_para_borrar
        )
        self.detener = False

    # --- política y utilidades -----------------------------------------------------------

    def max_reintentos(self, stream: str) -> int:
        if self._max_reintentos is not None:
            return self._max_reintentos
        return politica(stream).max_reintentos

    def espera(self, fallos: int, stream: str | None = None) -> float:
        """Segundos sin latido que debe llevar un mensaje antes de reclamarlo: con fallos,
        la espera creciente desde el último fallo; sin fallos, el plazo sin latido (su
        consumidor murió a la mitad)."""
        if fallos <= 0:
            return self.plazo_sin_latido
        base = self._espera_base if self._espera_base is not None else politica(stream).espera_base
        return max(base * 2 ** (fallos - 1), self.plazo_sin_latido)

    def clave_procesado(self, evento_id: str) -> str:
        return f"{PREFIJO}procesados:{self.grupo}:{evento_id}"

    def clave_fallos(self, stream: str, id_mensaje: str) -> str:
        return f"{PREFIJO}fallos:{self.grupo}:{stream}:{id_mensaje}"

    def fallos(self, stream: str, id_mensaje: str) -> int:
        return int(self.redis.get(self.clave_fallos(stream, id_mensaje)) or 0)

    def renovar(self, stream: str, id_mensaje: str) -> None:
        """Se queda con el mensaje y pone su tiempo sin actividad en cero, sin sumar una
        entrega (JUSTID)."""
        self.redis.xclaim(
            stream, self.grupo, self.nombre, min_idle_time=0, message_ids=[id_mensaje],
            justid=True,
        )  # fmt: skip

    def preparar(self) -> None:
        """Crea los grupos si no existen (desde el inicio del stream: lo publicado antes
        también se procesa) y quita los consumidores viejos."""
        for stream in self.streams:
            try:
                self.redis.xgroup_create(stream, self.grupo, id="0", mkstream=True)
            except redis.ResponseError as error:
                if "BUSYGROUP" not in str(error):
                    raise
            self._borrar_viejos(stream)

    def _borrar_viejos(self, stream: str) -> None:
        limite_ms = self.inactivo_para_borrar * 1000
        for otro in self.redis.xinfo_consumers(stream, self.grupo):
            if otro["name"] != self.nombre and otro["pending"] == 0 and otro["idle"] > limite_ms:
                self.redis.xgroup_delconsumer(stream, self.grupo, otro["name"])
                registrar(
                    "consumidor_viejo_borrado",
                    grupo=self.grupo,
                    stream=stream,
                    consumidor=otro["name"],
                    inactivo_segundos=round(otro["idle"] / 1000),
                )

    # --- un mensaje ----------------------------------------------------------------------

    def procesar(self, stream: str, id_mensaje: str, campos: dict, fallos: int = 0) -> str:
        """Procesa un mensaje y devuelve qué pasó: procesado, duplicado, ignorado,
        reintento, ocupado o fallido. `fallos` son los fallos reales que ya lleva."""
        base = {"grupo": self.grupo, "stream": stream, "id_mensaje": id_mensaje}
        try:
            sobre = Sobre.de_json(campos.get("sobre", ""))
        except ErrorEvento as error:
            self._a_fallidos(stream, id_mensaje, None, campos.get("sobre", ""), 1, error, base)
            return "fallido"
        datos_log = {**base, **sobre.para_log(), "intento": fallos + 1}

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
            self._a_fallidos(stream, id_mensaje, sobre, None, fallos + 1, error, datos_log)
            return "fallido"

        if self.redis.exists(self.clave_procesado(sobre.id)):
            self._confirmar(stream, id_mensaje)
            registrar("evento_duplicado", **datos_log)
            return "duplicado"

        # Para seguir cada mensaje en el log: quién lo atendió, cuándo empezó, cuánto tardó y
        # cuántas veces lo entregó Redis (el latido renueva con JUSTID y no suma entregas).
        datos_log.update(
            consumidor=self.nombre,
            entregas=self.entregas(stream, id_mensaje),
            inicio=datetime.now(UTC).isoformat(timespec="milliseconds"),
        )
        reloj = time.monotonic()
        try:
            # La correlación del sobre mientras corre el manejador: si publica otro evento,
            # conserva la cadena. Se limpia al terminar, también si falla.
            with (
                _Latido(self, stream, id_mensaje),
                correlacion.con_correlacion(sobre.correlacion_id),
            ):
                manejador(sobre)
        except Ocupado as error:
            datos_log["duracion_ms"] = round((time.monotonic() - reloj) * 1000)
            self.renovar(stream, id_mensaje)
            registrar("evento_ocupado", **datos_log, motivo=motivo_de(error))
            return "ocupado"
        except Exception as error:  # cualquier otro error del manejador cuenta como fallo
            datos_log["duracion_ms"] = round((time.monotonic() - reloj) * 1000)
            return self._fallo(stream, id_mensaje, sobre, fallos + 1, error, datos_log)
        datos_log["duracion_ms"] = round((time.monotonic() - reloj) * 1000)

        # Solo después de que el manejador terminó bien.
        transaccion = self.redis.pipeline(transaction=True)
        transaccion.set(self.clave_procesado(sobre.id), 1, ex=TTL_PROCESADOS)
        transaccion.xack(stream, self.grupo, id_mensaje)
        transaccion.delete(self.clave_fallos(stream, id_mensaje))
        transaccion.execute()
        registrar("evento_procesado", **datos_log)
        return "procesado"

    def entregas(self, stream: str, id_mensaje: str) -> int | None:
        """Cuántas veces entregó Redis el mensaje (XPENDING). None si no se pudo leer."""
        try:
            pendiente = self.redis.xpending_range(
                stream, self.grupo, min=id_mensaje, max=id_mensaje, count=1
            )
        except redis.RedisError:
            return None
        return pendiente[0]["times_delivered"] if pendiente else None

    def _fallo(self, stream, id_mensaje, sobre, fallos, error, datos_log) -> str:
        if fallos > self.max_reintentos(stream):
            self._agotado(sobre, error, datos_log)
            self._a_fallidos(stream, id_mensaje, sobre, None, fallos, error, datos_log)
            return "fallido"
        transaccion = self.redis.pipeline(transaction=True)
        transaccion.set(self.clave_fallos(stream, id_mensaje), fallos, ex=TTL_FALLOS)
        transaccion.execute()
        self.renovar(stream, id_mensaje)  # la espera cuenta desde el fallo
        registrar(
            "evento_reintentado",
            logging.WARNING,
            **datos_log,
            motivo=motivo_de(error),
            siguiente_en_segundos=self.espera(fallos, stream),
        )
        return "reintento"

    def _agotado(self, sobre: Sobre, error, datos_log) -> None:
        accion = self.al_agotar.get(sobre.tipo)
        if accion is None:
            return
        try:
            with correlacion.con_correlacion(sobre.correlacion_id):
                accion(sobre, error)
        except Exception as fallo_al_agotar:
            registrar(
                "al_agotar_fallo",
                logging.ERROR,
                **datos_log,
                motivo=motivo_de(fallo_al_agotar),
            )

    def _confirmar(self, stream: str, id_mensaje: str) -> None:
        transaccion = self.redis.pipeline(transaction=True)
        transaccion.xack(stream, self.grupo, id_mensaje)
        transaccion.delete(self.clave_fallos(stream, id_mensaje))
        transaccion.execute()

    def _a_fallidos(self, stream, id_mensaje, sobre, crudo, intentos, error, datos_log) -> None:
        """Copia el evento a fallidos y lo confirma. Sin los campos no registrables de su
        tipo (marca `datos_omitidos`): esos eventos no se pueden reprocesar."""
        motivo = motivo_de(error)
        campos = {
            "stream": stream,
            "grupo": self.grupo,
            "id_mensaje": id_mensaje,
            "intentos": intentos,
            "motivo": motivo,
        }
        if sobre is None:
            campos["sobre"] = crudo or ""
        else:
            definicion = obtener_tipo(sobre.tipo)
            omitidos = sorted(definicion.no_registrables & set(sobre.datos))
            if omitidos:
                sobre = Sobre(**{**sobre.__dict__, "datos": definicion.registrable(sobre.datos)})
                campos["datos_omitidos"] = ",".join(omitidos)
            campos["sobre"] = sobre.a_json()
        transaccion = self.redis.pipeline(transaction=True)
        # Sin MAXLEN: los fallidos no se recortan (ver docs/eventos.md).
        transaccion.xadd(STREAM_FALLIDOS, campos)
        transaccion.xack(stream, self.grupo, id_mensaje)
        transaccion.delete(self.clave_fallos(stream, id_mensaje))
        transaccion.execute()
        registrar("evento_fallido", logging.ERROR, **datos_log, intentos=intentos, motivo=motivo)

    # --- una vuelta del ciclo ------------------------------------------------------------

    def reclamar_pendientes(self) -> int:
        """Reintenta los mensajes del grupo cuya espera ya pasó: los que fallaron y los
        que dejó colgados otro consumidor. Nunca los que alguien sigue procesando (su
        latido los mantiene recientes)."""
        atendidos = 0
        for stream in self.streams:
            pendientes = self.redis.xpending_range(
                stream, self.grupo, min="-", max="+", count=PENDIENTES_POR_VUELTA
            )
            for pendiente in pendientes:
                if self.detener:
                    return atendidos
                id_mensaje = pendiente["message_id"]
                fallos = self.fallos(stream, id_mensaje)
                espera_ms = int(self.espera(fallos, stream) * 1000)
                if pendiente["time_since_delivered"] < espera_ms:
                    continue
                # min_idle_time: si otro lo tomó o lo renovó entre tanto, no se reclama.
                reclamados = self.redis.xclaim(
                    stream, self.grupo, self.nombre, min_idle_time=espera_ms,
                    message_ids=[id_mensaje],
                )  # fmt: skip
                for reclamado, campos in reclamados:
                    if campos is None:  # ya no está en el stream (recortado)
                        self._confirmar(stream, reclamado)
                        continue
                    self.procesar(stream, reclamado, campos, fallos)
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
                self.procesar(stream, id_mensaje, campos, 0)
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

    def correr(self, instalar_senales: bool = True) -> None:
        if instalar_senales:
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


def correr_en_hilos(fabricar: Callable[[str], Consumidor], hilos: int) -> list[Consumidor]:
    """Corre `hilos` consumidores del mismo grupo en este proceso, cada uno con su nombre
    (`<grupo>-<host>-1`…). Se reparten los eventos: sirve cuando cada evento tarda (la IA)
    y no conviene que se formen en fila. El hilo principal atiende SIGTERM y los detiene a
    todos; cada uno termina su evento en curso."""
    base = f"{socket.gethostname()}"
    consumidores = [fabricar(f"{base}-{numero}") for numero in range(1, hilos + 1)]

    def detener_todos(*_):
        for consumidor in consumidores:
            consumidor.pedir_detener()

    signal.signal(signal.SIGTERM, detener_todos)
    signal.signal(signal.SIGINT, detener_todos)
    trabajadores = [
        threading.Thread(target=c.correr, kwargs={"instalar_senales": False}, name=c.nombre)
        for c in consumidores
    ]
    for trabajador in trabajadores:
        trabajador.start()
    while any(t.is_alive() for t in trabajadores):
        for trabajador in trabajadores:
            trabajador.join(timeout=0.5)
    return consumidores
