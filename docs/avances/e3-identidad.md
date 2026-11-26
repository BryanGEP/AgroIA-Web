# Entrega 3 · Identidad en svc-usuarios

**Fecha:** 19 de noviembre de 2026 · **Entregable:** Entrega 3 · **Responsable:** Bryan Gael Esquivel Pérez

## Resumen

svc-usuarios pasó de la versión básica de la Entrega 2 a ser el servicio de identidad completo. Ahora emite los tokens (access de 15 minutos y refresh de 7 días, RS256) con rotación y blacklist. Además verifica el correo, recupera y cambia contraseñas, cambia roles dejando registro, limita los intentos con DRF + Redis y django-axes, y registra los eventos de seguridad. Todos los servicios registran sus 401 y 403.

Para dejar el sistema listo para reemplazarlo por [ms-usuarios](https://github.com/LeoMtzGlz/ms-usuarios), el `id` del usuario pasó a UUID en todos los servicios y el emisor del token es configurable (`JWT_ISSUER`). El contrato quedó escrito en [`docs/contrato-identidad.md`](../contrato-identidad.md).

La colección de Postman ya inicia sesión sola. Todo se verificó en Docker el mismo día. Las pantallas quedan para la fase del gateway.

## Qué se construyó

### svc-usuarios

- **Tokens** (`apps/usuarios/tokens.py`):
  - `RefreshToken.for_user` con los claims `rol`, `email_verificado` y `token_version`.
  - simplejwt agrega `token_type`, `user_id`, `iat`, `exp`, `jti` e `iss`.
  - Sin datos personales (sin el claim `email`).
- **Endpoints nuevos:**
  - `auth/login/`, `auth/token/renovar/`, `auth/logout/` y `auth/logout-todo/`.
  - `auth/verificar-correo/`, `auth/reenviar-verificacion/`, `auth/recuperar/`, `auth/restablecer/` y `auth/cambiar-password/`.
  - `usuarios/<id>/rol/`.
  - La lógica está en `servicios.py`, como pide `CLAUDE.md`.
- **Login:**
  - Usa `authenticate` con axes. Correo inexistente, contraseña incorrecta y cuenta desactivada responden igual (401 `credenciales_invalidas`).
  - Envía `user_logged_in`, que actualiza `last_login` y reinicia el contador de axes.
  - El `if usuario.tiene_2fa` responde 501 `2fa_no_disponible`, con un comentario que apunta a la sección 12.
- **Renovación:** primero valida el refresh (firma, vencimiento, tipo y blacklist). Después lee al usuario con `select_for_update` y revisa `is_active` y `token_version`. Si todo está bien, mete el refresh anterior a la blacklist; si otra renovación ya lo había hecho, la rechaza. Al final emite un par con los claims recalculados.
- **Logout:**
  - Valida la firma sin exigir vigencia y comprueba que el refresh sea del mismo usuario (si no, 403). Responde 205 aunque ya estuviera en la blacklist o vencido.
  - `logout-todo` sube `token_version`.
- **Correos** (`apps/usuarios/correos.py`):
  - Usa `EmailMultiAlternatives` con plantillas `.txt` y `.html`: base, botón, verificación, recuperación y contraseña cambiada.
  - Se envían con `transaction.on_commit`. Si fallan, se registra el error y la petición sigue.
  - El backend de consola es el valor por defecto.
- **Verificación:** `TimestampSigner(salt="verificacion-email")` de 24 horas. El enlace es `{FRONTEND_URL}/verificar-correo/?token=...`.
- **Recuperación:**
  - Usa `default_token_generator` con `PASSWORD_RESET_TIMEOUT = 3600`. El enlace es `{FRONTEND_URL}/restablecer/<uid>/<token>/`.
  - Al restablecer: cierra las sesiones, marca el correo como verificado y envía un aviso.
- **Cambio de contraseña:** pide la actual y rechaza que la nueva sea igual. Cierra las demás sesiones, devuelve un par nuevo y envía un aviso.
- **Roles:** modelo `CambioRol` (usuario, rol anterior y nuevo, quién y cuándo), visible en el admin y de solo lectura. Un administrador no puede quitarse su rol (409 `auto_degradacion`).
- **Límite de intentos:**
  - `ScopedRateThrottle` con caché en Redis:
    - login: 10 por minuto por IP;
    - registro: 5 por hora por IP;
    - recuperar y reenviar: 3 por hora por IP;
    - cambiar contraseña: 5 por hora por usuario.
  - `LimitePorCorreo` agrega 3 por hora por correo; en Redis guarda un hash del correo.
  - django-axes 8.3.1 bloquea 15 minutos por correo + IP al quinto fallo, con la respuesta en el formato común. `AXES_USERNAME_CALLABLE` y `AXES_LOCKOUT_CALLABLE` están en `apps/usuarios/bloqueo.py`.
- **Comando `cargar_usuarios_demo`:** crea tres cuentas con una contraseña evidentemente de demostración. Falla con un mensaje claro si `DJANGO_DEBUG=False`.
- **Configuración:**
  - `JWT_PRIVATE_KEY_PATH` es obligatoria; el servicio no arranca sin la llave.
  - `JWT_ISSUER`, `CACHES` con Redis y `EMAIL_*`.
  - `NUM_PROXIES = 1`, `LOGGING` y las apps `token_blacklist` y `axes`.

### Paquete `comun`

- **`seguridad.py` (nuevo):**
  - `registrar_evento()` escribe una línea JSON en el logger `seguridad` y descarta las llaves sensibles.
  - `ip_cliente()` confía en un proxy y también la usa axes.
- **`errores.py`:**
  - Registra cada 401 y 403 como `acceso_denegado`; los `ErrorDeNegocio` no, para no duplicarlos.
  - El 429 ahora es `demasiados_intentos`, con «Intenta de nuevo en N segundos».
  - Respeta el `code` propio de una clase de permiso.
- **`permisos.py`:**
  - `CorreoVerificado` responde 403 `email_no_verificado`, «Verifica tu correo para poder hacer esta acción.».
  - `usuario_id()` devuelve un `uuid.UUID`.
- **`autenticacion.py`:** rechaza con 401 un `user_id` que no sea UUID.
- **`configuracion.py`:** agrega `configurar_jwt(..., issuer=)`, `ISSUER_POR_DEFECTO` y `configurar_logging()`.
- **`openapi.py`:** ejemplos de los códigos nuevos. **`pruebas.py`:** `firmar_token(usuario_id=UUID, emisor=...)`.

### UUID en el resto del sistema

- **svc-tienda:** `Carrito.usuario_id` y `Pedido.usuario_id` son `UUIDField`.
  - La migración `0002` borra los carritos y pedidos de prueba; la `0003` cambia la columna.
  - PostgreSQL no convierte `bigint` a `uuid`, así que se quita la columna y se vuelve a crear.
  - El catálogo no se toca.
- **svc-contenido:** guarda `usuario_id` como el UUID en texto en Mongo, y los serializers usan `UUIDField`.
- **svc-ia:** `JWT_ISSUER`, `user_id` UUID y `app/eventos.py`, el equivalente del log de seguridad, que registra los 401 y 403.
- **`infra/emitir_token.py`:** `--usuario-id <uuid>` (opcional), `--vencido` y `--emisor`. Queda documentado como solo para pruebas.
- **Ejemplos de Swagger, datos de prueba y factories** pasaron a UUID.

### Postman

- **Carpeta «Autenticación» al inicio:**
  - Login de las tres cuentas de demostración, que guarda los tokens con un script.
  - Renovación con rotación y reúso del refresh anterior.
  - Verificación con un token alterado, reenvío, recuperación y restablecimiento con un enlace inválido.
- **svc-usuarios:**
  - El registro inicia sesión solo.
  - Nuevos casos: cambio de rol de ida y vuelta, 409 por quitarse el propio rol, cambio de contraseña, refresh de antes del cambio (401) y contraseña actual incorrecta.
- **Carpeta «Seguridad» al final:**
  - Sin token, token vencido, token de otra llave, refresh usado como acceso.
  - Rol equivocado, compra sin correo verificado (`email_no_verificado`).
  - Logout y refresh en blacklist.
  - Cinco intentos fallidos (bloqueo) y exceso de logins (429 con `Retry-After`).
- **Tokens:** ya no se pegan a mano, salvo `token_vencido` (opcional), que necesita la llave privada; si está vacío, esa petición se omite. El token de otra llave es fijo y está en la colección, firmado con una llave descartable.

### Documentación

- **Nuevo:** [`docs/contrato-identidad.md`](../contrato-identidad.md), con el contrato, la sección «Diferencias con ms-usuarios», la razón de publicar los puertos solo en `127.0.0.1` y los límites conocidos.
- **Actualizados:**
  - Los READMEs raíz, de svc-usuarios (reescrito), comun, svc-tienda, svc-contenido y svc-ia.
  - `definicion-tecnica.md` (códigos de error, endpoints, UUID, plan) y `.env.example` (`JWT_ISSUER`).
  - Los comentarios de `docker-compose.yml` y `CLAUDE.md` (`usuario_id` como UUID y log de seguridad).
- **Pasos para quien baja la rama:** reiniciar `usuarios_db`, limpiar Mongo y reconstruir, sin `down -v`.

## Decisiones técnicas

### Aprobadas para esta fase

| Decisión | Qué se hizo |
| --- | --- |
| Claim `email` | No va en el token, aunque la sección 3 lo menciona: mismos claims que `emitir_token.py` y sin datos personales |
| Código del 429 | `demasiados_intentos` en `comun` (antes `demasiadas_peticiones`); el formato no cambia |
| IP detrás del gateway | `NUM_PROXIES = 1` y `AXES_CLIENT_IP_CALLABLE`; los puertos directos solo en `127.0.0.1` |
| Cuentas de demostración | En el repo, con una contraseña evidentemente de demostración; el comando falla con `DEBUG=False` |
| Postman dos veces | Con un minuto de diferencia; no se subieron los límites |
| 2FA | `if` listo con 501 `2fa_no_disponible` |
| Límite de `logout-todo` | Un access ya emitido sirve hasta 15 minutos; escrito en el contrato |
| `CorreoVerificado` | 403 `email_no_verificado` en esta fase, también en Postman |
| UUID e `JWT_ISSUER` | Para poder cambiar a ms-usuarios; sin cambiar nuestro formato de errores |

### Tomadas durante la fase

- **django-axes 8.3.1 y no 9.0.0:** la 9.0.0 salió el 30 de octubre de 2026 y es versión mayor; la 8.3.1 es de febrero de 2026.
- **Dependencias nuevas:** `django-axes==8.3.1`, `redis==8.1.0` y, en desarrollo, `freezegun==1.5.5`, todas en svc-usuarios.
- **El bloqueo ocurre al quinto fallo, no al sexto:** el documento de requerimientos dice «el sexto intento fallido bloquea», pero axes bloquea cuando el contador llega a `AXES_FAILURE_LIMIT = 5`. La quinta respuesta ya es 403, y desde ahí la contraseña correcta tampoco entra.
- **Login sin `EmailField`:** un correo mal escrito también responde `credenciales_invalidas`, así que todas las fallas se ven iguales y axes las cuenta.
- **Cuenta desactivada en el login:** responde lo mismo que credenciales inválidas (el documento dice «rechazar»; no se revela que la cuenta existe).
- **Logout con algo que no es un refresh:** 400 `refresh_invalido` (el documento no lo define).
- **Cambiar contraseña:** el límite de 5 por hora cuenta todos los intentos del usuario, no solo los fallidos.
- **Logo de los correos:** el nombre «AgroIA» en texto con los colores del tema, no una imagen, para que se vea aunque el cliente de correo bloquee imágenes.
- **Postman sin el caso «sin aceptar privacidad»:** cada registro cuenta para el límite de 5 por hora por IP y la colección registraba tres veces. El caso sigue en pytest y en Swagger.
- **Contradicción con `CLAUDE.md`:** decía «guarda `usuario_id` como entero». Se cambió a UUID, como se pidió para esta fase.

## Verificación

Todo en Docker, el 19 de noviembre de 2026.

- **Arranque:** `docker compose up -d --build` en 47 s; los 10 contenedores arriba y las bases, `agente` y `agente-db` *healthy*. svc-usuarios aplicó su `0001` nueva y svc-tienda sus `0002` y `0003`. `makemigrations --check` no detecta cambios.
- **Recorrido completo** contra los puertos locales, 0 fallas:
  1. Registro: 201 con UUID.
  2. El correo de verificación se imprime en `docker compose logs svc-usuarios`, con el enlace.
  3. Login sin verificar: 200 con `email_verificado=false`; comprar responde 403 `email_no_verificado`.
  4. Verificar con el token del enlace de la consola: 200.
  5. Login: 200. Con el token, en svc-tienda: agregar al carrito 201, ver el carrito 200 y crear el pedido 201 con `usuario_id` UUID.
  6. Renovar: 200 con un refresh nuevo; reusar el anterior: 401.
  7. Logout: 205; renovar después: 401.
  8. Recuperar: 200 genérico, con el enlace en la consola; restablecer: 200; el mismo enlace otra vez: 400 `enlace_invalido`. Login con la nueva: 200.
  9. Cuatro fallos (401) y el quinto 403 `cuenta_bloqueada_temporalmente`; con la contraseña correcta, también 403. `axes_reset_username` desbloqueó («1 attempts removed»).
- **Log de seguridad:** las líneas JSON de svc-usuarios cubrieron los eventos del recorrido, y svc-tienda registró el 403 `email_no_verificado` con el `usuario_id`. Se buscaron las contraseñas usadas y `eyJ` (inicio de un JWT) en las líneas del log: 0 coincidencias. El límite por correo guarda en Redis un hash, no el correo.
- **`cargar_usuarios_demo`:** con `DJANGO_DEBUG=False` falla con el mensaje esperado; con `True` crea las tres cuentas.
- **Comandos de reinicio del README:** el de MongoDB y el de PostgreSQL se probaron desde PowerShell.
- **pytest:** 508 en verde (418 en la Entrega 2).

  | Servicio | Pruebas |
  | --- | --- |
  | web | 45 |
  | svc-usuarios | 141 (antes 71) |
  | svc-tienda | 144 |
  | svc-contenido | 70 (antes 69) |
  | svc-ia | 63 (antes 58) |
  | comun | 45 (antes 31) |

- **ruff:** `ruff check` y `ruff format --check` en verde en los cinco servicios, `comun` e `infra/`.
- **Swagger:** `spectacular --validate --fail-on-warn` termina con código 0 en svc-usuarios, svc-tienda y svc-contenido.
- **Postman** con Newman 6.2.1, dos corridas con 62 s de diferencia: **100 peticiones y 163 aserciones, 0 fallas** en cada una. Con `token_vencido` vacío, esa petición se omite (0 peticiones, 0 fallas).

## Problemas encontrados

| Problema | Solución |
| --- | --- |
| `cannot ALTER TABLE "pedidos_carrito" because it has pending trigger events` al borrar filas y cambiar la columna en la misma migración | Dos migraciones: `0002` borra los datos y `0003` cambia la columna |
| PostgreSQL no convierte `bigint` a `uuid` con `ALTER COLUMN` | Quitar y volver a crear `usuario_id` (no había datos que conservar) |
| `UUIDField` de DRF acepta un entero y lo convierte (`uuid.UUID(int=10)`) | La prueba del 400 de la bitácora usa un texto inválido. La autenticación sí rechaza un `user_id` entero, porque lo lee como texto |
| simplejwt lee `SIMPLE_JWT` al arrancar y no lo recarga en las pruebas | El emisor se prueba en `configurar_jwt`; svc-ia lo prueba de punta a punta |
| Los logins a un correo inexistente también cuentan para axes | Las pruebas del límite por IP usan un correo distinto en cada intento |
| El token de recuperación se generó con el `last_login` viejo en memoria (el login lo cambia) | `refresh_from_db()` antes de generar el enlace en la prueba |
| El logger `seguridad` de svc-ia no propaga, así que `caplog` no lo veía | Se activa `propagate` con `monkeypatch` solo en sus pruebas |
| Docker Desktop estaba detenido al retomar | Se inició y en 10 s respondió |

## Revisión de seguridad

Revisión del 19 de noviembre de 2026 sobre svc-usuarios, comun y svc-ia (autenticación, tokens, correos, límite de intentos y log de seguridad), más `docker-compose.yml` y `.env.example`. Los resultados completos (SARIF) quedaron fuera del repositorio.

### Herramientas

| Herramienta | Versión y configuración | Alcance |
| --- | --- | --- |
| insecure-defaults (skill de Trail of Bits) | Revisión manual de valores por defecto que dejan el sistema abierto si falta una variable | Configuración de los servicios, `docker-compose.yml` y `.env.example` |
| Semgrep | 1.183.0 (imagen oficial en Docker), OSS, `--metrics=off`. Reglas `p/security-audit`, `p/secrets`, `p/python`, `p/django`, `p/fastapi`, `p/dockerfile` y `p/docker-compose`, más Trail of Bits (`python`, `generic`) y elttam (`orm-leak` de Django): 303 reglas | 67 archivos de svc-usuarios, comun, svc-ia y `docker-compose.yml`, sin pruebas ni migraciones. Filtro «solo importantes»: categoría seguridad, confianza e impacto medio o alto |
| CodeQL | 2.25.6, paquete `codeql/python-queries` 1.5.0, suite `python-security-extended`: 49 reglas | 45 archivos de Python de svc-usuarios, comun y svc-ia, sin pruebas ni migraciones |
| `manage.py check --deploy` | Django 5.2.18, svc-usuarios con `DJANGO_DEBUG=False` | Configuración de despliegue de Django |

**Resultados:**
- **Semgrep:** 12 hallazgos, 6 importantes; los otros 6 se revisaron y son falsos positivos.
- **CodeQL:** 0 hallazgos.
- **`check --deploy`:** 4 advertencias (W004, W008, W012, W016).
- No hubo hallazgos de gravedad alta.

### Hallazgos

| Id | Gravedad | Hallazgo | Fuente | Decisión |
| --- | --- | --- | --- | --- |
| M1 | Media | Con `DEBUG=False`, los correos se seguían imprimiendo en la consola si faltaba `EMAIL_BACKEND`: los enlaces de recuperación (que permiten tomar la cuenta) quedaban en el log | insecure-defaults | Corregido |
| M2 | Media | Se aceptaba la `DJANGO_SECRET_KEY` de `.env.example`, que es pública; con ella se pueden firmar enlaces de verificación de correo | insecure-defaults | Corregido |
| M3 | Media | Contenedores como root (`missing-user` en `svc-usuarios/Dockerfile` y `svc-ia/Dockerfile`) y servidores de desarrollo (`runserver`, `uvicorn --reload`) | Semgrep | Aceptado |
| B1 | Baja | Redis y MongoDB sin contraseña ni TLS (`redis-unencrypted-transport` ×3 y `mongodb-insecure-transport`) | Semgrep | Aceptado |
| B2 | Baja | El log de un login fallido guardaba el campo del correo tal cual: si alguien escribía ahí su contraseña, quedaba en el log | insecure-defaults | Corregido |
| B3 | Baja | El registro no limitaba el largo de la contraseña (los demás endpoints, 128) | Revisión manual | Corregido |
| B4 | Baja | `X-Forwarded-For` se puede falsificar desde la red interna o un puerto directo y esquivar el límite por IP y el bloqueo de axes | Revisión manual | Aceptado, con condición para el gateway |
| B5 | Baja | Se puede saber si un correo está registrado: el registro responde `email_registrado` y, con SMTP real, recuperar tardaría más si la cuenta existe | Revisión manual | Aceptado; el tiempo, cerrado en la Entrega 4 |
| B6 | Baja | Sin HSTS, redirección a HTTPS ni cookies `Secure` (W004, W008, W012 y W016) | `check --deploy` | Aceptado |
| B7 | Baja | Un access sirve hasta 15 minutos tras logout o cambio de rol, y el token no lleva `aud` | Revisión manual | Aceptado |
| B8 | Baja | `.env.example` trae `DJANGO_DEBUG=True` y contraseñas de ejemplo que compose acepta | insecure-defaults | Comentario agregado; se acepta como plantilla de desarrollo |

### Qué se corrigió

- **M1:** `comun.configuracion.validar_backend_de_correo()`. Con `DEBUG=False`, svc-usuarios no arranca si `EMAIL_BACKEND` es el de consola, memoria, archivo o *dummy*, y el mensaje explica que falta SMTP.
- **M2:** `comun.configuracion.validar_secret_key()`, conectada en los cuatro servicios Django (svc-usuarios, svc-tienda, svc-contenido y web). Con `DEBUG=False` rechaza:
  - la clave de `.env.example`;
  - una clave de menos de 50 caracteres o con menos de 5 caracteres distintos;
  - una que empiece con `django-insecure-`.

  Son los mismos criterios que la advertencia W009 de Django. Con `DEBUG=True` no se revisa, para no estorbar en local.
- **B2:** `login_fallido` y `cuenta_bloqueada` registran el correo solo si tiene formato de correo; si no, `email_no_valido`.
- **B3:** `password` y `password_confirmacion` del registro con `max_length=128`.
- **B8:** comentarios en `.env.example`: para la demo y la entrega, `DJANGO_DEBUG=False`, una clave propia y SMTP real.
- **Pruebas nuevas, 26 en total:**
  - `comun`: 10 de las dos validaciones.
  - Por servicio (`tests/test_configuracion.py`): 3 en cada uno, que cargan `config.settings` en otro proceso con `DEBUG=False` y la clave de ejemplo. svc-usuarios suma 2 del backend de correo.
  - svc-usuarios: 1 de la contraseña escrita en el campo del correo y 1 del límite de 128 caracteres.
- Para que las pruebas pasen también con `DEBUG=False`, la clave de los `settings_pruebas.py` ahora es larga. svc-usuarios fija SMTP antes de cargar la configuración; pytest-django lo cambia después a `locmem`.

**Verificación después de corregir:**
- **pytest:** 534 en verde.

  | Servicio | Pruebas |
  | --- | --- |
  | svc-usuarios | 148 |
  | svc-tienda | 147 |
  | svc-contenido | 73 |
  | web | 48 |
  | svc-ia | 63 |
  | comun | 55 |

- **ruff:** `ruff check` y `ruff format --check` en verde en los cinco servicios, `comun` e `infra/`.
- **Servicios:** los cinco siguen respondiendo `GET /salud/` con la configuración local.

### Qué se acepta y por qué

- **M3. Root y servidores de desarrollo:** son imágenes de desarrollo con el código montado y recarga automática. Se corrige al preparar el despliegue (Entrega 5).
- **B1. Redis y MongoDB sin contraseña ni TLS:** viven en la red interna de Docker y sus puertos solo se publican en `127.0.0.1`. Contraseña y TLS van al despliegue (Entrega 5).
- **B4. `X-Forwarded-For`:** los servicios confían en un proxy, y los puertos directos solo existen en `127.0.0.1`, como dice el contrato de identidad. **Condición para la fase del gateway:** el gateway debe poner en `X-Forwarded-For` la IP real del cliente (la `REMOTE_ADDR` de la conexión que recibe) y no reenviar el que mande el cliente. Quedó escrita en el plan de la definición técnica y en el contrato.
- **B5. Saber si un correo está registrado:** el registro tiene que avisar que el correo ya existe (lo pide el documento de requerimientos) y está limitado a 5 por hora por IP. El envío de correos en segundo plano, que iguala los tiempos de recuperar, llegó con los eventos de la Entrega 4 ([avance](e4-eventos-negocio.md)): con un servidor de correo que no responde, recuperar con un correo que existe respondía **504 en 10 016 ms** y con uno que no, 200 en 57 ms; después, 200 en 15 ms y 200 en 17 ms (`infra/medir_recuperacion.py`).
- **B6. HTTPS y cookies seguras:** hoy no hay HTTPS y svc-usuarios no se expone; solo afecta al admin de Django. Va al despliegue (Entrega 5).
- **B7. Revocación y `aud`:** es por diseño y está en los límites conocidos del contrato. Revocar antes requeriría consultar Redis en cada petición (Entrega 4).

### Falsos positivos

| Regla (Semgrep) | Dónde | Por qué no aplica |
| --- | --- | --- |
| `unvalidated-password` | `servicios.py` (restablecer y cambiar contraseña) | `validar_password_nueva()` corre antes de `set_password` |
| `unvalidated-password` | `managers.py` (`create_user`) | Recibe contraseñas que ya validó `RegistroSerializer` |
| `unvalidated-password` | `cargar_usuarios_demo.py` | Contraseña fija de demostración; el comando solo corre con `DEBUG=True` |
| `var-in-href` ×2 | `templates/emails/_boton.html` | El enlace lo arma el servidor con `FRONTEND_URL` y un token firmado; el usuario no lo controla y la plantilla escapa HTML |

### Lo que se revisó y está bien

- **Configuración:**
  - `AUTH_ACTIVA` vale `True` por defecto y no se puede apagar con `DEBUG=False`.
  - Las llaves JWT y `JWT_ISSUER` son obligatorias: si faltan, el servicio no arranca.
  - Las contraseñas de las bases son obligatorias en compose.
  - La llave privada solo llega a svc-usuarios.
- **Tokens:**
  - Algoritmo fijo `RS256` en simplejwt y en PyJWT, así que no hay confusión de algoritmos.
  - `exp` e `iss` obligatorios; un refresh no sirve como access.
  - El logout comprueba que el refresh sea del dueño.
  - La renovación con el mismo refresh no tiene condición de carrera (blacklist con `get_or_create`).
- **Contraseñas y enlaces:**
  - El login simula el hash cuando el usuario no existe, para que tarde lo mismo.
  - El enlace de recuperación es de un solo uso y vence en 1 hora.
  - El bloqueo de axes también aplica a correos inexistentes, así que no revela cuentas.
- **Correos y log:**
  - Sin inyección de encabezados: el asunto es fijo y el destinatario sale de la base.
  - El log es JSON (`json.dumps`), así que no se pueden inyectar líneas.
  - El límite por correo guarda en Redis un hash, no el correo.

## Commits y Pull Requests

Rama `feat/e3-identidad` desde `develop`. Commits sugeridos, a hacer a mano por el integrante:

| Commit | Título |
| --- | --- |
| 1 | `feat(comun): emisor configurable, UUID, email_no_verificado y log de seguridad` |
| 2 | `feat(usuarios): login JWT, renovación, logout, correos, recuperación, roles y límite de intentos` |
| 3 | `refactor(tienda): usuario_id como UUID` |
| 4 | `refactor(contenido): usuario_id como UUID` |
| 5 | `feat(ia): emisor configurable, user_id UUID y registro de accesos denegados` |
| 6 | `chore(infra): JWT_ISSUER y emitir_token solo para pruebas` |
| 7 | `test(postman): carpetas de autenticación y seguridad con login automático` |
| 8 | `docs: contrato de identidad, diferencias con ms-usuarios y pasos para bajar la rama` |
| 9 | `fix(seguridad): SECRET_KEY y backend de correo obligatorios sin DEBUG, log y registro más estrictos` |
| 10 | `docs(seguridad): revisión con Semgrep, CodeQL y check --deploy` |

## Pendientes y siguiente paso

- **Siguiente:** fase del gateway: sesión, enrutamiento, CORS y pantallas de login, registro y perfil. Allí se agrega `X-Forwarded-For` y se guardan los tokens en la sesión del servidor.
- **Pantallas de verificación y restablecimiento** en el gateway (hoy el enlace se copia de la consola).
- **Correo real:** probar SMTP (`sendtestemail`) antes de la demo; hoy solo se probó la consola.
- **Condición para el gateway (B4 de la revisión de seguridad):** poner en `X-Forwarded-For` la IP real del cliente y no reenviar la que mande el cliente.
- **Despliegue (Entrega 5):** contenedores sin root, gunicorn y uvicorn sin `--reload`, contraseña y TLS en Redis y MongoDB, HTTPS y cookies seguras, y SMTP real (ver la revisión de seguridad).
- **2FA:** sección 12, solo si sobra tiempo.
- **Revocar el access antes de que venza:** si hiciera falta, publicar en Redis los `jti` revocados o el `token_version` (Entrega 4).
- **`flushexpiredtokens`:** hoy es manual; documentado en el README de svc-usuarios.
- **ms-usuarios:** si el grupo lo adopta, seguir la lista de [`contrato-identidad.md`](../contrato-identidad.md#qué-haría-falta-para-usar-ms-usuarios-en-lugar-del-nuestro).
