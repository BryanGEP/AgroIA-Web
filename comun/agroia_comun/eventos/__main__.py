"""python -m agroia_comun.eventos estado | reprocesar (ver operacion.py)."""

import argparse
import json
import logging
import sys

from agroia_comun.eventos import operacion
from agroia_comun.eventos.catalogo import ErrorEvento


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


def main(argumentos: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    parser = argparse.ArgumentParser(prog="python -m agroia_comun.eventos")
    sub = parser.add_subparsers(dest="comando", required=True)
    p_estado = sub.add_parser("estado", help="Streams, grupos, pendientes y fallidos.")
    p_estado.add_argument("--json", action="store_true")
    p_rep = sub.add_parser("reprocesar", help="Vuelve a publicar eventos fallidos.")
    p_rep.add_argument("--id", action="append", dest="ids", help="Id del mensaje en fallidos.")
    p_rep.add_argument("--todos", action="store_true")
    args = parser.parse_args(argumentos)

    if args.comando == "estado":
        datos = operacion.estado()
        if args.json:
            print(json.dumps(datos, ensure_ascii=False, indent=2))
        else:
            _imprimir_estado(datos)
        return 0
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
