# AgroIA-Web · Requerimientos de autenticación

Oct 13, 2026 · @bry

## Alcance y decisiones base

Este documento detalla qué implica cada tarea de autenticación de `svc-usuarios` y del gateway `web/`, para que cada integrante sepa exactamente qué construir y cuándo está terminado.

**Stack:** Django 5, Django REST Framework, `djangorestframework-simplejwt`, PostgreSQL. Todos los endpoints viven bajo `/api/v1/auth/` en `svc-usuarios`.

**Decisiones que se toman antes de escribir código:**

1. **Modelo de usuario personalizado desde la primera migración.** Crear `Usuario(AbstractUser)` con `email` único como `USERNAME_FIELD` y `AUTH_USER_MODEL = "usuarios.Usuario"`. Cambiarlo después de migrar obliga a borrar la base.
2. **Campos extra del usuario:** `email_verificado` (bool, default `False`), `rol` (`cliente` | `administrador`, default `cliente`), `acepto_privacidad_en` (datetime), `token_version` (entero, default 0, sirve para invalidar sesiones).
3. **Respuestas de error con un formato único:** `{"error": "codigo_corto", "detalle": "mensaje para el usuario"}`.
4. **Configuración sensible en `.env`:** `SECRET_KEY`, llaves JWT, credenciales SMTP, `FRONTEND_URL`. Se documentan en `.env.example`.

**Orden sugerido por sprint:**

| Sprint | Funcionalidades |
| --- | --- |
| 1 | Envío de correos, registro, verificación de correo, aviso de privacidad, inicio de sesión, renovación, cierre de sesión |
| 2 | Recuperación y cambio de contraseña, roles y permisos, límite de intentos |
| 3 | Validación de JWT en los demás servicios, sesión en el gateway |
| 4 | Autenticación de dos pasos, opcionales |

## 1. Registro de usuario

Endpoint `POST /api/v1/auth/registro/`, público. Crea la cuenta sin verificar y dispara el correo de verificación.

1. **Recibir nombre, correo y contraseña.**
   - Crear `RegistroSerializer` con `nombre` (máx. 150), `apellidos` (máx. 150), `email`, `password`, `password_confirmacion`, `acepto_privacidad` (bool).
   - `password` y `password_confirmacion` son `write_only`; nunca se devuelven en la respuesta.
   - Validar que ambas contraseñas coincidan; si no, error `password_no_coincide`.
2. **Validar formato de correo y que no esté registrado.**
   - Normalizar: quitar espacios y pasar a minúsculas antes de validar y guardar.
   - Usar `EmailField` del serializer para el formato.
   - Buscar con `Usuario.objects.filter(email__iexact=email).exists()`; si existe, error `email_registrado` con código 400.
   - El campo `email` lleva `unique=True` en el modelo como respaldo ante dos registros simultáneos.
3. **Validar la contraseña.**
   - En `settings.py`, activar los cuatro validadores: `UserAttributeSimilarityValidator`, `MinimumLengthValidator` (`min_length: 8`), `CommonPasswordValidator` y `NumericPasswordValidator`.
   - En el serializer, llamar `validate_password(password, user=usuario_temporal)` para que compare contra el nombre y el correo.
   - Traducir los mensajes con `LANGUAGE_CODE = "es-mx"`.
4. **Guardar al usuario.**
   - Crear con `Usuario.objects.create_user(...)`, que aplica el hash automáticamente; nunca asignar `password` directo.
   - Valores iniciales: `email_verificado=False`, `rol="cliente"`, `is_active=True`.
   - Envolver la creación y el registro del aviso en `transaction.atomic()`.
5. **Pedir la aceptación del aviso de privacidad.**
   - Si `acepto_privacidad` no es `true`, error `privacidad_no_aceptada`.
   - Guardar `acepto_privacidad_en = timezone.now()` (ver sección 14).
6. **Disparar el correo de verificación.**
   - Llamar a la función de la sección 2 con `transaction.on_commit(...)`, para que solo se envíe si el usuario se guardó.
   - Si el envío falla, el registro no se revierte: el usuario puede pedir reenvío.
   - Responder `201` con `{"id", "email", "mensaje": "Revisa tu correo para verificar tu cuenta"}`. No devolver tokens.

