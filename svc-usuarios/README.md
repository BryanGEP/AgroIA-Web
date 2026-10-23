# svc-usuarios

Registro, perfil, direcciones y roles de los usuarios. En la Entrega 2 es la versión básica: login, emisión de JWT, verificación de correo, recuperación y cambio de contraseña llegan en la Entrega 3.

- **Puerto local:** 8001 (dentro de Docker escucha en el 8000 y se llama `http://svc-usuarios:8000`).
- **Datos:** PostgreSQL, base `usuarios_db` con el usuario `usuarios` (creados por `infra/postgres/init.sql`).
- **Documentación de la API:** http://localhost:8001/api/docs/ (botón **Authorize** para pegar un token)
- **Admin de Django:** http://localhost:8001/admin/
- **Salud:** `GET http://localhost:8001/salud/` → `{"estado": "ok"}`

Contratos, modelo de datos y códigos de error en [`docs/definicion-tecnica.md`](../docs/definicion-tecnica.md); detalle de cada tarea de autenticación en [`docs/requerimientos-autenticacion.md`](../docs/requerimientos-autenticacion.md). Colección de Postman en [`docs/postman/`](../docs/postman/).

## ⚠️ Una vez al bajar esta rama: reiniciar `usuarios_db`

En la fase 0, svc-usuarios migró `usuarios_db` con el usuario estándar de Django. Ahora usa su propio modelo (`AUTH_USER_MODEL = "usuarios.Usuario"`), y Django no permite cambiarlo sobre una base ya migrada. **Cada integrante debe hacer este reinicio una sola vez** al bajar la rama `feat/fase-1-usuarios-basico` (o `develop` después de fusionarla). Solo vacía `usuarios_db`; `tienda_db`, `web_db` y MongoDB no se tocan.

```powershell
# 1. Detener solo svc-usuarios
docker compose stop svc-usuarios

# 2. Vaciar usuarios_db como su dueño
docker compose exec postgres psql -U usuarios -d usuarios_db -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public AUTHORIZATION pg_database_owner; GRANT USAGE ON SCHEMA public TO PUBLIC;"

# 4. Arrancar: el contenedor aplica las migraciones nuevas
docker compose up -d --build svc-usuarios
```

El paso 3 (`makemigrations`) solo lo hizo quien implementó la fase: la migración ya viene en el repo. **No uses `docker compose down -v`**: borra también los datos de la tienda y de MongoDB.

Si al arrancar ves `InconsistentMigrationHistory` o `relation "usuarios_usuario" does not exist`, es que falta este reinicio.

## Modelos

| Modelo | Campos |
| --- | --- |
| `Usuario` (`AbstractUser` sin `username`) | `email` (único, es el login), `nombre`, `apellidos`, `telefono`, `rol` (`cliente` por defecto o `administrador`), `email_verificado` (False), `token_version` (0), `acepto_privacidad_en`, `version_privacidad`, `tiene_2fa` (False), además de `is_active`, `is_staff`, `is_superuser`, `date_joined` y `last_login` de Django |
| `Direccion` | `usuario`, `alias`, `calle`, `numero`, `colonia`, `municipio`, `estado`, `codigo_postal` (5 dígitos), `referencias`, `predeterminada`, `creada_en` |

- `UsuarioManager.create_user` y `create_superuser` trabajan por correo (lo normalizan sin espacios y en minúsculas) y siempre aplican el hash a la contraseña. `create_superuser` deja `rol=administrador`.
- Una sola dirección predeterminada por usuario (`UniqueConstraint` condicional). Al marcar una, las demás se desmarcan en la misma transacción; la primera dirección queda predeterminada; si se borra la predeterminada, pasa a serlo la más reciente.
- El `id` del Usuario es el `user_id` del JWT que validan todos los servicios.

## Endpoints × rol

Todas las rutas van bajo `/api/v1/`. "Rol válido" = token con `rol` `cliente` o `administrador`.

