# AgroIA-Web

Plataforma web para el agronegocio del aguacate: tienda en línea de insumos, asistente conversacional AgroIA y diagnóstico de enfermedades por imagen.

Proyecto académico (Ingeniería en Sistemas Computacionales — TecNM Jiquilpan). Metodología Scrum, gestión en Jira. Repositorio monorepo con arquitectura de microservicios sobre Django y FastAPI.

## Estructura

| Carpeta | Descripción | Base de datos | Puerto local | Detalle |
| :-- | :-- | :-- | :-- | :-- |
| `web/` | Gateway: plantillas, sesión, enruta al resto y valida JWT. Único punto de entrada del navegador. | PostgreSQL `web_db` (sesiones) | 8000 | [README](web/README.md) |
| `svc-usuarios/` | Registro, perfil, direcciones y roles (Entrega 2); login, JWT y recuperación de contraseña en la Entrega 3. | PostgreSQL `usuarios_db` | 8001 | [README](svc-usuarios/README.md) |
| `svc-tienda/` | Categorías, productos, stock, carrito y pedidos (pago simulado). | PostgreSQL `tienda_db` | 8002 | [README](svc-tienda/README.md) |
| `svc-contenido/` | Conversaciones con el agente, historial de diagnósticos y bitácora. | MongoDB `contenido` | 8003 | [README](svc-contenido/README.md) |
| `svc-ia/` | Adaptador en FastAPI: traduce las preguntas al contenedor `agente` y clasifica imágenes (sano, roña o antracnosis; el modelo llega en una entrega posterior). | ninguna | 8004 | [README](svc-ia/README.md) |
| `comun/` | Paquete `agroia_comun`: autenticación JWT, permisos y formato de errores para los servicios Django. | — | — | [README](comun/README.md) |
| `infra/` | `postgres/init.sql` (bases y usuarios) y `generar_llaves.py` (llaves JWT). | — | — | — |
| `docs/` | Definición técnica, requerimientos y entregables. | — | — | ver [Documentación](#documentación) |

Además corren tres contenedores de infraestructura, `postgres` (16), `mongo` (7) y `redis` (7), y el contenedor **`agente`**: el agente conversacional del repo [BryanGEP/AgroIA](https://github.com/BryanGEP/AgroIA), que Docker Compose construye directamente desde GitHub (carpeta `svc-agente`, rama `main`). Solo está en la red interna; se publica en `127.0.0.1:8005` para pruebas.

## Requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) con Docker Compose.
- Python 3.12, solo para generar las llaves y para el entorno virtual del editor.
- Una llave de API de Groq **propia** (gratuita) para que el agente responda. Ver [Llave de Groq](#llave-de-groq).

## Levantar el proyecto por primera vez

Desde la raíz del repo, en PowerShell:

```powershell
# 1. Variables de entorno: copia el ejemplo y cambia las contraseñas y la DJANGO_SECRET_KEY.
#    Pon tu propia GROQ_API_KEY (ver "Llave de Groq").
Copy-Item .env.example .env

# 2. Llaves JWT (se crean en infra/llaves/, que nunca se sube al repo).
#    Con el venv de la raíz activo (ver más abajo):
python infra/generar_llaves.py
#    O sin venv, usando Docker:
docker run --rm -v "${PWD}:/repo" -w /repo python:3.12-slim sh -c "pip install -q cryptography==50.0.2 && python infra/generar_llaves.py"

# 3. Construir y levantar todo (la primera vez descarga el agente desde GitHub).
docker compose up --build
```

### Llave de Groq

El agente usa el LLM de [Groq](https://groq.com/). **Cada integrante necesita su propia llave gratuita**; no se comparten ni se suben al repo:

1. Entra a https://console.groq.com/keys e inicia sesión.
2. Crea una llave ("Create API Key") y cópiala.
3. Pégala en tu `.env`: `GROQ_API_KEY=gsk_...`
4. Reinicia el agente: `docker compose up -d agente`.

La llave solo llega al contenedor `agente`, no a svc-ia. Sin llave el sistema arranca igual, pero `POST /agente/preguntar/` responde 503 `agente_no_disponible`. Para traer la versión más reciente del agente desde GitHub: `docker compose build --no-cache agente`.

Cuando todo esté arriba, cada servicio responde `{"estado": "ok"}` en `GET /salud/` y tiene su documentación en `/api/docs/`:

| Servicio | Salud | Documentación |
| --- | --- | --- |
| web | http://localhost:8000/salud/ | http://localhost:8000/api/docs/ |
| svc-usuarios | http://localhost:8001/salud/ | http://localhost:8001/api/docs/ |
| svc-tienda | http://localhost:8002/salud/ | http://localhost:8002/api/docs/ |
| svc-contenido | http://localhost:8003/salud/ | http://localhost:8003/api/docs/ |
| svc-ia | http://localhost:8004/salud/ | http://localhost:8004/api/docs/ |
| agente (solo pruebas) | http://localhost:8005/health | — (chat propio en http://localhost:8005/) |

Los puertos (también 5432, 27017 y 6379 de las bases) solo se publican en `127.0.0.1`: son para probar desde tu computadora. El navegador de los usuarios solo habla con `web`.

### Bases de datos

- `infra/postgres/init.sql` crea `usuarios_db`, `tienda_db` y `web_db`, cada una con su propio usuario, y lee las contraseñas del `.env`. **Solo corre la primera vez que se crea el volumen de PostgreSQL**: si después cambias esas contraseñas en `.env` o modificas `init.sql`, no se vuelve a ejecutar.
- Para reiniciar las bases desde cero:

  ```powershell
  docker compose down -v
  docker compose up --build
  ```

  > **Cuidado:** `down -v` borra los volúmenes, es decir, **todos los datos** de PostgreSQL y MongoDB. Sin `-v`, `docker compose down` detiene los contenedores y conserva los datos.

### Tokens de desarrollo

Mientras svc-usuarios no emite tokens (Entrega 3), los endpoints protegidos se prueban con tokens firmados por `infra/emitir_token.py`. **Es solo para desarrollo y pruebas**: firma con la llave privada local y los mismos claims que emitirá svc-usuarios.

Para probar con un usuario real, regístralo con `POST http://localhost:8001/api/v1/auth/registro/` y usa el `id` que devuelve como `--usuario-id` (ver el [README de svc-usuarios](svc-usuarios/README.md#probar-con-un-usuario-real)). Los servicios que no consultan a svc-usuarios (tienda, contenido, IA) aceptan cualquier id.

> **Al bajar la fase 1 de usuarios**, cada integrante debe reiniciar una vez `usuarios_db` (ver el [README de svc-usuarios](svc-usuarios/README.md)), sin `docker compose down -v`.

```powershell
python infra/emitir_token.py --usuario-id 10 --rol cliente
python infra/emitir_token.py --usuario-id 1 --rol administrador --minutos 480
python infra/emitir_token.py --usuario-id 12 --rol cliente --sin-verificar
```

Pega el token en el botón **Authorize** de `/api/docs/` o en las variables `token`, `token_admin` y `token_sin_verificar` del entorno de Postman (`docs/postman/`).

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

## Entregas

- **Entrega 1:** fundamentos y planeación del proyecto (equipo y roles Scrum, definición del proyecto, arquitectura, configuración de Jira y estándares de trabajo).
  - [Documento del Entregable 1](docs/Entregable1_AgroIAWeb.docx)

## Cómo contribuir

El equipo trabaja con ramas por tarea que se integran en `develop` mediante Pull Requests; `main` está protegida y solo contiene versiones estables.

Antes de hacer cualquier cambio, lee la [guía de contribución](CONTRIBUTING.md). Al abrir un Pull Request se carga automáticamente la [plantilla de PR](.github/pull_request_template.md).

## Equipo

- Isis Lizbeth Vázquez Avalos
- Danna Geraldine Ávila García
- Bryan Gael Esquivel Pérez