**Pruebas mínimas:** registro correcto; correo duplicado (incluyendo mayúsculas distintas); contraseñas distintas; contraseña débil; sin aceptar privacidad; la contraseña guardada no está en texto plano.

## 2. Verificación de correo

Confirma que el correo es del usuario. Sin verificar puede iniciar sesión y navegar, pero no comprar.

1. **Generar un token con expiración.**
   - Usar `django.core.signing.TimestampSigner` con `salt="verificacion-email"` para firmar el `id` del usuario.
   - El token se valida con `max_age=86400` (24 horas).
   - El `salt` distinto evita que un token de verificación sirva para recuperar contraseña.
2. **Enviar el enlace por correo.**
   - Enlace: `{FRONTEND_URL}/verificar-correo/?token=<token>`. Apunta al gateway, no a la API.
   - Plantilla `emails/verificacion.html` y versión `.txt`, con nombre del usuario, botón, enlace en texto plano y la leyenda "El enlace vence en 24 horas".
3. **Validar el token al abrir el enlace.**
   - El gateway llama a `POST /api/v1/auth/verificar-correo/` con `{"token"}`.
   - Casos: token alterado → `token_invalido`; vencido (`SignatureExpired`) → `token_expirado`; usuario inexistente → `token_invalido`.
   - El gateway muestra una página distinta para cada caso, con botón de reenvío cuando expiró.
4. **Marcar la cuenta como verificada.**
   - Poner `email_verificado=True` y guardar solo ese campo (`save(update_fields=[...])`).
   - Si ya estaba verificada, responder `200` con "Tu correo ya estaba verificado" en lugar de error.
5. **Reenviar el correo si el enlace expiró.**
   - `POST /api/v1/auth/reenviar-verificacion/` con `{"email"}`.
   - Responder siempre `200` con mensaje genérico, exista o no la cuenta.
   - Limitar a 3 reenvíos por hora por correo (sección 9).
6. **Bloquear la compra a cuentas no verificadas.**
   - Incluir `email_verificado` como claim del JWT (sección 3).
   - En `svc-tienda`, el endpoint de crear pedido revisa ese claim y responde `403` con `email_no_verificado`.
   - El gateway muestra un banner "Verifica tu correo para poder comprar" con botón de reenvío.

**Pruebas mínimas:** token válido; token alterado; token vencido (simular tiempo con `freezegun`); doble verificación; reenvío con correo inexistente responde igual que con uno real.

## 3. Inicio de sesión (JWT)

Endpoint `POST /api/v1/auth/login/`, público. Recibe `{"email", "password"}` y devuelve los tokens.

1. **Validar correo y contraseña.**
   - Normalizar el correo igual que en el registro.
   - Usar `django.contrib.auth.authenticate(request, email=..., password=...)`.
   - Rechazar cuentas con `is_active=False` (desactivadas por un admin).
2. **Emitir los tokens.**
   - Configurar `SIMPLE_JWT`: `ACCESS_TOKEN_LIFETIME = 15 min`, `REFRESH_TOKEN_LIFETIME = 7 días`, `ALGORITHM = "RS256"` con las llaves de `.env` (sección 10).
   - Extender `TokenObtainPairSerializer` y agregar claims: `user_id`, `email`, `rol`, `email_verificado`, `token_version`.
   - No meter datos sensibles en el token (teléfono, dirección): el JWT se puede leer sin la llave.
   - Respuesta `200`: `{"access", "refresh", "usuario": {"id", "nombre", "rol", "email_verificado"}}`.
   - Actualizar `last_login`.
3. **Responder con un mensaje genérico si las credenciales fallan.**
   - Correo inexistente y contraseña incorrecta devuelven lo mismo: `401` con `credenciales_invalidas` y "Correo o contraseña incorrectos".
   - Registrar el intento fallido para el límite de intentos (sección 9).
