# comun — paquete compartido `agroia_comun`

Código que comparten los servicios Django (`web`, `svc-usuarios`, `svc-tienda` y `svc-contenido`). `svc-ia` no lo instala: valida el JWT con PyJWT.

| Módulo | Contenido |
| --- | --- |
| `configuracion.py` | `validar_modo_auth`, `leer_llave_publica` y `configurar_jwt`, para `config/settings.py` (no importa Django) |
| `autenticacion.py` | `AutenticacionJWT`: valida el JWT RS256 con la llave pública, sin consultar svc-usuarios. Registra el esquema Bearer en Swagger |
| `permisos.py` | `EsAdministrador`, `EsCliente`, `CorreoVerificado`, `EsDuenoOAdmin` y los helpers `usuario_id`, `rol_de`, `es_administrador` |
| `errores.py` | Manejador de excepciones con el formato común y `ErrorDeNegocio` para las reglas de negocio |
| `pruebas.py` | Solo para pruebas: par de llaves temporal y `firmar_token(...)` |

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
```

En las vistas: `permission_classes = [IsAuthenticated, EsCliente, CorreoVerificado]`, `usuario_id(request)` para el id del usuario y `raise ErrorDeNegocio("stock_insuficiente", "mensaje")` desde `servicios.py`. Los endpoints públicos declaran `AllowAny`.

## Autenticación

- El token se firma en svc-usuarios con la llave privada (RS256, emisor `agroia-usuarios`). Cada servicio recibe solo la llave pública (`JWT_PUBLIC_KEY_PATH`, montada en `/run/secrets/jwt_publica.pem`).
- Se valida la firma, el vencimiento, el emisor y que sea un token de acceso (`token_type: "access"`). Los claims que se leen son `user_id`, `rol` y `email_verificado`.
- Sin token: **401** (`no_autenticado`). Token inválido o vencido: **401** (`token_invalido`). Rol equivocado, token sin `rol` o correo sin verificar donde se pide: **403** (`sin_permiso`).
- Todavía no se revisa `token_version` (cerrar sesión en todos los dispositivos): necesita a svc-usuarios y llega en la fase 4.

### `AUTH_ACTIVA`

| Valor | Comportamiento |
| --- | --- |
| `True` (por defecto en el código) | Se aplican JWT y roles. |
| `False` (solo en el `.env` local) | Se apagan las revisiones de rol (`EsAdministrador`, `EsCliente`, `CorreoVerificado`, `EsDuenoOAdmin`). Un token que llega se valida igual, y los endpoints que necesitan saber quién es el usuario siguen respondiendo **401** sin token. No hay usuario de desarrollo: los tokens se generan con `infra/emitir_token.py`. |

`AUTH_ACTIVA=False` solo se acepta con `DJANGO_DEBUG=True`; con `DEBUG=False` el servicio no arranca. Con `AUTH_ACTIVA=True` y sin la llave pública, tampoco arranca. Para la entrega debe estar en `True`.

## Formato de errores

```json
{"error": "codigo_corto", "detalle": "mensaje para el usuario"}
{"error": "validacion", "detalle": "Revisa los datos enviados.", "campos": {"cantidad": ["..."]}}
```

La lista de códigos está en la [definición técnica](../docs/definicion-tecnica.md#contratos-de-api).

## Cómo se instala

- **Docker:** cada `Dockerfile` copia `comun/` a `/comun` y lo instala con `pip install -e /comun` (con sus dependencias: simplejwt, PyJWT y cryptography). `docker-compose.yml` monta `./comun` en `/comun`, así que los cambios de código se ven sin reconstruir; los de `pyproject.toml` piden `docker compose up --build`.
- **Venv local de la raíz:** el `requirements-dev.txt` de la raíz lo instala en modo editable (`-e ./comun`).

No copies este código dentro de los servicios: impórtalo desde `agroia_comun`.

## Pruebas

Corren con un Django mínimo propio (sin base de datos), dentro del contenedor de cualquier servicio Django:

```bash
docker compose exec -w /comun svc-tienda pytest
docker compose exec -w /comun svc-tienda ruff check .
```
