"""python -m agroia_comun.eventos estado | reprocesar | descartar (ver operacion.py)."""

import argparse
import json
import logging
import sys

from agroia_comun.eventos import conexion, operacion
from agroia_comun.eventos.catalogo import STREAM_FALLIDOS, ErrorEvento


def _imprimir_estado(datos: dict) -> None:
    for s in datos["streams"]:
        print(f"{s['stream']}  ({s['largo']} mensajes)")
        if not s["grupos"]:
            print("  sin grupos de consumidores")
        for g in s["grupos"]:
            print(f"  grupo {g['grupo']}: pendientes {g['pendientes']}, sin leer {g['sin_leer']}")
            for c in g["consumidores"]:
                segundos = c["inactivo_ms"] / 1000
                print(
                    f"    consumidor {c['nombre']}: pendientes {c['pendientes']}, "
                    f"inactivo {segundos:.0f} s"
                )
    f = datos["fallidos"]
    print(f"\nFallidos: {f['total']}")
    for x in f["ultimos"]:
        print(
            f"  {x['id']}  {x['tipo']}  grupo {x['grupo']}  intentos {x['intentos']}  "
            f"motivo: {x['motivo']}"
        )


def _descartar(args) -> int:
    if not args.ids and not args.todos:
        print("Indica --id o --todos.", file=sys.stderr)
        return 2
    if args.todos and not args.si:
        total = conexion.cliente().xlen(STREAM_FALLIDOS)
        if total == 0:
            print("No hay fallidos.")
            return 0
        # Borrar todo no se puede deshacer: se confirma, salvo con --si (scripts).
        try:
            respuesta = input(f"¿Borrar los {total} eventos fallidos? No se puede deshacer [s/N]: ")
        except EOFError:
            respuesta = ""
        if respuesta.strip().lower() not in ("s", "si", "sí"):
            print("No se borró nada.")
            return 1
    resultado = operacion.descartar(ids=args.ids, todos=args.todos)
    print(f"Descartados: {len(resultado['descartados'])}")
    for id_mensaje in resultado["descartados"]:
        print(f"  {id_mensaje}")
    for id_mensaje in resultado["no_encontrados"]:
        print(f"  No estaba en fallidos: {id_mensaje}")
    return 0


def main(argumentos: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    parser = argparse.ArgumentParser(prog="python -m agroia_comun.eventos")
    sub = parser.add_subparsers(dest="comando", required=True)
    p_estado = sub.add_parser("estado", help="Streams, grupos, pendientes y fallidos.")
    p_estado.add_argument("--json", action="store_true")
    p_rep = sub.add_parser("reprocesar", help="Vuelve a publicar eventos fallidos.")
    p_rep.add_argument("--id", action="append", dest="ids", help="Id del mensaje en fallidos.")
    p_rep.add_argument("--todos", action="store_true")
    p_des = sub.add_parser("descartar", help="Borra eventos del stream de fallidos.")
    p_des.add_argument("--id", action="append", dest="ids", help="Id del mensaje en fallidos.")
    p_des.add_argument("--todos", action="store_true")
    p_des.add_argument("--si", action="store_true", help="No pedir confirmación (scripts).")
    args = parser.parse_args(argumentos)

    if args.comando == "estado":
        datos = operacion.estado()
        if args.json:
            print(json.dumps(datos, ensure_ascii=False, indent=2))
        else:
            _imprimir_estado(datos)
        return 0
    if args.comando == "descartar":
        return _descartar(args)
    try:
        resultado = operacion.reprocesar(ids=args.ids, todos=args.todos)
    except ErrorEvento as error:
        print(error, file=sys.stderr)
        return 2
    print(f"Republicados: {len(resultado['republicados'])}")
    for r in resultado["republicados"]:
        print(f"  {r['id']} -> {r['tipo']} {r['evento_id']}")
    for r in resultado["no_reprocesables"]:
        print(f"  No se pudo: {r['id']} ({r['motivo']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
