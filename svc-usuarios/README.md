# svc-usuarios

Identidad de AgroIA-Web: registro, inicio de sesión con JWT, renovación y cierre de sesión, verificación de correo, recuperación y cambio de contraseña, roles, perfil y direcciones. Es el único servicio que firma tokens.

- **Puerto local:** 8001 (dentro de Docker escucha en el 8000 y se llama `http://svc-usuarios:8000`).
- **Datos:** PostgreSQL, base `usuarios_db` con el usuario `usuarios` (creados por `infra/postgres/init.sql`). Redis guarda los contadores del límite de intentos.
- **Documentación de la API:** http://localhost:8001/api/docs/ (botón **Authorize** para pegar el `access` del login)
- **Admin de Django:** http://localhost:8001/admin/ (intentos fallidos, bloqueos y cambios de rol)
- **Salud:** `GET http://localhost:8001/salud/` → `{"estado": "ok"}`

El contrato de los tokens (algoritmo, emisor, claims, duración y cómo valida cada servicio) está en [`docs/contrato-identidad.md`](../docs/contrato-identidad.md). Contratos y modelo de datos en [`docs/definicion-tecnica.md`](../docs/definicion-tecnica.md); detalle de cada tarea de autenticación en [`docs/requerimientos-autenticacion.md`](../docs/requerimientos-autenticacion.md). Colección de Postman en [`docs/postman/`](../docs/postman/).

## Al bajar la rama de la Entrega 3 (`feat/e3-identidad`): reiniciar los datos de prueba

