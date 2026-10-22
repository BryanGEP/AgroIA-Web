# svc-tienda

Categorías, productos, stock, carrito y pedidos (pago simulado).

- **Puerto local:** 8002 (dentro de Docker escucha en el 8000 y se llama `http://svc-tienda:8000`).
- **Datos:** PostgreSQL, base `tienda_db` con el usuario `tienda` (creados por `infra/postgres/init.sql`).
- **Documentación de la API:** http://localhost:8002/api/docs/ (botón **Authorize** para pegar un token)
- **Salud:** `GET http://localhost:8002/salud/` → `{"estado": "ok"}`

Contratos, modelo de datos y códigos de error en [`docs/definicion-tecnica.md`](../docs/definicion-tecnica.md). Colección de Postman en [`docs/postman/`](../docs/postman/).

## Estructura

| App | Modelos | Lógica de negocio |
| --- | --- | --- |
| `apps/catalogo` | `Categoria`, `Producto` | `servicios.py`: slugs, visibilidad y borrado lógico. Comando `cargar_datos_demo` |
| `apps/pedidos` | `Carrito`, `ItemCarrito`, `Pedido`, `ItemPedido` | `servicios.py`: carrito, `crear_pedido_desde_carrito`, envío, pago simulado y transiciones de estado |

Reglas que se cumplen en `servicios.py`:

- Crear un pedido corre en `transaction.atomic()` con `select_for_update()` sobre los productos (ordenados por id): valida stock y que el producto siga activo, descuenta, copia nombre, precio y dirección, calcula subtotal, envío y total, y vacía el carrito. Si algo falla, no cambia nada.
- Envío: `COSTO_ENVIO`; gratis si el subtotal es **mayor** que `ENVIO_GRATIS_DESDE`.
- Estados: `pendiente → pagado → enviado → entregado`, y `cancelado` desde `pendiente` o `pagado`. Al cancelar se devuelve el stock.
- El carrito no aparta stock: se valida al agregar y se descuenta al crear el pedido.
- Categorías y productos se borran de forma lógica (`activa` / `activo` en `False`).
- Dinero siempre en `Decimal`; en JSON se devuelve como texto (`"245.50"`).

## Endpoints × rol

Todas las rutas van bajo `/api/v1/`. "Rol válido" = token con `rol` `cliente` o `administrador`.

