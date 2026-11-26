# comun — paquete compartido `agroia_comun`

Código que comparten los servicios. Tiene dos partes:

- **Núcleo, sin Django** (`pip install -e /comun`): `tokens.py` y el paquete `eventos/`. Lo instalan todos, también `svc-ia` (FastAPI), que lo usa para los eventos. Dependencias: PyJWT, cryptography y redis.
- **Extra `[django]`** (`pip install -e "/comun[django]"`): todo lo demás, para `web`, `svc-usuarios`, `svc-tienda` y `svc-contenido`. Agrega simplejwt y django-filter. `svc-ia` valida el JWT con PyJWT en su propio código.

| Módulo | Contenido |
| --- | --- |
| `configuracion.py` | `validar_modo_auth`, `leer_llave_publica` y `configurar_jwt`, para `config/settings.py` (no importa Django) |
| `autenticacion.py` | `AutenticacionJWT`: valida el JWT RS256 con la llave pública, sin consultar svc-usuarios. Registra el esquema Bearer en Swagger |
| `permisos.py` | `EsAdministrador`, `EsCliente`, `CorreoVerificado` (403 `email_no_verificado`), `EsDuenoOAdmin` y los helpers `usuario_id` (devuelve un `uuid.UUID`), `rol_de`, `es_administrador` |
| `seguridad.py` | Log de seguridad: `registrar_evento(evento, request, **datos)` escribe una línea JSON en el logger `seguridad`, sin contraseñas ni tokens; `ip_cliente(request)` (un proxy de confianza) |
| `errores.py` | Manejador de excepciones con el formato común y `ErrorDeNegocio` para las reglas de negocio |
| `openapi.py` | Hook de drf-spectacular `documentar_errores`: agrega a cada respuesta de error de Swagger el esquema común y un ejemplo por código |
| `filtros.py` | `FechaDesde` y `FechaHasta` de django-filter: días completos en la zona del servidor (hora de México) aunque la base guarde en UTC. Los usan los filtros `desde`/`hasta` de pedidos (svc-tienda) y de usuarios (svc-usuarios) |
| `pruebas.py` | Solo para pruebas: par de llaves temporal y `firmar_token(...)` (con `usuario_id` UUID y `emisor=`) |
| `eventos/` (núcleo) | Eventos con Redis Streams (ver [`docs/eventos.md`](../docs/eventos.md)): `catalogo.py` (tipos, streams y campos permitidos), `sobre.py` (sobre común y `correlacion_valida`), `productor.py` (`publicar`, sin romper si Redis no responde), `consumidor.py` (`Consumidor`: grupos, reintentos con espera creciente y política por stream, latido, fallidos, idempotencia, varios hilos y apagado limpio), `operacion.py` y `python -m agroia_comun.eventos estado\|reprocesar\|descartar`, `conexion.py` (clientes con timeout) y `registro.py` (logger `eventos`) |
| `eventos/en_django.py` | `publicar_al_confirmar` (publica con `transaction.on_commit`) y `correlacion_de(request)` |

## Cómo se usa en un servicio

```python
# config/settings.py
from agroia_comun.configuracion import configurar_jwt, leer_llave_publica, validar_modo_auth

AUTH_ACTIVA = booleano("AUTH_ACTIVA", True)
validar_modo_auth(AUTH_ACTIVA, DEBUG)
SIMPLE_JWT = configurar_jwt(leer_llave_publica(JWT_PUBLIC_KEY_PATH, AUTH_ACTIVA))

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["agroia_comun.autenticacion.AutenticacionJWT"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "EXCEPTION_HANDLER": "agroia_comun.errores.manejador_de_excepciones",
    ...
}

SPECTACULAR_SETTINGS = {
    ...,
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "agroia_comun.openapi.documentar_errores",
    ],
}
```

En Swagger, cada vista declara sus errores solo con una descripción, por ejemplo `409: OpenApiResponse(description="`stock_insuficiente` o `producto_no_disponible`.")`. El hook agrega el esquema `Error` y un ejemplo por cada código conocido que aparezca entre comillas invertidas (o el código por omisión del estado HTTP). Para un código de negocio nuevo, agrega su mensaje de ejemplo en `DETALLES`.

