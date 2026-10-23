# Fase 1 · Usuarios (versión básica)

**Fecha:** 22 de octubre de 2026 · **Entregable:** Entrega 2 · **Responsable:** Bryan Gael Esquivel Pérez

## Resumen

Se construyó la versión básica de `svc-usuarios` para la Entrega 2: modelo de usuario propio identificado por correo, registro con aceptación del aviso de privacidad, perfil, direcciones con una sola predeterminada, listado para el administrador y un comando para asignar administradores. El `id` del usuario es el `user_id` de los tokens que validan todos los servicios; mientras no hay login (Entrega 3), los tokens se generan con `infra/emitir_token.py` usando el id real del registro. Se verificó dentro de Docker el mismo día: 71 pruebas en svc-usuarios, sin regresiones en los demás servicios.

## Qué se construyó

### Modelos (`usuarios_db`)

| Modelo | Detalle |
| --- | --- |
| `Usuario` | `AbstractUser` sin `username`, `first_name` ni `last_name`. `email` único como `USERNAME_FIELD`; `nombre`, `apellidos`, `telefono` (10 a 15 dígitos), `rol` (`cliente` por defecto o `administrador`), `email_verificado` (False), `token_version` (0), `acepto_privacidad_en`, `version_privacidad` y `tiene_2fa` (False). `AUTH_USER_MODEL = "usuarios.Usuario"`. |
| `UsuarioManager` | `create_user` y `create_superuser` por correo: normalizan el correo (sin espacios, minúsculas) y aplican el hash a la contraseña. `create_superuser` deja `rol=administrador`, `is_staff`, `is_superuser` y el correo verificado. |
| `Direccion` | `usuario`, `alias`, `calle`, `numero`, `colonia`, `municipio`, `estado`, `codigo_postal` (5 dígitos), `referencias`, `predeterminada` y `creada_en`. `UniqueConstraint` condicional: una sola predeterminada por usuario. |

Los dos modelos están en el admin de Django, adaptado a usuarios sin `username`.

### Endpoints (`/api/v1/`)

| Método | Ruta | Acceso |
| --- | --- | --- |
| POST | `/auth/registro/` | público |
| GET, PATCH | `/usuarios/yo/` | autenticado |
| GET, POST, PATCH, DELETE | `/usuarios/yo/direcciones/` y `/usuarios/yo/direcciones/<id>/` | autenticado, solo las propias |
| GET | `/usuarios/` | administrador |

- **Registro:** pasos 1 a 5 de la sección 1 del documento de autenticación.
  - Normaliza el correo y rechaza los duplicados aunque cambien las mayúsculas.
  - Aplica los cuatro validadores de contraseña de Django (mínimo 8 caracteres, parecida al correo o al nombre, común, solo números), con mensajes en español.
  - Crea la cuenta con `create_user` y guarda la fecha y la versión del aviso de privacidad, todo en una transacción.
  - Responde 201 con `{"id", "email", "mensaje"}` y sin tokens.
  - El envío del correo de verificación quedó marcado con un comentario para la Entrega 3.
- **Perfil:** solo se editan `nombre`, `apellidos` y `telefono`. El usuario se busca por el `user_id` del token; si no existe, 404.
- **Direcciones:**
  - La primera queda como predeterminada.
  - Marcar otra desmarca las demás en la misma transacción, bloqueando al usuario.
  - Si se borra la predeterminada, pasa a serlo la más reciente.
  - Las direcciones de otro usuario dan 404, también para el administrador.
- **Listado del administrador:** paginado de 20, con filtros `rol` y `q` (correo, nombre y apellidos).

### Comando `asignar_admin <email>`

Promueve a administrador a un usuario existente; si el correo no existe, falla con un mensaje que indica registrarlo o usar `createsuperuser`. No hay registro de administradores por la API.

### Documentación

