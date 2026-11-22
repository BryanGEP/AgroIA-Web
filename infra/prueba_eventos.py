"""Prueba de punta a punta de los eventos (Entrega 4), SOLO EN DESARROLLO.

Corre contra el sistema levantado con `docker compose up` y comprueba, con el evento
usuario_registrado (svc-usuarios -> Redis -> svc-contenido-eventos -> bitácora):

1. Punta a punta: un registro por el gateway llega a la bitácora.
2. Apagado limpio: `docker compose stop` del consumidor (SIGTERM) sale con código 0 y sin
   mensajes a medias.
3. Consumidor caído: lo que se publica mientras está detenido se procesa al volver.
4. Fallido y reproceso: con MongoDB detenido, el evento agota sus reintentos y llega al
   stream de fallidos; con MongoDB de vuelta, `reprocesar` lo guarda una sola vez.
5. Flujo de negocio completo, cada petición con su propio X-Correlacion-Id: registro ->
   correo de verificación (svc-usuarios-eventos) -> verificar con el enlace del correo ->
   pedido -> pago -> cambio de estado del administrador. Cada evento aparece en la
   bitácora con la correlación de su petición (filtro correlacion_id).
6. La correlación del pedido en los logs del gateway (`peticion`), de svc-tienda
   (`evento_publicado`) y del consumidor (`evento_procesado`); el token de verificación
   en ningún log del gateway.
7. Un correo que falla: con un servidor de correo que no responde, la recuperación llega
   a fallidos; con el servidor de vuelta, `reprocesar` lo envía con un token nuevo y
   vigente, que sirve para restablecer la contraseña.

Uso, desde la raíz con el venv activo (unos 3 minutos; el paso 4 espera los 5 reintentos
reales con espera creciente; el 7 recrea svc-usuarios-eventos con otro servidor de
correo y lo devuelve a la consola al terminar):

    python infra/prueba_eventos.py

Necesita `docker` en el PATH (otra ruta: variable DOCKER) y las cuentas de demostración
(`cargar_usuarios_demo`). Al empezar corre `reiniciar_limites` (registra 3 usuarios y el
límite es de 5 por hora por IP) y al terminar borra los usuarios de prueba y sus eventos
con `limpiar_datos_prueba`. Termina con código 1 si algún paso falla.
"""

import json
import os
import quopri
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

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


