"""Operación: estado de los streams y reproceso de los eventos fallidos.

    python -m agroia_comun.eventos estado
    python -m agroia_comun.eventos reprocesar --id <id del mensaje en fallidos>
    python -m agroia_comun.eventos reprocesar --todos

Se corre dentro de cualquier contenedor que tenga `comun` (por ejemplo,
`docker compose exec svc-contenido python -m agroia_comun.eventos estado`).

Reprocesar vuelve a publicar el sobre **con su mismo id** en su stream original y lo quita
de fallidos. Se niega con los que se guardaron sin sus campos no registrables
(`datos_omitidos`, por ejemplo una pregunta a la IA): esos no se pueden rearmar. Los grupos
que ya lo habían procesado lo saltan por su llave de procesados (dura 7 días) o por la
idempotencia de su manejador.
"""

import redis

from agroia_comun.eventos import conexion
from agroia_comun.eventos.catalogo import STREAM_FALLIDOS, ErrorEvento, streams
from agroia_comun.eventos.productor import publicar_sobre
from agroia_comun.eventos.registro import registrar
from agroia_comun.eventos.sobre import Sobre


def estado(cliente: redis.Redis | None = None, ultimos_fallidos: int = 10) -> dict:
    cliente = cliente or conexion.cliente()
    resultado: dict = {"streams": [], "fallidos": {}}
    for stream in streams():
        if not cliente.exists(stream):
            resultado["streams"].append({"stream": stream, "largo": 0, "grupos": []})
            continue
        grupos = []
        for grupo in cliente.xinfo_groups(stream):
            consumidores = cliente.xinfo_consumers(stream, grupo["name"])
            grupos.append(
                {
                    "grupo": grupo["name"],
                    "pendientes": grupo["pending"],
                    "sin_leer": grupo.get("lag"),
                    "consumidores": [
                        {
                            "nombre": c["name"],
                            "pendientes": c["pending"],
                            "inactivo_ms": c["idle"],
                        }
                        for c in consumidores
                    ],
                }
            )
        resultado["streams"].append(
            {"stream": stream, "largo": cliente.xlen(stream), "grupos": grupos}
        )
    fallidos = cliente.xrevrange(STREAM_FALLIDOS, count=ultimos_fallidos)
    resultado["fallidos"] = {
        "total": cliente.xlen(STREAM_FALLIDOS),
        "ultimos": [_resumen_fallido(id_mensaje, campos) for id_mensaje, campos in fallidos],
    }
    return resultado


def _resumen_fallido(id_mensaje: str, campos: dict) -> dict:
    resumen = {
        "id": id_mensaje,
        "grupo": campos.get("grupo"),
        "stream": campos.get("stream"),
        "intentos": campos.get("intentos"),
        "motivo": campos.get("motivo"),
        "datos_omitidos": campos.get("datos_omitidos"),
    }
    try:
        sobre = Sobre.de_json(campos.get("sobre", ""))
        resumen.update(tipo=sobre.tipo, evento_id=sobre.id)
    except ErrorEvento:
        resumen.update(tipo=None, evento_id=None)
    return resumen


def reprocesar(
    cliente: redis.Redis | None = None, ids: list[str] | None = None, todos: bool = False
) -> dict:
    """Vuelve a publicar los fallidos elegidos. Devuelve cuántos se republicaron y cuáles
    no se pudieron (sobre ilegible o tipo desconocido; esos se quedan en fallidos)."""
    if not ids and not todos:
        raise ErrorEvento("Indica --id o --todos.")
    cliente = cliente or conexion.cliente()
    if todos:
        entradas = cliente.xrange(STREAM_FALLIDOS)
    else:
        entradas = []
        for id_mensaje in ids:
            entradas += cliente.xrange(STREAM_FALLIDOS, min=id_mensaje, max=id_mensaje)
    republicados, no_reprocesables = [], []
    for id_mensaje, campos in entradas:
        if campos.get("datos_omitidos"):
            # Se guardó sin sus campos no registrables (la pregunta, la respuesta...): no se
            # puede volver a publicar. En la IA, el usuario usa «Reintentar».
            no_reprocesables.append(
                {"id": id_mensaje, "motivo": f"datos omitidos: {campos['datos_omitidos']}"}
            )
            continue
        try:
            sobre = Sobre.de_json(campos.get("sobre", ""))
            if publicar_sobre(sobre, cliente=cliente, suceso="evento_reprocesado") is None:
                no_reprocesables.append({"id": id_mensaje, "motivo": "Redis no respondió"})
                continue
        except ErrorEvento as error:
            no_reprocesables.append({"id": id_mensaje, "motivo": str(error)})
            continue
        cliente.xdel(STREAM_FALLIDOS, id_mensaje)
        republicados.append({"id": id_mensaje, "evento_id": sobre.id, "tipo": sobre.tipo})
    registrar(
        "fallidos_reprocesados",
        republicados=len(republicados),
        no_reprocesables=len(no_reprocesables),
    )
    return {"republicados": republicados, "no_reprocesables": no_reprocesables}


def descartar(
    cliente: redis.Redis | None = None, ids: list[str] | None = None, todos: bool = False
) -> dict:
    """Borra del stream de fallidos los elegidos, sin volver a publicarlos: para los que ya
    se revisaron y no hace falta reprocesar (por ejemplo, los de `datos_omitidos`, que no se
    pueden). Registra `fallidos_descartados` con cuántos y sus ids (nunca sus datos).
    Devuelve los ids borrados y los que no estaban."""
    if not ids and not todos:
        raise ErrorEvento("Indica --id o --todos.")
    cliente = cliente or conexion.cliente()
    if todos:
        elegidos = [id_mensaje for id_mensaje, _ in cliente.xrange(STREAM_FALLIDOS)]
    else:
        elegidos = list(dict.fromkeys(ids))
    descartados, no_encontrados = [], []
    for id_mensaje in elegidos:
        if cliente.xdel(STREAM_FALLIDOS, id_mensaje):
            descartados.append(id_mensaje)
        else:
            no_encontrados.append(id_mensaje)
    registrar(
        "fallidos_descartados",
        descartados=len(descartados),
        ids=descartados,
        no_encontrados=no_encontrados or None,
    )
    return {"descartados": descartados, "no_encontrados": no_encontrados}