- Swagger con descripción y ejemplos en cada endpoint y esquema Bearer.
- Carpeta `svc-usuarios` en Postman (14 peticiones) con el flujo registrar → generar token con el id real (comando en la descripción y en la consola) → ver perfil → crear dirección, y las variables `base_usuarios`, `token_usuario`, `usuario_id` y `direccion_id`.
- README de svc-usuarios con el reinicio de `usuarios_db`, la matriz de endpoints × rol, cómo probar con un usuario real y las dos formas de crear administradores. README raíz y definición técnica actualizados: contratos de la Entrega 2 y la 3, códigos del registro, modelo y variable `VERSION_AVISO_PRIVACIDAD`.

## Reinicio de `usuarios_db`

En la fase 0, `usuarios_db` se migró con el usuario estándar de Django, y Django no permite cambiar `AUTH_USER_MODEL` sobre una base ya migrada. Como la base estaba vacía, se reinició **solo ella**, sin `docker compose down -v` (que habría borrado también `tienda_db` y MongoDB):

```powershell
docker compose stop svc-usuarios
docker compose exec postgres psql -U usuarios -d usuarios_db -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public AUTHORIZATION pg_database_owner; GRANT USAGE ON SCHEMA public TO PUBLIC;"
docker compose run --rm --no-deps svc-usuarios python manage.py makemigrations usuarios   # solo una vez, ya está en el repo
docker compose up -d svc-usuarios
```

Cada integrante debe correr una vez los pasos 1, 2 y 4 al bajar esta rama (documentado en el README del servicio).

## Decisiones técnicas

| Decisión | Por qué |
| --- | --- |
| Los errores propios del registro (`email_registrado`, `password_no_coincide`, `privacidad_no_aceptada`) son mensajes de campo dentro de `validacion` | El documento de autenticación nombraba esos códigos, pero así el gateway puede mostrar varios errores a la vez y el formato es el mismo en todo el sistema. Se anotó en la definición técnica. |
| El registro no lee tokens (`authentication_classes = []`) | Un token vencido en el navegador no debe impedir crear una cuenta. |
| `asignar_admin` solo promueve; para crear desde cero se usa `createsuperuser` | Así lo describe la sección 8 del documento de autenticación. Ambas opciones están en el README. |
| `email_registrado` revela si un correo existe | Lo pide la sección 1; CLAUDE.md exige mensajes genéricos solo en login y recuperación. El límite de intentos (Entrega 3) reducirá el riesgo. |
| Los permisos leen el rol del token, no de la base | Es como funcionan todos los servicios. Después de `asignar_admin` hace falta un token nuevo; en la Entrega 3 el login leerá el rol de la base. |
| Las direcciones son solo del usuario, también para el administrador | El contrato dice "autenticado" sobre `/usuarios/yo/`; no hay un endpoint de administración de direcciones. |
| El listado de usuarios pide token aunque `AUTH_ACTIVA` sea `False` | Son datos personales; con `AUTH_ACTIVA=False` solo se apaga la revisión de rol. |
| La versión del aviso sale de `VERSION_AVISO_PRIVACIDAD` (por defecto `2026-10`) | La sección 14 pide subirla "en settings" cuando el aviso cambie; aquí toda la configuración va por variables de entorno. |
| Teléfono de 10 a 15 dígitos con `+` opcional | Admite números de México con y sin lada internacional. |
| Sin dependencias nuevas | simplejwt, PyJWT y cryptography ya llegaban por `comun`; solo se fijaron en el `requirements.txt` del servicio, como en los demás. |

## Verificación

Se hizo el 22 de octubre de 2026 dentro de Docker.

