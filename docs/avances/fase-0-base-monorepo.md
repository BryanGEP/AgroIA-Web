# Fase 0 · Base del monorepo

**Fecha:** 22 de octubre de 2026 · **Entregable:** Entrega 2 · **Responsable:** Bryan Gael Esquivel Pérez

## Resumen

Se construyó la base técnica sobre la que trabajará todo el equipo: el monorepo con los cinco servicios (`web`, `svc-usuarios`, `svc-tienda`, `svc-contenido` y `svc-ia`), las tres bases de datos y la configuración común. Con un solo comando, `docker compose up --build`, se levantan los ocho contenedores y cada servicio responde en `GET /salud/`. Todo se verificó con Docker el mismo día. Con esto, las fases 1, 2 y 3 ya pueden avanzar en paralelo.

## Qué se construyó

### Configuración del repositorio

| Archivo | Para qué |
| --- | --- |
| `ruff.toml` | Linter y formateador únicos para todo el repo: línea de 100 caracteres, reglas para Django (`DJ`), imports, bugbear y sintaxis moderna. |
| `.gitattributes` | Fuerza finales de línea LF en `*.py`, `*.sh`, `Dockerfile`, `*.yml`, `*.toml`, `*.txt`, `*.md`, `*.sql` y otros. |
| `.gitignore` | Excluye `.env`, `venv/`, `svc-ia/venv/`, `infra/llaves/`, `*.pem`, cachés, `media/`, `staticfiles/` y `.claude/settings.local.json`. Incluye las reglas útiles del repo AgroIA. |
| `.dockerignore` | Evita que `.git`, los entornos virtuales, `.env` y las llaves terminen dentro de las imágenes. |
| `.env.example` | Todas las variables de la definición técnica con valores de ejemplo seguros para desarrollo. |
| `requirements-dev.txt` (raíz) | Entorno virtual compartido para el editor: incluye los cuatro servicios Django, `comun` en modo editable y `cryptography`. |
| `CLAUDE.md` y `.claude/settings.json` | Reglas para Claude Code, para que el código generado siga la misma estructura sin importar quién lo pida. |

### Infraestructura

- **`docker-compose.yml`:** ocho contenedores en una red interna común: los cinco servicios propios, `postgres:16`, `mongo:7` y `redis:7`.
  - Cada servicio escucha en el puerto 8000 dentro del contenedor y se publica en su puerto local: 8000 web, 8001 usuarios, 8002 tienda, 8003 contenido y 8004 ia.
  - Las bases tienen `healthcheck` y los servicios esperan con `depends_on: condition: service_healthy`.
  - Volúmenes con nombre para PostgreSQL y MongoDB. El código se monta como volumen, así que los cambios se ven sin reconstruir la imagen.
  - Los servicios Django corren `migrate` al arrancar y luego el servidor de desarrollo.
  - Cada contenedor recibe solo las variables que usa.
- **`infra/postgres/init.sql`:** crea `usuarios_db`, `tienda_db` y `web_db`, cada una con su propio usuario, y le quita el acceso a los demás.
- **`infra/generar_llaves.py`:** genera el par RSA de 2048 bits para firmar los JWT en `infra/llaves/`. Nunca sobrescribe llaves que ya existen. Compose monta la llave pública en todos los servicios y la privada solo en `svc-usuarios`.

### Paquete `comun`

Paquete instalable (`comun/pyproject.toml`) con `agroia_comun/autenticacion.py`, `permisos.py` y `errores.py`. Por ahora solo documentan lo que contendrán: la autenticación se implementa en la fase 4. Lo instalan los cuatro servicios Django; `svc-ia` no.

### Servicios

Los cuatro servicios Django usan Python 3.12, Django 5.2.18 (LTS), DRF 3.18.3, drf-spectacular 0.30.0 y django-filter 26.2, con las mismas versiones en todos. Cada uno tiene:

- `config/settings.py`, que lee todo de variables de entorno.
- Paginación de 20 elementos y filtros configurados.
- `GET /salud/` → `{"estado": "ok"}` y la documentación en `/api/docs/`.
- `Dockerfile`, `requirements.txt` y `requirements-dev.txt` con versiones fijas, `pytest.ini`, pruebas y `README.md`.