4. **Si el usuario tiene 2FA, entregar un token temporal.**
   - Si `usuario.tiene_2fa` es `True`, en lugar de los JWT responder `{"requiere_2fa": true, "token_temporal"}`.
   - El token temporal se firma con `TimestampSigner(salt="login-2fa")`, vence en 5 minutos y solo sirve en `/auth/2fa/verificar/` (sección 12).
   - Este paso se implementa en el sprint de 2FA; antes basta con dejar el `if` preparado.

**Pruebas mínimas:** login correcto devuelve ambos tokens con los claims; contraseña incorrecta y correo inexistente dan la misma respuesta; cuenta desactivada rechazada; el token de acceso caduca a los 15 minutos.

## 4. Renovación de token

Endpoint `POST /api/v1/auth/token/renovar/` con `{"refresh"}`. Mantiene la sesión sin pedir la contraseña.

1. **Recibir el refresh token.**
   - Usar `TokenRefreshView` de simplejwt con un serializer propio.
   - Rechazar refresh vencido, alterado o en blacklist con `401` y `refresh_invalido`.
2. **Emitir un nuevo token de acceso.**
   - Antes de emitir, leer al usuario de la base y comprobar: `is_active=True` y que el `token_version` del token sea igual al de la base. Si no, `401` (así funciona el cierre de todas las sesiones en las secciones 6 y 7).
   - Recalcular los claims con los datos actuales, para que un cambio de rol o la verificación de correo se reflejen en la siguiente renovación.
3. **Rotar el refresh y meter el anterior a la blacklist.**
   - Agregar `rest_framework_simplejwt.token_blacklist` a `INSTALLED_APPS` y correr `migrate`.
   - Configurar `ROTATE_REFRESH_TOKENS = True` y `BLACKLIST_AFTER_ROTATION = True`.
   - Respuesta `200`: `{"access", "refresh"}`; el cliente debe reemplazar ambos.
   - Programar limpieza semanal de tokens vencidos con `python manage.py flushexpiredtokens` (tarea programada o comando manual documentado).

**Pruebas mínimas:** renovación correcta devuelve un refresh nuevo; reusar el refresh anterior falla; usuario desactivado no renueva; `token_version` distinto no renueva; el cambio de rol aparece en el nuevo token.

## 5. Cierre de sesión

Endpoint `POST /api/v1/auth/logout/` con `{"refresh"}`, requiere token de acceso.

1. **Meter el refresh token a la blacklist.**
   - Crear `RefreshToken(refresh)` y llamar `.blacklist()`.
   - Verificar que el refresh pertenezca al usuario del token de acceso; si no, `403`.
   - Si el refresh ya estaba en blacklist o vencido, responder `205` igual: el objetivo (sesión cerrada) ya se cumple.
   - El token de acceso sigue siendo válido hasta que caduca (máx. 15 min). Es aceptable porque el gateway lo borra en el paso siguiente.
2. **Borrar los tokens de la sesión del gateway.**
   - La vista de logout de `web/` llama al endpoint anterior y después ejecuta `request.session.flush()`.
   - La vista solo acepta `POST` con token CSRF, para que un enlace externo no pueda cerrar la sesión del usuario.
   - Redirigir al inicio con el mensaje "Cerraste sesión".
   - Opcional: endpoint `POST /api/v1/auth/logout-todo/` que incrementa `token_version` y cierra la sesión en todos los dispositivos.

**Pruebas mínimas:** tras el logout, renovar con ese refresh falla; logout con refresh de otro usuario da 403; logout repetido no da error.

## 6. Recuperación de contraseña

Dos endpoints públicos: uno pide el enlace y otro fija la nueva contraseña.

1. **Recibir el correo.**
   - `POST /api/v1/auth/recuperar/` con `{"email"}`, normalizado.
   - Solo enviar si la cuenta existe y `is_active=True`.
2. **Responder siempre con un mensaje genérico.**
   - Siempre `200` con "Si el correo está registrado, te enviamos un enlace".
   - Enviar el correo con `transaction.on_commit` o en segundo plano, para que la respuesta tarde lo mismo exista o no la cuenta.
