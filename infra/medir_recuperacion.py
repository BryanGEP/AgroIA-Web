"""Mide cuánto tarda «recuperar contraseña» con un correo que existe y con uno que no.
SOLO EN DESARROLLO. Sirve para comprobar el riesgo B5 de la Entrega 3: si la respuesta
tarda distinto según exista la cuenta, se puede saber qué correos están registrados.

    python infra/medir_recuperacion.py [--veces 3]

Antes de cada par corre `reiniciar_limites` (la recuperación permite 3 por hora por IP y
por correo). Para que la diferencia se note, svc-usuarios debe usar un SMTP que tarde (por
ejemplo, uno que no responde, con EMAIL_HOST=10.255.255.1); con el backend de consola el
envío dura milisegundos.
"""

import argparse
import os
import shutil
import statistics
import subprocess
import time
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parent.parent
BASE = os.environ.get("PRUEBA_BASE", "http://127.0.0.1:8000")
EXISTE = "cliente@demo.agroia.test"
NO_EXISTE = "nadie-registrado@demo.agroia.test"


def reiniciar_limites() -> None:
    docker = os.environ.get("DOCKER") or shutil.which("docker")
    subprocess.run(
        [docker, "compose", "exec", "-T", "svc-usuarios", "python", "manage.py",
         "reiniciar_limites"],
        cwd=RAIZ, check=True, capture_output=True,
    )  # fmt: skip


def medir(correo: str) -> tuple[float, int]:
    """Una conexión nueva por petición, para que reutilizar la conexión no cambie el
    tiempo de una de las dos."""
    with httpx.Client(base_url=BASE, timeout=60) as cliente:
        inicio = time.perf_counter()
        respuesta = cliente.post("/api/usuarios/auth/recuperar/", json={"email": correo})
        return time.perf_counter() - inicio, respuesta.status_code


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--veces", type=int, default=5)
    args = parser.parse_args()
    tiempos: dict[str, list[float]] = {EXISTE: [], NO_EXISTE: []}
    for vuelta in range(1, args.veces + 1):
        reiniciar_limites()
        # Se alterna cuál va primero.
        orden = (EXISTE, NO_EXISTE) if vuelta % 2 else (NO_EXISTE, EXISTE)
        for correo in orden:
            segundos, estado = medir(correo)
            tiempos[correo].append(segundos)
            print(f"  vuelta {vuelta}  {correo:36} {estado}  {segundos * 1000:8.0f} ms")
    reiniciar_limites()
    for correo, valores in tiempos.items():
        print(f"mediana {correo:36} {statistics.median(valores) * 1000:8.0f} ms")


if __name__ == "__main__":
    main()