| Servicio | Base | Particularidad |
| --- | --- | --- |
| `web` | PostgreSQL `web_db` | Gateway. Guarda las sesiones en su base y ya tiene configuradas las direcciones internas de los demás servicios. |
| `svc-usuarios` | PostgreSQL `usuarios_db` | Único servicio que recibe la llave privada para firmar los JWT. Tiene activados los validadores de contraseña de Django. |
| `svc-tienda` | PostgreSQL `tienda_db` | Listo para los modelos de catálogo y pedidos de la fase 2. |
| `svc-contenido` | MongoDB `contenido` | Sin base relacional (ver decisiones). Su conexión con pymongo está en `config/mongo.py`. |
| `svc-ia` | ninguna | FastAPI con la misma estructura y versiones que el agente del repo AgroIA, para copiarlo en la fase 3 sin rehacer nada. |

### Documentación

- `README.md` raíz: estructura real, cómo levantar el proyecto por primera vez, reinicio de bases con `docker compose down -v` y entornos virtuales en Windows.
- `CONTRIBUTING.md`: las pruebas se corren con `docker compose exec <servicio> pytest`, y como opción local, con el venv.
- `docs/definicion-tecnica.md` y `docs/requerimientos-autenticacion.md`: se alinearon con lo implementado (`web_db`, variables nuevas, `generar_llaves.py` y llaves montadas como *secrets*).
- `README.md` de cada servicio y de `comun`.

## Decisiones técnicas

### Aprobadas por el equipo (definición técnica)

| Decisión | Por qué |
| --- | --- |
| Catálogo y pedidos juntos en `svc-tienda`; agente y diagnóstico juntos en `svc-ia` | Crear un pedido descuenta stock en la misma transacción; separarlos obligaría a una transacción distribuida. Agente y visión comparten dependencias. |
| Ficha técnica del producto como `JSONField` en PostgreSQL | MongoDB queda para los datos que crecen y cambian de forma: conversaciones, diagnósticos y bitácora. |
| `svc-ia` en FastAPI, reutilizando el agente de AgroIA y validando el JWT con PyJWT | Evita reescribir el agente; las clases de `comun/` son de DRF. |
| Proveedor del LLM: el que ya usa el agente (Groq) | La llave vive solo en `.env`, con límite de gasto en la cuenta. |
| Pago simulado, con la etiqueta "pago simulado" | Ninguna entrega califica pagos. |
| Imágenes siempre con `STORAGES` y `default_storage` | En la Entrega 5 se pasa a Cloud Storage cambiando solo la configuración. |
| Solo los roles `cliente` y `administrador` | No hay funciones que requieran otro rol. |
| Commits y push manuales | Cada integrante revisa y es responsable de su código. |

### Tomadas en la fase 0

| Decisión | Por qué |
| --- | --- |
| `DATABASES = {}` en `svc-contenido` | El servicio no necesita base relacional. Con el backend *dummy* de Django, cualquier uso accidental del ORM falla con un error claro. No hay admin ni `migrate`, y en las pruebas se usa `mongomock`. |
| Contraseñas de PostgreSQL leídas con `\getenv` en `init.sql` | Ninguna contraseña queda escrita en el repositorio; psql las toma del entorno del contenedor. |
| `generar_llaves.py` en lugar de `openssl` | Funciona igual en Windows y Linux sin instalar `openssl`, y no sobrescribe llaves existentes. |
| Build context en la raíz del repo | Permite copiar e instalar `comun/` dentro de la imagen de cada servicio. |
| `.gitattributes` con LF | El equipo trabaja en Windows, y los scripts con CRLF fallan dentro de los contenedores Linux. |
| Puertos publicados solo en `127.0.0.1` | Sirven para probar desde la computadora sin exponer los servicios internos ni las bases a la red. |
| Versiones de `svc-ia` iguales a las del agente de AgroIA | fastapi 0.141.1, starlette 1.7.0, uvicorn 0.53.0, pydantic 2.13.5 y python-dotenv 1.2.3, las versiones con las que pasan las pruebas del agente. LangChain se agrega en la fase 3, cuando se copie el agente. |

## Verificación