3. **Generar un enlace de un solo uso que expire.**
   - Usar `default_token_generator.make_token(usuario)` de Django y `urlsafe_base64_encode(force_bytes(usuario.pk))` como `uid`.
   - Este token es de un solo uso por diseño: depende del hash de la contraseña y de `last_login`, así que deja de servir en cuanto la contraseña cambia.
   - Configurar `PASSWORD_RESET_TIMEOUT = 3600` (1 hora).
   - Enlace: `{FRONTEND_URL}/restablecer/<uid>/<token>/`. Plantilla con aviso "Si no pediste este cambio, ignora este correo".
4. **Validar el token y recibir la nueva contraseña.**
   - `POST /api/v1/auth/restablecer/` con `{"uid", "token", "password", "password_confirmacion"}`.
   - Decodificar el `uid`, buscar al usuario y validar con `default_token_generator.check_token`. Inválido o vencido → `400` con `enlace_invalido` y "El enlace no es válido o ya expiró. Solicita uno nuevo".
5. **Validar la nueva contraseña.**
   - Mismas reglas que en el registro: coincidencia y `validate_password(password, user=usuario)`.
   - Guardar con `usuario.set_password(password)` y `save()`.
6. **Invalidar las sesiones abiertas.**
   - Incrementar `usuario.token_version` en el mismo `save()`; los refresh existentes dejan de renovar (sección 4).
   - Si la cuenta no estaba verificada, marcar `email_verificado=True`: abrir el enlace prueba que el correo es suyo.
   - Enviar correo de aviso "Tu contraseña fue cambiada" y redirigir al login.

**Pruebas mínimas:** correo inexistente responde igual que uno real; restablecimiento correcto; mismo enlace usado dos veces falla; enlace vencido falla; tras restablecer, el refresh anterior ya no renueva.

## 7. Cambio de contraseña

Endpoint `POST /api/v1/auth/cambiar-password/`, requiere token de acceso.

1. **Pedir la contraseña actual y la nueva.**
   - Body: `{"password_actual", "password_nueva", "password_confirmacion"}`, todos `write_only`.
2. **Verificar la actual.**
   - `usuario.check_password(password_actual)`; si falla, `400` con `password_actual_incorrecta`.
   - Contar este fallo para el límite de intentos (sección 9): evita adivinar la contraseña con una sesión robada.
3. **Validar la nueva.**
   - Coincidencia con la confirmación y `validate_password(password_nueva, user=usuario)`.
   - Rechazar si es igual a la actual (`check_password(password_nueva)` devuelve `True`): `password_repetida`.
4. **Guardar e invalidar las demás sesiones.**
   - `set_password`, incrementar `token_version` y `save()`.
   - Emitir y devolver un par de tokens nuevo con el `token_version` actualizado, para que el dispositivo actual no pierda la sesión.
   - El gateway reemplaza los tokens guardados en su sesión.
5. **Avisar por correo del cambio.**
   - Plantilla `emails/password_cambiada.html` con fecha, hora y la indicación "Si no fuiste tú, restablece tu contraseña" con enlace a recuperación.

**Pruebas mínimas:** cambio correcto; contraseña actual incorrecta; nueva igual a la actual; el refresh de otro dispositivo deja de renovar; el dispositivo actual sigue funcionando con los tokens nuevos.

## 8. Roles y permisos

Dos roles: `cliente` compra y usa el agente; `administrador` gestiona catálogo, pedidos y usuarios.

1. **Definir los roles.**
   - Campo `rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.CLIENTE)` con `class Rol(models.TextChoices)`.
   - El primer administrador se crea con `python manage.py createsuperuser` y un comando propio `asignar_admin <email>`; nadie puede registrarse como admin desde la API.
2. **Incluir el rol en el JWT.**
   - Claim `rol` agregado en el login y recalculado en cada renovación (secciones 3 y 4).
3. **Crear clases de permiso en DRF.**
   - En un paquete compartido (por ejemplo `comun/permisos.py`), crear `EsCliente`, `EsAdministrador`, `EsDuenoOAdmin` (el usuario solo ve sus propios pedidos, direcciones y conversaciones) y `CorreoVerificado`.
   - Cada clase lee el rol desde el token, no desde la base, para que funcione en todos los servicios.