| Método | Ruta | Público | Cliente | Admin | Sin token | Rol equivocado |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/auth/registro/` | ✓ | ✓ | ✓ | — | — |
| GET, PATCH | `/usuarios/yo/` | | ✓ | ✓ | 401 | 403 (sin rol) |
| GET, POST | `/usuarios/yo/direcciones/` | | ✓ (las propias) | ✓ (las propias) | 401 | 403 (sin rol) |
| GET, PATCH, DELETE | `/usuarios/yo/direcciones/<id>/` | | ✓ (propia) | ✓ (propia) | 401 | 403 (sin rol) |
| GET | `/usuarios/` | | 403 | ✓ | 401 | 403 |

- **Registro:** recibe `nombre`, `apellidos`, `email`, `password`, `password_confirmacion` y `acepto_privacidad` (debe ser `true`). Responde 201 con `{"id", "email", "mensaje"}`, sin tokens. La cuenta queda como `cliente`, sin verificar y con la fecha y la versión del aviso de privacidad (`VERSION_AVISO_PRIVACIDAD`). No lee tokens, para que uno vencido no impida registrarse. El correo de verificación se enviará en la Entrega 3 (está marcado en `servicios.registrar_usuario`).
- **Errores del registro:** responden 400 `validacion` con el código como mensaje del campo: `email` → `email_registrado` (aunque cambien las mayúsculas), `password_confirmacion` → `password_no_coincide`, `acepto_privacidad` → `privacidad_no_aceptada`. Los mensajes de contraseña débil vienen de los validadores de Django, en español.
- **Perfil:** solo se editan `nombre`, `apellidos` y `telefono`; `email`, `rol` y los campos de seguridad se ignoran si se envían. Si el `user_id` del token no corresponde a ningún usuario, 404.
- **Direcciones:** solo las propias, también para el administrador; las de otro usuario dan 404.
- **Listado (admin):** paginado de 20, filtros `rol` y `q` (busca en correo, nombre y apellidos). Pide token aunque `AUTH_ACTIVA` sea `False`, porque son datos personales. El cambio de rol por API (`PATCH /usuarios/<id>/rol/`) llega en la Entrega 3.

## Probar con un usuario real

Mientras no hay login (Entrega 3), el token se genera con `infra/emitir_token.py` usando el **id real** que devuelve el registro:

```powershell
# 1. Registrar (o desde /api/docs/ o Postman)
curl.exe -s -X POST http://127.0.0.1:8001/api/v1/auth/registro/ -H "Content-Type: application/json" `
  -d '{\"nombre\":\"Maria\",\"email\":\"maria@example.com\",\"password\":\"Aguacate-Hass-2026\",\"password_confirmacion\":\"Aguacate-Hass-2026\",\"acepto_privacidad\":true}'
# → {"id": 1, "email": "maria@example.com", "mensaje": "..."}

# 2. Token para ese id (desde la raíz, con el venv activo)
python infra/emitir_token.py --usuario-id 1 --rol cliente

# 3. Usarlo en Authorize de /api/docs/ o como Authorization: Bearer <token>
```

`curl.exe` en Windows maltrata los acentos al enviarlos; para nombres con acentos usa `/api/docs/` o Postman.

## Administradores

No hay registro de administradores por la API. Hay dos formas:

```powershell
# A) Promover a un usuario que ya se registró
docker compose exec svc-usuarios python manage.py asignar_admin maria@example.com

# B) Crear uno desde cero (pide correo, nombre y contraseña; también entra al admin de Django)
docker compose exec svc-usuarios python manage.py createsuperuser
```

`asignar_admin` falla con un mensaje claro si el correo no existe. Los permisos leen el rol **del token**, no de la base: después de promover a alguien, genera un token nuevo con `--rol administrador`. En la Entrega 3 el login tomará el rol de la base.

## Autenticación

Usa la autenticación, los permisos y el formato de errores de [`comun`](../comun/README.md), igual que svc-tienda: valida el JWT RS256 con la llave pública. En la Entrega 3 este servicio también firmará los tokens con la llave privada (`JWT_PRIVATE_KEY_PATH`, que ya recibe). Con `AUTH_ACTIVA=False` (solo con `DJANGO_DEBUG=True`) se apaga la revisión de roles, pero perfil, direcciones y listado siguen pidiendo token.

## Variables de entorno

| Variable | Uso |
| --- | --- |
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | Django |
| `AUTH_ACTIVA` | Revisión de roles (`True` por defecto) |
| `JWT_PUBLIC_KEY_PATH` | Llave pública para validar los JWT |
| `JWT_PRIVATE_KEY_PATH` | Llave privada para firmar los JWT (Entrega 3; solo este servicio la recibe) |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Servidor de PostgreSQL (`postgres`, `5432`) |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | `usuarios_db`, `usuarios` y la contraseña de `.env`; docker-compose.yml los asigna |
| `VERSION_AVISO_PRIVACIDAD` | Versión vigente del aviso de privacidad (`2026-10`) |
| `REDIS_URL` | Redis para límites de intentos (Entrega 3) |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL`, `FRONTEND_URL` | Envío de correos (Entrega 3) |

## Pruebas y estilo

```bash
docker compose exec svc-usuarios pytest
docker compose exec svc-usuarios ruff check .
docker compose exec svc-usuarios ruff format --check .
```

Las pruebas usan PostgreSQL (pytest-django crea `test_usuarios_db`), siempre con `AUTH_ACTIVA=True` y un par de llaves generado al vuelo. Las fixtures crean usuarios con ids fijos y firman tokens para esos ids (`conftest.py`, `tests/tokens.py`).
