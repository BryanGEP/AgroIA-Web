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

8. IA asíncrona con el agente real: preguntar responde 202 al momento, la respuesta llega
   por svc-ia-worker y queda en la conversación; la correlación en web, svc-contenido,
   svc-ia-worker y svc-contenido-eventos; ni la pregunta ni la respuesta en los logs.
9. Agente detenido: 2 reintentos, fallida con `agente_no_disponible` (sin esperar al
   vencimiento), fallidos sin la pregunta, `reprocesar` que lo rechaza y `descartar` que lo
   borra; con el agente de
   vuelta, «Reintentar» trae la respuesta sin repetir la pregunta.
10. Concurrencia: 5 preguntas a la vez. Por cada una, del log del worker: el hilo, cuándo
    empezó, cuántas entregas e intentos tuvo y cuánto tardó el agente. Antes espera a que
    pasen 90 s sin llamadas al agente (límite por minuto de Groq). Se atienden de N en
    N (N = IA_WORKER_HILOS del worker que corre, 2 por defecto) y ninguna tiene entregas
    de más (el reclamo no tomó ninguna en curso).
11. Diagnóstico: sin modelo `modelo_no_disponible` y sin foto guardada; con el
    clasificador de prueba (recrea svc-ia-worker con IA_CLASIFICADOR_PRUEBA=1 y
    DEBUG=True, y lo devuelve al terminar), un resultado marcado `es_prueba`; ninguna
    copia de la imagen queda en Redis.

Uso, desde la raíz con el venv activo (unos 3 minutos; el paso 4 espera los 5 reintentos
reales con espera creciente; el 7 recrea svc-usuarios-eventos con otro servidor de
correo y lo devuelve a la consola al terminar):

    python infra/prueba_eventos.py
    python infra/prueba_eventos.py --solo-ia     # solo los pasos 8 a 11
    python infra/prueba_eventos.py --solo-ia --pasos=10,11

Los pasos 8, 9 y 10 llaman al agente real (gastan tokens de Groq).