En la Entrega 3 el `id` del usuario pasó de entero a UUID (para ser compatible con [ms-usuarios](../docs/contrato-identidad.md#diferencias-con-ms-usuarios)) y la migración `0001` de svc-usuarios se reescribió. Las bases solo tenían datos de prueba, así que cada integrante hace este reinicio **una sola vez**. No toca el catálogo de la tienda, la base de conocimiento del agente (`agente-db`) ni el modelo descargado (`modelos_hf`).

```powershell
# 1. Detener svc-usuarios y vaciar usuarios_db como su dueño
docker compose stop svc-usuarios
docker compose exec postgres psql -U usuarios -d usuarios_db -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public AUTHORIZATION pg_database_owner; GRANT USAGE ON SCHEMA public TO PUBLIC;"

# 2. Vaciar conversaciones, diagnósticos y bitácora (guardaban ids enteros)
docker compose exec mongo mongosh contenido --quiet --eval "for (const c of ['conversaciones','diagnosticos','bitacora']) print(c, db.getCollection(c).deleteMany({}).deletedCount)"

# 3. Reconstruir y arrancar: svc-usuarios aplica su 0001 nueva y svc-tienda sus migraciones
#    0002 y 0003, que borran carritos y pedidos de prueba y pasan usuario_id a UUID.
docker compose up -d --build

# 4. Cuentas de demostración para Postman (solo desarrollo)
docker compose exec svc-usuarios python manage.py cargar_usuarios_demo
```

**No uses `docker compose down -v`**: borra también el catálogo, la base de conocimiento del agente y el modelo de 471 MB. Si al arrancar ves `InconsistentMigrationHistory` o `relation "usuarios_usuario" does not exist`, falta el paso 1.

## Modelos

| Modelo | Campos |
| --- | --- |
| `Usuario` (`AbstractUser` sin `username`) | `id` (UUID), `email` (único, es el login), `nombre`, `apellidos`, `telefono`, `rol` (`cliente` por defecto o `administrador`), `email_verificado` (False), `token_version` (0), `acepto_privacidad_en`, `version_privacidad`, `tiene_2fa` (False), además de `is_active`, `is_staff`, `is_superuser`, `date_joined` y `last_login` de Django |
| `Direccion` | `usuario`, `alias`, `calle`, `numero`, `colonia`, `municipio`, `estado`, `codigo_postal` (5 dígitos), `referencias`, `predeterminada`, `creada_en` |
| `CambioRol` | `usuario`, `rol_anterior`, `rol_nuevo`, `cambiado_por` (el administrador), `cambiado_en` |

- `UsuarioManager.create_user` y `create_superuser` trabajan por correo (lo normalizan sin espacios y en minúsculas) y siempre aplican el hash a la contraseña. `create_superuser` deja `rol=administrador`.
- Una sola dirección predeterminada por usuario (`UniqueConstraint` condicional). Al marcar una, las demás se desmarcan en la misma transacción; la primera dirección queda predeterminada; si se borra la predeterminada, pasa a serlo la más reciente.
- El `id` del Usuario es el `user_id` del JWT y el `usuario_id` que guardan svc-tienda y svc-contenido.
- `token_version` se sube al cerrar todas las sesiones, al restablecer y al cambiar la contraseña: ningún refresh emitido antes vuelve a renovar.
- Además, `rest_framework_simplejwt.token_blacklist` guarda los refresh emitidos y los que están en la blacklist, y `django-axes` guarda los intentos fallidos (`AccessAttempt`) y los accesos (`AccessLog`).

## Endpoints × rol

Todas las rutas van bajo `/api/v1/`. "Rol válido" = token con `rol` `cliente` o `administrador`. Los públicos no leen tokens, para que uno vencido no estorbe.

| Método | Ruta | Público | Cliente | Admin | Sin token | Rol equivocado | Límite |
| --- | --- | --- | --- | --- | --- | --- | --- |
| POST | `/auth/registro/` | ✓ | ✓ | ✓ | — | — | 5/hora por IP |
| POST | `/auth/login/` | ✓ | ✓ | ✓ | — | — | 10/min por IP; bloqueo por correo + IP |
| POST | `/auth/token/renovar/` | ✓ | ✓ | ✓ | — | — | |
| POST | `/auth/verificar-correo/` | ✓ | ✓ | ✓ | — | — | |
| POST | `/auth/reenviar-verificacion/` | ✓ | ✓ | ✓ | — | — | 3/hora por IP y 3/hora por correo |
| POST | `/auth/recuperar/` | ✓ | ✓ | ✓ | — | — | 3/hora por IP y 3/hora por correo |
| POST | `/auth/restablecer/` | ✓ | ✓ | ✓ | — | — | |
| POST | `/auth/logout/`, `/auth/logout-todo/` | | ✓ | ✓ | 401 | — | |
| POST | `/auth/cambiar-password/` | | ✓ | ✓ | 401 | — | 5/hora por usuario |
| GET, PATCH | `/usuarios/yo/` | | ✓ | ✓ | 401 | 403 (sin rol) | |
| GET, POST | `/usuarios/yo/direcciones/` | | ✓ (las propias) | ✓ (las propias) | 401 | 403 (sin rol) | |
| GET, PATCH, DELETE | `/usuarios/yo/direcciones/<id>/` | | ✓ (propia) | ✓ (propia) | 401 | 403 (sin rol) | |
| GET | `/usuarios/` | | 403 | ✓ | 401 | 403 | |
| PATCH | `/usuarios/<id>/rol/` | | 403 | ✓ | 401 | 403 | |

Al rebasar un límite: 429 `demasiados_intentos` con el encabezado `Retry-After`.

### Registro, login y sesión

- **Registro:** recibe `nombre`, `apellidos`, `email`, `password`, `password_confirmacion` y `acepto_privacidad` (debe ser `true`). Responde 201 con `{"id", "email", "mensaje"}`, sin tokens, y envía el correo de verificación con `transaction.on_commit`. Errores en `validacion`: `email_registrado`, `password_no_coincide`, `privacidad_no_aceptada` y los mensajes de contraseña de Django, en español.
- **Login:** `{"email", "password"}` → `{"access", "refresh", "usuario": {"id", "nombre", "rol", "email_verificado"}}`. Access de 15 minutos y refresh de 7 días, RS256. Correo inexistente, contraseña incorrecta y cuenta desactivada responden igual: 401 `credenciales_invalidas`, «Correo o contraseña incorrectos.». Si la cuenta tiene `tiene_2fa`, responde 501 `2fa_no_disponible` (el `if` de la sección 12 queda listo; todavía no hay forma de activar 2FA).
- **Renovación:** `{"refresh"}` → `{"access", "refresh"}`. El anterior entra a la blacklist (rotación); hay que reemplazar ambos. Revisa en la base `is_active` y `token_version`, y recalcula los claims: un cambio de rol o la verificación del correo aparecen aquí. Si falla, 401 `refresh_invalido`.
- **Logout:** `{"refresh"}` con el access → 205. Mete el refresh a la blacklist; si ya estaba o venció, también 205. Un refresh de otro usuario da 403. **Logout de todos los dispositivos:** `POST /auth/logout-todo/` sube `token_version`.
- **Límite conocido:** un access ya emitido sigue sirviendo hasta que vence (máximo 15 minutos) aunque se cierre la sesión, porque los demás servicios no consultan la base. Ver [`docs/contrato-identidad.md`](../docs/contrato-identidad.md#límites-conocidos).

### Correo y contraseña

- **Verificación:** el correo trae `{FRONTEND_URL}/verificar-correo/?token=...` (firmado con `TimestampSigner`, vence en 24 horas). La pantalla `/verificar-correo/` del gateway manda ese `token` a `POST /auth/verificar-correo/`: 400 `token_invalido` si se alteró, 400 `token_expirado` si venció, 200 «Tu correo ya estaba verificado.» si ya lo estaba. Sin verificar se puede iniciar sesión, pero comprar en svc-tienda responde 403 `email_no_verificado`.
- **Reenvío y recuperación:** siempre 200 con un mensaje genérico, exista o no la cuenta.
- **Restablecer:** el correo trae `{FRONTEND_URL}/restablecer/<uid>/<token>/` (de un solo uso, vence en 1 hora). `POST /auth/restablecer/` con `{"uid", "token", "password", "password_confirmacion"}`: cierra todas las sesiones, marca el correo como verificado y envía el aviso «Tu contraseña fue cambiada». Enlace inválido, usado o vencido: 400 `enlace_invalido`.
- **Cambiar contraseña:** `{"password_actual", "password_nueva", "password_confirmacion"}`. Errores: `password_actual_incorrecta`, `password_repetida` o `validacion`. Cierra las demás sesiones y devuelve un par nuevo para este dispositivo, más el aviso por correo.
- Los enlaces abren las pantallas del gateway (`/verificar-correo/` y `/restablecer/<uid>/<token>/`). En desarrollo, el correo se imprime en `docker compose logs svc-usuarios` y el enlace se copia de ahí.

### Roles

- **Listado (admin):** paginado de 20, filtros `rol` y `q` (busca en correo, nombre y apellidos).
- **Cambiar rol (admin):** `PATCH /usuarios/<id>/rol/` con `{"rol"}`. Cada cambio queda en `CambioRol` (admin de Django, «Cambios de rol»). Un administrador no puede quitarse su propio rol: 409 `auto_degradacion`. El rol nuevo llega al token del usuario en su siguiente renovación o login.

## Correos

Todos salen de `apps/usuarios/correos.py`, con versión `.txt` y `.html` en `apps/usuarios/templates/emails/` (verificación, recuperación y contraseña cambiada). En desarrollo `EMAIL_BACKEND` es el de consola: el correo completo, con su enlace, se ve en

```powershell
docker compose logs -f svc-usuarios
```

Ese log de consola sí muestra los enlaces con su token: es solo para desarrollo. Para la demo con correos reales se configuran las variables `EMAIL_*` en `.env` (por ejemplo, una cuenta de Gmail con contraseña de aplicación) y se prueba con `python manage.py sendtestemail tu@correo.com`. Si el envío falla, se registra el error (sin el contenido) y la petición sigue.

## Bloqueo por intentos

`django-axes` cuenta los intentos fallidos por la combinación **correo + IP**: al quinto, esa combinación queda bloqueada 15 minutos (403 `cuenta_bloqueada_temporalmente`), aun con la contraseña correcta. Desde otra IP el dueño de la cuenta sigue entrando. Un login correcto reinicia el contador. Para desbloquear a mano:

```powershell
docker compose exec svc-usuarios python manage.py axes_reset_username <correo>
```

La IP sale del último valor de `X-Forwarded-For` (lo pondrá el gateway) o de la conexión; por eso el puerto 8001 solo se publica en `127.0.0.1`.

## Log de seguridad

Cada evento sale en una línea JSON del logger `seguridad` (en `docker compose logs svc-usuarios`): `login_exitoso`, `login_fallido`, `cuenta_bloqueada`, `renovacion_rechazada`, `logout`, `logout_todo`, `verificacion_reenviada`, `recuperacion_solicitada`, `password_restablecida`, `restablecimiento_rechazado`, `password_cambiada`, `cambio_password_rechazado`, `rol_cambiado` y `acceso_denegado` (los 401 y 403). Lleva fecha, IP, método, ruta, `usuario_id` y datos como el correo; nunca contraseñas ni tokens.

## Administradores y cuentas de demostración

No hay registro de administradores por la API:

```powershell
# A) Promover a un usuario que ya se registró (o con PATCH /usuarios/<id>/rol/)
docker compose exec svc-usuarios python manage.py asignar_admin maria@example.com

# B) Crear uno desde cero (también entra al admin de Django)
docker compose exec svc-usuarios python manage.py createsuperuser
```

`cargar_usuarios_demo` crea `cliente@demo.agroia.test` (verificado), `sin-verificar@demo.agroia.test` y `admin@demo.agroia.test`, las tres con la contraseña `solo-demo-no-usar-en-produccion`, que está en el entorno de Postman a propósito. **Estas cuentas no deben existir fuera de desarrollo:** el comando se niega a correr con `DJANGO_DEBUG=False`.

Para las pruebas de seguridad hay dos comandos más, también solo con `DJANGO_DEBUG=True`: `reiniciar_limites` vacía los contadores de intentos de Redis y los bloqueos de axes, y `limpiar_datos_prueba` borra los usuarios que registran las pruebas (`<palabra>.<timestamp>@example.com`); con `--listar-ids` solo imprime los ids de las cuentas demo y de prueba para svc-tienda y svc-contenido. Ver [Correr las pruebas de seguridad](../README.md#correr-las-pruebas-de-seguridad).

## Mantenimiento

Los refresh emitidos y los que están en la blacklist se acumulan en la base. Una vez por semana (o antes de una demo):

```powershell
docker compose exec svc-usuarios python manage.py flushexpiredtokens
```

## Variables de entorno

| Variable | Uso |
| --- | --- |
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | Django |
| `AUTH_ACTIVA` | Revisión de roles (`True` por defecto) |
| `JWT_PRIVATE_KEY_PATH` | Llave privada para firmar los JWT; solo este servicio la recibe. Sin ella no arranca |
| `JWT_PUBLIC_KEY_PATH` | Llave pública para validar los JWT |
| `JWT_ISSUER` | Emisor de los tokens (`agroia-usuarios` por defecto) |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Servidor de PostgreSQL (`postgres`, `5432`) |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | `usuarios_db`, `usuarios` y la contraseña de `.env`; docker-compose.yml los asigna |
| `REDIS_URL` | Caché de los contadores del límite de intentos |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | Envío de correos (consola por defecto) |
| `FRONTEND_URL` | Base de los enlaces de los correos (el gateway) |
| `VERSION_AVISO_PRIVACIDAD` | Versión vigente del aviso de privacidad (`2026-10`) |

## Pruebas y estilo

```bash
docker compose exec svc-usuarios pytest
docker compose exec svc-usuarios ruff check .
docker compose exec svc-usuarios ruff format --check .
```

Las pruebas usan PostgreSQL (pytest-django crea `test_usuarios_db`), siempre con `AUTH_ACTIVA=True`, un par de llaves generado al vuelo y la caché en memoria (se vacía antes de cada prueba). Los correos quedan en `mail.outbox`, los vencimientos se simulan con `freezegun` y axes queda activo: sus intentos viven en la base y se revierten con cada prueba. Las fixtures crean usuarios con UUID fijos y firman tokens para esos ids (`conftest.py`, `tests/tokens.py`).
