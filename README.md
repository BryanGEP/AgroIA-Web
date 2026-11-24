# AgroIA-Web

Plataforma web para el agronegocio del aguacate: tienda en línea de insumos, asistente conversacional AgroIA y diagnóstico de enfermedades por imagen.

Proyecto académico (Ingeniería en Sistemas Computacionales — TecNM Jiquilpan). Metodología Scrum, gestión en Jira. Repositorio monorepo con arquitectura de microservicios sobre Django y FastAPI.

## Estructura

| Carpeta | Descripción | Base de datos | Puerto local | Detalle |
| :-- | :-- | :-- | :-- | :-- |
| `web/` | Gateway: plantillas, sesión, enruta al resto y valida JWT. Único punto de entrada del navegador. | PostgreSQL `web_db` (sesiones) | 8000 | [README](web/README.md) |
| `svc-usuarios/` | Identidad: registro, login con JWT, renovación, verificación de correo, recuperación de contraseña, roles, perfil y direcciones. | PostgreSQL `usuarios_db` | 8001 | [README](svc-usuarios/README.md) |
| `svc-tienda/` | Categorías, productos, stock, carrito y pedidos (pago simulado). | PostgreSQL `tienda_db` | 8002 | [README](svc-tienda/README.md) |
| `svc-contenido/` | Conversaciones con el agente, historial de diagnósticos y bitácora. | MongoDB `contenido` | 8003 | [README](svc-contenido/README.md) |
| `svc-ia/` | Adaptador en FastAPI: traduce las preguntas al contenedor `agente` y clasifica imágenes (sano, roña o antracnosis; el modelo llega en una entrega posterior). | ninguna | 8004 | [README](svc-ia/README.md) |
| `comun/` | Paquete `agroia_comun`: autenticación JWT, permisos y formato de errores para los servicios Django, y la librería de eventos con Redis Streams (sin Django; también la usa svc-ia). | — | — | [README](comun/README.md) |
| `infra/` | `postgres/init.sql` (bases y usuarios), `generar_llaves.py` (llaves JWT), `emitir_token.py` (tokens solo para pruebas), `matriz_seguridad.py` ([matriz de accesos](#matriz-de-accesos)) y `prueba_eventos.py` ([prueba de los eventos](#eventos-entre-servicios)). | — | — | — |
| `docs/` | Definición técnica, requerimientos y entregables. | — | — | ver [Documentación](#documentación) |

Además corren tres contenedores de infraestructura, `postgres` (16), `mongo` (7) y `redis` (7), el contenedor **`agente`**, que es el agente conversacional del repo [BryanGEP/AgroIA](https://github.com/BryanGEP/AgroIA) construido directamente desde GitHub (carpeta `svc-agente`, rama `main`), **`agente-db`**, su base de conocimiento (PostgreSQL con pgvector), y tres procesos de eventos con la misma imagen que su servicio y otro comando: **`svc-contenido-eventos`** (bitácora y resultados de la IA), **`svc-usuarios-eventos`** (correos) y **`svc-ia-worker`** (atiende las preguntas y los diagnósticos y llama al agente). En total, trece contenedores. El agente solo está en la red interna y se publica en `127.0.0.1:8005` para pruebas; `agente-db` no se publica.

## Requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) con Docker Compose.
- Python 3.12, solo para generar las llaves y para el entorno virtual del editor.
- Una llave de API de Groq **propia** (gratuita) para que el agente responda. Ver [Llave de Groq](#llave-de-groq).

## Levantar el proyecto por primera vez

Desde la raíz del repo, en PowerShell:

```powershell
# 1. Variables de entorno: copia el ejemplo y cambia las contraseñas (también
#    AGENTE_DB_PASSWORD) y la DJANGO_SECRET_KEY. Pon tu propia GROQ_API_KEY (ver "Llave de Groq").
Copy-Item .env.example .env

# 2. Llaves JWT (se crean en infra/llaves/, que nunca se sube al repo).
#    Con el venv de la raíz activo (ver más abajo):
python infra/generar_llaves.py
#    O sin venv, usando Docker:
docker run --rm -v "${PWD}:/repo" -w /repo python:3.12-slim sh -c "pip install -q cryptography==50.0.2 && python infra/generar_llaves.py"

# 3. Construir y levantar todo (la primera vez descarga el agente desde GitHub).
docker compose up --build -d

# 4. Cargar la base de conocimiento del agente (una vez; ver abajo).
docker compose run --rm agente python -m ingesta.cargar

# 5. Opcional: productos de demostración y cuentas de demostración (solo desarrollo).
docker compose exec svc-tienda python manage.py cargar_datos_demo
docker compose exec svc-usuarios python manage.py cargar_usuarios_demo
```

**¿Ya tenías el proyecto y bajas la rama de la Entrega 3?** El id de los usuarios pasó a UUID: reinicia los datos de prueba una vez con los pasos del [README de svc-usuarios](svc-usuarios/README.md#al-bajar-la-rama-de-la-entrega-3-feate3-identidad-reiniciar-los-datos-de-prueba) (vaciar `usuarios_db` y las colecciones de MongoDB y reconstruir). No uses `docker compose down -v`: borraría también el catálogo, la base de conocimiento del agente y el modelo descargado.

### Base de conocimiento del agente

El agente responde las preguntas técnicas buscando en su base de conocimiento (11 documentos sobre enfermedades, riego, suelo y manejo del aguacate, que vienen dentro de su imagen) y devuelve las fuentes que usó. Esa base vive en el contenedor `agente-db` (PostgreSQL con pgvector) y se llena con el paso 4:

- **La primera vez descarga unos 471 MB**: el modelo de embeddings `intfloat/multilingual-e5-small` (Hugging Face, sin llave). Queda en el volumen `modelos_hf` y no se vuelve a bajar. En nuestra máquina la primera ingesta tardó **unos 40 s** con la descarga y las siguientes **unos 11 s**.
- **Se puede repetir sin duplicar**: cada corrida recrea la colección (71 fragmentos). Córrela otra vez cuando cambie la base de conocimiento en el repo AgroIA, después de `docker compose build --no-cache agente`.
- **Sin ingesta el sistema funciona igual**: el agente responde, pero avisa que no pudo consultar su base y `fuentes` llega vacía.
- `AGENTE_DB_PASSWORD` solo se usa la primera vez que se crea el volumen `agente_db_datos`. Si la cambias después, bórralo con `docker volume rm agroia-web_agente_db_datos` y repite el paso 4.

### Llave de Groq

El agente usa el LLM de [Groq](https://groq.com/). **Cada integrante necesita su propia llave gratuita**; no se comparten ni se suben al repo:

1. Entra a https://console.groq.com/keys e inicia sesión.
2. Crea una llave ("Create API Key") y cópiala.
3. Pégala en tu `.env`: `GROQ_API_KEY=gsk_...`
4. Reinicia el agente: `docker compose up -d agente`.

La llave solo llega al contenedor `agente`, no a svc-ia. Sin llave el sistema arranca igual, pero `POST /agente/preguntar/` responde 503 `agente_no_disponible`. Para traer la versión más reciente del agente desde GitHub: `docker compose build --no-cache agente`.

### Tiempo de respuesta del agente

El agente tarda normalmente de 2 a 6 segundos, pero el LLM a veces se toma de 20 a 30 segundos en cualquier pregunta, no solo en la primera. Por eso la pregunta va por eventos: svc-contenido la acepta al momento (202), `svc-ia-worker` espera al agente hasta `AGENTE_TIMEOUT=45` segundos (con 2 reintentos) y la pantalla muestra «AgroIA está escribiendo…» y consulta el estado cada 2 s (cada 5 s después de 20 s). Si la solicitud falla o pasa de `IA_SOLICITUD_VENCE_SEGUNDOS=180`, el chat ofrece «Reintentar». `IA_TIMEOUT=50` sigue siendo el límite del gateway para los endpoints síncronos de svc-ia, que quedan por compatibilidad.

- **Medición del 20 de noviembre de 2026** (agente recién reiniciado, tres preguntas seguidas, dos veces): primeras preguntas de 5,2 s y 5,9 s; las más lentas, 21,0 s y 29,3 s, fueron la tercera y la segunda.
- **Arranque:** la primera pregunta carga el modelo de embeddings desde el volumen `modelos_hf`, lo que toma menos de un segundo. Si el volumen está vacío, primero lo descarga (unos 471 MB, ver arriba).
- **Antes de una demo:** haz una pregunta de prueba en http://localhost:8000/agroia/. Así se carga el modelo y confirmas que la llave de Groq funciona.
- **Si tu `.env` ya tenía** `AGENTE_TIMEOUT=30` o `IA_TIMEOUT=35`, cámbialos a `45` y `50` (`.env.example` ya los trae así) y reinicia con `docker compose up -d svc-ia svc-ia-worker web`.
- **Límite de la llave gratuita de Groq:** con 3 llamadas a la vez, Groq rechaza algunas (`RateLimitError`) y el agente tarda de 11 a 39 s en responder 503. Por eso `svc-ia-worker` atiende 2 a la vez (`IA_WORKER_HILOS=2`); con una llave de pago se puede subir. Si Groq rechaza una llamada, el worker reintenta a los 5 s y la respuesta llega, pero más tarde. Si pasa de 180 s, «Reintentar». Para que un solo usuario no agote el límite, svc-contenido limita las preguntas por usuario (ver «Eventos entre servicios»). Medición del 22 de noviembre de 2026 en [`docs/avances/e4-ia-asincrona.md`](docs/avances/e4-ia-asincrona.md).

Cuando todo esté arriba, cada servicio responde `{"estado": "ok"}` en `GET /salud/` y tiene su documentación en `/api/docs/`:

| Servicio | Salud | Documentación |
| --- | --- | --- |
| web | http://localhost:8000/salud/ | http://localhost:8000/api/docs/ |
| svc-usuarios | http://localhost:8001/salud/ | http://localhost:8001/api/docs/ |
| svc-tienda | http://localhost:8002/salud/ | http://localhost:8002/api/docs/ |
| svc-contenido | http://localhost:8003/salud/ | http://localhost:8003/api/docs/ |
| svc-ia | http://localhost:8004/salud/ | http://localhost:8004/api/docs/ |
| agente (solo pruebas) | http://localhost:8005/health | — (chat propio en http://localhost:8005/) |

**El punto de entrada es `web` (8000):** las páginas y el proxy de API `/api/<servicio>/<ruta>` (por ejemplo, `http://localhost:8000/api/tienda/productos/`), que valida el token antes de reenviar. Los puertos directos de los servicios (8001 a 8005) y de las bases (5432, 27017 y 6379; `agente-db` no se publica) son **solo para desarrollo**: se publican en `127.0.0.1`, sirven para el Swagger de cada servicio y para depurar, y no forman parte de la API pública. Además, los servicios confían en el `X-Forwarded-For` que pone el gateway, que desde un puerto directo se podría falsificar: nunca los publiques en `0.0.0.0` (ver [`docs/contrato-identidad.md`](docs/contrato-identidad.md#ip-del-cliente-y-puertos-publicados)).

### Bases de datos

- `infra/postgres/init.sql` crea `usuarios_db`, `tienda_db` y `web_db`, cada una con su propio usuario, y lee las contraseñas del `.env`. **Solo corre la primera vez que se crea el volumen de PostgreSQL**: si después cambias esas contraseñas en `.env` o modificas `init.sql`, no se vuelve a ejecutar.
- Para reiniciar las bases desde cero:

  ```powershell
  docker compose down -v
  docker compose up --build
  ```

  > **Cuidado:** `down -v` borra los volúmenes, es decir, **todos los datos** de PostgreSQL, MongoDB y Redis (incluidos los eventos sin procesar y los fallidos), la base de conocimiento del agente y el modelo descargado. Sin `-v`, `docker compose down` detiene los contenedores y conserva los datos.

### Iniciar sesión y tokens

En el navegador, inicia sesión en http://localhost:8000/iniciar-sesion/: los tokens se quedan en la sesión del servidor. Para la API, los tokens los emite svc-usuarios: `POST http://localhost:8000/api/usuarios/auth/login/` (a través del gateway) con `{"email", "password"}` devuelve el `access` (15 minutos) y el `refresh` (7 días). Pega el `access` en el botón **Authorize** de `/api/docs/` de cualquier servicio o úsalo como `Authorization: Bearer <access>`. El contrato completo está en [`docs/contrato-identidad.md`](docs/contrato-identidad.md).

Para tener cuentas listas en desarrollo:

```powershell
docker compose exec svc-usuarios python manage.py cargar_usuarios_demo
```

Crea `cliente@demo.agroia.test` (verificado), `sin-verificar@demo.agroia.test` y `admin@demo.agroia.test` con la contraseña `solo-demo-no-usar-en-produccion`. **Esas cuentas no deben existir fuera de desarrollo**: el comando se niega a correr con `DJANGO_DEBUG=False`. Los correos (verificación, recuperación) se imprimen en `docker compose logs -f svc-usuarios-eventos`, el consumidor que los envía.

`infra/emitir_token.py` se conserva **solo para pruebas y desarrollo**, para lo que el login no cubre: un token vencido (`--vencido`), un usuario que no existe o probar un servicio sin levantar svc-usuarios. Firma con la llave privada local.

```powershell
python infra/emitir_token.py --rol cliente
python infra/emitir_token.py --vencido
```

### Postman

La colección [`docs/postman/`](docs/postman/) inicia sesión sola: la carpeta «Autenticación» guarda los tokens en el entorno y no hay que pegar ninguno, salvo `token_vencido` para un caso opcional de «Seguridad». Antes de la primera corrida: `cargar_datos_demo` y `cargar_usuarios_demo`. Con Newman, desde la raíz:

```powershell
newman run docs/postman/AgroIA-Web.postman_collection.json -e docs/postman/local.postman_environment.json --working-dir docs/postman --env-var "token_vencido=$(python infra/emitir_token.py --vencido)"
```

La carpeta «Seguridad» agota el límite de 10 logins por minuto: entre dos corridas espera un minuto. Además, cada corrida hace dos registros (límite de 5 por hora por IP), así que caben dos corridas por hora. Para empezar con los límites en cero, ver [Correr las pruebas de seguridad](#correr-las-pruebas-de-seguridad).

### Matriz de accesos

[`infra/matriz_seguridad.py`](infra/matriz_seguridad.py) prueba quién puede hacer qué **a través del gateway** (`http://127.0.0.1:8000/api/`): ocho actores (anónimo, cliente sin verificar, cliente verificado, administrador, token vencido, token de otra llave, refresh en la blacklist y origen no permitido) contra endpoints de los cuatro servicios, más el bloqueo por intentos fallidos y el exceso de logins y de recuperaciones. Compara el código HTTP y el código de error de cada respuesta con lo esperado y escribe [`docs/entregable-4/matriz-accesos.md`](docs/entregable-4/matriz-accesos.md) (el reporte de la Entrega 3, [`docs/entregable-3/matriz-accesos.md`](docs/entregable-3/matriz-accesos.md), queda como se entregó). Termina con código 1 si algún caso no coincide.

Con el sistema levantado, `cargar_datos_demo` y `cargar_usuarios_demo`, y el venv de la raíz activo, desde la raíz:

```powershell
python infra/matriz_seguridad.py                    # completa, unos 2 minutos
python infra/matriz_seguridad.py --omitir-limites   # sin los casos de exceso de intentos
python infra/matriz_seguridad.py --salida docs/entregable-3/matriz-accesos.md   # otra ruta
```

- **Usa las cuentas de demostración** y crea lo que necesita: un producto, un pedido, y una conversación y dos diagnósticos por cuenta (uno por eventos). Al terminar lo borra (el pedido, el producto y los diagnósticos con el `manage.py` de su servicio, porque la API no los borra), restaura el carrito del cliente y cierra sus sesiones. Necesita `docker` en el PATH para esa limpieza.
- **Respeta los límites, sin subirlos:** antes de los casos de login espera 61 s. La recuperación permite 3 por hora por IP y la matriz la agota: si corres Postman después, «Pedir recuperación» responde 429 hasta que pase una hora o hasta correr `reiniciar_limites`. Por eso Postman va primero y la matriz al final.
- **Llama al agente** seis veces (por cuenta, una directa a svc-ia y una pregunta por eventos), así que necesita la llave de Groq.
- **Prueba el control de acceso, no la disponibilidad del agente** (eso lo cubre `infra/prueba_eventos.py`). Si una fila espera acceso permitido y la respuesta es 503 con `agente_no_disponible` o `modelo_no_disponible` (por ejemplo, porque se acabó la cuota de Groq), el control de acceso dejó pasar la petición: cuenta como coincidencia, marcada «permitido (servicio externo no disponible)» (✓* en la tabla), y el resumen dice cuántas hubo. Un 401 o 403 donde se esperaba permitido sigue siendo una falla, igual que un 503 en una fila que esperaba 401 o 403. La clasificación tiene sus pruebas: `python -m pytest infra/tests`.

### Eventos entre servicios

Desde la Entrega 4 los servicios se avisan por **eventos con Redis Streams** (base lógica 1 de Redis, con persistencia). Hoy funcionan:
- **Bitácora:** los eventos de cuenta (registro, verificación, cambio de rol y de contraseña, cierre de sesiones) y de pedidos (creado y cada cambio de estado, también el pago) llegan a la bitácora de svc-contenido por el contenedor `svc-contenido-eventos`.
- **Correos:** se envían en segundo plano por `svc-usuarios-eventos`, que genera el token de cada enlace al enviar.
- **Límite de preguntas por usuario:** preguntar, reintentar y solicitar un diagnóstico comparten `IA_SOLICITUDES_POR_MINUTO` (10) e `IA_SOLICITUDES_POR_HORA` (30) por usuario; al pasarse, 429 `demasiados_intentos` y la pantalla dice «Hiciste muchas preguntas seguidas». Los GET del polling no cuentan. El límite de tokens del LLM es de toda la aplicación: así un solo usuario no lo agota.
- **IA asíncrona:** el chat y el diagnóstico piden la respuesta a svc-contenido (202), `svc-ia-worker` la genera y `svc-contenido-eventos` la guarda; la pantalla consulta el estado con HTMX. Para probar el diagnóstico sin modelo hay un clasificador de prueba (`IA_CLASIFICADOR_PRUEBA=1`, solo con `DJANGO_DEBUG=True`), cuyos resultados se marcan «Resultado de prueba: no es un diagnóstico real».

Cada petición lleva un `X-Correlacion-Id` que el gateway reenvía a los servicios; la bitácora se puede filtrar por correlación y por usuario (`GET /api/contenido/bitacora/?correlacion_id=…`). El catálogo completo, el sobre común, los reintentos, el stream de fallidos y el diagrama están en [`docs/eventos.md`](docs/eventos.md).

```powershell
# Estado: streams, grupos, pendientes, consumidores y los últimos fallidos
docker compose exec svc-contenido python -m agroia_comun.eventos estado

# Volver a publicar eventos fallidos (con el mismo id)
docker compose exec svc-contenido python -m agroia_comun.eventos reprocesar --id <id>
docker compose exec svc-contenido python -m agroia_comun.eventos reprocesar --todos

# Borrar fallidos ya revisados, sin volver a publicarlos (por ejemplo, los de la IA,
# que no se pueden reprocesar). --todos pide confirmación; --si la salta en scripts
docker compose exec svc-contenido python -m agroia_comun.eventos descartar --id <id>
docker compose exec -it svc-contenido python -m agroia_comun.eventos descartar --todos

# Ver lo que hacen los consumidores y el worker de IA
docker compose logs -f svc-contenido-eventos svc-usuarios-eventos svc-ia-worker
```

**Los correos en desarrollo** (backend de consola) se imprimen en `docker compose logs svc-usuarios-eventos`: el enlace de verificación o de recuperación se copia de ahí.

**Prueba de punta a punta:** [`infra/prueba_eventos.py`](infra/prueba_eventos.py) comprueba, con el sistema levantado:
1. un registro por el gateway llega a la bitácora;
2. `docker compose stop` del consumidor sale limpio, con código 0;
3. lo publicado con el consumidor detenido se procesa al volver;
4. con MongoDB detenido, el evento agota sus 5 reintentos y llega a fallidos, y al reprocesarlo se guarda una sola vez;
5. y 6. el flujo de negocio completo con su correlación en la bitácora y en los logs;
7. un correo que falla, llega a fallidos y se reprocesa;
8. una pregunta a AgroIA por eventos con el agente real, con su correlación en web, svc-contenido, svc-ia-worker y svc-contenido-eventos;
9. con el agente detenido, los 2 reintentos y la fallida, y «Reintentar» cuando vuelve;
10. 5 preguntas a la vez, con sus tiempos;
11. el diagnóstico sin modelo y con el clasificador de prueba.

Imprime cada comprobación con `[ok]` o `[FALLA]` y sirve como evidencia del entregable. Tarda unos 5 minutos porque espera los reintentos reales, y los pasos 8 a 10 gastan tokens de Groq. Necesita `docker` en el PATH y las cuentas demo. Al empezar corre `reiniciar_limites` y al terminar borra lo que creó con `limpiar_datos_prueba`.

```powershell
python infra/prueba_eventos.py
python infra/prueba_eventos.py --solo-ia --pasos=10,11   # solo algunos pasos de la IA
```

### Correr las pruebas de seguridad

Postman y la matriz usan las cuentas de demostración, gastan los límites de intentos y dejan datos de prueba. Dos comandos, que **solo corren con `DJANGO_DEBUG=True`** (con `False` fallan con un mensaje claro), preparan y limpian el entorno sin cambiar los límites ni la lógica de seguridad:

- **`reiniciar_limites`** borra los contadores de intentos de Redis (`throttle_*`). En svc-usuarios: login, registro, recuperación, reenvío y cambio de contraseña, y los bloqueos de django-axes. En svc-contenido: el límite de solicitudes a la IA por usuario. Cada servicio borra solo los suyos, así que se corre en los dos.
- **`limpiar_datos_prueba`** (svc-usuarios, svc-tienda y svc-contenido) borra lo que crean las pruebas. Se puede correr varias veces y dice cuánto borró:
  - en svc-tienda, los productos y categorías con sufijo de timestamp (los de Postman, como `Fosfito de potasio 1 L 1795210684`) o de la matriz (`matriz-…`), y los pedidos y carritos de las cuentas demo y de prueba;
  - en svc-contenido, las conversaciones, los diagnósticos con su foto y los eventos de bitácora de esas cuentas;
  - en svc-usuarios, los usuarios que registran las pruebas (`<palabra>.<timestamp>@example.com`).

  Nunca toca el catálogo de demostración, las cuentas demo ni la base de conocimiento del agente. svc-tienda y svc-contenido no leen la base de usuarios: los ids de las cuentas demo y de prueba los imprime svc-usuarios con `--listar-ids` y se les pasan con `--usuarios`. Por eso svc-usuarios se limpia al final.

Orden recomendado, desde la raíz en PowerShell, con el venv activo:

```powershell
# 1. Stock del catálogo de demostración (Postman compra en cada corrida) y límites en cero
docker compose exec svc-tienda python manage.py cargar_datos_demo
docker compose exec svc-usuarios python manage.py reiniciar_limites
docker compose exec svc-contenido python manage.py reiniciar_limites

# 2. Postman
newman run docs/postman/AgroIA-Web.postman_collection.json -e docs/postman/local.postman_environment.json --working-dir docs/postman --env-var "token_vencido=$(python infra/emitir_token.py --vencido)"

# 3. Esperar un minuto (10 logins por minuto) y correr la matriz
Start-Sleep -Seconds 60
python infra/matriz_seguridad.py

# 4. Limpiar los datos de prueba (svc-usuarios al final)
$ids = docker compose exec -T svc-usuarios python manage.py limpiar_datos_prueba --listar-ids
docker compose exec svc-tienda python manage.py limpiar_datos_prueba --usuarios $ids
docker compose exec svc-contenido python manage.py limpiar_datos_prueba --usuarios $ids
docker compose exec svc-usuarios python manage.py limpiar_datos_prueba
```

Las compras de Postman descuentan stock del catálogo de demostración; `cargar_datos_demo` lo restablece.

## Comandos del día a día

```bash
docker compose up --build                       # levantar todo
docker compose exec <servicio> pytest           # pruebas de un servicio
docker compose exec <servicio> ruff check .     # linter
docker compose exec <servicio> ruff format .    # formateador
docker compose exec <servicio> python manage.py makemigrations
docker compose logs -f <servicio>               # ver logs de un servicio
```

El código está montado como volumen: los cambios se ven sin reconstruir la imagen. Solo hay que usar `--build` cuando cambian los `requirements*.txt` o un `Dockerfile`.

**En Windows, después de cambiar de rama o hacer `pull`, reinicia los servicios.** Con Docker Desktop en Windows, los volúmenes montados no siempre le avisan al contenedor que un archivo cambió, y el autorreload de Django (y el de uvicorn en svc-ia) puede quedarse con una versión anterior del código. Pasa sobre todo cuando muchos archivos cambian de golpe. **El síntoma típico: una ruta nueva responde 404** aunque esté en el código (por ejemplo, `POST /api/v1/conversaciones/<id>/preguntar/` con la página «Page not found» de Django). Se arregla reiniciando los servicios propios y los procesos de eventos:

```powershell
docker compose restart web svc-usuarios svc-tienda svc-contenido svc-ia svc-contenido-eventos svc-usuarios-eventos svc-ia-worker
```

## Entornos virtuales (opcional)

La forma oficial de correr los servicios y sus pruebas es Docker. Los entornos virtuales solo sirven para que el editor reconozca los paquetes y para correr ruff y pytest localmente:

- `venv/` en la raíz, compartido por `web`, `svc-usuarios`, `svc-tienda` y `svc-contenido`. Su `requirements-dev.txt` incluye los de esos cuatro servicios, el paquete `comun` en modo editable y `cryptography` para generar las llaves.
- `svc-ia/venv/`, propio de svc-ia (ver su [README](svc-ia/README.md)).

En Windows, con PowerShell y Python 3.12 instalado, desde la raíz:

```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

ruff check .
cd svc-tienda; pytest
```

Si PowerShell no deja ejecutar `Activate.ps1`, corre una vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Las pruebas se corren desde la carpeta de cada servicio. Ambas carpetas `venv/` están en `.gitignore`.

## Documentación

- [Definición técnica](docs/definicion-tecnica.md): servicios, contratos de API, modelo de datos, frontend, entorno local y plan por fases.
- [Requerimientos de autenticación](docs/requerimientos-autenticacion.md): registro, verificación, JWT, recuperación, roles, límites de intentos y 2FA.
- [Avances](docs/avances/): un documento por fase con lo construido, decisiones, verificación y commits.
- [Bitácora diaria](docs/bitacora.md): qué hizo cada integrante por sesión; evidencia de los dailies para Jira.
- [CLAUDE.md](CLAUDE.md): reglas que siempre se respetan (resumen para Claude Code y para el equipo).
- [Documento del Entregable 1](docs/Entregable1_AgroIAWeb.docx)
- [Documento del Entregable 2](docs/entregable-2.md)
- [Documento del Entregable 3](docs/entregable-3.md) y su [matriz de accesos](docs/entregable-3/matriz-accesos.md)
- [Contrato de identidad](docs/contrato-identidad.md): qué emite svc-usuarios y cómo valida el token cada servicio.
- [Eventos entre servicios](docs/eventos.md): qué es asíncrono, catálogo de eventos, sobre común, reintentos, fallidos y diagrama del flujo.

## Entregas

- **Entrega 1:** fundamentos y planeación del proyecto (equipo y roles Scrum, definición del proyecto, arquitectura, configuración de Jira y estándares de trabajo).
  - [Documento del Entregable 1](docs/Entregable1_AgroIAWeb.docx)
- **Entrega 2:** microservicios con Django/DRF y FastAPI, PostgreSQL y MongoDB, integración con el agente de IA, pruebas, Swagger, Postman y Docker Compose.
  - [Documento del Entregable 2](docs/entregable-2.md)
- **Entrega 3:** seguridad: autenticación JWT con rotación y blacklist, propagación de identidad a los microservicios, API Gateway, control de acceso por roles, buenas prácticas (CORS, CSP, límites de intentos, log de seguridad) y las pantallas protegidas.
  - [Documento del Entregable 3](docs/entregable-3.md)
  - [Matriz de accesos](docs/entregable-3/matriz-accesos.md)

## Cómo contribuir

El equipo trabaja con ramas por tarea que se integran en `develop` mediante Pull Requests; `main` está protegida y solo contiene versiones estables.

Antes de hacer cualquier cambio, lee la [guía de contribución](CONTRIBUTING.md). Al abrir un Pull Request se carga automáticamente la [plantilla de PR](.github/pull_request_template.md).

## Equipo

- Isis Lizbeth Vázquez Avalos
- Danna Geraldine Ávila García
- Bryan Gael Esquivel Pérez