Necesita `docker` en el PATH (otra ruta: variable DOCKER) y las cuentas de demostración
(`cargar_usuarios_demo`). Al empezar corre `reiniciar_limites` en svc-usuarios (registra 4
usuarios y el límite es de 5 por hora por IP) y en svc-contenido (límite de preguntas a la
IA), y al terminar borra los usuarios de prueba y sus eventos
con `limpiar_datos_prueba`. Termina con código 1 si algún paso falla.
"""

import base64
import json
import os
import quopri
import re
import shutil
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
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


# --- IA asíncrona (fase 3) -----------------------------------------------------------------

WORKER = "svc-ia-worker"
# PNG de 1x1 píxel (válido: svc-contenido lo abre con Pillow).
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
PREGUNTAS = [
    "¿Cada cuándo se riega un aguacate Hass en temporada de secas?",
    "¿Cómo distingo la roña de la antracnosis en el fruto?",
    "¿Qué fertilizante conviene antes de la floración?",
    "¿Cómo se poda un árbol de aguacate joven?",
    "¿Qué hago si las hojas del aguacate se ponen amarillas?",
    "¿A qué altura se da mejor el aguacate en Michoacán?",
]


def usuario_ia() -> dict:
    """Un usuario de prueba verificado (registro -> correo -> enlace) para los pasos de la IA.
    Es @example.com: `limpiar_datos_prueba` borra sus conversaciones y diagnósticos."""
    desde = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    correo = f"eventos-ia.{int(time.time() * 1000)}@example.com"
    r = http.post(
        "/api/usuarios/auth/registro/",
        json={"nombre": "Prueba", "apellidos": "IA", "email": correo,
              "password": PASSWORD_FLUJO, "password_confirmacion": PASSWORD_FLUJO,
              "acepto_privacidad": True},
    )  # fmt: skip
    if r.status_code != 201:
        raise RuntimeError(f"El registro respondió {r.status_code}")
    texto = correo_en_log(correo, "verificar-correo/?token=", desde)
    if texto is None:
        raise RuntimeError("No llegó el correo de verificación del usuario de la IA.")
    token = re.search(r"verificar-correo/\?token=([^\s\"<>]+)", texto).group(1)
    http.post("/api/usuarios/auth/verificar-correo/", json={"token": unquote(token)})
    return {"correo": correo, "id": r.json()["id"]}


def sesion(usuario: dict) -> dict:
    r = http.post("/api/usuarios/auth/login/",
                  json={"email": usuario["correo"], "password": PASSWORD_FLUJO})  # fmt: skip
    return {"Authorization": f"Bearer {r.json()['access']}"}


def nueva_conversacion(cliente: dict, nombre: str) -> str:
    r = http.post("/api/contenido/conversaciones/", json={"titulo": nombre}, headers=cliente)
    return r.json()["id"]


def preguntar_ia(cliente: dict, conv: str, texto: str, correlacion: dict | None = None):
    return http.post(f"/api/contenido/conversaciones/{conv}/preguntar/", json={"texto": texto},
                     headers={**cliente, **(correlacion or {})})  # fmt: skip


def solicitud_ia(cliente: dict, conv: str) -> dict:
    return http.get(f"/api/contenido/conversaciones/{conv}/solicitud/", headers=cliente).json()


def esperar_final(cliente: dict, conv: str, limite: float = 200) -> dict:
    """Consulta como la pantalla (cada 2 s) hasta `listo` o `fallido`."""

    def terminada():
        s = solicitud_ia(cliente, conv)
        return s if s.get("estado") in ("listo", "fallido") else None

    return esperar(terminada, limite, 2) or solicitud_ia(cliente, conv)


def lineas_con(servicio: str, desde: str, *marcas: str) -> list[str]:
    registro = docker("logs", "--no-log-prefix", "--since", desde, servicio)
    return [linea for linea in registro.splitlines() if all(m in linea for m in marcas)]


def mensajes_de(cliente: dict, conv: str) -> list[str]:
    datos = http.get(f"/api/contenido/conversaciones/{conv}/", headers=cliente).json()
    return [m["rol"] for m in datos["mensajes"]]


def ia_punta_a_punta(cliente: dict) -> None:
    titulo("8. IA asíncrona: pregunta -> svc-ia-worker -> agente real -> conversación")
    desde = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    conv = nueva_conversacion(cliente, "Prueba de eventos")
    c = nueva_correlacion()
    inicio = time.monotonic()
    r = preguntar_ia(cliente, conv, PREGUNTAS[0], c)
    paso("Preguntar responde 202 al momento", r.status_code == 202
         and r.json()["estado"] == "pendiente",
         f"{r.elapsed.total_seconds() * 1000:.0f} ms")  # fmt: skip
    final = esperar_final(cliente, conv)
    tardanza = time.monotonic() - inicio
    listo = final.get("estado") == "listo"
    detalle = (
        f"en {tardanza:.1f} s, {len(final.get('respuesta') or '')} caracteres, "
        f"{len(final.get('fuentes') or [])} fuentes"
        if listo
        else f"estado {final.get('estado')}, código {final.get('codigo')}"
    )
    if not paso("La respuesta del agente llegó", listo, detalle):
        return
    paso("Quedó guardada en la conversación", mensajes_de(cliente, conv) == ["usuario", "agente"])

    correlacion = c["X-Correlacion-Id"]
    print(f"  la correlación {correlacion} en los 4 contenedores:")
    for servicio, marca in (
        ("web", '"evento": "peticion"'),
        ("svc-contenido", '"evento": "evento_publicado"'),
        (WORKER, '"evento": "evento_procesado"'),
        (CONSUMIDOR, '"evento": "evento_procesado"'),
    ):
        lineas = lineas_con(servicio, desde, correlacion, marca)
        if lineas:
            print(f"    {servicio}: {lineas[-1][:220]}")
        paso(f"  {servicio}: {marca.split(': ')[1]}", bool(lineas))
    todo = "".join(docker("logs", "--no-log-prefix", "--since", desde, s)
                   for s in ("web", "svc-contenido", WORKER, CONSUMIDOR))  # fmt: skip
    paso("Ni la pregunta ni la respuesta aparecen en los logs",
         PREGUNTAS[0] not in todo and final["respuesta"][:60] not in todo)  # fmt: skip


def ia_agente_caido(cliente: dict) -> None:
    titulo("9. Agente detenido: reintentos -> fallida -> «Reintentar» al volver")
    desde = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    antes = estado()["fallidos"]["total"]
    conv = nueva_conversacion(cliente, "Agente caído")
    docker("stop", "agente")
    try:
        inicio = time.monotonic()
        preguntar_ia(cliente, conv, PREGUNTAS[1])
        final = esperar_final(cliente, conv, 90)
        tardanza = time.monotonic() - inicio
        paso("La solicitud termina en fallida con agente_no_disponible",
             final.get("estado") == "fallido" and final.get("codigo") == "agente_no_disponible",
             f"en {tardanza:.1f} s (sin esperar los 180 s del vencimiento)")  # fmt: skip
        reintentos = lineas_con(WORKER, desde, '"evento": "evento_reintentado"')
        paso("El worker reintentó 2 veces antes de rendirse", len(reintentos) == 2,
             f"{len(reintentos)} evento_reintentado")  # fmt: skip
        datos = estado()["fallidos"]
        ultimo = datos["ultimos"][0] if datos["total"] > antes else {}
        paso("En fallidos, sin la pregunta ni el historial",
             ultimo.get("datos_omitidos") == "historial,pregunta",
             f"datos_omitidos={ultimo.get('datos_omitidos')}")  # fmt: skip
        if ultimo:
            salida = docker("exec", "-T", "svc-contenido", "python", "-m", "agroia_comun.eventos",
                            "reprocesar", "--id", ultimo["id"])  # fmt: skip
            paso("reprocesar lo rechaza (datos omitidos)", "datos omitidos" in salida,
                 salida.strip().splitlines()[-1] if salida.strip() else "")  # fmt: skip
            # Ya se revisó y el usuario usa «Reintentar»: se descarta, para no dejar residuos.
            salida = docker("exec", "-T", "svc-contenido", "python", "-m", "agroia_comun.eventos",
                            "descartar", "--id", ultimo["id"])  # fmt: skip
            paso("descartar lo borra de fallidos", "Descartados: 1" in salida
                 and estado()["fallidos"]["total"] == antes)  # fmt: skip
    finally:
        docker("start", "agente")
    esperar(lambda: "healthy" in docker("ps", "agente", "--format", "{{.Health}}"), 120, 2)
    print("  agente de vuelta")
    r = http.post(f"/api/contenido/conversaciones/{conv}/reintentar/", headers=cliente)
    paso("Reintentar responde 202", r.status_code == 202)
    final = esperar_final(cliente, conv)
    paso("Al reintentar llega la respuesta", final.get("estado") == "listo",
         f"estado {final.get('estado')}, código {final.get('codigo')}")  # fmt: skip
    paso("La pregunta no se repitió", mensajes_de(cliente, conv) == ["usuario", "agente"])


def lineas_json(servicio: str, desde: str) -> list[dict]:
    """Las líneas JSON del log de un contenedor desde `desde`."""
    salida = []
    for linea in docker("logs", "--no-log-prefix", "--since", desde, servicio).splitlines():
        if linea.startswith("{"):
            try:
                salida.append(json.loads(linea))
            except ValueError:
                continue
    return salida


def momento(texto: str) -> float:
    return datetime.fromisoformat(texto).timestamp()


def ia_concurrencia(cliente: dict) -> None:
    # Los hilos del worker que está corriendo (IA_WORKER_HILOS), no un número fijo.
    leer_hilos = "from app.config import settings; print(settings.ia_worker_hilos)"
    hilos_worker = int(docker("exec", "-T", WORKER, "python", "-c", leer_hilos))
    titulo(f"10. Concurrencia: 5 preguntas a la vez ({hilos_worker} hilos en el worker)")
    desde = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    convs = [nueva_conversacion(cliente, f"Concurrencia {n}") for n in range(5)]
    correlaciones = [str(uuid.uuid4()) for _ in range(5)]
    cero = time.time()

    def una(n: int) -> tuple:
        inicio = time.monotonic()
        r = preguntar_ia(cliente, convs[n], PREGUNTAS[n + 1],
                         {"X-Correlacion-Id": correlaciones[n]})  # fmt: skip
        aceptada = time.monotonic() - inicio
        final = esperar_final(cliente, convs[n])
        return final.get("estado"), aceptada, time.monotonic() - inicio, r.status_code

    with ThreadPoolExecutor(5) as hilos:
        tiempos = list(hilos.map(una, range(5)))
    total = time.time() - cero
    time.sleep(2)  # que el log del worker termine de escribirse

    registro = [x for x in lineas_json(WORKER, desde) if x.get("correlacion_id") in correlaciones]
    print("    n | intento | hilo | empieza | entregas | dura   | resultado")
    bien_entregas, intervalos = True, []
    for n, correlacion in enumerate(correlaciones):
        intentos = sorted(
            (x for x in registro if x["correlacion_id"] == correlacion
             and x["evento"] in ("evento_procesado", "evento_reintentado", "evento_ocupado",
                                 "evento_fallido")),
            key=lambda x: x["inicio"],
        )  # fmt: skip
        final, aceptada, tardo, _ = tiempos[n]
        if not intentos:
            bien_entregas = False
        fin_anterior = None
        for x in intentos:
            empieza = momento(x["inicio"]) - cero
            dura = x["duracion_ms"] / 1000
            intervalos.append((empieza, empieza + dura, x["consumidor"]))
            # Cada entrega de Redis corresponde a un intento real. Si el reclamo hubiera
            # tomado el mensaje mientras otro hilo lo procesaba, habría más entregas que
            # intentos (o un evento_ocupado).
            bien_entregas &= x["entregas"] == x["intento"] and x["evento"] != "evento_ocupado"
            resultado = {
                "evento_procesado": "bien",
                "evento_fallido": "agotó los reintentos: ",
            }.get(x["evento"], "") + (
                "" if x["evento"] == "evento_procesado" else x.get("motivo", "")
            )
            espera = f", {empieza - fin_anterior:.1f} s después del fallo" if fin_anterior else ""
            hilo = x["consumidor"].rsplit("-", 1)[-1]
            print(f"    {n + 1} | {x['intento']:7} | {hilo:>4} | {empieza:5.1f} s | "
                  f"{x['entregas']:8} | {dura:4.1f} s | {resultado}{espera}")  # fmt: skip
            fin_anterior = empieza + dura
        print(f"      202 en {aceptada * 1000:.0f} ms; {final} a los {tardo:.1f} s")

    # Cuántos hilos estaban ocupados a la vez, como máximo (IA_WORKER_HILOS). Se cuentan hilos
    # distintos: dos intentos seguidos del mismo hilo pueden «tocarse» por el redondeo a
    # milisegundos de `inicio`, pero un hilo nunca procesa dos cosas a la vez (se comprueba).
    maximo, solapados = 0, False
    for a, _, _hilo in intervalos:
        ocupados = {h for b, c, h in intervalos if b <= a + 0.001 and c > a + 0.001}
        maximo = max(maximo, len(ocupados))
    for a, b, hilo in intervalos:
        for c, d, otro in intervalos:
            if hilo == otro and (a, b) != (c, d) and a + 0.01 < d and c + 0.01 < b:
                solapados = True
    paso("Las 5 se aceptaron con 202", all(t[3] == 202 for t in tiempos))
    paso("Las 5 terminaron con respuesta", all(t[0] == "listo" for t in tiempos),
         ", ".join(t[0] or "?" for t in tiempos))  # fmt: skip
    paso(f"Se atienden de {hilos_worker} en {hilos_worker}",
         maximo == hilos_worker and not solapados,
         f"máximo {maximo} hilos ocupados a la vez")  # fmt: skip
    paso("Ninguna con entregas de más (una entrega por intento, sin reclamos en curso)",
         bien_entregas)  # fmt: skip
    print("  log del agente (solo estado, sin contenido):")
    for linea in docker(
        "logs", "--no-log-prefix", "--timestamps", "--since", desde, "agente"
    ).splitlines():
        if "RateLimitError" in linea or "POST /chat" in linea:
            hora, _, resto = linea.partition(" ")
            cuando = datetime.fromisoformat(hora[:26] + "+00:00").timestamp() - cero
            texto = "RateLimitError" if "RateLimitError" in resto else resto.split('" ')[-1]
            print(f"    {cuando:5.1f} s  {texto}")
    print(f"  en total {total:.1f} s; la más lenta {max(t[2] for t in tiempos):.1f} s")


def diagnostico_ia(cliente: dict) -> dict:
    r = http.post("/api/contenido/diagnosticos/solicitar/", headers=cliente,
                  files={"imagen": ("hoja.png", PNG_1X1, "image/png")})  # fmt: skip
    if r.status_code != 202:
        return {"estado": f"HTTP {r.status_code}"}
    ident = r.json()["id"]

    def final():
        d = http.get(f"/api/contenido/diagnosticos/{ident}/", headers=cliente).json()
        return d if d.get("estado") in ("listo", "fallido") else None

    return esperar(final, 60, 1) or {"estado": "sin_terminar", "id": ident}


def copias_de_imagen() -> int:
    salida = docker("exec", "-T", "redis", "redis-cli", "-n", "1", "--scan", "--pattern",
                    "agroia:ia:imagen:*")  # fmt: skip
    return len([linea for linea in salida.splitlines() if linea.strip()])


def ia_diagnostico(cliente: dict) -> None:
    titulo("11. Diagnóstico asíncrono: sin modelo y con el clasificador de prueba")
    d = diagnostico_ia(cliente)
    paso("Sin modelo: fallido con modelo_no_disponible",
         d.get("estado") == "fallido" and d.get("codigo") == "modelo_no_disponible",
         f"estado {d.get('estado')}, código {d.get('codigo')}")  # fmt: skip
    paso("Sin modelo no queda la foto", d.get("imagen_url") is None)
    paso("No quedan copias de la imagen en Redis", copias_de_imagen() == 0)
    print("  recreo svc-ia-worker con IA_CLASIFICADOR_PRUEBA=1 y DEBUG=True")
    desde = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    docker("up", "-d", WORKER, entorno={"IA_CLASIFICADOR_PRUEBA": "1", "DJANGO_DEBUG": "True"})
    try:
        esperar(lambda: lineas_con(WORKER, desde, '"clasificador_de_prueba": true'), 60, 1)
        d = diagnostico_ia(cliente)
        paso("Con el de prueba: listo y marcado es_prueba",
             d.get("estado") == "listo" and d.get("es_prueba") is True
             and d.get("modelo_version") == "prueba-no-es-un-modelo",
             f"clase {d.get('clase')}, confianza {d.get('confianza')}")  # fmt: skip
        paso("La copia de la imagen se borró al procesarla", copias_de_imagen() == 0)
    finally:
        docker("up", "-d", WORKER)
        print("  svc-ia-worker de vuelta, sin clasificador de prueba")


# Segundos sin llamadas al agente antes del paso 10. La llave gratuita de Groq tiene un límite
# de tokens por minuto: los pasos 8 y 9 lo gastan, y el paso 10 mide la concurrencia del
# worker, no lo que dejaron los pasos anteriores (como la matriz, que espera 61 s antes de
# los casos de login). Se espera solo lo que falte desde la última llamada.
ENFRIAR_GROQ_SEGUNDOS = 90


def esperar_cupo_del_agente() -> None:
    llamadas = [
        linea.split(" ", 1)[0]
        for linea in docker("logs", "--no-log-prefix", "--timestamps", "--since", "10m",
                            "agente").splitlines()
        if "POST /chat" in linea
    ]  # fmt: skip
    if not llamadas:
        return
    ultima = datetime.fromisoformat(llamadas[-1][:26] + "+00:00")
    falta = ENFRIAR_GROQ_SEGUNDOS - (datetime.now(UTC) - ultima).total_seconds()
    if falta > 0:
        print()
        print(f"  espero {falta:.0f} s sin llamadas al agente (límite por minuto de Groq)")
        time.sleep(falta)


def pasos_ia() -> None:
    try:
        usuario = usuario_ia()
    except RuntimeError as error:
        paso("Usuario de prueba para la IA", False, str(error))
        return
    pedidos = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--pasos=")), "")
    elegidos = {int(n) for n in pedidos.split(",") if n.strip()} or {8, 9, 10, 11}
    for numero, funcion in ((8, ia_punta_a_punta), (9, ia_agente_caido),
                            (10, ia_concurrencia), (11, ia_diagnostico)):  # fmt: skip
        if numero in elegidos:
            if numero == 10:
                esperar_cupo_del_agente()
            funcion(sesion(usuario))


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
    print("  " + manage("svc-contenido", "reiniciar_limites"))
    for servicio in ("redis", "mongo", "svc-usuarios", "svc-contenido", CONSUMIDOR, WORKER):
        if not corriendo(servicio):
            sys.exit(f"{servicio} no está corriendo. Levanta todo con docker compose up -d.")
    admin = {"Authorization": f"Bearer {token_admin()}"}
    try:
        if "--solo-ia" in sys.argv:
            pasos_ia()
            return
        punta_a_punta(admin)
        apagado_y_consumidor_caido(admin)
        admin = {"Authorization": f"Bearer {token_admin()}"}  # por si venció el access
        fallido_y_reproceso(admin)
        admin = {"Authorization": f"Bearer {token_admin()}"}
        flujo = flujo_de_negocio(admin)
        correo_que_falla(admin, flujo)
        pasos_ia()
    finally:
        for servicio in ("mongo", CONSUMIDOR, CONSUMIDOR_CORREOS, "agente", WORKER):
            if not corriendo(servicio):
                docker("start", servicio, verificar=False)
        limpiar()
        resumen()


def resumen() -> None:
    bien = sum(ok for _, ok, _ in resultados)
    titulo("Resumen")
    print(f"  {bien} de {len(resultados)} comprobaciones correctas "
          f"en {time.monotonic() - inicio_total:.0f} s")  # fmt: skip
    sys.exit(0 if bien == len(resultados) else 1)


if __name__ == "__main__":
    main()