def docker(*argumentos: str, verificar: bool = True, entorno: dict | None = None) -> str:
    """`entorno` cambia variables solo para este comando (por ejemplo, para recrear un
    contenedor con otro servidor de correo)."""
    hecho = subprocess.run(
        [DOCKER, "compose", *argumentos],
        cwd=RAIZ,
        env={**os.environ, **(entorno or {})},
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


CONSUMIDOR_CORREOS = "svc-usuarios-eventos"
PASSWORD_FLUJO = "Aguacate-Hass-2026"
DIRECCION = {
    "calle": "Camino a La Palma",
    "numero": "km 3",
    "colonia": "La Palma",
    "municipio": "Jiquilpan",
    "estado": "Michoacán",
    "codigo_postal": "59510",
}


def nueva_correlacion() -> dict:
    return {"X-Correlacion-Id": str(uuid.uuid4())}


def correo_en_log(destinatario: str, marca: str, desde: str, limite: float = 30) -> str | None:
    """El texto (ya decodificado) del último correo a `destinatario` que contiene `marca`,
    tomado del log del consumidor de correos (backend de consola)."""

    def buscar():
        registro = docker("logs", "--no-log-prefix", "--since", desde, CONSUMIDOR_CORREOS)
        encontrado = None
        for bloque in registro.split("Content-Type: multipart/alternative")[1:]:
            if f"To: {destinatario}" not in bloque:
                continue
            texto = bloque
            if "quoted-printable" in bloque:  # Django usa 8bit, salvo líneas muy largas
                texto = quopri.decodestring(bloque.encode("utf-8")).decode("utf-8", "replace")
            if marca in texto:
                encontrado = texto
        return encontrado

    return esperar(buscar, limite, 1)


def en_bitacora_por(encabezados: dict, **filtros) -> list[dict]:
    r = http.get("/api/contenido/bitacora/", params=filtros, headers=encabezados)
    return r.json()["results"] if r.status_code == 200 else []


def flujo_de_negocio(admin: dict) -> dict:
    titulo("5. Flujo completo con correlación: registro -> correo -> verificar -> pedido")
    desde = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    correo = f"eventos-flujo.{int(time.time() * 1000)}@example.com"
    flujo: dict[str, str] = {}

    c = nueva_correlacion()
    r = http.post(
        "/api/usuarios/auth/registro/",
        json={"nombre": "Prueba", "apellidos": "Flujo", "email": correo,
              "password": PASSWORD_FLUJO, "password_confirmacion": PASSWORD_FLUJO,
              "acepto_privacidad": True},
        headers=c,
    )  # fmt: skip
    usuario = r.json()["id"]
    flujo["usuario_registrado"] = c["X-Correlacion-Id"]
    paso("Registro (201) devuelve la misma correlación", r.status_code == 201
         and r.headers.get("X-Correlacion-Id") == c["X-Correlacion-Id"])  # fmt: skip

    texto = correo_en_log(correo, "verificar-correo/?token=", desde)
    if not paso("El consumidor de correos envió la verificación", texto is not None):
        return {"usuario": usuario, "correo": correo}
    token = re.search(r"verificar-correo/\?token=([^\s\"<>]+)", texto).group(1)
    c = nueva_correlacion()
    r = http.post("/api/usuarios/auth/verificar-correo/", json={"token": unquote(token)},
                  headers=c)  # fmt: skip
    flujo["correo_verificado"] = c["X-Correlacion-Id"]
    paso("El enlace del correo verifica la cuenta", r.status_code == 200, r.json().get("mensaje"))

    r = http.post("/api/usuarios/auth/login/", json={"email": correo, "password": PASSWORD_FLUJO})
    cliente = {"Authorization": f"Bearer {r.json()['access']}"}
    productos = http.get("/api/tienda/productos/", params={"disponible": "true"}).json()
    slug = productos["results"][0]["slug"]
    http.post("/api/tienda/carrito/items/", json={"producto": slug, "cantidad": 1},
              headers=cliente)  # fmt: skip

    c = nueva_correlacion()
    r = http.post("/api/tienda/pedidos/", json={"direccion_envio": DIRECCION,
                  "metodo_pago": "tarjeta"}, headers={**cliente, **c})  # fmt: skip
    pedido = r.json()["id"]
    flujo["pedido_creado"] = c["X-Correlacion-Id"]
    paso("Pedido creado (201)", r.status_code == 201, f"pedido {pedido}")

    c = nueva_correlacion()
    r = http.post(f"/api/tienda/pedidos/{pedido}/pagar/", headers={**cliente, **c})
    flujo["pedido_estado_cambiado:pagado"] = c["X-Correlacion-Id"]
    paso("Pago simulado (200)", r.status_code == 200)

    # El administrador lo cancela: también es un cambio de estado y devuelve el stock, así
    # que el catálogo de demostración queda como estaba.
    c = nueva_correlacion()
    r = http.patch(f"/api/tienda/pedidos/{pedido}/estado/", json={"estado": "cancelado"},
                   headers={**admin, **c})  # fmt: skip
    flujo["pedido_estado_cambiado:cancelado"] = c["X-Correlacion-Id"]
    paso("El administrador cambia el estado (200)", r.status_code == 200)

    print("  bitácora por correlación (una petición, un evento):")
    for clave, correlacion in flujo.items():
        tipo, _, estado_nuevo = clave.partition(":")
        eventos = esperar(lambda c=correlacion: en_bitacora_por(admin, correlacion_id=c), 20, 0.5)
        ok = (
            len(eventos) == 1
            and eventos[0]["tipo"] == tipo
            and eventos[0]["usuario_id"] == usuario
            and (not estado_nuevo or eventos[0]["datos"].get("estado_nuevo") == estado_nuevo)
        )
        detalle = f"{eventos[0]['tipo']} de {eventos[0]['servicio']}" if eventos else "no llegó"
        paso(f"  {clave} con correlación {correlacion[:8]}…", ok, detalle)

    todos = en_bitacora_por(admin, usuario_id=usuario)
    paso("Filtro por usuario: los 5 eventos del flujo", len(todos) == 5,
         ", ".join(sorted(e["tipo"] for e in todos)))  # fmt: skip

    titulo("6. La correlación en los logs del gateway y de los servicios")
    correlacion = flujo["pedido_creado"]
    for servicio, que in (
        ("web", '"evento": "peticion"'),
        ("svc-tienda", '"evento": "evento_publicado"'),
        ("svc-contenido-eventos", '"evento": "evento_procesado"'),
    ):
        lineas = [
            linea for linea in docker("logs", "--no-log-prefix", "--since", desde, servicio)
            .splitlines() if correlacion in linea and que in linea
        ]  # fmt: skip
        paso(f"{servicio}: {que.split(': ')[1]} con la correlación del pedido", bool(lineas))
    registro_web = docker("logs", "--no-log-prefix", "--since", desde, "web")
    paso("Ningún log del gateway trae el token de verificación", token not in registro_web
         and unquote(token) not in registro_web)  # fmt: skip
    return {"usuario": usuario, "correo": correo}


def correo_que_falla(admin: dict, flujo: dict) -> None:
    titulo("7. Un correo que falla, llega a fallidos y se reprocesa")
    if not flujo.get("correo"):
        paso("Hay un usuario del flujo para pedir la recuperación", False)
        return
    falla = {
        "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "EMAIL_HOST": "10.255.255.1",  # no responde
        "EMAIL_TIMEOUT": "2",
        "EVENTOS_MAX_REINTENTOS": "2",
        "EVENTOS_ESPERA_BASE": "1",
    }
    print("  servidor de correo que no responde (10.255.255.1, timeout 2 s), 2 reintentos")
    docker("up", "-d", CONSUMIDOR_CORREOS, entorno=falla)
    try:
        antes = estado()["fallidos"]["total"]
        desde = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = http.post("/api/usuarios/auth/recuperar/", json={"email": flujo["correo"]})
        paso("La recuperación responde 200 al momento", r.status_code == 200,
             f"{r.elapsed.total_seconds() * 1000:.0f} ms")  # fmt: skip

        def nuevo_fallido():
            datos = estado()["fallidos"]
            return datos["ultimos"][0] if datos["total"] > antes else None

        fallido = esperar(nuevo_fallido, 60, 2)
        if not paso(
            "Llegó a fallidos",
            fallido is not None,
            fallido and f"grupo {fallido['grupo']}, intentos {fallido['intentos']}",
        ):
            return  # fmt: skip
        paso("El motivo no trae el destinatario", flujo["correo"] not in fallido["motivo"],
             fallido["motivo"])  # fmt: skip
    finally:
        docker("up", "-d", CONSUMIDOR_CORREOS)  # vuelve el backend de consola
        print("  servidor de correo de vuelta (consola)")
    esperar(lambda: corriendo(CONSUMIDOR_CORREOS), 30, 1)
    time.sleep(3)
    salida = docker("exec", "-T", "svc-usuarios", "python", "-m", "agroia_comun.eventos",
                    "reprocesar", "--id", fallido["id"])  # fmt: skip
    print("  " + salida.strip().replace("\n", "\n  "))
    texto = correo_en_log(flujo["correo"], "/restablecer/", desde)
    if not paso("Al reprocesar se envió el correo", texto is not None):
        return
    uid, token = re.search(r"/restablecer/([^/\s]+)/([^/\s]+)/", texto).groups()
    r = http.post(
        "/api/usuarios/auth/restablecer/",
        json={"uid": uid, "token": token, "password": "Hass-Mendez-2026",
              "password_confirmacion": "Hass-Mendez-2026"},
    )  # fmt: skip
    paso("El token, generado al reprocesar, está vigente", r.status_code == 200)
    eventos = esperar(
        lambda: en_bitacora_por(admin, usuario_id=flujo["usuario"], tipo="password_cambiada"),
        20, 0.5,
    )  # fmt: skip
    paso("password_cambiada (recuperación) en la bitácora", len(eventos) == 1
         and eventos[0]["datos"] == {"motivo": "recuperacion"})  # fmt: skip


def limpiar() -> None:
    titulo("Limpieza")
    ids = manage("svc-usuarios", "limpiar_datos_prueba", "--listar-ids")
    print("  " + manage("svc-tienda", "limpiar_datos_prueba", "--usuarios", ids))
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
        admin = {"Authorization": f"Bearer {token_admin()}"}
        flujo = flujo_de_negocio(admin)
        correo_que_falla(admin, flujo)
    finally:
        for servicio in ("mongo", CONSUMIDOR, CONSUMIDOR_CORREOS):
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