4. **Proteger cada endpoint según el rol.**
   - Default en `REST_FRAMEWORK`: `DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]`; los endpoints públicos declaran `AllowAny` explícitamente.
   - Hacer una matriz endpoint × rol en el README de cada servicio. Ejemplo: `GET /productos/` público; `POST /productos/` solo admin; `POST /pedidos/` cliente con correo verificado; `GET /pedidos/<id>/` dueño o admin.
   - Responder `401` sin token y `403` con token pero sin permiso.
5. **Permitir al admin asignar roles.**
   - `PATCH /api/v1/usuarios/<id>/rol/` con `{"rol"}`, solo administradores.
   - Un admin no puede quitarse su propio rol, para no dejar el sistema sin administradores.
   - Registrar quién cambió el rol y cuándo (tabla `CambioRol` o `django-simple-history`).

**Pruebas mínimas:** por cada endpoint protegido, una prueba sin token (401), una con rol equivocado (403) y una con el rol correcto; un cliente no puede ver el pedido de otro.

## 9. Límite de intentos

Frena ataques de fuerza bruta y el abuso del envío de correos.

1. **Configurar throttling de DRF.**
   - Crear `ScopedRateThrottle` por endpoint con estas tasas iniciales:

| Endpoint | Límite | Por |
| --- | --- | --- |
| `login/` | 10 / minuto | IP |
| `registro/` | 5 / hora | IP |
| `recuperar/` | 3 / hora | IP y correo |
| `reenviar-verificacion/` | 3 / hora | IP y correo |
| `2fa/verificar/` | 5 / 5 minutos | token temporal |

- El throttling por correo requiere una clase propia que use el email del body como clave.
- DRF guarda los contadores en la caché: en desarrollo `LocMemCache`; con varios procesos, Redis.
- Al rebasar el límite: `429` con `demasiados_intentos` y el encabezado `Retry-After`.

2. **Bloquear temporalmente tras varios intentos fallidos.**
   - Instalar `django-axes`, agregar `AxesStandaloneBackend` al inicio de `AUTHENTICATION_BACKENDS` y su middleware.
   - Configurar `AXES_FAILURE_LIMIT = 5`, `AXES_COOLOFF_TIME = timedelta(minutes=15)`, `AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]` (bloquea la combinación correo + IP, para que un atacante no pueda bloquear a cualquier usuario desde otra IP).
   - `AXES_RESET_ON_SUCCESS = True`.
   - Respuesta al bloqueo: `403` con `cuenta_bloqueada_temporalmente` y "Intenta de nuevo en 15 minutos o restablece tu contraseña".
   - Comando para desbloquear manualmente: `python manage.py axes_reset_username <email>`.
3. **Registrar los intentos fallidos.**
   - `django-axes` guarda cada intento en `AccessAttempt` (correo, IP, fecha); visible en el admin de Django.
   - Configurar `logging` para escribir en el log de seguridad: login fallido, bloqueo, recuperación solicitada, cambio de contraseña. Nunca registrar contraseñas ni tokens.

**Pruebas mínimas:** el sexto intento fallido bloquea; tras el bloqueo, la contraseña correcta tampoco entra; después del enfriamiento vuelve a entrar; el límite de recuperación devuelve 429. En pruebas, desactivar o reiniciar axes entre casos (`AXES_ENABLED = False` en la configuración de test, salvo en sus pruebas).

## 10. Validación de JWT en los servicios

Catálogo, pedidos, agente y diagnóstico reconocen al usuario leyendo el token, sin consultar la base de `svc-usuarios`.

1. **Firmar los tokens con RS256 en `svc-usuarios`.**
   - Generar el par de llaves una vez con `python infra/generar_llaves.py` (crea `infra/llaves/privada.pem` y `publica.pem`, sin depender de `openssl`).
   - En `SIMPLE_JWT`: `ALGORITHM = "RS256"`, `SIGNING_KEY` = privada, `VERIFYING_KEY` = pública, `ISSUER = "agroia-usuarios"`.
   - Las llaves se leen de los archivos que indican `JWT_PRIVATE_KEY_PATH` y `JWT_PUBLIC_KEY_PATH`; `infra/llaves/` y `*.pem` están en `.gitignore`.
