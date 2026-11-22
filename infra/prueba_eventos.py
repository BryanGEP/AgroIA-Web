"""Prueba de punta a punta de los eventos (Entrega 4), SOLO EN DESARROLLO.

Corre contra el sistema levantado con `docker compose up` y comprueba, con el evento
usuario_registrado (svc-usuarios -> Redis -> svc-contenido-eventos -> bitácora):

1. Punta a punta: un registro por el gateway llega a la bitácora.
2. Apagado limpio: `docker compose stop` del consumidor (SIGTERM) sale con código 0 y sin
   mensajes a medias.
3. Consumidor caído: lo que se publica mientras está detenido se procesa al volver.
4. Fallido y reproceso: con MongoDB detenido, el evento agota sus reintentos y llega al
   stream de fallidos; con MongoDB de vuelta, `reprocesar` lo guarda una sola vez.

Uso, desde la raíz con el venv activo (unos 3 minutos; el paso 4 espera los 5 reintentos
reales con espera creciente):

    python infra/prueba_eventos.py

Necesita `docker` en el PATH (otra ruta: variable DOCKER) y las cuentas de demostración
(`cargar_usuarios_demo`). Al empezar corre `reiniciar_limites` (registra 3 usuarios y el
límite es de 5 por hora por IP) y al terminar borra los usuarios de prueba y sus eventos
con `limpiar_datos_prueba`. Termina con código 1 si algún paso falla.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parent.parent
BASE = os.environ.get("PRUEBA_BASE", "http://127.0.0.1:8000")
PASSWORD_DEMO = os.environ.get("MATRIZ_PASSWORD_DEMO", "solo-demo-no-usar-en-produccion")
CONSUMIDOR = "svc-contenido-eventos"
STREAM = "agroia:eventos:usuarios"

DOCKER = os.environ.get("DOCKER") or shutil.which("docker")
http = httpx.Client(base_url=BASE, timeout=30)
resultados: list[tuple[str, bool, str]] = []
inicio_total = time.monotonic()


# --- utilidades -----------------------------------------------------------------------------


def titulo(texto: str) -> None:
    print(f"\n== {texto} " + "=" * max(0, 70 - len(texto)))


def paso(nombre: str, ok: bool, detalle: str = "") -> bool:
    resultados.append((nombre, ok, detalle))
    print(f"  [{'ok' if ok else 'FALLA'}] {nombre}" + (f": {detalle}" if detalle else ""))
    return ok


def docker(*argumentos: str, verificar: bool = True) -> str:
    hecho = subprocess.run(
        [DOCKER, "compose", *argumentos],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if verificar and hecho.returncode != 0:
        raise RuntimeError(f"docker compose {' '.join(argumentos)}: {hecho.stderr.strip()}")
    return hecho.stdout


def manage(servicio: str, *argumentos: str) -> str:
    return docker("exec", "-T", servicio, "python", "manage.py", *argumentos).strip()


def estado() -> dict:
    salida = docker("exec", "-T", "svc-contenido", "python", "-m", "agroia_comun.eventos",
                    "estado", "--json")  # fmt: skip
    return json.loads(salida)


def grupo_contenido(datos: dict) -> dict:
    for stream in datos["streams"]:
        if stream["stream"] == STREAM:
            for grupo in stream["grupos"]:
                if grupo["grupo"] == "svc-contenido":
                    return grupo
    return {"pendientes": None, "sin_leer": None}


def esperar(condicion, limite: float, cada: float = 1.0):
    """Repite `condicion()` hasta que devuelva algo verdadero o pase `limite` segundos."""
    fin = time.monotonic() + limite
    while True:
        valor = condicion()
        if valor or time.monotonic() > fin:
            return valor
        time.sleep(cada)


def token_admin() -> str:
    r = http.post(
        "/api/usuarios/auth/login/",
        json={"email": "admin@demo.agroia.test", "password": PASSWORD_DEMO},
    )
    if r.status_code != 200:
        sys.exit(f"No pude iniciar sesión como admin ({r.status_code}). ¿cargar_usuarios_demo?")
    return r.json()["access"]


def registrar(etiqueta: str) -> tuple[str, float]:
    correo = f"eventos-{etiqueta}.{int(time.time() * 1000)}@example.com"
    r = http.post(
        "/api/usuarios/auth/registro/",
        json={
            "nombre": "Prueba",
            "apellidos": "Eventos",
            "email": correo,
            "password": "Aguacate-Hass-2026",
            "password_confirmacion": "Aguacate-Hass-2026",
            "acepto_privacidad": True,
        },
    )
    if r.status_code != 201:
        raise RuntimeError(f"El registro respondió {r.status_code}: {r.text[:200]}")
    return r.json()["id"], time.monotonic()


def en_bitacora(usuario_id: str, encabezados: dict) -> list[dict]:
    r = http.get(
        "/api/contenido/bitacora/", params={"tipo": "usuario_registrado"}, headers=encabezados
    )
    if r.status_code != 200:
        return []
    return [e for e in r.json()["results"] if e["usuario_id"] == usuario_id]


def corriendo(servicio: str) -> bool:
    return servicio in docker("ps", "--status", "running", "--services")


# --- pasos ---------------------------------------------------------------------------------


def punta_a_punta(admin: dict) -> None:
    titulo("1. Punta a punta: registro por el gateway -> bitácora")
    usuario, momento = registrar("punta")
    print(f"  usuario registrado: {usuario}")
    eventos = esperar(lambda: en_bitacora(usuario, admin), 20, 0.5)
    tardanza = time.monotonic() - momento
    if not paso("El evento llegó a la bitácora", len(eventos) == 1, f"en {tardanza:.1f} s"):
        return
    e = eventos[0]
    print(f"  bitácora: tipo={e['tipo']} servicio={e['servicio']} datos={e['datos']}")
    print(f"            evento_id={e['evento_id']} correlacion_id={e['correlacion_id']}")
    paso("Sin datos personales en el evento", set(e["datos"]) == {"rol"}, f"datos={e['datos']}")


def apagado_y_consumidor_caido(admin: dict) -> None:
    titulo("2. Apagado limpio del consumidor (SIGTERM)")
    antes = time.monotonic()
    docker("stop", CONSUMIDOR)
    duracion = time.monotonic() - antes
    salida = docker("ps", "-a", "--format", "{{.Service}} {{.State}} {{.ExitCode}}", CONSUMIDOR)
    codigo = salida.split()[-1] if salida.split() else "?"
    registro = docker("logs", "--no-log-prefix", "--tail", "5", CONSUMIDOR)
    paso("Se detuvo con código 0", codigo == "0", f"en {duracion:.1f} s, código {codigo}")
    paso(
        "Registró consumidor_deteniendo y consumidor_detenido",
        "consumidor_deteniendo" in registro and "consumidor_detenido" in registro,
    )
    paso("No dejó mensajes a medias", grupo_contenido(estado())["pendientes"] == 0)

    titulo("3. Consumidor caído: lo publicado mientras tanto se procesa al volver")
    usuario, _ = registrar("caido")
    print(f"  usuario registrado con el consumidor detenido: {usuario}")
    time.sleep(2)
    grupo = grupo_contenido(estado())
    paso("Mientras está detenido, no llega a la bitácora", en_bitacora(usuario, admin) == [])
    paso(
        "El evento espera en Redis sin leer",
        grupo["sin_leer"] == 1,
        f"sin leer={grupo['sin_leer']}",
    )
    docker("start", CONSUMIDOR)
    momento = time.monotonic()
    eventos = esperar(lambda: en_bitacora(usuario, admin), 30, 0.5)
    tardanza = time.monotonic() - momento
    paso("Al volver lo procesó", len(eventos) == 1, f"{tardanza:.1f} s después de arrancar")


def fallido_y_reproceso(admin: dict) -> None:
    titulo("4. Fallido y reproceso (MongoDB detenido)")
    antes = estado()["fallidos"]["total"]
    docker("stop", "mongo")
    print("  mongo detenido")
    usuario, momento = registrar("fallido")
    print(f"  usuario registrado: {usuario}")
    print("  esperando los reintentos (5, con espera creciente de 2, 4, 8, 16 y 32 s)...")

    def nuevo_fallido():
        datos = estado()["fallidos"]
        return datos["ultimos"][0] if datos["total"] > antes else None

    fallido = esperar(nuevo_fallido, 180, 3)
    tardanza = time.monotonic() - momento
    if not paso("Llegó al stream de fallidos", fallido is not None, f"en {tardanza:.0f} s"):
        docker("start", "mongo")
        return
    print(f"  fallido: id={fallido['id']} grupo={fallido['grupo']} intentos={fallido['intentos']}")
    print(f"           motivo: {fallido['motivo'][:110]}")
    paso("Con 6 intentos (1 + 5 reintentos)", fallido["intentos"] == "6")
    registro = docker("logs", "--no-log-prefix", "--since", "5m", CONSUMIDOR)
    reintentos = registro.count('"evento_reintentado"')
    paso(
        "Quedó cada reintento en el log", reintentos >= 5, f"{reintentos} líneas evento_reintentado"
    )

    docker("start", "mongo")
    esperar(lambda: "healthy" in docker("ps", "--format", "{{.Status}}", "mongo"), 60, 2)
    print("  mongo de vuelta")
    paso("Antes de reprocesar no está en la bitácora", en_bitacora(usuario, admin) == [])
    salida = docker("exec", "-T", "svc-contenido", "python", "-m", "agroia_comun.eventos",
                    "reprocesar", "--id", fallido["id"])  # fmt: skip
    print("  " + salida.strip().replace("\n", "\n  "))
    eventos = esperar(lambda: en_bitacora(usuario, admin), 30, 0.5)
    paso("Después de reprocesar está en la bitácora una sola vez", len(eventos) == 1)
    if eventos:
        paso(
            "Conservó el id del evento",
            eventos[0]["evento_id"] == fallido.get("evento_id"),
            eventos[0]["evento_id"],
        )
    paso("El stream de fallidos volvió a como estaba", estado()["fallidos"]["total"] == antes)


def limpiar() -> None:
    titulo("Limpieza")
    ids = manage("svc-usuarios", "limpiar_datos_prueba", "--listar-ids")
    print("  " + manage("svc-contenido", "limpiar_datos_prueba", "--usuarios", ids))
    print("  " + manage("svc-usuarios", "limpiar_datos_prueba"))


def main() -> None:
    if not DOCKER:
        sys.exit("Necesito docker en el PATH (o la variable DOCKER).")
    print(f"Prueba de eventos · {datetime.now():%Y-%m-%d %H:%M} · gateway {BASE}")
    print("  " + manage("svc-usuarios", "reiniciar_limites"))
    for servicio in ("redis", "mongo", "svc-usuarios", "svc-contenido", CONSUMIDOR):
        if not corriendo(servicio):
            sys.exit(f"{servicio} no está corriendo. Levanta todo con docker compose up -d.")
    admin = {"Authorization": f"Bearer {token_admin()}"}
    try:
        punta_a_punta(admin)
        apagado_y_consumidor_caido(admin)
        admin = {"Authorization": f"Bearer {token_admin()}"}  # por si venció el access
        fallido_y_reproceso(admin)
    finally:
        for servicio in ("mongo", CONSUMIDOR):
            if not corriendo(servicio):
                docker("start", servicio, verificar=False)
        limpiar()

    bien = sum(ok for _, ok, _ in resultados)
    titulo("Resumen")
    print(f"  {bien} de {len(resultados)} comprobaciones correctas "
          f"en {time.monotonic() - inicio_total:.0f} s")  # fmt: skip
    sys.exit(0 if bien == len(resultados) else 1)


if __name__ == "__main__":
    main()
