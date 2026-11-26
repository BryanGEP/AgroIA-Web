# svc-contenido

Conversaciones con el agente, historial de diagnósticos y bitácora de actividad.

- **Puerto local:** 8003 (dentro de Docker escucha en el 8000 y se llama `http://svc-contenido:8000`).
- **Datos:** MongoDB, base `contenido` (pymongo). No usa base relacional.
- **Documentación de la API:** http://localhost:8003/api/docs/ (botón **Authorize** para pegar el `access` del login de svc-usuarios)
- **Salud:** `GET http://localhost:8003/salud/` → `{"estado": "ok"}`

Contratos, modelo de datos y códigos de error en [`docs/definicion-tecnica.md`](../docs/definicion-tecnica.md). Colección de Postman en [`docs/postman/`](../docs/postman/).

Este servicio no llama a nadie por HTTP. **Desde la Entrega 4 la IA es asíncrona y pasa por aquí:** el gateway pide la pregunta o el diagnóstico (`preguntar`, `diagnosticos/solicitar`, 202), svc-contenido guarda la solicitud en la conversación o el diagnóstico y publica el evento para `svc-ia-worker`. Su consumidor, `svc-contenido-eventos` (`python manage.py consumir_eventos`, grupo `svc-contenido`), guarda la respuesta o el resultado que llega por `ia-resultados`, y los eventos de negocio en la bitácora (una sola vez aunque lleguen repetidos: índice único de `evento_id`). Ver [`docs/eventos.md`](../docs/eventos.md).

## Estructura

| App | Colección | Lógica de negocio (`servicios.py`) |
| --- | --- | --- |
| `apps/conversaciones` | `conversaciones` | crear, listar las propias, ver, borrar y agregar mensajes (límite de 200). Comando `crear_indices` |
| `apps/diagnosticos` | `diagnosticos` | guardar la imagen con `default_storage` y el resultado; listar y ver |
| `apps/bitacora` | `bitacora` | registrar eventos y consultarlos por tipo y fechas |

Las apps no tienen `models.py` ni `admin.py` porque no hay ORM. `config/mongo.py` da la conexión (`coleccion()`), la fecha con la precisión de MongoDB (`ahora()`) y `object_id_o_404()`. `config/paginacion.py` adapta las consultas de MongoDB al `PageNumberPagination` de DRF, así la respuesta es igual que en svc-tienda: `{"count", "next", "previous", "results"}`.

### Documentos e índices

```json
// conversaciones — índice usuario_id + actualizada_en
{"_id": ObjectId, "usuario_id": "8d3f6c2a-1b4e-4f7a-9c5d-2e6f8a0b1c3d", "titulo": "Manchas en hojas", "creada_en": ISODate, "actualizada_en": ISODate,
 "mensajes": [{"rol": "usuario", "texto": "...", "fecha": ISODate},
              {"rol": "agente", "texto": "...", "fuentes": ["..."], "fecha": ISODate}]}

// diagnosticos — índice usuario_id + creado_en
{"_id": ObjectId, "usuario_id": "8d3f6c2a-1b4e-4f7a-9c5d-2e6f8a0b1c3d", "imagen": "diagnosticos/<uuid>.png", "clase": "antracnosis",
 "confianza": 0.91, "probabilidades": {"sano": 0.03, "rona": 0.06, "antracnosis": 0.91},
 "modelo_version": "v1", "creado_en": ISODate}

// bitacora — índices tipo + fecha y fecha
{"_id": ObjectId, "tipo": "pedido_creado", "usuario_id": "8d3f6c2a-1b4e-4f7a-9c5d-2e6f8a0b1c3d", "servicio": "svc-tienda", "datos": {...}, "fecha": ISODate}
```