| Prueba | Resultado |
| --- | --- |
| Reinicio de `usuarios_db` | Antes había 18 migraciones de la fase 0. El esquema se reinició como el usuario `usuarios`; `tienda_db` siguió con sus 20 productos |
| Migraciones | `makemigrations` generó `usuarios.0001_initial`; al arrancar, el contenedor aplicó `usuarios.0001` y `admin.0001`; `makemigrations --check` no detecta cambios |
| Registro real | 201 con el correo normalizado (`  Maria.Lopez…@Example.com ` → minúsculas). Duplicado con mayúsculas → `email_registrado`; contraseñas distintas → `password_no_coincide`; `12345678` → "Esta contraseña es muy común." y "Esta contraseña es totalmente numérica."; sin aviso → `privacidad_no_aceptada` |
| Contraseña en la base | Guardada con `pbkdf2_sha256`, no en texto plano |
| Perfil con token de desarrollo | 200 con rol `cliente`, sin verificar y versión `2026-10`; al editar se intentó cambiar rol y correo y solo cambió el teléfono; un token de un id inexistente → 404; sin token → 401 |
| Direcciones | La primera quedó como predeterminada; al crear otra con `predeterminada: true`, la anterior se desmarcó; al borrar la predeterminada, pasó a la otra; código postal inválido → 400. Otro usuario real recibió 404 en GET, PATCH y DELETE de la dirección ajena |
| `asignar_admin` | Con un correo inexistente, error claro; con el usuario registrado, lo promovió. Con su token de administrador, el listado filtrado por rol lo mostró; como cliente → 403 |
| `pytest` en svc-usuarios | 71 pruebas pasan: modelos y manager 13, servicios 8, endpoints 43, comando 3 y salud 4 |
| `ruff check` y `ruff format --check` | Pasan |
| Esquema OpenAPI | `spectacular --validate --fail-on-warn` sin advertencias; `/api/docs/` y `/admin/login/` responden 200 |
| Postman | Las 14 peticiones de `svc-usuarios` y el resto de la colección devolvieron el código esperado, dos veces seguidas |
| Sin regresiones | svc-tienda 144, svc-contenido 69, svc-ia 55, web 4 y `comun` 26 pruebas siguen pasando |

## Problemas encontrados

| Problema | Solución |
| --- | --- |
| `AUTH_USER_MODEL` no se puede cambiar sobre la base migrada en la fase 0 | Reinicio solo del esquema de `usuarios_db`, en el orden detener → vaciar → `makemigrations` → arrancar (si el contenedor arranca antes de tener la migración, `migrate` falla). |
| Las fixtures crean usuarios con ids fijos (para firmar sus tokens) y la secuencia de PostgreSQL no avanza, así que el registro chocaría con esos ids | La fixture adelanta la secuencia con `setval` después de crear cada usuario con id fijo; hay una prueba para ese caso. |
| `UserAttributeSimilarityValidator` revisa `first_name` y `last_name`, que este modelo no tiene | Se configuró con `user_attributes = ["email", "nombre", "apellidos"]`. |
| Una prueba esperaba que `maria.lopez2026` se rechazara por parecerse al correo, pero para Django no se parece lo suficiente (similitud de 0.58, el límite es 0.7) | Se corrigió la prueba con una contraseña que sí se parece (`maria.lopez@example`); el validador funciona como debe. |
| En la verificación manual, una dirección "ajena" respondió 200 | Era un error del script de prueba: el token "ajeno" usaba el mismo id que el usuario registrado. Se repitió con un segundo usuario real y respondió 404. |

## Commits y Pull Requests

Rama `feat/fase-1-usuarios-basico` → `develop`. Los commits los hace el integrante a mano; esta sección se completa con los hashes al hacer el PR.

## Pendientes y siguiente paso

- **Cada integrante:** reiniciar una vez `usuarios_db` al bajar la rama (pasos 1, 2 y 4 del README de svc-usuarios).
- **Entrega 3:** login y emisión de JWT con el rol tomado de la base, renovación y logout, verificación por correo (el lugar está marcado en `registrar_usuario`), recuperación y cambio de contraseña, `PATCH /usuarios/<id>/rol/`, límite de intentos con django-axes y 2FA.
- Pedir aceptar un aviso de privacidad nuevo cuando suba `VERSION_AVISO_PRIVACIDAD` (lo hará el gateway al iniciar sesión).
- **Siguiente:** completar la calidad de la Entrega 2 (revisión de Swagger y Postman de todos los servicios) y documentar los sprints en Jira.
