# Contrato de identidad

Noviembre de 2026 · Entrega 3

Qué emite `svc-usuarios` y qué espera cada servicio de un token. Cualquier proveedor de identidad que cumpla este contrato puede reemplazar a `svc-usuarios` sin tocar los demás servicios. La última sección compara el contrato con [ms-usuarios](https://github.com/LeoMtzGlz/ms-usuarios), que el grupo está construyendo.

## Resumen

| Concepto | Valor |
| --- | --- |
| Formato | JWT (`djangorestframework-simplejwt` 5.5.1 en svc-usuarios; PyJWT 2.15.1 en svc-ia) |
| Algoritmo | `RS256`. Firma con la llave privada; verifica con la pública |
| Emisor (`iss`) | Variable `JWT_ISSUER`; por defecto `agroia-usuarios`. Debe valer lo mismo en todos los servicios |
| Access | 15 minutos. Va en `Authorization: Bearer <access>` |
| Refresh | 7 días. Solo sirve en `POST /api/v1/auth/token/renovar/` de svc-usuarios |
| Rotación | Cada renovación devuelve un par nuevo y el refresh anterior entra a la blacklist |
| Cierre de sesión | `logout` mete el refresh a la blacklist; `logout-todo` y los cambios de contraseña suben `token_version` |
| Roles | `cliente` y `administrador` |
| Id del usuario | UUID (versión 4), en texto en el claim `user_id` |

## Llaves

- Se generan una vez con `python infra/generar_llaves.py` (RSA de 2048 bits) en `infra/llaves/`, que nunca se sube al repositorio.
- `docker-compose.yml` monta la pública en `/run/secrets/jwt_publica.pem` de cada servicio y la privada en `/run/secrets/jwt_privada.pem` **solo de svc-usuarios**.
- Variables: `JWT_PRIVATE_KEY_PATH` (solo svc-usuarios, que no arranca sin ella) y `JWT_PUBLIC_KEY_PATH` (todos).

## Claims

Access y refresh llevan los mismos claims; solo cambia `token_type`. No llevan datos personales (correo, nombre, teléfono, dirección): el JWT se puede leer sin la llave.

| Claim | Tipo | Ejemplo | Significado |
| --- | --- | --- | --- |
| `token_type` | texto: `access` o `refresh` | `"access"` | Los servicios solo aceptan `access` |
| `user_id` | texto (UUID) | `"8d3f6c2a-1b4e-4f7a-9c5d-2e6f8a0b1c3d"` | `id` del usuario en svc-usuarios; es el `usuario_id` que guardan los demás servicios |
| `rol` | texto: `cliente` o `administrador` | `"cliente"` | Lo leen las clases de permiso. Sin `rol` válido, 403 |
| `email_verificado` | booleano | `true` | Comprar exige `true` |
| `token_version` | entero ≥ 0 | `0` | Versión de sesión. svc-usuarios rechaza renovar si no coincide con la de la base |
| `iss` | texto | `"agroia-usuarios"` | Emisor; se compara con `JWT_ISSUER` |
| `iat` | entero (segundos Unix) | `1795107600` | Emisión |
| `exp` | entero (segundos Unix) | `1795108500` | Vencimiento. Obligatorio; sin margen (`LEEWAY = 0`) |
| `jti` | texto (32 hexadecimales) | `"4f1c2b0a9d8e4c7b8a6f5e4d3c2b1a09"` | Id único del token; identifica al refresh en la blacklist |

Ejemplo de payload de un access:

```json
{
  "token_type": "access",
  "exp": 1795108500,
  "iat": 1795107600,
  "jti": "4f1c2b0a9d8e4c7b8a6f5e4d3c2b1a09",
  "user_id": "8d3f6c2a-1b4e-4f7a-9c5d-2e6f8a0b1c3d",
  "rol": "cliente",
  "email_verificado": true,
  "token_version": 0,
  "iss": "agroia-usuarios"
}
```

Los claims se calculan con los datos de la base al iniciar sesión y en cada renovación: un cambio de rol o la verificación del correo se reflejan en el siguiente token, no en el que ya se emitió.

## Endpoints de identidad (svc-usuarios)

| Endpoint | Entrada | Respuesta |
| --- | --- | --- |
| `POST /api/v1/auth/login/` | `{"email", "password"}` | `{"access", "refresh", "usuario": {"id", "nombre", "rol", "email_verificado"}}` |
| `POST /api/v1/auth/token/renovar/` | `{"refresh"}` | `{"access", "refresh"}` |
| `POST /api/v1/auth/logout/` | `{"refresh"}` + access | 205 sin cuerpo |
| `POST /api/v1/auth/logout-todo/` | access | `{"mensaje"}` |

El resto (registro, verificación, recuperación, cambio de contraseña y de rol) está en el [README de svc-usuarios](../svc-usuarios/README.md#endpoints--rol).

## Cómo valida cada servicio

| Servicio | Cómo | Qué revisa |
| --- | --- | --- |
| svc-tienda, svc-contenido, svc-usuarios | `agroia_comun.autenticacion.AutenticacionJWT` (simplejwt `JWTStatelessUserAuthentication`), configurada con `configurar_jwt(llave_publica, issuer=JWT_ISSUER)` | Firma RS256 con la pública, `exp`, `iss`, `token_type == "access"`, `user_id` presente y UUID. No consulta la base de svc-usuarios |
| svc-ia (FastAPI) | `app/seguridad.py` con PyJWT | Las mismas reglas: `require` de `exp`, `iss` y `jti`, `token_type == "access"`, `user_id` UUID, emisor `JWT_ISSUER` |
| svc-usuarios, al renovar | `RefreshToken` de simplejwt más la base | Además: blacklist, `is_active` y `token_version` contra la base |
| web (gateway) | Proxy `/api/<servicio>/` con `agroia_comun.tokens.validar_access` (PyJWT); las páginas guardan los tokens en la sesión del servidor | Las mismas reglas que svc-ia antes de reenviar; no revisa roles (ver «Dos capas de validación») |

Permisos (en `agroia_comun.permisos` y su equivalente en svc-ia), leídos del token:

| Clase | Pide | Si falla |
| --- | --- | --- |
| `IsAuthenticated` | Token de acceso válido | 401 `no_autenticado` o `token_invalido` |
| `EsCliente`, `EsAdministrador` | `rol` igual a ese rol | 403 `sin_permiso` |
| `EsDuenoOAdmin` | Rol válido; a nivel objeto, dueño (`usuario_id == user_id`) o administrador | 403 `sin_permiso` |
| `CorreoVerificado` | `email_verificado` en `true` | 403 `email_no_verificado`, «Verifica tu correo para poder hacer esta acción.» |

Con `AUTH_ACTIVA=False` (solo con `DEBUG=True`) se apagan las revisiones de rol; un token que llega se sigue validando.

## Dos capas de validación

| Capa | Dónde | Qué revisa | Si falla |
| --- | --- | --- | --- |
| 1. Gateway | `web`, proxy `/api/<servicio>/<ruta>` (`agroia_comun.tokens.validar_access`) | Firma RS256, `JWT_ISSUER`, `exp`, `token_type == "access"` y `user_id` UUID, antes de reenviar. Las rutas públicas (login, registro, verificación, recuperación, catálogo) pasan sin token | 401 `no_autenticado` o `token_invalido`, sin llegar al servicio |
| 2. Servicio | Cada servicio (`AutenticacionJWT` en los Django, `app/seguridad.py` en svc-ia) | Las mismas reglas, y además los roles y la verificación del correo | 401, o 403 `sin_permiso` / `email_no_verificado` |

La segunda capa no se quita aunque exista la primera (defensa en profundidad): un servicio nunca confía en que la petición pasó por el gateway.

**El proxy nunca toma el token de la sesión del navegador.** Solo acepta `Authorization: Bearer <access>`; una petición a `/api/` con una cookie de sesión válida y sin ese encabezado es anónima (401 en una ruta privada). Así ningún sitio ajeno puede usar la sesión de un usuario a través del proxy, y el proxy no necesita CSRF. Las páginas del gateway sí usan la sesión: el gateway guarda los tokens en `web_db` y los manda él mismo.

## Errores

Todos con el formato común `{"error": "codigo_corto", "detalle": "mensaje para el usuario"}`.

| Código | Estado | Cuándo |
| --- | --- | --- |
| `no_autenticado` | 401 | No viene `Authorization` |
| `token_invalido` | 401 | Firma de otra llave, vencido, otro emisor, un refresh usado como access, `user_id` que no es UUID, o un JWT mal formado |
| `credenciales_invalidas` | 401 | Login con correo inexistente, contraseña incorrecta o cuenta desactivada (mismo mensaje) |
| `refresh_invalido` | 401 | Renovar con un refresh vencido, alterado, en blacklist o de una sesión cerrada |
| `sin_permiso` | 403 | Rol equivocado, o logout con el refresh de otro usuario |
| `email_no_verificado` | 403 | Acción que exige correo verificado (crear un pedido) |
| `cuenta_bloqueada_temporalmente` | 403 | 5 logins fallidos con el mismo correo desde la misma IP; dura 15 minutos |
| `demasiados_intentos` | 429 | Se rebasó el límite de intentos; trae `Retry-After` en segundos |
| `2fa_no_disponible` | 501 | La cuenta tiene 2FA, que todavía no se implementa |

## IP del cliente y puertos publicados

Los límites de intentos, el bloqueo de axes y el log de seguridad necesitan la IP del cliente. Los servicios confían en **un** proxy, el gateway `web` (`NUM_PROXIES = 1` en DRF y `AXES_CLIENT_IP_CALLABLE = agroia_comun.seguridad.ip_cliente`): toman el último valor de `X-Forwarded-For`, que agrega el gateway, o la IP de la conexión si no viene.

Quien llegue directo a un servicio podría mandar su propio `X-Forwarded-For` y hacerse pasar por otra IP. Por eso los puertos directos (8001 a 8005) **solo se publican en `127.0.0.1` y solo para desarrollo** (Swagger de cada servicio, Postman por servicio, depuración): no son visibles en la red, no forman parte de la API pública y nunca deben publicarse en `0.0.0.0`. El punto de entrada es el gateway (`8000`); en el despliegue (Entrega 5) solo se publica web.

**Cumplido en la fase del gateway:** el gateway pone en `X-Forwarded-For` la IP real del cliente (la `REMOTE_ADDR` de la conexión que recibe) y **no** reenvía el `X-Forwarded-For` que mande el cliente (`web/clientes/api.py`; hay pruebas para el proxy y para el login desde `/iniciar-sesion/`). Si un balanceador se pone delante de web en el despliegue, esta regla se revisa. Si lo reenviara, cualquier cliente elegiría la IP con la que se le cuentan los intentos y podría esquivar el límite de logins y el bloqueo por correo + IP.

## Log de seguridad

Cada servicio escribe una línea JSON por evento en el logger `seguridad` (`agroia_comun.seguridad.registrar_evento`; en svc-ia, `app/eventos.py`): `evento`, `fecha` (UTC), `servicio`, `ip`, `metodo`, `ruta`, `usuario_id` y datos del evento. Todos los 401 y 403 quedan como `acceso_denegado`; svc-usuarios registra además login, bloqueo, renovación rechazada, logout, recuperación y cambios de contraseña y de rol. Se descarta cualquier dato cuya llave contenga `password`, `token`, `refresh`, `access`, `authorization`, `secreto` o `uid`.

## Límites conocidos

- **Un access ya emitido sigue sirviendo hasta que vence (máximo 15 minutos)** después de `logout`, `logout-todo`, un cambio de contraseña, un cambio de rol o la desactivación de la cuenta. Los servicios validan el token sin consultar la base, así que no conocen `token_version` ni la blacklist. Lo que sí se corta de inmediato es la renovación. Si hiciera falta cortarlo antes, la opción sería publicar en Redis los `jti` revocados o el `token_version` vigente (Entrega 4).
- El refresh queda en quien inició sesión: en las pantallas, en la sesión del servidor del gateway (`web_db`), nunca en el navegador; en el proxy `/api/`, en el cliente de API.
- 2FA está preparado en el login, pero todavía no se puede activar.

## Diferencias con ms-usuarios

Revisión de solo lectura de [LeoMtzGlz/ms-usuarios](https://github.com/LeoMtzGlz/ms-usuarios), rama `main`, commit `f8799c9` (13 de noviembre de 2026).

| Tema | Nuestro svc-usuarios | ms-usuarios |
| --- | --- | --- |
| Formato de errores | `{"error", "detalle"}` y `campos` solo en validación; código `validacion` | `{"codigo", "mensaje", "campos"}`, con `campos` siempre; código `datos_invalidos` |
| Roles | `cliente`, `administrador` | Además `operativo` (con su clase `EsOperativo`) |
| Estado de la cuenta | `is_active` | `estado`: `pendiente`, `activo` o `inactivo`; `is_active` se deriva de él. Pasar a `inactivo` sube `token_version` |
| Activación | Cuenta activa desde el registro; se verifica el correo con un enlace | Cuenta `pendiente` hasta escribir un código (`cuenta_pendiente`, `codigo_invalido`, `codigo_expirado`), por correo o WhatsApp |
| Id del usuario | UUID | UUID (lo adoptamos en la Entrega 3) |
| Nombre | `nombre`, `apellidos` | `first_name`, `last_name` de Django |
| Otros campos | `telefono` libre, `tiene_2fa`, direcciones | `telefono` único en E.164, `telefono_verificado`, `canal_preferido`, `debe_cambiar_password`; sin direcciones |
| Emisor | `agroia-usuarios` (configurable con `JWT_ISSUER`) | `svc-usuarios`, fijo en `settings.py` |
| Llaves | Rutas en `JWT_PRIVATE_KEY_PATH` y `JWT_PUBLIC_KEY_PATH` | `JWT_LLAVE_PRIVADA` y `JWT_LLAVE_PUBLICA`: ruta o el PEM en la variable |
| Duraciones | Access 15 min, refresh 7 días, rotación y blacklist | Access 15 min y refresh 7 días; sin rotación ni blacklist configuradas todavía |
| Login y claims | Login, renovación y logout con claims propios | Todavía no expone login ni agrega claims propios (`rol`, `email_verificado`, `token_version`) |
| Bloqueo por intentos | django-axes, `cuenta_bloqueada_temporalmente` | Código `cuenta_bloqueada` definido; sin axes ni throttling configurados todavía |
| Contraseñas | Hasher por defecto de Django (PBKDF2) | Argon2 primero |
| Auditoría | Log `seguridad` en JSON | `registrar_evento()` en el log `svc.auditoria`, en JSON |
| Salud | `GET /salud/` | `GET /api/v1/salud/` |

Coinciden: RS256 con llaves PEM, `USER_ID_CLAIM = "user_id"`, Bearer, las duraciones, `token_version`, los códigos `credenciales_invalidas`, `token_invalido`, `sin_permiso`, `no_encontrado` y `demasiados_intentos`, y el correo único sin distinguir mayúsculas.

### Qué haría falta para usar ms-usuarios en lugar del nuestro

1. **En ms-usuarios:** exponer login, renovación (con `ROTATE_REFRESH_TOKENS` y blacklist) y logout, y agregar al token los claims `rol`, `email_verificado` y `token_version` con los tipos de este contrato.
2. **Roles:** decidir qué hace `operativo` en nuestros servicios. Hoy lo rechazarían con 403 en todo lo que pide rol, porque no está en `ROLES`.
3. **Emisor y llaves:** poner `JWT_ISSUER=svc-usuarios` en el `.env` (o cambiar el suyo a `agroia-usuarios`) y que firme con la llave privada de `infra/llaves/`, montada como secret.
4. **Direcciones:** ms-usuarios no las tiene. Hay que agregarlas allá con los mismos campos, o dejar un servicio pequeño de direcciones. svc-tienda no las lee de svc-usuarios (las recibe en el pedido), así que no cambia.
5. **Formato de errores:** no cambiamos el nuestro. El gateway tendría que traducir `{"codigo", "mensaje"}` a `{"error", "detalle"}` en las respuestas de identidad, o ms-usuarios adoptar el nuestro.
6. **Verificación:** su `pendiente` con código reemplaza nuestro enlace de verificación. Para comprar seguiría bastando el claim `email_verificado`.
7. **Pruebas:** `agroia_comun.pruebas.firmar_token` acepta `emisor=` para probar con el emisor de ellos.

Lo que **no** cambia: svc-tienda, svc-contenido y svc-ia solo dependen de este contrato (llave pública, emisor, claims y UUID), no de svc-usuarios.
