# svc-usuarios

Registro, login, JWT, recuperación de contraseña, roles, perfil y direcciones.

- **Puerto local:** 8001 (dentro de Docker escucha en el 8000 y se llama `http://svc-usuarios:8000`).
- **Datos:** PostgreSQL, base `usuarios_db` con el usuario `usuarios` (creados por `infra/postgres/init.sql`).
- **Documentación de la API:** http://localhost:8001/api/docs/
- **Salud:** `GET http://localhost:8001/salud/` → `{"estado": "ok"}`

Contratos y modelo de datos en [`docs/definicion-tecnica.md`](../docs/definicion-tecnica.md).

## Variables de entorno

Salen del `.env` de la raíz (ver [`.env.example`](../.env.example)); `docker-compose.yml` le pasa a este servicio solo las suyas.

| Variable | Uso |
| --- | --- |
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | Django |
| `AUTH_ACTIVA` | Activa JWT y roles (`True` por defecto) |
| `JWT_PUBLIC_KEY_PATH` | Llave pública para validar los JWT |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Servidor de PostgreSQL (`postgres`, `5432`) |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | `usuarios_db`, `usuarios` y la contraseña de `.env`; docker-compose.yml los asigna |
| `JWT_PRIVATE_KEY_PATH` | Llave privada para firmar los JWT (solo este servicio la recibe) |
| `REDIS_URL` | Redis para límites de intentos (fase 4) |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL`, `FRONTEND_URL` | Envío de correos (fase 1) |

## Pruebas y estilo

La forma oficial es dentro del contenedor:

```bash
docker compose exec svc-usuarios pytest
docker compose exec svc-usuarios ruff check .
docker compose exec svc-usuarios ruff format --check .
```

También se pueden correr en el venv de la raíz (ver el [README](../README.md)): `cd svc-usuarios` y `pytest`. Las pruebas usan `config/settings_pruebas.py`, que completa las variables que falten.

## Endpoints

| Método | Ruta | Acceso |
| --- | --- | --- |
| GET | `/salud/` | público |
| GET | `/api/docs/`, `/api/schema/` | público |