2. **Distribuir la llave pública a los demás servicios.**
   - Cada servicio recibe solo `JWT_PUBLIC_KEY_PATH`; la privada nunca sale de `svc-usuarios`.
   - `docker-compose.yml` monta `publica.pem` como *secret* (solo lectura) en `/run/secrets/jwt_publica.pem` de cada contenedor.
3. **Crear la clase de autenticación compartida.**
   - Usar `JWTStatelessUserAuthentication` de simplejwt: valida firma, expiración e `iss` sin buscar al usuario en la base.
   - Configurarla en `DEFAULT_AUTHENTICATION_CLASSES` de cada servicio, con el mismo bloque `SIMPLE_JWT` (solo `VERIFYING_KEY`, sin `SIGNING_KEY`).
   - Poner esta configuración y las clases de permiso de la sección 8 en un paquete común del monorepo (por ejemplo `comun/`), para no copiar código entre servicios.
4. **Leer el id y el rol del usuario desde el token.**
   - `request.user` será un `TokenUser`: `request.user.id` y `request.user.token["rol"]`.
   - Los modelos de otros servicios guardan `usuario_id` como entero o UUID simple, sin `ForeignKey` a `Usuario` (viven en otra base).
   - Si un servicio necesita datos del usuario que no están en el token (por ejemplo, la dirección en pedidos), llama a `svc-usuarios` reenviando el token del usuario.

**Pruebas mínimas:** en cada servicio, token válido aceptado; token firmado con otra llave rechazado; token vencido rechazado; token sin `rol` rechazado en endpoints que lo piden.

## 11. Sesión en el gateway (`web/`)

El gateway guarda los JWT en su sesión de servidor; el navegador solo recibe la cookie de sesión de Django.

1. **Guardar los JWT en la sesión de Django.**
   - Usar `SESSION_ENGINE = "django.contrib.sessions.backends.db"` (o `cache` con Redis).
   - Al hacer login: `request.session["access"]`, `["refresh"]`, `["usuario"]` (id, nombre, rol, email\_verificado) y llamar `request.session.cycle_key()` para evitar fijación de sesión.
   - Crear un cliente HTTP único (`web/servicios/api.py`) que agrega `Authorization: Bearer <access>` a cada llamada a los servicios.
2. **Configurar la cookie de sesión.**
   - `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = "Lax"`, `SESSION_COOKIE_AGE = 604800` (7 días, igual que el refresh).
   - En producción: `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`; en desarrollo pueden quedar en `False` porque se usa HTTP.
   - Todos los formularios llevan `{% csrf_token %}`.
3. **Renovar el token de acceso automáticamente.**
   - En el cliente HTTP: si un servicio responde `401`, llamar a `/token/renovar/`, guardar el par nuevo en la sesión y repetir la petición una sola vez.
   - Opcional: renovar antes de que caduque leyendo el `exp` del token, para ahorrar el primer `401`.
4. **Redirigir al login cuando el refresh expire.**
   - Si la renovación falla: `session.flush()` y redirigir a `/login/?next=<ruta actual>` con el mensaje "Tu sesión expiró".
   - Crear el decorador `@login_requerido` y `@rol_requerido("administrador")` para las vistas del gateway.
   - Hacer disponible `usuario` en todas las plantillas con un *context processor*, para el menú y el banner de correo sin verificar.

**Pruebas mínimas:** en el navegador no aparece el JWT (ni en cookies ni en el HTML); acceso vencido se renueva sin que el usuario lo note; refresh vencido manda al login; una vista de admin redirige a un cliente.

## 12. Autenticación de dos pasos (2FA)

Segundo factor con app autenticadora (TOTP): obligatorio para administradores y opcional para clientes. Librerías: `pyotp` y `qrcode`.

1. **Generar el secreto TOTP y mostrar el código QR.**
   - Modelo `Dispositivo2FA`: `usuario` (OneToOne), `secreto` (cifrado), `confirmado` (bool), `creado_en`.
   - Cifrar el secreto en la base con `cryptography.fernet` y una llave en `.env`: si se filtra la base, los secretos no sirven.
   - `POST /api/v1/auth/2fa/activar/` genera `pyotp.random_base32()`, lo guarda sin confirmar y devuelve el QR en base64 de `pyotp.TOTP(secreto).provisioning_uri(name=email, issuer_name="AgroIA")`, más el secreto en texto para escribirlo a mano.