Se hizo el 22 de octubre de 2026 con Docker Desktop 29.9.2 y Docker Compose v5.6.1.

| Prueba | Resultado |
| --- | --- |
| `docker compose config` | Sin errores |
| `docker compose up --build` | Los 8 contenedores en ejecución |
| Healthchecks de `postgres`, `mongo` y `redis` | Los tres en `healthy` |
| `GET /salud/` en los puertos 8000 a 8004 | Los cinco responden `{"estado":"ok"}` |
| `/api/docs/` en los puertos 8000 a 8004 | Los cinco responden 200 |
| `pytest` dentro de cada contenedor | web 4, svc-usuarios 4, svc-tienda 4, svc-contenido 4 y svc-ia 3 pruebas; todas pasan |
| `ruff check` y `ruff format --check` dentro de cada contenedor | Pasan en los cinco servicios |
| `init.sql` | Creó `usuarios_db`, `tienda_db` y `web_db`, cada una con su usuario como dueño |
| `migrate` al arrancar | Corrió en web, svc-usuarios y svc-tienda |
| Aislamiento entre bases | El usuario `tienda` no puede conectarse a `usuarios_db` ("User does not have CONNECT privilege") |
| Llaves JWT | `svc-tienda` solo recibe la llave pública; `svc-usuarios` recibe ambas |
| `git status` | No aparecen `.env`, llaves ni entornos virtuales |

## Problemas encontrados

| Problema | Solución |
| --- | --- |
| Docker no estaba instalado al empezar | Se implementó y se verificó primero lo que no depende de Docker (pytest y ruff en entornos temporales). Después se instaló Docker Desktop y se completó la verificación. |
| La terminal no encontraba `docker` después de instalarlo | La sesión se había abierto antes de la instalación. Se agregó manualmente la ruta de Docker Desktop al `PATH` de esa sesión; las terminales nuevas ya la incluyen. |
| Solo había Python 3.14 en la computadora | Las pruebas locales se corrieron con 3.14 en entornos temporales fuera del repo. Las imágenes usan 3.12 y el README indica `py -3.12 -m venv venv`. |
| starlette no estaba fijada y se instalaba la 1.9.0, que mostraba un aviso en las pruebas | Se fijó `starlette==1.7.0`, la versión del agente, y se agregó `httpx2==2.13.1`, que usa el `TestClient`, en `requirements-dev.txt` de `svc-ia`. |

## Commits y Pull Requests

**PR #1 · `docs/configuracion-claude-code` → `develop`**

| Commit | Título |
| --- | --- |
| `724c548` | docs: reglas de Claude Code y definición técnica |
| `9353c9e` | docs: renombrar documentos sin acentos ni espacios |

**PR #2 · `feat/fase-0-base-monorepo` → `develop`**

| Commit | Título |
| --- | --- |
| `e91baae` | chore(repo): configuración de git, docker, ruff y variables de entorno |
| `59136ff` | feat(infra): init de PostgreSQL y generador de llaves JWT |
| `e5eb21e` | feat(comun): paquete compartido agroia_comun |
| `847acc6` | feat(usuarios): esqueleto de svc-usuarios |
| `85a5b36` | feat(tienda): esqueleto de svc-tienda |
| `66eff90` | feat(contenido): esqueleto de svc-contenido |
| `b9b0a21` | feat(web): esqueleto del gateway |
| `10de2d4` | feat(ia): esqueleto de svc-ia |
| `9483b7a` | feat(infra): docker-compose con los servicios y las bases |
| `36222b6` | docs: guía de instalación, pruebas con Docker y definición técnica actualizada |
| `86b830d` | chore(claude): sin commits ni PR |

## Pendientes y siguiente paso

- **Siguiente:** fase 2, API de `svc-tienda`: modelos de categorías, productos, carrito y pedidos; CRUD con filtros, búsqueda y paginación; creación de pedidos que descuenta stock en una transacción.
- Los cinco servicios todavía no tienen `healthcheck` propio; solo lo tienen las bases.
- El paquete `comun` está vacío hasta la fase 4 (autenticación) y hasta que se implemente el formato común de errores.
- `svc-ia` recibe el código del agente en la fase 3.