| Método | Ruta | Público | Cliente | Cliente sin verificar | Admin | Sin token | Rol equivocado |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/categorias/`, `/categorias/<slug>/` | ✓ (activas) | ✓ (activas) | ✓ (activas) | ✓ (todas) | — | — |
| POST, PATCH, DELETE | `/categorias/...` | | | | ✓ | 401 | 403 |
| GET | `/productos/`, `/productos/<slug>/` | ✓ (activos) | ✓ (activos) | ✓ (activos) | ✓ (todos) | — | — |
| POST, PATCH, DELETE | `/productos/...` | | | | ✓ | 401 | 403 |
| GET, DELETE | `/carrito/` | | ✓ | ✓ | ✓ | 401 | 403 (sin rol) |
| POST | `/carrito/items/` | | ✓ | ✓ | ✓ | 401 | 403 (sin rol) |
| PATCH, DELETE | `/carrito/items/<id>/` | | ✓ (propio) | ✓ (propio) | ✓ (propio) | 401 | 403 (sin rol) |
| POST | `/pedidos/` | | ✓ | 403 | 403 | 401 | 403 |
| POST | `/pedidos/<id>/pagar/` | | ✓ (propio) | ✓ (propio) | 403 | 401 | 403 |
| GET | `/pedidos/`, `/pedidos/<id>/` | | ✓ (propios) | ✓ (propios) | ✓ (todos, filtro `estado`) | 401 | 403 (sin rol) |
| PATCH | `/pedidos/<id>/estado/` | | 403 | 403 | ✓ | 401 | 403 |

Un cliente que pide el pedido o el item de carrito de otro recibe **404**, para no revelar que existe.

Filtros de `/productos/`: `categoria` (slug), `precio_min`, `precio_max`, `disponible` (`true`/`false`), `q` (busca en nombre y descripción) y, para administradores, `activo`. Orden con `ordering`: `precio`, `nombre`, `creado_en` (`-precio` para descendente). Paginación con `?page=`, 20 por página.

## Autenticación y tokens de desarrollo

svc-tienda valida el JWT con la llave pública, sin consultar svc-usuarios (ver [`comun/README.md`](../comun/README.md)). Mientras svc-usuarios no emite tokens (Entrega 3), se generan con **`infra/emitir_token.py`, que es solo para desarrollo y pruebas**. Firma con la llave privada de `infra/llaves/` y los mismos claims que emitirá svc-usuarios.

Desde la raíz, con el venv de la raíz activo:

```powershell
python infra/emitir_token.py --usuario-id 10 --rol cliente                  # cliente verificado
python infra/emitir_token.py --usuario-id 12 --rol cliente --sin-verificar  # no puede comprar
python infra/emitir_token.py --usuario-id 1 --rol administrador --minutos 480
```

Opciones: `--usuario-id` (obligatorio), `--rol` (`cliente` o `administrador`), `--sin-verificar` y `--minutos` (vigencia, 60 por defecto). Pega el token en **Authorize** de `/api/docs/` o como `Authorization: Bearer <token>`.

### `AUTH_ACTIVA=False`

Solo en el `.env` local y solo con `DJANGO_DEBUG=True` (si no, el servicio no arranca). Apaga las revisiones de rol: por ejemplo, el CRUD de categorías y productos acepta peticiones sin token. **Carrito y pedidos siguen respondiendo 401 sin token**, porque necesitan saber quién es el usuario; no hay usuario de desarrollo, usa `emitir_token.py`.

## Datos de demostración

```bash
docker compose exec svc-tienda python manage.py cargar_datos_demo
```

Carga 5 categorías (fungicidas, fertilizantes, herramientas, riego y protección) y 20 productos con precios en pesos y fichas técnicas. Se puede correr varias veces: no duplica y restablece precio y stock de esos productos.

## Variables de entorno

Salen del `.env` de la raíz (ver [`.env.example`](../.env.example)).

| Variable | Uso |
| --- | --- |
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | Django |
| `AUTH_ACTIVA` | Revisión de roles (`True` por defecto) |
| `JWT_PUBLIC_KEY_PATH` | Llave pública para validar los JWT |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Servidor de PostgreSQL (`postgres`, `5432`) |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | `tienda_db`, `tienda` y la contraseña de `.env`; docker-compose.yml los asigna |
| `COSTO_ENVIO`, `ENVIO_GRATIS_DESDE` | Costo de envío y monto a partir del cual es gratis (`150.00`, `1500.00`) |

## Imágenes

`Producto.imagen` acepta JPG, PNG o WebP de hasta 5 MB y se guarda con `default_storage` (en la Entrega 5 pasa a Cloud Storage cambiando solo `STORAGES`). Para subirla, envía el producto como `multipart/form-data`; en ese caso `ficha_tecnica` va como texto JSON. En desarrollo (`DEBUG=True`) svc-tienda sirve los archivos en `/media/`; más adelante los servirá el gateway.

## Pruebas y estilo

La forma oficial es dentro del contenedor:

```bash
docker compose exec svc-tienda pytest
docker compose exec svc-tienda ruff check .
docker compose exec svc-tienda ruff format --check .
```

Las pruebas usan PostgreSQL (pytest-django crea `test_tienda_db` en el contenedor `postgres`), porque `select_for_update` no hace nada en SQLite y la prueba de dos pedidos compitiendo por el último producto no tendría sentido. Siempre corren con `AUTH_ACTIVA=True` y con un par de llaves generado al vuelo (`config/settings_pruebas.py`).

Para correrlas en el venv local hay que levantar `docker compose up -d postgres` y pasar la contraseña del usuario `tienda`:

```powershell
cd svc-tienda
$env:POSTGRES_PASSWORD = "<TIENDA_DB_PASSWORD de tu .env>"
pytest
```

El usuario `admin/` de Django (http://localhost:8002/admin/) es local de `tienda_db`; se crea con `docker compose exec svc-tienda python manage.py createsuperuser`. No es un usuario de svc-usuarios.