2. **Confirmar la activación con un primer código.**
   - `POST /api/v1/auth/2fa/confirmar/` con `{"codigo"}`; validar con `totp.verify(codigo, valid_window=1)` (tolera 30 s de desfase de reloj).
   - Solo al confirmar se marca `confirmado=True` y `tiene_2fa=True`. Si no confirma, el 2FA no se activa.
3. **Generar códigos de respaldo.**
   - Al confirmar, generar 10 códigos de 8 caracteres con `secrets.token_hex(4)`.
   - Guardarlos con hash (`make_password`) en el modelo `CodigoRespaldo` con campo `usado`; mostrarlos al usuario una sola vez, con opción de descargarlos.
   - Endpoint para regenerarlos que pida contraseña e invalide los anteriores.
4. **Validar el código en el login.**
   - `POST /api/v1/auth/2fa/verificar/` con `{"token_temporal", "codigo"}` (token del paso 4 de la sección 3).
   - Aceptar código TOTP o de respaldo; un código de respaldo se marca `usado`.
   - Evitar reutilizar el mismo TOTP: guardar el último intervalo usado y rechazar uno igual o anterior.
   - Si es válido, emitir los JWT normales. Máximo 5 intentos por token temporal (sección 9).
5. **Permitir desactivarlo pidiendo contraseña.**
   - `POST /api/v1/auth/2fa/desactivar/` con `{"password", "codigo"}`; borra el dispositivo y los códigos.
   - Enviar correo "Se desactivó la verificación en dos pasos".
   - Un administrador no puede desactivarlo (ver siguiente paso).
6. **Exigirlo a los administradores.**
   - Si un admin sin 2FA inicia sesión, el login devuelve `{"requiere_configurar_2fa": true}` y el gateway lo manda a la pantalla de activación antes de entrar al panel.
   - `EsAdministrador` (sección 8) también revisa un claim `mfa: true`, que solo existe en tokens emitidos tras pasar el 2FA.

**Pruebas mínimas:** activación completa; código incorrecto; código de respaldo funciona una sola vez; mismo TOTP rechazado la segunda vez; admin sin 2FA no entra al panel. Para generar códigos en las pruebas: `pyotp.TOTP(secreto).now()`.

## 13. Envío de correos

Un solo módulo (`usuarios/correos.py`) envía todos los correos; se construye primero porque registro y recuperación dependen de él.

1. **Usar el backend de consola en desarrollo.**
   - `EMAIL_BACKEND` se lee de `.env`; valor por defecto `django.core.mail.backends.console.EmailBackend`. Los correos se imprimen en la terminal con el enlace listo para copiar.
   - En pruebas, Django usa `locmem` automáticamente y los correos quedan en `django.core.mail.outbox` para verificarlos.
