# AgroIA-Web

Plataforma web para el agronegocio del aguacate: tienda en línea de insumos, asistente conversacional AgroIA y diagnóstico de enfermedades por imagen.

Proyecto académico (Ingeniería en Sistemas Computacionales — TecNM Jiquilpan). Metodología Scrum, gestión en Jira. Repositorio monorepo con arquitectura de microservicios sobre Django y FastAPI.

## Estructura

| Carpeta | Descripción | Base de datos | Puerto local | Detalle |
| :-- | :-- | :-- | :-- | :-- |
| `web/` | Gateway: plantillas, sesión, enruta al resto y valida JWT. Único punto de entrada del navegador. | PostgreSQL `web_db` (sesiones) | 8000 | [README](web/README.md) |
| `svc-usuarios/` | Registro, login (JWT), recuperación de contraseña, roles, perfil y direcciones. | PostgreSQL `usuarios_db` | 8001 | [README](svc-usuarios/README.md) |
| `svc-tienda/` | Categorías, productos, stock, carrito y pedidos (pago simulado). | PostgreSQL `tienda_db` | 8002 | [README](svc-tienda/README.md) |
| `svc-contenido/` | Conversaciones con el agente, historial de diagnósticos y bitácora. | MongoDB `contenido` | 8003 | [README](svc-contenido/README.md) |
| `svc-ia/` | Agente AgroIA (FastAPI, desde el repo [AgroIA](https://github.com/BryanGEP/AgroIA)) y clasificación de imágenes: sano, roña o antracnosis. | ninguna | 8004 | [README](svc-ia/README.md) |
| `comun/` | Paquete `agroia_comun`: autenticación JWT, permisos y formato de errores para los servicios Django. | — | — | [README](comun/README.md) |
| `infra/` | `postgres/init.sql` (bases y usuarios) y `generar_llaves.py` (llaves JWT). | — | — | — |
| `docs/` | Definición técnica, requerimientos y entregables. | — | — | ver [Documentación](#documentación) |

Además corren tres contenedores de infraestructura: `postgres` (16), `mongo` (7) y `redis` (7).

## Requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) con Docker Compose.
- Python 3.12, solo para generar las llaves y para el entorno virtual del editor.

## Levantar el proyecto por primera vez

Desde la raíz del repo, en PowerShell:

```powershell
# 1. Variables de entorno: copia el ejemplo y cambia las contraseñas y la DJANGO_SECRET_KEY.
Copy-Item .env.example .env

# 2. Llaves JWT (se crean en infra/llaves/, que nunca se sube al repo).
#    Con el venv de la raíz activo (ver más abajo):
python infra/generar_llaves.py
#    O sin venv, usando Docker:
docker run --rm -v "${PWD}:/repo" -w /repo python:3.12-slim sh -c "pip install -q cryptography==50.0.2 && python infra/generar_llaves.py"

# 3. Construir y levantar todo.
docker compose up --build
```

Cuando todo esté arriba, cada servicio responde `{"estado": "ok"}` en `GET /salud/` y tiene su documentación en `/api/docs/`:

| Servicio | Salud | Documentación |
| --- | --- | --- |
| web | http://localhost:8000/salud/ | http://localhost:8000/api/docs/ |
| svc-usuarios | http://localhost:8001/salud/ | http://localhost:8001/api/docs/ |
| svc-tienda | http://localhost:8002/salud/ | http://localhost:8002/api/docs/ |
| svc-contenido | http://localhost:8003/salud/ | http://localhost:8003/api/docs/ |
| svc-ia | http://localhost:8004/salud/ | http://localhost:8004/api/docs/ |

Los puertos (también 5432, 27017 y 6379 de las bases) solo se publican en `127.0.0.1`: son para probar desde tu computadora. El navegador de los usuarios solo habla con `web`.

### Bases de datos

- `infra/postgres/init.sql` crea `usuarios_db`, `tienda_db` y `web_db`, cada una con su propio usuario, y lee las contraseñas del `.env`. **Solo corre la primera vez que se crea el volumen de PostgreSQL**: si después cambias esas contraseñas en `.env` o modificas `init.sql`, no se vuelve a ejecutar.
- Para reiniciar las bases desde cero:

  ```powershell
  docker compose down -v
  docker compose up --build
  ```

  > **Cuidado:** `down -v` borra los volúmenes, es decir, **todos los datos** de PostgreSQL y MongoDB. Sin `-v`, `docker compose down` detiene los contenedores y conserva los datos.

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
