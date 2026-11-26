"""Matriz de accesos: prueba quién puede hacer qué, a través del gateway, SOLO EN DESARROLLO.

Corre contra el sistema levantado con `docker compose up` y manda todo por el proxy del
gateway (http://127.0.0.1:8000/api/). Para cada actor y endpoint compara el código HTTP y el
código de error del cuerpo con lo esperado, y escribe el reporte en
docs/entregable-4/matriz-accesos.md (otra ruta con --salida; el de la Entrega 3 queda
como estaba).

Actores: anónimo, cliente sin verificar, cliente verificado, administrador, token vencido,
token firmado con otra llave, refresh en blacklist (usado como access) y origen no permitido
(token válido del cliente con un `Origin` ajeno).

Requisitos:
- Cuentas de demostración: `docker compose exec svc-usuarios python manage.py cargar_usuarios_demo`.
- Catálogo de demostración (al menos una categoría): `cargar_datos_demo` en svc-tienda.
- La llave privada local en infra/llaves/ (para el token vencido, con emitir_token.py).
- El venv de la raíz (httpx, PyJWT y cryptography).
- `docker` en el PATH para limpiar lo que la API no deja borrar (pedido, producto y
  diagnósticos de prueba). Otra ruta: variable DOCKER.

Uso, desde la raíz del repo:

    python infra/matriz_seguridad.py
    python infra/matriz_seguridad.py --omitir-limites   # sin los casos de exceso de intentos
    python infra/matriz_seguridad.py --salida /ruta/reporte.md

Límites de intentos (no se suben):
- Antes de los casos de login espera 61 s, para empezar con la ventana de 10 por minuto libre.
- La recuperación permite 3 por hora por IP: la matriz la agota, así que la petición
  «Pedir recuperación» de Postman responde 429 hasta que pase una hora.

Recursos que crea y borra al final: un producto, un pedido, una conversación y dos
diagnósticos por cuenta (uno pedido por eventos). Preguntar en la conversación propia llama
al agente real una vez por cuenta (3 preguntas cortas). El carrito del cliente se vacía para
el pedido y se restaura después.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "docs" / "entregable-4" / "matriz-accesos.md"
IMAGEN = RAIZ / "docs" / "postman" / "archivos" / "imagen-prueba.png"

# Contraseña pública de las cuentas de demostración (cargar_usuarios_demo, README raíz y
# entorno de Postman). Esas cuentas solo existen con DJANGO_DEBUG=True.
PASSWORD_DEMO = os.environ.get("MATRIZ_PASSWORD_DEMO", "solo-demo-no-usar-en-produccion")
CUENTAS = {
    "sin_verificar": "sin-verificar@demo.agroia.test",
    "cliente": "cliente@demo.agroia.test",
    "admin": "admin@demo.agroia.test",
}
ORIGEN_AJENO = "https://sitio-ajeno.example"
# Un 503 con estos códigos en una fila que esperaba acceso permitido no es una falla del
# control de acceso: es el agente o el modelo (ver Caso.servicio_externo).
CODIGOS_SERVICIO_EXTERNO = {"agente_no_disponible", "modelo_no_disponible"}
EXTERNO = "permitido (servicio externo no disponible)"

ACTORES = [
    ("anonimo", "Anónimo"),
    ("sin_verificar", "Cliente sin verificar"),
    ("cliente", "Cliente verificado"),
    ("admin", "Administrador"),
    ("vencido", "Token vencido"),
    ("otra_llave", "Token de otra llave"),
    ("refresh_blacklist", "Refresh en blacklist"),
    ("origen", "Origen no permitido"),
]
NOMBRE_ACTOR = dict(ACTORES)
TOKENS_ATAQUE = ("vencido", "otra_llave", "refresh_blacklist")

# Lo que se espera de cada actor que no pasa la autenticación: lo decide el gateway.
DENEGADO_GATEWAY = {
    "anonimo": (401, "no_autenticado"),
    "vencido": (401, "token_invalido"),
    "otra_llave": (401, "token_invalido"),
    "refresh_blacklist": (401, "token_invalido"),
    "origen": (403, "origen_no_permitido"),
}


@dataclass
class Caso:
    """Un actor contra un endpoint.

    La matriz prueba el control de acceso, no la disponibilidad del agente o del modelo
    (eso lo cubre infra/prueba_eventos.py). Si se esperaba acceso permitido y la respuesta
    es 503 con un código de servicio externo (`agente_no_disponible`,
    `modelo_no_disponible`), el control de acceso dejó pasar la petición: cuenta como
    coincidencia, marcada aparte como «permitido (servicio externo no disponible)». Un 401
    o 403 donde se esperaba permitido, o un 503 donde se esperaba 401 o 403, sigue siendo
    una falla.
    """

    grupo: str
    actor: str
    metodo: str
    ruta: str
    esperado: int
    codigo_esperado: str | None
    obtenido: int | None = None
    codigo: str | None = None
    nota: str = ""

    @property
    def servicio_externo(self) -> bool:
        """Permitido por el control de acceso, pero el servicio externo no estaba."""
        return self.permitido and self.obtenido == 503 and self.codigo in CODIGOS_SERVICIO_EXTERNO

    @property
    def coincide(self) -> bool:
        if self.servicio_externo:
            return True
        if self.obtenido != self.esperado:
            return False
        return self.codigo_esperado is None or self.codigo == self.codigo_esperado

    @property
    def permitido(self) -> bool:
        return self.esperado < 400


@dataclass
class Estado:
    tokens: dict = field(default_factory=dict)
    refresh: dict = field(default_factory=dict)
    ids: dict = field(default_factory=dict)
    producto: str | None = None
    pedido: int | None = None
    carrito_original: list = field(default_factory=list)
    conversaciones: dict = field(default_factory=dict)
    diagnosticos: dict = field(default_factory=dict)
    diagnosticos_ia: list = field(default_factory=list)
    limpieza: list = field(default_factory=list)


def codigo_de_error(respuesta: httpx.Response) -> str | None:
    try:
        cuerpo = respuesta.json()
    except ValueError:
        return None
    return cuerpo.get("error") if isinstance(cuerpo, dict) else None


class Matriz:
    def __init__(self, base: str):
        self.http = httpx.Client(base_url=base.rstrip("/"), timeout=70)
        self.casos: list[Caso] = []
        self.e = Estado()

    # --- peticiones -------------------------------------------------------------------

    def encabezados(self, actor: str) -> dict:
        h = {"Accept": "application/json"}
        token = {
            "origen": self.e.tokens.get("cliente"),
            "refresh_blacklist": self.e.tokens.get("refresh_blacklist"),
        }.get(actor, self.e.tokens.get(actor))
        if actor != "anonimo" and token:
            h["Authorization"] = f"Bearer {token}"
        if actor == "origen":
            h["Origin"] = ORIGEN_AJENO
        return h

    def pedir(self, actor: str, metodo: str, ruta: str, **opciones) -> httpx.Response:
        return self.http.request(metodo, ruta, headers=self.encabezados(actor), **opciones)

    def probar(self, grupo, actor, metodo, ruta, esperado, codigo=None, mostrar=None, **opc):
        caso = Caso(grupo, actor, metodo, mostrar or ruta, esperado, codigo)
        try:
            respuesta = self.pedir(actor, metodo, ruta, **opc)
            caso.obtenido, caso.codigo = respuesta.status_code, codigo_de_error(respuesta)
        except httpx.HTTPError as error:
            caso.nota = f"sin respuesta: {type(error).__name__}"
            respuesta = None
        self.casos.append(caso)
        marca = "externo" if caso.servicio_externo else ("ok" if caso.coincide else "NO COINCIDE")
        print(f"  {marca:11} {NOMBRE_ACTOR[actor]:22} {caso.obtenido} {caso.codigo or ''}")
        return respuesta

    def fila(self, grupo, metodo, ruta, permitidos: dict, mostrar=None, ruta_de=None, **opc):
        """Una fila de la matriz: los 8 actores contra el mismo endpoint.

        `permitidos` dice qué esperar de las tres cuentas reales (y del anónimo en una ruta
        pública): un código (int) o una tupla (código, error). Los demás actores que no
        pasan la autenticación siempre se deniegan en el gateway. `ruta_de(actor)` cambia
        la ruta por actor (recursos propios o ajenos); por omisión, todos usan `ruta`.
        """
        print(f"\n{grupo}")
        respuestas = {}
        for actor, _ in ACTORES:
            if actor in permitidos:
                valor = permitidos[actor]
                esperado, codigo = valor if isinstance(valor, tuple) else (valor, None)
            else:
                esperado, codigo = DENEGADO_GATEWAY[actor]
            r = ruta_de(actor) if ruta_de else ruta
            respuestas[actor] = self.probar(
                grupo, actor, metodo, r, esperado, codigo, mostrar, **opc
            )
        return respuestas

    # --- preparación ------------------------------------------------------------------

    def login(self, cuenta: str) -> dict:
        for _ in range(3):
            r = self.http.post(
                "/api/usuarios/auth/login/",
                json={"email": CUENTAS[cuenta], "password": PASSWORD_DEMO},
                headers={"Accept": "application/json"},
            )
            if r.status_code != 429:
                break
            espera = int(r.headers.get("Retry-After", "60")) + 1
            print(f"  límite de logins: espero {espera} s")
            time.sleep(espera)
        self.casos.append(
            Caso(
                "Iniciar sesión",
                cuenta,
                "POST",
                "/api/usuarios/auth/login/",
                200,
                None,
                r.status_code,
                codigo_de_error(r),
            )
        )
        if r.status_code != 200:
            sys.exit(
                f"No pude iniciar sesión con {CUENTAS[cuenta]} ({r.status_code}). "
                "¿Corriste cargar_usuarios_demo?"
            )
        return r.json()

    def preparar_identidades(self):
        print("Iniciar sesión")
        for cuenta in CUENTAS:
            datos = self.login(cuenta)
            self.e.tokens[cuenta] = datos["access"]
            self.e.refresh[cuenta] = datos["refresh"]
            self.e.ids[cuenta] = datos["usuario"]["id"]
            print(f"  ok          {NOMBRE_ACTOR[cuenta]:22} 200")
        r = self.http.post(
            "/api/usuarios/auth/login/",
            json={"email": CUENTAS["cliente"], "password": PASSWORD_DEMO},
            headers={"Origin": ORIGEN_AJENO, "Accept": "application/json"},
        )
        self.casos.append(
            Caso(
                "Iniciar sesión",
                "origen",
                "POST",
                "/api/usuarios/auth/login/",
                403,
                "origen_no_permitido",
                r.status_code,
                codigo_de_error(r),
            )
        )

        # Rotación: el refresh del login entra a la blacklist al renovar.
        print("\nRenovar el token")
        anterior = self.e.refresh["cliente"]
        ruta = "/api/usuarios/auth/token/renovar/"
        r = self.http.post(ruta, json={"refresh": anterior})
        self.casos.append(
            Caso(
                "Renovar el token",
                "cliente",
                "POST",
                ruta,
                200,
                None,
                r.status_code,
                codigo_de_error(r),
                "refresh vigente; devuelve un par nuevo",
            )
        )
        if r.status_code == 200:
            self.e.tokens["cliente"] = r.json()["access"]
            self.e.refresh["cliente"] = r.json()["refresh"]
        r = self.http.post(ruta, json={"refresh": anterior})
        self.casos.append(
            Caso(
                "Renovar el token",
                "refresh_blacklist",
                "POST",
                ruta,
                401,
                "refresh_invalido",
                r.status_code,
                codigo_de_error(r),
                "el refresh ya usado, en la blacklist",
            )
        )
        self.e.tokens["refresh_blacklist"] = anterior

        # Token vencido del mismo cliente, firmado con la llave real (emitir_token.py).
        self.e.tokens["vencido"] = subprocess.run(
            [
                sys.executable,
                str(RAIZ / "infra" / "emitir_token.py"),
                "--vencido",
                "--usuario-id",
                self.e.ids["cliente"],
                "--rol",
                "cliente",
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=RAIZ,
        ).stdout.strip()

        # Mismos claims que el access del cliente, firmados con una llave RSA recién creada.
        claims = jwt.decode(self.e.tokens["cliente"], options={"verify_signature": False})
        llave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.e.tokens["otra_llave"] = jwt.encode(claims, llave, algorithm="RS256")

    # --- filas ------------------------------------------------------------------------

    def tienda(self):
        cliente_y_mas = {"sin_verificar": 200, "cliente": 200, "admin": 200}
        # Público: el anónimo entra; un token que viene se valida igual (vencido: 401).
        self.fila(
            "Catálogo (público)", "GET", "/api/tienda/productos/", {"anonimo": 200} | cliente_y_mas
        )

        categorias = self.http.get("/api/tienda/categorias/").json()["results"]
        if not categorias:
            sys.exit("No hay categorías. Corre cargar_datos_demo en svc-tienda.")
        marca = uuid.uuid4().hex[:8]
        producto = {
            "nombre": f"Producto de la matriz {marca}",
            "slug": f"matriz-{marca}",
            "categoria": categorias[0]["slug"],
            "precio": "10.00",
            "stock": 1,
            "unidad": "pieza",
            "descripcion": "Creado por infra/matriz_seguridad.py; se borra al terminar.",
        }
        solo_admin = {
            "sin_verificar": (403, "sin_permiso"),
            "cliente": (403, "sin_permiso"),
            "admin": 201,
        }
        r = self.fila(
            "Crear producto (administrador)",
            "POST",
            "/api/tienda/productos/",
            solo_admin,
            json=producto,
        )
        if r["admin"] is not None and r["admin"].status_code == 201:
            self.e.producto = producto["slug"]

        self.fila("Ver carrito", "GET", "/api/tienda/carrito/", cliente_y_mas)

        # El pedido se hace con el producto de la matriz, sin tocar el stock de la demo.
        cli = self.encabezados("cliente")
        carrito = self.http.get("/api/tienda/carrito/", headers=cli).json()
        self.e.carrito_original = [
            (i["producto"]["slug"], i["cantidad"]) for i in carrito.get("items", [])
        ]
        self.http.delete("/api/tienda/carrito/", headers=cli)
        if self.e.producto:
            self.http.post(
                "/api/tienda/carrito/items/",
                headers=cli,
                json={"producto": self.e.producto, "cantidad": 1},
            )
        pedido = {
            "direccion_envio": {
                "calle": "Av. de Prueba",
                "numero": "1",
                "colonia": "Centro",
                "municipio": "Jiquilpan",
                "estado": "Michoacán",
                "codigo_postal": "59510",
            },
            "metodo_pago": "transferencia",
        }
        r = self.fila(
            "Crear pedido",
            "POST",
            "/api/tienda/pedidos/",
            {
                "sin_verificar": (403, "email_no_verificado"),
                "cliente": 201,
                "admin": (403, "sin_permiso"),
            },
            json=pedido,
        )
        if r["cliente"] is not None and r["cliente"].status_code == 201:
            self.e.pedido = r["cliente"].json()["id"]

        # El administrador cancela el pedido: el stock vuelve al producto de la matriz.
        self.fila(
            "Cambiar estado de un pedido (administrador)",
            "PATCH",
            f"/api/tienda/pedidos/{self.e.pedido or 0}/estado/",
            solo_admin | {"admin": 200},
            mostrar="/api/tienda/pedidos/<id>/estado/",
            json={"estado": "cancelado"},
        )

        # Panel de administración: el resumen (pedidos, ventas por pagado_en, stock).
        self.fila(
            "Resumen del panel (administrador)",
            "GET",
            "/api/tienda/resumen/?umbral=5",
            solo_admin | {"admin": 200},
            mostrar="/api/tienda/resumen/",
        )

    def usuarios(self):
        solo_admin = {
            "sin_verificar": (403, "sin_permiso"),
            "cliente": (403, "sin_permiso"),
            "admin": 200,
        }
        self.fila("Listar usuarios (administrador)", "GET", "/api/usuarios/usuarios/", solo_admin)
        self.fila(
            "Ver un usuario (administrador)",
            "GET",
            f"/api/usuarios/usuarios/{self.e.ids['cliente']}/",
            solo_admin,
            mostrar="/api/usuarios/usuarios/<id>/",
        )
        # Al mismo rol que ya tiene: responde 200 sin cambiar nada ni dejar registro.
        self.fila(
            "Cambiar rol (administrador)",
            "PATCH",
            f"/api/usuarios/usuarios/{self.e.ids['sin_verificar']}/rol/",
            solo_admin,
            mostrar="/api/usuarios/usuarios/<id>/rol/",
            json={"rol": "cliente"},
        )

    def contenido(self):
        cuentas = ("sin_verificar", "cliente", "admin")
        # Panel de administración: bitácora (con la línea de tiempo de un pedido) y estado de
        # los eventos. Solo administrador.
        solo_admin = {
            "sin_verificar": (403, "sin_permiso"),
            "cliente": (403, "sin_permiso"),
            "admin": 200,
        }
        self.fila(
            "Bitácora de un pedido (administrador)",
            "GET",
            f"/api/contenido/bitacora/?pedido_id={self.e.pedido or 1}",
            solo_admin,
            mostrar="/api/contenido/bitacora/?pedido_id=<id>",
        )
        self.fila(
            "Estado de los eventos (administrador)",
            "GET",
            "/api/contenido/eventos/estado/",
            solo_admin,
        )
        ajena = {"sin_verificar": "cliente", "cliente": "sin_verificar", "admin": "cliente"}
        for cuenta in cuentas:
            r = self.http.post(
                "/api/contenido/conversaciones/",
                headers=self.encabezados(cuenta),
                json={"titulo": "Matriz de accesos"},
            )
            self.e.conversaciones[cuenta] = r.json()["id"]
            with IMAGEN.open("rb") as imagen:
                r = self.http.post(
                    "/api/contenido/diagnosticos/",
                    headers=self.encabezados(cuenta),
                    files={"imagen": ("matriz.png", imagen.read(), "image/png")},
                    data={
                        "clase": "sano",
                        "confianza": "0.9",
                        "modelo_version": "matriz",
                        "probabilidades": json.dumps(
                            {"sano": 0.9, "rona": 0.05, "antracnosis": 0.05}
                        ),
                    },
                )
            self.e.diagnosticos[cuenta] = r.json()["id"]

        def propia(recursos, plantilla):
            return lambda actor: plantilla.format(recursos.get(actor, recursos["cliente"]))

        def de_otro(recursos, plantilla):
            return lambda actor: plantilla.format(recursos[ajena.get(actor, "sin_verificar")])

        conv = "/api/contenido/conversaciones/{}/"
        self.fila(
            "Conversación propia",
            "GET",
            conv,
            dict.fromkeys(cuentas, 200),
            mostrar="/api/contenido/conversaciones/<propia>/",
            ruta_de=propia(self.e.conversaciones, conv),
        )
        # Las conversaciones son privadas también para el administrador.
        self.fila(
            "Conversación ajena",
            "GET",
            conv,
            dict.fromkeys(cuentas, (404, "no_encontrado")),
            mostrar="/api/contenido/conversaciones/<ajena>/",
            ruta_de=de_otro(self.e.conversaciones, conv),
        )
        foto = "/api/contenido/diagnosticos/{}/imagen/"
        self.fila(
            "Foto de diagnóstico propia",
            "GET",
            foto,
            dict.fromkeys(cuentas, 200),
            mostrar="/api/contenido/diagnosticos/<propio>/imagen/",
            ruta_de=propia(self.e.diagnosticos, foto),
        )
        # El administrador sí ve los diagnósticos de todos.
        self.fila(
            "Foto de diagnóstico ajena",
            "GET",
            foto,
            {
                "sin_verificar": (404, "no_encontrado"),
                "cliente": (404, "no_encontrado"),
                "admin": 200,
            },
            mostrar="/api/contenido/diagnosticos/<ajeno>/imagen/",
            ruta_de=de_otro(self.e.diagnosticos, foto),
        )

        # IA asíncrona (Entrega 4): la pregunta se acepta con 202 y se consulta su estado.
        preguntar = "/api/contenido/conversaciones/{}/preguntar/"
        self.fila(
            "Preguntar en la conversación propia (IA por eventos)",
            "POST",
            preguntar,
            dict.fromkeys(cuentas, 202),
            mostrar="/api/contenido/conversaciones/<propia>/preguntar/",
            ruta_de=propia(self.e.conversaciones, preguntar),
            json={"texto": "En una frase: ¿qué es la roña del aguacate?"},
        )
        self.fila(
            "Preguntar en una conversación ajena",
            "POST",
            preguntar,
            dict.fromkeys(cuentas, (404, "no_encontrado")),
            mostrar="/api/contenido/conversaciones/<ajena>/preguntar/",
            ruta_de=de_otro(self.e.conversaciones, preguntar),
            json={"texto": "¿Y la antracnosis?"},
        )
        solicitud = "/api/contenido/conversaciones/{}/solicitud/"
        self.fila(
            "Estado de la solicitud propia",
            "GET",
            solicitud,
            dict.fromkeys(cuentas, 200),
            mostrar="/api/contenido/conversaciones/<propia>/solicitud/",
            ruta_de=propia(self.e.conversaciones, solicitud),
        )
        self.fila(
            "Estado de la solicitud de otro usuario",
            "GET",
            solicitud,
            dict.fromkeys(cuentas, (404, "no_encontrado")),
            mostrar="/api/contenido/conversaciones/<ajena>/solicitud/",
            ruta_de=de_otro(self.e.conversaciones, solicitud),
        )
        with IMAGEN.open("rb") as imagen:
            contenido_imagen = imagen.read()
        respuestas = self.fila(
            "Solicitar un diagnóstico (IA por eventos)",
            "POST",
            "/api/contenido/diagnosticos/solicitar/",
            dict.fromkeys(cuentas, 202),
            files={"imagen": ("matriz.png", contenido_imagen, "image/png")},
        )
        self.e.diagnosticos_ia = [
            r.json()["id"] for r in respuestas.values() if r is not None and r.status_code == 202
        ]

        # Límite de solicitudes a la IA por usuario (10 por minuto): cada cuenta pregunta en
        # su conversación hasta que svc-contenido responde 429; la fila comprueba que la
        # siguiente también lo es, con `demasiados_intentos`. La limpieza borra los contadores
        # (`reiniciar_limites` de svc-contenido) para no dejar bloqueadas las cuentas demo.
        for cuenta in cuentas:
            ruta = preguntar.format(self.e.conversaciones[cuenta])
            for _ in range(12):
                r = self.http.post(ruta, headers=self.encabezados(cuenta), json={"texto": "¿Y?"})
                if r.status_code == 429:
                    break
        self.e.limpieza.append(("limite_ia", "svc-contenido"))
        self.fila(
            "Exceso de solicitudes a la IA (límite por usuario)",
            "POST",
            preguntar,
            dict.fromkeys(cuentas, (429, "demasiados_intentos")),
            mostrar="/api/contenido/conversaciones/<propia>/preguntar/",
            ruta_de=propia(self.e.conversaciones, preguntar),
            json={"texto": "Una más"},
        )

    def agente(self):
        self.fila(
            "Pregunta al agente",
            "POST",
            "/api/ia/agente/preguntar/",
            {"sin_verificar": 200, "cliente": 200, "admin": 200},
            json={"pregunta": "En una frase: ¿qué es la roña del aguacate?"},
        )

    # --- límites de intentos ----------------------------------------------------------

    def limites(self):
        print("\nLímites de intentos: espero 61 s para empezar con la ventana de logins libre")
        time.sleep(61)
        ruta = "/api/usuarios/auth/login/"
        marca = uuid.uuid4().hex[:8]
        correo = f"bloqueo-{marca}@demo.agroia.test"
        intentos = []
        for _ in range(5):
            r = self.http.post(ruta, json={"email": correo, "password": "incorrecta-1"})
            intentos.append((r.status_code, codigo_de_error(r)))
        primeros = intentos[:4]
        iguales = all(i == (401, "credenciales_invalidas") for i in primeros)
        self.casos.append(
            Caso(
                "Login fallido con el mismo correo",
                "anonimo",
                "POST",
                ruta,
                401,
                "credenciales_invalidas",
                primeros[0][0] if iguales else primeros[-1][0],
                "credenciales_invalidas" if iguales else primeros[-1][1],
                "intentos 1 a 4: " + ", ".join(str(c) for c, _ in primeros),
            )
        )
        self.casos.append(
            Caso(
                "Login fallido con el mismo correo",
                "anonimo",
                "POST",
                ruta,
                403,
                "cuenta_bloqueada_temporalmente",
                *intentos[4],
                "intento 5: bloqueo de 15 minutos",
            )
        )
        self.e.limpieza.append(("axes", correo))

        # Ya van 5 logins en este minuto; con el límite de 10, el 11.º debe dar 429.
        numero, r = 5, None
        while numero < 15:
            numero += 1
            r = self.http.post(
                ruta, json={"email": f"limite-{marca}@demo.agroia.test", "password": "x"}
            )
            if r.status_code == 429:
                break
        nota = f"429 en el login {numero} del minuto"
        if r is not None and "Retry-After" in r.headers:
            nota += f", Retry-After: {r.headers['Retry-After']} s"
        caso = Caso(
            "Exceso de logins (10 por minuto por IP)",
            "anonimo",
            "POST",
            ruta,
            429,
            "demasiados_intentos",
            r.status_code,
            codigo_de_error(r),
            nota,
        )
        if numero != 11 or "Retry-After" not in r.headers:
            caso.nota += " (se esperaba en el 11.º, con Retry-After)"
            caso.codigo = f"{caso.codigo} (login {numero})"
        self.casos.append(caso)

        # Recuperación: 3 por hora por IP. Lo que ya se usó en la hora no se sabe, así que
        # se pide hasta recibir el 429.
        ruta = "/api/usuarios/auth/recuperar/"
        aceptados, r = 0, None
        for n in range(5):
            r = self.http.post(ruta, json={"email": f"recuperar-{marca}-{n}@demo.agroia.test"})
            if r.status_code != 200:
                break
            aceptados += 1
        nota = f"aceptadas antes del 429 en esta corrida (200 genérico): {aceptados}"
        if r is not None and "Retry-After" in r.headers:
            nota += f", Retry-After: {r.headers['Retry-After']} s"
        self.casos.append(
            Caso(
                "Exceso de recuperaciones (3 por hora por IP)",
                "anonimo",
                "POST",
                ruta,
                429,
                "demasiados_intentos",
                r.status_code,
                codigo_de_error(r),
                nota,
            )
        )

    # --- limpieza ---------------------------------------------------------------------

    def anotar(self, texto: str):
        print(f"  {texto}")
        self.e.limpieza.append(("hecho", texto))

    def limpiar(self):
        print("\nLimpieza")
        cli = self.encabezados("cliente")
        self.http.delete("/api/tienda/carrito/", headers=cli)
        devueltos = 0
        for slug, cantidad in self.e.carrito_original:
            r = self.http.post(
                "/api/tienda/carrito/items/",
                headers=cli,
                json={"producto": slug, "cantidad": cantidad},
            )
            devueltos += r.status_code < 300
        total = len(self.e.carrito_original)
        self.anotar(f"Carrito del cliente restaurado: {devueltos} de {total} productos.")

        borradas = sum(
            self.http.delete(
                f"/api/contenido/conversaciones/{id_conv}/", headers=self.encabezados(cuenta)
            ).status_code
            == 204
            for cuenta, id_conv in self.e.conversaciones.items()
        )
        self.anotar(
            f"Conversaciones borradas por la API: {borradas} de {len(self.e.conversaciones)}."
        )

        docker = os.environ.get("DOCKER") or shutil.which("docker")
        pendientes = []
        if self.e.pedido or self.e.producto:
            pendientes.append(
                (
                    "svc-tienda",
                    (
                        "from apps.pedidos.models import ItemCarrito, Pedido\n"
                        "from apps.catalogo.models import Producto\n"
                        f"Pedido.objects.filter(id={self.e.pedido or 0}).delete()\n"
                        f"ItemCarrito.objects.filter(producto__slug={self.e.producto!r}).delete()\n"
                        f"Producto.objects.filter(slug={self.e.producto!r}).delete()\n"
                    ),
                    "pedido y producto de la matriz",
                )
            )
        if self.e.diagnosticos or self.e.diagnosticos_ia:
            ids = list(self.e.diagnosticos.values()) + self.e.diagnosticos_ia
            pendientes.append(
                (
                    "svc-contenido",
                    (
                        "from bson import ObjectId\n"
                        "from django.core.files.storage import default_storage\n"
                        "from apps.diagnosticos.servicios import _coleccion\n"
                        f"for i in {ids!r}:\n"
                        "    d = _coleccion().find_one_and_delete({'_id': ObjectId(i)})\n"
                        "    if d and d.get('imagen'): default_storage.delete(d['imagen'])\n"
                    ),
                    f"{len(ids)} diagnósticos y sus fotos",
                )
            )
        comandos = [
            (servicio, ["shell", "-c", codigo], descripcion)
            for servicio, codigo, descripcion in pendientes
        ]
        comandos += [
            ("svc-usuarios", ["axes_reset_username", correo], "bloqueo del correo de prueba")
            for tipo, correo in self.e.limpieza
            if tipo == "axes"
        ]
        comandos += [
            (servicio, ["reiniciar_limites"], "contadores del límite de la IA")
            for tipo, servicio in self.e.limpieza
            if tipo == "limite_ia"
        ]
        for servicio, argumentos, descripcion in list(comandos):
            if not docker:
                self.anotar(f"Sin docker en el PATH: quedó {descripcion}.")
                continue
            comando = [
                docker,
                "compose",
                "exec",
                "-T",
                servicio,
                "python",
                "manage.py",
                *argumentos,
            ]
            hecho = subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True)
            estado = "Borrado" if hecho.returncode == 0 else "**No se pudo borrar**"
            self.anotar(f"{estado} con `manage.py` de {servicio}: {descripcion}.")

        cerradas = sum(
            self.http.post(
                "/api/usuarios/auth/logout/",
                headers=self.encabezados(cuenta),
                json={"refresh": self.e.refresh[cuenta]},
            ).status_code
            == 205
            for cuenta in CUENTAS
        )
        self.anotar(f"Sesiones de la matriz cerradas (logout, 205): {cerradas} de {len(CUENTAS)}.")

    # --- reporte ----------------------------------------------------------------------

    def reporte(self, inicio: datetime, segundos: float, con_limites: bool) -> str:
        casos = self.casos
        coinciden = sum(c.coincide for c in casos)
        externos = sum(c.servicio_externo for c in casos)
        permitidos = [c for c in casos if c.permitido]
        denegados = [c for c in casos if not c.permitido]
        grupos = list(dict.fromkeys(c.grupo for c in casos))

        def celda(c: Caso | None) -> str:
            if c is None:
                return "—"
            if c.servicio_externo:
                return f"{c.obtenido} ✓*"
            return f"{c.obtenido} {'✓' if c.coincide else '✗'}"

        def coincide(c: Caso) -> str:
            if c.servicio_externo:
                return f"sí, {EXTERNO}"
            return "sí" if c.coincide else "**no**"

        def texto(c: Caso) -> str:
            return f"`{c.codigo}`" if c.codigo else "—"

        lineas = [
            "# Matriz de accesos",
            "",
            f"Generada por [`infra/matriz_seguridad.py`](../../infra/matriz_seguridad.py) el "
            f"{inicio:%Y-%m-%d %H:%M} contra el sistema levantado con `docker compose`, a través "
            f"del gateway (`{self.http.base_url}`). Duración: {segundos:.0f} s."
            + (
                "" if con_limites else " Sin los casos de límites de intentos (`--omitir-limites`)."
            ),
            "",
            "Cómo leerla: cada caso es una petición real. **Esperado** sale de las reglas de "
            "[`docs/contrato-identidad.md`](../contrato-identidad.md); **coincide** exige el mismo "
            "código HTTP y, en las denegadas, el mismo código de error del cuerpo. La matriz "
            "prueba el control de acceso, no la disponibilidad del agente: un 503 "
            "`agente_no_disponible` o `modelo_no_disponible` donde se esperaba acceso permitido "
            f"cuenta como coincidencia, marcado como «{EXTERNO}» (✓*).",
            "",
            "## Resumen",
            "",
            "| Concepto | Casos |",
            "| --- | --- |",
            f"| Combinaciones probadas | {len(casos)} |",
            f"| Permitidas (2xx esperado) | {len(permitidos)} |",
            f"| Denegadas (4xx esperado) | {len(denegados)} |",
            f"| Coinciden con lo esperado | **{coinciden} de {len(casos)} "
            f"({100 * coinciden / len(casos):.0f} %)** |",
            f"| De ellas, {EXTERNO} | {externos} |",
            "",
            "## Matriz",
            "",
            "Código obtenido por actor; ✓ coincide con lo esperado, ✓* "
            f"{EXTERNO}, ✗ no coincide, — no aplica.",
            "",
            "| Endpoint | " + " | ".join(n for _, n in ACTORES) + " |",
            "| --- | " + " | ".join("---" for _ in ACTORES) + " |",
        ]
        for g in grupos:
            por_actor = {c.actor: c for c in casos if c.grupo == g}
            if len(por_actor) < len([c for c in casos if c.grupo == g]):
                continue  # los límites tienen varios casos del mismo actor; van abajo
            lineas.append(
                f"| {g} | " + " | ".join(celda(por_actor.get(a)) for a, _ in ACTORES) + " |"
            )

        lineas += ["", "## Detalle", ""]
        for g in grupos:
            del_grupo = [c for c in casos if c.grupo == g]
            lineas += [
                f"### {g}",
                "",
                f"`{del_grupo[0].metodo} {del_grupo[0].ruta}`",
                "",
                "| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
            for c in del_grupo:
                esperado = f"{c.esperado}" + (
                    f" `{c.codigo_esperado}`" if c.codigo_esperado else ""
                )
                lineas.append(
                    f"| {NOMBRE_ACTOR[c.actor]} | {esperado} | {c.obtenido} | {texto(c)} | "
                    f"{coincide(c)} | {c.nota} |"
                )
            lineas.append("")

        lineas += [
            "## Qué capa decide",
            "",
            "- **Gateway** (`web`, primera capa): sin token (401 `no_autenticado`), token "
            "vencido, de otra llave o un refresh usado como access (401 `token_invalido`), y "
            "un `Origin` ajeno (403 `origen_no_permitido`). Esas peticiones no llegan al "
            "servicio. Las rutas públicas (catálogo, login) también validan el token si viene.",
            "- **Servicio** (segunda capa): el rol (403 `sin_permiso`), el correo verificado "
            "(403 `email_no_verificado`), los recursos de otro usuario (404 `no_encontrado`, "
            "para no revelar que existen), los límites de intentos de svc-usuarios y el de "
            "solicitudes a la IA por usuario de svc-contenido (429 `demasiados_intentos`).",
            "- **Recursos propios y ajenos:** las conversaciones son privadas para todos, "
            "también para el administrador; los diagnósticos los puede ver el administrador.",
            "",
            "## Limpieza",
            "",
            "La matriz borra lo que creó: las conversaciones por la API, y el pedido, el "
            "producto y los diagnósticos (que la API no deja borrar) con el `manage.py` de su "
            "servicio. Resultado de esta corrida:",
            "",
        ]
        lineas += [f"- {texto}" for tipo, texto in self.e.limpieza if tipo == "hecho"]
        lineas.append("")
        return "\n".join(lineas)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default=os.environ.get("MATRIZ_BASE", "http://127.0.0.1:8000"))
    parser.add_argument(
        "--omitir-limites",
        action="store_true",
        help="No correr los casos de exceso de intentos (login y recuperación).",
    )
    parser.add_argument("--salida", type=Path, default=SALIDA)
    args = parser.parse_args()

    inicio, reloj = datetime.now(), time.monotonic()
    matriz = Matriz(args.base)
    try:
        matriz.preparar_identidades()
        matriz.tienda()
        matriz.usuarios()
        # Primero la pregunta síncrona al agente (espera 200) y después las de IA por eventos
        # (basta el 202): así esas no gastan antes el límite de tokens de la llave de Groq.
        matriz.agente()
        matriz.contenido()
        if not args.omitir_limites:
            matriz.limites()
    finally:
        if matriz.e.tokens:
            matriz.limpiar()

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(
        matriz.reporte(inicio, time.monotonic() - reloj, not args.omitir_limites),
        encoding="utf-8",
        newline="\n",
    )
    total, bien = len(matriz.casos), sum(c.coincide for c in matriz.casos)
    externos = sum(c.servicio_externo for c in matriz.casos)
    print(f"\n{bien} de {total} casos coinciden ({externos} {EXTERNO}). Reporte: {args.salida}")
    sys.exit(0 if bien == total else 1)


if __name__ == "__main__":
    main()