2. **Configurar SMTP real para la demo.**
   - Variables: `EMAIL_HOST`, `EMAIL_PORT=587`, `EMAIL_USE_TLS=True`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL="AgroIA <correo@dominio>"`.
   - Opción sencilla: una cuenta de Gmail del proyecto con verificación en dos pasos activada y una "contraseña de aplicación" (la contraseña normal no funciona).
   - Probar el envío con `python manage.py sendtestemail tu@correo.com`.
   - Revisar que no lleguen a spam; si llegan, considerar un servicio de correo transaccional.
3. **Guardar las credenciales en `.env`.**
   - Agregar todas las variables a `.env.example` con valores vacíos o de ejemplo.
   - Confirmar que `.env` esté en `.gitignore` antes del primer commit del servicio.
4. **Crear las plantillas de cada correo.**
   - Función `enviar_correo(destinatario, asunto, plantilla, contexto)` que usa `EmailMultiAlternatives` con versión `.txt` y `.html` renderizadas con `render_to_string`.
   - Plantilla base `emails/base.html` con logo, colores y pie "Este correo fue enviado automáticamente, no respondas". Estilos en línea (los clientes de correo ignoran CSS externo).
   - Correos: verificación, recuperación, contraseña cambiada, 2FA desactivado y, si se hace, inicio de sesión desde dispositivo nuevo.
   - Envolver el envío en `try/except`, registrar el error en el log y no romper la petición del usuario.
   - Opcional: enviar en segundo plano con Celery para que la respuesta no espere al servidor de correo.

**Pruebas mínimas:** cada flujo deja exactamente un correo en `mail.outbox` con el destinatario y asunto correctos y el enlace válido; un error del servidor SMTP no rompe el registro.

## 14. Aviso de privacidad

La plataforma guarda nombres, correos, teléfonos, direcciones, conversaciones con el agente e imágenes de diagnóstico, así que necesita un aviso de privacidad.

1. **Redactar la página del aviso.**
   - Página pública `/aviso-de-privacidad/` en el gateway, enlazada en el pie de todas las páginas y en el formulario de registro.
   - Debe decir: quién es el responsable de los datos, qué datos se recaban, para qué se usan (pedidos, envíos, mejorar el agente), si se comparten con terceros, cómo ejercer los derechos de acceso, rectificación, cancelación y oposición (ARCO) y la fecha de última actualización.
   - Como es un proyecto académico, aclararlo en el aviso. Si se usará con productores reales, conviene que lo revise alguien con conocimiento legal.
2. **Agregar la casilla de aceptación en el registro.**
   - Casilla sin marcar por defecto: "Leí y acepto el \[aviso de privacidad\]", con enlace que abre en otra pestaña.
   - El botón de registro se habilita solo con la casilla marcada; el backend lo valida de nuevo (sección 1).
3. **Guardar la fecha de aceptación.**
   - Campos `acepto_privacidad_en` (datetime) y `version_privacidad` (texto, por ejemplo `"2026-10"`) en `Usuario`.
   - Si el aviso cambia, subir la versión en `settings`; al iniciar sesión, si la versión del usuario es anterior, el gateway le pide aceptar la nueva antes de continuar.

**Pruebas mínimas:** el registro sin aceptar falla; la fecha y la versión se guardan; un usuario con versión anterior ve la pantalla de aceptación.

## 15. Opcionales

Solo si sobra tiempo después del sprint de 2FA.

### Login con Google

1. **Configurar `django-allauth` y las credenciales OAuth.**
   - Crear el proyecto en Google Cloud Console, configurar la pantalla de consentimiento y crear un "ID de cliente OAuth" tipo aplicación web.
   - URI de redirección: `http://localhost:8000/accounts/google/login/callback/` en desarrollo y la del dominio real después.
   - Guardar `GOOGLE_CLIENT_ID` y `GOOGLE_CLIENT_SECRET` en `.env`.
   - El flujo OAuth vive en el gateway (necesita redirecciones del navegador); el gateway le pasa a `svc-usuarios` el token de Google para que lo valide.
2. **Crear o vincular la cuenta.**
   - Si el correo de Google ya existe, vincular a esa cuenta; si no, crearla sin contraseña usable (`set_unusable_password()`).
   - Marcar `email_verificado=True`: Google ya lo verificó.
   - Pedir la aceptación del aviso de privacidad en el primer acceso.
3. **Emitir el JWT igual que en el login normal.**
   - Mismos claims y mismo paso de 2FA si el usuario lo tiene activo.

### Historial de accesos

1. **Registrar fecha, IP y dispositivo de cada login.**
   - Modelo `RegistroAcceso`: `usuario`, `fecha`, `ip`, `user_agent`, `exitoso`.
   - Tomar la IP de `X-Forwarded-For` que reenvía el gateway y el navegador con la librería `user-agents`.
   - Borrar registros de más de 90 días.
2. **Mostrar el historial en el perfil.**
   - `GET /api/v1/auth/accesos/` con los últimos 20 accesos del usuario, paginado.
   - Mostrar "Chrome en Windows · 13 oct 2026, 08:30", no el user agent crudo.
3. **Avisar por correo de un dispositivo nuevo.**
   - Considerar nuevo un par navegador + sistema operativo que no aparece en los últimos 90 días.
   - Correo con fecha, dispositivo y enlace para cambiar la contraseña si no fue el usuario.
