# svc-contenido

Conversaciones con el agente, historial de diagnósticos y bitácora de actividad.

- **Puerto local:** 8003 (dentro de Docker escucha en el 8000 y se llama `http://svc-contenido:8000`).
- **Datos:** MongoDB, base `contenido` (pymongo). No usa base relacional.
- **Documentación de la API:** http://localhost:8003/api/docs/
- **Salud:** `GET http://localhost:8003/salud/` → `{"estado": "ok"}`

Contratos y modelo de datos en [`docs/definicion-tecnica.md`](../docs/definicion-tecnica.md).

## Variables de entorno

Salen del `.env` de la raíz (ver [`.env.example`](../.env.example)); `docker-compose.yml` le pasa a este servicio solo las suyas.

| Variable | Uso |
| --- | --- |
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | Django |
| `AUTH_ACTIVA` | Activa JWT y roles (`True` por defecto) |
| `JWT_PUBLIC_KEY_PATH` | Llave pública para validar los JWT |
| `MONGO_URL` | Conexión a MongoDB, con la base al final (`mongodb://mongo:27017/contenido`) |

## MongoDB y Django

Este servicio no tiene base relacional: `DATABASES = {}` activa el backend *dummy* de Django.

- Cualquier uso del ORM falla con un error claro; los datos se leen y escriben con pymongo a través de `config/mongo.py` (`obtener_base()`).
- No hay admin de Django ni sesiones, y al arrancar no se corre `migrate`.
- `django.contrib.auth` y `contenttypes` siguen instaladas solo para que DRF (y en la fase 4 el usuario del token) puedan importarse; no crean tablas.
- En pruebas, MongoDB se simula con `mongomock`; no se marca ninguna prueba con `django_db`.

## Pruebas y estilo

La forma oficial es dentro del contenedor:

```bash
docker compose exec svc-contenido pytest
docker compose exec svc-contenido ruff check .
docker compose exec svc-contenido ruff format --check .
```

También se pueden correr en el venv de la raíz (ver el [README](../README.md)): `cd svc-contenido` y `pytest`. Las pruebas usan `config/settings_pruebas.py`, que completa las variables que falten.

## Endpoints

| Método | Ruta | Acceso |
| --- | --- | --- |
| GET | `/salud/` | público |
| GET | `/api/docs/`, `/api/schema/` | público |