En las vistas: `permission_classes = [IsAuthenticated, EsCliente, CorreoVerificado]`, `usuario_id(request)` para el id del usuario y `raise ErrorDeNegocio("stock_insuficiente", "mensaje")` desde `servicios.py`. Los endpoints públicos declaran `AllowAny`.

## Autenticación

Contrato completo en [`docs/contrato-identidad.md`](../docs/contrato-identidad.md).

- El token se firma en svc-usuarios con la llave privada (RS256). Cada servicio recibe solo la llave pública (`JWT_PUBLIC_KEY_PATH`, montada en `/run/secrets/jwt_publica.pem`) y el emisor esperado (`JWT_ISSUER`, por defecto `agroia-usuarios`):

  ```python
  JWT_ISSUER = os.environ.get("JWT_ISSUER", ISSUER_POR_DEFECTO)
  SIMPLE_JWT = configurar_jwt(leer_llave_publica(JWT_PUBLIC_KEY_PATH, AUTH_ACTIVA), issuer=JWT_ISSUER)
  LOGGING = configurar_logging()
  ```

- Se valida la firma, el vencimiento, el emisor, que sea un token de acceso (`token_type: "access"`) y que `user_id` sea un UUID. Los claims que se leen son `user_id`, `rol` y `email_verificado`.
- Sin token: **401** (`no_autenticado`). Token inválido, vencido o con un `user_id` que no es UUID: **401** (`token_invalido`). Rol equivocado o token sin `rol`: **403** (`sin_permiso`). Correo sin verificar donde se pide: **403** (`email_no_verificado`).
- `token_version` y la blacklist solo los revisa svc-usuarios al renovar: un access ya emitido sirve hasta que vence (máximo 15 minutos). Ver los límites conocidos del contrato.
- Cada 401 y 403 queda como `acceso_denegado` en el log `seguridad`. Los `ErrorDeNegocio` no, porque el servicio los registra con un evento propio.

### `AUTH_ACTIVA`

| Valor | Comportamiento |
| --- | --- |
| `True` (por defecto en el código) | Se aplican JWT y roles. |
| `False` (solo en el `.env` local) | Se apagan las revisiones de rol (`EsAdministrador`, `EsCliente`, `CorreoVerificado`, `EsDuenoOAdmin`). Un token que llega se valida igual, y los endpoints que necesitan saber quién es el usuario siguen respondiendo **401** sin token. No hay usuario de desarrollo: el token sale del login de svc-usuarios (o de `infra/emitir_token.py`, solo para pruebas). |

`AUTH_ACTIVA=False` solo se acepta con `DJANGO_DEBUG=True`; con `DEBUG=False` el servicio no arranca. Con `AUTH_ACTIVA=True` y sin la llave pública, tampoco arranca. Para la entrega debe estar en `True`.

## Formato de errores

```json
{"error": "codigo_corto", "detalle": "mensaje para el usuario"}
{"error": "validacion", "detalle": "Revisa los datos enviados.", "campos": {"cantidad": ["..."]}}
```

La lista de códigos está en la [definición técnica](../docs/definicion-tecnica.md#contratos-de-api).

## Cómo se instala

- **Docker:** cada `Dockerfile` copia `comun/` a `/comun` y lo instala en modo editable: los servicios Django con `pip install -e "/comun[django]"` (PyJWT, cryptography, redis, simplejwt y django-filter) y svc-ia con `pip install -e /comun` (sin simplejwt ni Django). `docker-compose.yml` monta `./comun` en `/comun`, así que los cambios de código se ven sin reconstruir; los de `pyproject.toml` piden `docker compose up --build`.
- **Venv local de la raíz:** el `requirements-dev.txt` de la raíz lo instala en modo editable (`-e ./comun`).

No copies este código dentro de los servicios: impórtalo desde `agroia_comun`.

## Pruebas

Corren con un Django mínimo propio (sin base de datos), dentro del contenedor de cualquier servicio Django. Las de `eventos/` usan Redis simulado (`fakeredis`, en los `requirements-dev.txt` de svc-tienda, svc-usuarios, svc-contenido y svc-ia):

```bash
docker compose exec -w /comun svc-tienda pytest
docker compose exec -w /comun svc-tienda ruff check .
```
