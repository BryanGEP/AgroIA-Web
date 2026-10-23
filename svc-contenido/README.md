# svc-contenido

Conversaciones con el agente, historial de diagnósticos y bitácora de actividad.

- **Puerto local:** 8003 (dentro de Docker escucha en el 8000 y se llama `http://svc-contenido:8000`).
- **Datos:** MongoDB, base `contenido` (pymongo). No usa base relacional.
- **Documentación de la API:** http://localhost:8003/api/docs/ (botón **Authorize** para pegar un token)
- **Salud:** `GET http://localhost:8003/salud/` → `{"estado": "ok"}`

Contratos, modelo de datos y códigos de error en [`docs/definicion-tecnica.md`](../docs/definicion-tecnica.md). Colección de Postman en [`docs/postman/`](../docs/postman/).

En la Entrega 2 este servicio no llama a nadie: el gateway pregunta a svc-ia y después guarda aquí la conversación o el diagnóstico. En la Entrega 4 lo harán eventos por Redis.

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
{"_id": ObjectId, "usuario_id": 12, "titulo": "Manchas en hojas", "creada_en": ISODate, "actualizada_en": ISODate,
 "mensajes": [{"rol": "usuario", "texto": "...", "fecha": ISODate},
              {"rol": "agente", "texto": "...", "fuentes": ["..."], "fecha": ISODate}]}

// diagnosticos — índice usuario_id + creado_en
{"_id": ObjectId, "usuario_id": 12, "imagen": "diagnosticos/<uuid>.png", "clase": "antracnosis",
 "confianza": 0.91, "probabilidades": {"sano": 0.03, "rona": 0.06, "antracnosis": 0.91},
 "modelo_version": "v1", "creado_en": ISODate}

// bitacora — índices tipo + fecha y fecha
{"_id": ObjectId, "tipo": "pedido_creado", "usuario_id": 12, "servicio": "svc-tienda", "datos": {...}, "fecha": ISODate}
```

`imagen` guarda el nombre del archivo en `default_storage`, no la URL: la respuesta calcula `imagen_url`, así sigue funcionando cuando se pase a Cloud Storage (Entrega 5). En desarrollo (`DEBUG=True`) el servicio sirve las imágenes en `/media/`.

Los índices se crean con `python manage.py crear_indices`, que el contenedor corre al arrancar y se puede repetir sin problema.

## Endpoints × rol

Todas las rutas van bajo `/api/v1/`. "Rol válido" = token con `rol` `cliente` o `administrador`.

| Método | Ruta | Cliente | Admin | Sin token | Rol equivocado |
| --- | --- | --- | --- | --- | --- |
| GET, POST | `/conversaciones/` | ✓ (las propias) | ✓ (las propias) | 401 | 403 (sin rol) |
| GET, DELETE | `/conversaciones/<id>/` | ✓ (propia) | ✓ (propia) | 401 | 403 (sin rol) |
| POST | `/conversaciones/<id>/mensajes/` | ✓ (propia) | ✓ (propia) | 401 | 403 (sin rol) |
| GET, POST | `/diagnosticos/` | ✓ (los propios) | ✓ (lista todos) | 401 | 403 (sin rol) |
| GET | `/diagnosticos/<id>/` | ✓ (propio) | ✓ (todos) | 401 | 403 (sin rol) |
| GET, POST | `/bitacora/` | 403 | ✓ | 401 | 403 |

- **Las conversaciones son privadas**: ni el administrador ve las de otros (responde 404).
- Un id mal formado, inexistente o de otro usuario responde **404** (`no_encontrado`), sin revelar si existe.
- **Mensajes:** `{"rol": "usuario" | "agente", "texto", "fuentes"?}`; `fuentes` solo en mensajes del agente. Una conversación admite **200 mensajes**; al llegar al límite responde **409 `conversacion_llena`** y hay que iniciar otra. El límite se aplica en el mismo `update` de MongoDB, así que se respeta aunque lleguen dos mensajes al mismo tiempo.
- **Diagnósticos:** `multipart/form-data` con `imagen` (JPG, PNG o WebP, máximo 5 MB, debe ser una imagen real), `clase` (`sano`, `rona`, `antracnosis`), `confianza`, `probabilidades` (texto JSON con las tres clases, que suman 1) y `modelo_version`. `confianza` debe ser igual a la probabilidad de `clase`.
- **Bitácora:** filtros `tipo`, `desde` y `hasta` (`AAAA-MM-DD`, ambos inclusive). `POST` es solo para administradores por ahora; en la Entrega 4 la llenarán los eventos.
- Listados paginados de 20 en 20 (`?page=`), los más recientes primero.

## Autenticación

Usa la autenticación, los permisos y el formato de errores de [`comun`](../comun/README.md), igual que svc-tienda. Los tokens de desarrollo se generan con `infra/emitir_token.py` (ver el [README raíz](../README.md#tokens-de-desarrollo)). Con `AUTH_ACTIVA=False` (solo con `DJANGO_DEBUG=True`) se apaga la revisión de roles, pero todos los endpoints siguen pidiendo token, porque todo es por usuario.

## Variables de entorno

| Variable | Uso |
| --- | --- |
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | Django |
| `AUTH_ACTIVA` | Revisión de roles (`True` por defecto) |
| `JWT_PUBLIC_KEY_PATH` | Llave pública para validar los JWT |
| `MONGO_URL` | Conexión a MongoDB, con la base al final (`mongodb://mongo:27017/contenido`) |

## MongoDB y Django

Este servicio no tiene base relacional: `DATABASES = {}` activa el backend *dummy* de Django. Cualquier uso del ORM falla con un error claro, no hay admin ni sesiones y al arrancar no se corre `migrate` (se corre `crear_indices`). `django.contrib.auth` y `contenttypes` siguen instaladas solo para que DRF y el usuario del token puedan importarse; no crean tablas.

## Pruebas y estilo

```bash
docker compose exec svc-contenido pytest
docker compose exec svc-contenido ruff check .
docker compose exec svc-contenido ruff format --check .
```

Las pruebas usan `mongomock` (una base vacía por prueba, ver `conftest.py`), así que no necesitan el contenedor `mongo` y también corren en el venv local: `cd svc-contenido` y `pytest`. Siempre corren con `AUTH_ACTIVA=True` y con un par de llaves generado al vuelo.