`imagen` guarda el nombre del archivo en `default_storage`, no la URL. La respuesta trae `imagen_url`, que apunta a `GET /api/v1/diagnosticos/<id>/imagen/`: la foto solo la recibe el dueño o un administrador (404 para los demás, como el detalle), con `Cache-Control: private`. **Las fotos no se sirven como archivos estáticos, ni con `DEBUG=True`**: son datos personales (corrección de seguridad de la Entrega 3). El gateway las muestra en `/diagnostico/<id>/imagen/` pidiéndolas con el token del usuario.

Los índices se crean con `python manage.py crear_indices`, que el contenedor corre al arrancar y se puede repetir sin problema. `limpiar_datos_prueba --usuarios <ids>` (solo con `DJANGO_DEBUG=True`) borra las conversaciones, los diagnósticos con su foto y los eventos de bitácora de las cuentas demo y de prueba; ver [Correr las pruebas de seguridad](../README.md#correr-las-pruebas-de-seguridad).

## Endpoints × rol

Todas las rutas van bajo `/api/v1/`. "Rol válido" = token con `rol` `cliente` o `administrador`.

| Método | Ruta | Cliente | Admin | Sin token | Rol equivocado |
| --- | --- | --- | --- | --- | --- |
| GET, POST | `/conversaciones/` | ✓ (las propias) | ✓ (las propias) | 401 | 403 (sin rol) |
| GET, DELETE | `/conversaciones/<id>/` | ✓ (propia) | ✓ (propia) | 401 | 403 (sin rol) |
| POST | `/conversaciones/<id>/mensajes/` | ✓ (propia) | ✓ (propia) | 401 | 403 (sin rol) |
| POST | `/conversaciones/<id>/preguntar/`, `/conversaciones/<id>/reintentar/` | ✓ (propia), 202 | ✓ (propia), 202 | 401 | 403 (sin rol) |
| GET | `/conversaciones/<id>/solicitud/` | ✓ (propia) | ✓ (propia) | 401 | 403 (sin rol) |
| POST | `/diagnosticos/solicitar/` | ✓, 202 | ✓, 202 | 401 | 403 (sin rol) |
| GET, POST | `/diagnosticos/` | ✓ (los propios) | ✓ (lista todos) | 401 | 403 (sin rol) |
| GET | `/diagnosticos/<id>/` | ✓ (propio) | ✓ (todos) | 401 | 403 (sin rol) |
| GET | `/diagnosticos/<id>/imagen/` | ✓ (propio) | ✓ (todos) | 401 | 403 (sin rol) |
| GET, POST | `/bitacora/` | 403 | ✓ | 401 | 403 |

- **Las conversaciones son privadas**: ni el administrador ve las de otros (responde 404).
- Un id mal formado, inexistente o de otro usuario responde **404** (`no_encontrado`), sin revelar si existe.
- **Mensajes:** `{"rol": "usuario" | "agente", "texto", "fuentes"?}`; `fuentes` solo en mensajes del agente. Una conversación admite **200 mensajes**; al llegar al límite responde **409 `conversacion_llena`** y hay que iniciar otra. El límite se aplica en el mismo `update` de MongoDB, así que se respeta aunque lleguen dos mensajes al mismo tiempo.
- **IA por eventos:** `preguntar` recibe `{"texto"}`, guarda la pregunta y deja una solicitud `pendiente` en la conversación (una a la vez: 409 `solicitud_en_curso`); `reintentar` pide otra respuesta a la última pregunta sin repetirla (409 `sin_pregunta_pendiente`); `solicitud` devuelve su estado (`pendiente`, `listo` con `respuesta` y `fuentes`, o `fallido` con `codigo`). Vence a los `IA_SOLICITUD_VENCE_SEGUNDOS` (180): al leerla se marca `fallido` con `vencida`, y una respuesta que llegue después se descarta (`respuesta_tardia`). `diagnosticos/solicitar` recibe solo la foto, la guarda, deja el diagnóstico `pendiente` y una copia temporal en Redis para el worker; el diagnóstico trae `estado`, `codigo` y `es_prueba`, y el listado solo muestra los `listo`. Si falla, se borra la foto.
- **Límite por usuario** ([`config/limites.py`](config/limites.py)): `preguntar`, `reintentar` y `diagnosticos/solicitar` comparten 10 por minuto y 30 por hora por usuario (el `user_id` del token). Al pasarse, **429 `demasiados_intentos`** con `Retry-After`, antes de la vista: no se guarda nada. Los GET no cuentan. Cuenta con contadores atómicos (`incr`) por ventana fija de un minuto y de una hora, así peticiones simultáneas no se pisan; una rechazada devuelve su cuenta (`decr`) y no gasta el presupuesto. `python manage.py reiniciar_limites` vacía los contadores (solo con `DJANGO_DEBUG=True`).
- **Diagnósticos (guardado directo):** `multipart/form-data` con `imagen` (JPG, PNG o WebP, máximo 5 MB, debe ser una imagen real), `clase` (`sano`, `rona`, `antracnosis`), `confianza`, `probabilidades` (texto JSON con las tres clases, que suman 1) y `modelo_version`. `confianza` debe ser igual a la probabilidad de `clase`.
- **Bitácora:** filtros `tipo`, `usuario_id`, `correlacion_id` (UUID; todos los eventos de un flujo), `desde` y `hasta` (`AAAA-MM-DD`, ambos inclusive). El consumidor guarda `usuario_registrado`, `correo_verificado`, `rol_cambiado`, `password_cambiada`, `sesiones_cerradas`, `pedido_creado` y `pedido_estado_cambiado`. La llenan los eventos de Redis (cada documento trae `evento_id` y `correlacion_id`); el `POST`, solo para administradores, queda para registros manuales.
- Listados paginados de 20 en 20 (`?page=`), los más recientes primero.

## Autenticación

Usa la autenticación, los permisos y el formato de errores de [`comun`](../comun/README.md), igual que svc-tienda. El token sale del login de svc-usuarios (ver el [README raíz](../README.md#iniciar-sesión-y-tokens)). `usuario_id` se guarda en MongoDB como el UUID en texto. Con `AUTH_ACTIVA=False` (solo con `DJANGO_DEBUG=True`) se apaga la revisión de roles, pero todos los endpoints siguen pidiendo token, porque todo es por usuario.

## Variables de entorno

| Variable | Uso |
| --- | --- |
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | Django |
| `AUTH_ACTIVA` | Revisión de roles (`True` por defecto) |
| `JWT_PUBLIC_KEY_PATH` | Llave pública para validar los JWT |
| `JWT_ISSUER` | Emisor esperado en el claim `iss` (`agroia-usuarios` por defecto; ver `docs/contrato-identidad.md`) |
| `MONGO_URL` | Conexión a MongoDB, con la base al final (`mongodb://mongo:27017/contenido`) |
| `IA_SOLICITUD_VENCE_SEGUNDOS` | Segundos que una solicitud a la IA puede quedar pendiente (`180`) |
| `IA_SOLICITUDES_POR_MINUTO`, `IA_SOLICITUDES_POR_HORA` | Límite de solicitudes a la IA por usuario (`10` y `30`) |
| `REDIS_URL` | Caché de los contadores del límite (`redis://redis:6379/0`, prefijo `svc-contenido`) |

## MongoDB y Django

Este servicio no tiene base relacional: `DATABASES = {}` activa el backend *dummy* de Django. Cualquier uso del ORM falla con un error claro, no hay admin ni sesiones y al arrancar no se corre `migrate` (se corre `crear_indices`). `django.contrib.auth` y `contenttypes` siguen instaladas solo para que DRF y el usuario del token puedan importarse; no crean tablas.

## Pruebas y estilo

```bash
docker compose exec svc-contenido pytest
docker compose exec svc-contenido ruff check .
docker compose exec svc-contenido ruff format --check .
```

Las pruebas usan `mongomock` (una base vacía por prueba, ver `conftest.py`), así que no necesitan el contenedor `mongo` y también corren en el venv local: `cd svc-contenido` y `pytest`. Siempre corren con `AUTH_ACTIVA=True` y con un par de llaves generado al vuelo.
