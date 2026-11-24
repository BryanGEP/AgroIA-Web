"""Worker de svc-ia: atiende las solicitudes de IA que llegan por eventos (Entrega 4).

    python -m app.worker        (contenedor svc-ia-worker, misma imagen que svc-ia)

Grupo `svc-ia` sobre el stream `agroia:eventos:ia-solicitudes`, con IA_WORKER_HILOS hilos
(2): una respuesta del agente tarda hasta 30 s y las preguntas de varios usuarios no deben
formarse en fila. Son 2 y no más porque la llave gratuita de Groq rechaza llamadas
(RateLimitError) con 3 a la vez; con una llave de pago se puede subir.

- `ia_pregunta_solicitada` → llama al agente → publica `ia_respuesta_generada` o
  `ia_respuesta_fallida` (con el código).
- `diagnostico_solicitado` → lee la copia temporal de la imagen en Redis → clasifica →
  publica `diagnostico_generado` o `diagnostico_fallido` (hoy `modelo_no_disponible`).

Errores que vale la pena reintentar (tiempo agotado, sin conexión, 5xx, 429): el manejador
lanza el error y la librería reintenta con la política del stream (2 reintentos, espera de
5 y 10 s). Al agotarlos, `al_agotar` publica la fallida. Los que no (4xx, respuesta vacía):
se publica la fallida al momento, sin reintentar.

Idempotencia: un candado por solicitud en Redis (`agroia:ia:candado:<solicitud_id>`).
`procesando` mientras se llama al agente (vence si el worker muere) y `hecho` después; la
misma solicitud otra vez no vuelve a llamar al agente. Si otro hilo la tiene en
`procesando`, se lanza `Ocupado`, que no cuenta como intento.

Una solicitud que ya venció no se atiende (no gasta tokens): se publica la fallida con
`vencida`. La pregunta, el historial y la respuesta no se escriben en ningún log.
"""

import logging
import sys
from datetime import UTC, datetime

import httpx

from agroia_comun.eventos import Consumidor, Sobre, conexion, publicar
from agroia_comun.eventos.consumidor import Ocupado, correr_en_hilos
from agroia_comun.eventos.registro import registrar
from app.agente import AgenteNoDisponible, ClienteAgente
from app.config import settings, validar
from app.vision import obtener_clasificador

GRUPO = "svc-ia"
ORIGEN = "svc-ia"
FIRMAS_IMAGEN = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")
HECHO_SEGUNDOS = 24 * 3600


def llave_de_candado(solicitud_id: str) -> str:
    return f"agroia:ia:candado:{solicitud_id}"


def llave_de_imagen(solicitud_id: str) -> str:
    """La misma que usa svc-contenido al solicitar el diagnóstico."""
    return f"agroia:ia:imagen:{solicitud_id}"


def _vencida(sobre: Sobre) -> bool:
    return datetime.now(UTC) > datetime.fromisoformat(sobre.datos["vence_en"])


def _tomar(solicitud_id: str) -> bool:
    """Toma el candado de la solicitud. False si ya está hecha (no hay nada que hacer).
    Lanza Ocupado si otro la está procesando."""
    redis = conexion.cliente()
    duracion = int(settings.agente_timeout) + 15
    if redis.set(llave_de_candado(solicitud_id), "procesando", nx=True, ex=duracion):
        return True
    if redis.get(llave_de_candado(solicitud_id)) == "hecho":
        return False
    raise Ocupado(f"otro consumidor está atendiendo la solicitud {solicitud_id}")


def _terminar(solicitud_id: str) -> None:
    conexion.cliente().set(llave_de_candado(solicitud_id), "hecho", ex=HECHO_SEGUNDOS)


def _soltar(solicitud_id: str) -> None:
    """Para que el reintento pueda tomarlo."""
    conexion.cliente().delete(llave_de_candado(solicitud_id))


def _base_pregunta(sobre: Sobre) -> dict:
    return {k: sobre.datos[k] for k in ("solicitud_id", "usuario_id", "conversacion_id")}


def _base_diagnostico(sobre: Sobre) -> dict:
    return {k: sobre.datos[k] for k in ("solicitud_id", "diagnostico_id", "usuario_id")}


def _publicar(tipo: str, datos: dict) -> None:
    """Si Redis no responde, publicar no lanza: aquí sí hace falta saberlo, para que la
    librería reintente y la solicitud no quede sin resultado."""
    if publicar(tipo, datos, origen=ORIGEN) is None:
        raise ConnectionError(f"No se pudo publicar {tipo}.")


