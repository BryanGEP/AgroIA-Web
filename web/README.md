# web

Gateway: plantillas, sesión del usuario, enrutamiento a los servicios internos y validación del JWT.

- **Puerto local:** 8000 (dentro de Docker escucha en el 8000 y se llama `http://web:8000`).
- **Datos:** PostgreSQL, base `web_db` con el usuario `web` (creados por `infra/postgres/init.sql`).
- **Documentación de la API:** http://localhost:8000/api/docs/
- **Salud:** `GET http://localhost:8000/salud/` → `{"estado": "ok"}`

Contratos y modelo de datos en [`docs/definicion-tecnica.md`](../docs/definicion-tecnica.md).

## Variables de entorno

Salen del `.env` de la raíz (ver [`.env.example`](../.env.example)); `docker-compose.yml` le pasa a este servicio solo las suyas.

| Variable | Uso |
| --- | --- |
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | Django |
| `AUTH_ACTIVA` | Activa JWT y roles (`True` por defecto) |
| `JWT_PUBLIC_KEY_PATH` | Llave pública para validar los JWT |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Servidor de PostgreSQL (`postgres`, `5432`) |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | `web_db`, `web` y la contraseña de `.env`; docker-compose.yml los asigna |
| `URL_SVC_USUARIOS`, `URL_SVC_TIENDA`, `URL_SVC_CONTENIDO`, `URL_SVC_IA` | Direcciones internas de los servicios |
| `REDIS_URL` | Redis (caché y throttling) |

## Pruebas y estilo

La forma oficial es dentro del contenedor:

```bash
docker compose exec web pytest
docker compose exec web ruff check .
docker compose exec web ruff format --check .
```

También se pueden correr en el venv de la raíz (ver el [README](../README.md)): `cd web` y `pytest`. Las pruebas usan `config/settings_pruebas.py`, que completa las variables que falten.

## Endpoints

| Método | Ruta | Acceso |
| --- | --- | --- |
| GET | `/salud/` | público |
| GET | `/api/docs/`, `/api/schema/` | público |