# --- Pregunta al agente ---------------------------------------------------------------------


def agente() -> ClienteAgente:
    return ClienteAgente(
        httpx.Client(base_url=settings.url_agente, timeout=settings.agente_timeout)
    )


def responder(sobre: Sobre) -> None:
    datos = sobre.datos
    if _vencida(sobre):
        _publicar("ia_respuesta_fallida", {**_base_pregunta(sobre), "codigo": "vencida"})
        return
    if not _tomar(datos["solicitud_id"]):
        return  # ya se respondió
    cliente = agente()
    try:
        resultado = cliente.preguntar(datos["pregunta"], datos["historial"])
    except AgenteNoDisponible as error:
        if error.reintentable:
            _soltar(datos["solicitud_id"])
            raise  # la librería reintenta; al agotar, al_agotar publica la fallida
        _publicar("ia_respuesta_fallida", {**_base_pregunta(sobre), "codigo": "pregunta_invalida"})
        _terminar(datos["solicitud_id"])
        registrar("ia_sin_reintento", logging.WARNING, solicitud_id=datos["solicitud_id"],
                  correlacion_id=sobre.correlacion_id, motivo=error.motivo)  # fmt: skip
        return
    finally:
        cliente.http.close()
    _publicar(
        "ia_respuesta_generada",
        {**_base_pregunta(sobre), "respuesta": resultado.respuesta, "fuentes": resultado.fuentes},
    )
    _terminar(datos["solicitud_id"])


def pregunta_agotada(sobre: Sobre, error: BaseException) -> None:
    """Se agotaron los reintentos: el usuario ve el error sin esperar al vencimiento."""
    _publicar("ia_respuesta_fallida", {**_base_pregunta(sobre), "codigo": "agente_no_disponible"})
    _terminar(sobre.datos["solicitud_id"])


# --- Diagnóstico ----------------------------------------------------------------------------


def _fallido(sobre: Sobre, codigo: str) -> None:
    _publicar("diagnostico_fallido", {**_base_diagnostico(sobre), "codigo": codigo})
    conexion.cliente_binario().delete(llave_de_imagen(sobre.datos["solicitud_id"]))
    _terminar(sobre.datos["solicitud_id"])


def diagnosticar(sobre: Sobre) -> None:
    solicitud_id = sobre.datos["solicitud_id"]
    if _vencida(sobre):
        _fallido(sobre, "vencida")
        return
    if not _tomar(solicitud_id):
        return
    imagen = conexion.cliente_binario().get(llave_de_imagen(solicitud_id))
    if imagen is None:
        _fallido(sobre, "imagen_no_disponible")
        return
    if not imagen.startswith(FIRMAS_IMAGEN):
        _fallido(sobre, "imagen_invalida")
        return
    clasificador = obtener_clasificador()
    if clasificador is None:
        _fallido(sobre, "modelo_no_disponible")
        return
    try:
        resultado = clasificador.clasificar(imagen)
    except Exception:
        _soltar(solicitud_id)
        raise
    _publicar(
        "diagnostico_generado",
        {
            **_base_diagnostico(sobre),
            "clase": resultado.clase,
            "confianza": resultado.confianza,
            "probabilidades": resultado.probabilidades,
            "modelo_version": clasificador.modelo_version,
        },
    )
    conexion.cliente_binario().delete(llave_de_imagen(solicitud_id))
    _terminar(solicitud_id)


def diagnostico_agotado(sobre: Sobre, error: BaseException) -> None:
    _fallido(sobre, "clasificador_fallo")


MANEJADORES = {"ia_pregunta_solicitada": responder, "diagnostico_solicitado": diagnosticar}
AL_AGOTAR = {
    "ia_pregunta_solicitada": pregunta_agotada,
    "diagnostico_solicitado": diagnostico_agotado,
}


def fabricar(sufijo: str) -> Consumidor:
    return Consumidor(GRUPO, MANEJADORES, nombre=f"{GRUPO}-{sufijo}", al_agotar=AL_AGOTAR)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    validar(settings)
    registrar(
        "worker_iniciado",
        grupo=GRUPO,
        hilos=settings.ia_worker_hilos,
        clasificador_de_prueba=settings.clasificador_prueba,
    )
    correr_en_hilos(fabricar, settings.ia_worker_hilos)


if __name__ == "__main__":
    main()
