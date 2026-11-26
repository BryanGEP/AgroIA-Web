# Fase 2 · API de la tienda

**Fecha:** 22 de octubre de 2026 · **Entregable:** Entrega 2 · **Responsable:** Bryan Gael Esquivel Pérez

## Resumen

Se construyó la API de `svc-tienda`: catálogo de categorías y productos con filtros, búsqueda y paginación; carrito por usuario; creación de pedidos que descuenta stock en una sola transacción; pago simulado y cambios de estado con devolución de stock al cancelar. Para que el carrito y los pedidos sepan quién es el usuario, se adelantó la validación de JWT RS256 en el paquete `comun`, junto con los permisos por rol y el formato común de errores. Todo se verificó dentro de Docker el mismo día: 144 pruebas en `svc-tienda` y 26 en `comun`. Solo es API: las pantallas en `web` quedan para después.

## Qué se construyó

### Paquete `comun` (autenticación, permisos y errores)

| Archivo | Contenido |
| --- | --- |
| `configuracion.py` | `configurar_jwt` (RS256, solo llave pública, emisor `agroia-usuarios`), `leer_llave_publica` y `validar_modo_auth`. Va separado porque `settings.py` no puede importar simplejwt. |
| `autenticacion.py` | `AutenticacionJWT` (hereda de `JWTStatelessUserAuthentication`): valida firma, vencimiento, emisor y tipo de token sin consultar svc-usuarios. Registra el esquema Bearer en Swagger. |
| `permisos.py` | `EsAdministrador`, `EsCliente`, `CorreoVerificado` y `EsDuenoOAdmin`, que leen `rol`, `user_id` y `email_verificado` del token. |
| `errores.py` | Manejador de excepciones de DRF con el formato `{"error", "detalle"}` (más `campos` en validación) y `ErrorDeNegocio` para reglas de negocio. |
| `pruebas.py` | Par de llaves temporal y `firmar_token`, solo para pruebas. |

### `infra/emitir_token.py`

Script **solo para desarrollo y pruebas** que firma un token de acceso con la llave privada local y los mismos claims que emitirá svc-usuarios (`token_type`, `user_id`, `rol`, `email_verificado`, `token_version`, `iss`, `iat`, `exp` y `jti`). Opciones: `--usuario-id`, `--rol`, `--sin-verificar` y `--minutos`.

### Modelos (`tienda_db`)

| App | Modelo | Reglas |
| --- | --- | --- |
| `catalogo` | `Categoria` | `slug` único, `activa` |
| `catalogo` | `Producto` | `precio` Decimal(10,2) > 0 y `stock` ≥ 0 con `CheckConstraint`; `unidad` (pieza, kg, litro, costal); `imagen` JPG/PNG/WebP de hasta 5 MB con `default_storage`; `ficha_tecnica` JSON |
| `pedidos` | `Carrito` | uno por usuario (`usuario_id` único, sin ForeignKey) |
| `pedidos` | `ItemCarrito` | `cantidad` > 0; un producto solo una vez por carrito |
| `pedidos` | `Pedido` | `estado` (pendiente, pagado, enviado, entregado, cancelado); `direccion_envio` JSON copiada; `subtotal`, `envio` y `total` en Decimal; `metodo_pago` (tarjeta, transferencia, contra entrega; todos simulados) |
| `pedidos` | `ItemPedido` | copia de `nombre_producto` y `precio_unitario`; `importe` |

Todos los modelos están registrados en el admin de Django. Los montos y el estado del pedido son de solo lectura en el admin, para que los cambios pasen por la API y respeten las transiciones.

### Endpoints (`/api/v1/`)

| Grupo | Rutas | Acceso |
| --- | --- | --- |
| Categorías | `GET /categorias/`; `POST`, `PATCH` y `DELETE /categorias/<slug>/` | lectura pública; escritura de administrador (borrado lógico) |
| Productos | `GET /productos/` con filtros `categoria`, `precio_min`, `precio_max`, `disponible` y `q`, orden por `precio`, `nombre` y `creado_en`, 20 por página; `GET /productos/<slug>/`; `POST`, `PATCH` y `DELETE` | lectura pública (solo activos); escritura de administrador (borrado lógico) |
| Carrito | `GET` y `DELETE /carrito/`; `POST /carrito/items/`; `PATCH` y `DELETE /carrito/items/<id>/` | usuario autenticado, sobre su propio carrito |
| Pedidos | `POST /pedidos/` | cliente con correo verificado |
| | `POST /pedidos/<id>/pagar/` (nuevo) | cliente dueño |
| | `GET /pedidos/` y `/pedidos/<id>/` (filtro `estado`) | dueño o administrador |
| | `PATCH /pedidos/<id>/estado/` | administrador |

La lógica está en `servicios.py` de cada app. Crear un pedido corre en `transaction.atomic()` con `select_for_update()`: valida stock y disponibilidad, descuenta, copia nombre, precio y dirección, calcula subtotal, envío y total, y vacía el carrito. Si algo falla, no cambia nada.

### Datos de demostración

Comando `python manage.py cargar_datos_demo`: 5 categorías (fungicidas, fertilizantes, herramientas, riego y protección) y 20 productos para el cultivo del aguacate, con precios en pesos y fichas técnicas variadas. Se puede correr varias veces sin duplicar.

### Documentación

- Swagger en `/api/docs/` con descripción y ejemplos en cada endpoint, respuestas de error documentadas y botón **Authorize** (esquema Bearer).
- Colección de Postman `docs/postman/AgroIA-Web.postman_collection.json` (carpeta `svc-tienda` con 32 peticiones en orden y pruebas de código de respuesta) y entorno `docs/postman/local.postman_environment.json` con `token`, `token_admin` y `token_sin_verificar`.
- `README.md` de `svc-tienda` con la matriz de endpoints × rol y cómo obtener un token de desarrollo; `comun/README.md` con el uso de autenticación y `AUTH_ACTIVA`; sección de tokens en el README raíz.
- `docs/definicion-tecnica.md`: contratos de carrito y pedidos precisados, `POST /pedidos/<id>/pagar/`, tabla de códigos de error, variables `COSTO_ENVIO` y `ENVIO_GRATIS_DESDE`, y plan de fases ajustado.

## Decisiones técnicas

| Decisión | Por qué |
| --- | --- |
| La validación RS256 de `comun` se adelantó de la fase 4 a la fase 2 | El carrito y los pedidos necesitan saber quién es el usuario. Se descartó usar encabezados como `X-Usuario-Id`, que cualquiera puede falsificar. |
| `AUTH_ACTIVA=False` solo apaga las revisiones de rol; no hay usuario de desarrollo | Un usuario falso sin token sería un hueco si la variable llegara a producción. Carrito y pedidos responden 401 sin token y para desarrollo se usa `emitir_token.py`. Además, `AUTH_ACTIVA=False` con `DEBUG=False` impide arrancar el servicio. |
| `IsAuthenticated` por defecto y `AllowAny` explícito en lo público | Un endpoint nuevo queda protegido aunque se olvide declarar permisos. |
| Pedido o item de otro cliente → 404, no 403 | No se revela que el recurso existe. |
| Errores de validación con `campos` | Sin el detalle por campo, quien consume la API no sabe qué corregir. Se documentó en la definición técnica junto con los códigos de negocio. |
| `select_for_update()` sobre los productos, ordenados por id | Evita vender más piezas de las que hay cuando dos clientes compran al mismo tiempo; el orden fijo evita bloqueos mutuos. |
| Las pruebas usan PostgreSQL, no SQLite | En SQLite `select_for_update` no hace nada y la prueba de concurrencia no demostraría nada. Es la base propia del servicio, no otro servicio. |
| El carrito no aparta stock | El stock se valida al agregar y se descuenta al crear el pedido; apartarlo exigiría liberar carritos abandonados. |
| Envío gratis solo si el subtotal es mayor que `ENVIO_GRATIS_DESDE` | Es la regla pedida ("supera"). Con exactamente 1500.00 se cobra envío; hay una prueba para ese límite. |
| Borrado lógico de categorías y productos | Los pedidos conservan la referencia (`PROTECT`) a lo que se compró. |
| `POST /pedidos/` con rol administrador → 403 | El contrato dice "cliente con correo verificado". |
| Imágenes servidas por svc-tienda solo con `DEBUG=True` | En desarrollo basta; después las servirá el gateway y en la Entrega 5 Cloud Storage. |

## Verificación

Se hizo el 22 de octubre de 2026 dentro de Docker, con las imágenes reconstruidas.

| Prueba | Resultado |
| --- | --- |
| `makemigrations --check` | Sin cambios pendientes |
| `migrate` al arrancar | Aplicó `catalogo.0001_initial` y `pedidos.0001_initial` |
| `cargar_datos_demo` dos veces | 5 categorías y 20 productos; la segunda vez, 0 productos nuevos |
| `pytest` en `svc-tienda` | 144 pruebas pasan: modelos 16, servicios 44, endpoints 77, concurrencia 1, datos demo 2 y salud 4 |
| `pytest` en `comun` | 26 pruebas pasan: token válido, firmado con otra llave, vencido, de otro emisor, de renovación, sin rol, permisos por rol, `AUTH_ACTIVA` y formato de errores |
| Prueba de concurrencia | Con el código real: un pedido y un `stock_insuficiente`, stock final 0. Se quitó `select_for_update` temporalmente para confirmar que la prueba detecta el problema: falló con dos pedidos vendidos (`['ok', 'ok']`) |
| `ruff check` y `ruff format --check` | Pasan en `svc-tienda`, `comun` e `infra` |
| Esquema OpenAPI (`spectacular --validate --fail-on-warn`) | Sin errores ni advertencias; esquema Bearer presente y endpoints públicos sin seguridad |
| Flujo completo por HTTP con tokens de `emitir_token.py` | Agregar al carrito (201), exceder stock (409), pedido sin correo verificado (403), pedido como admin (403), dirección inválida (400 con `campos`), crear pedido (201, stock 12 → 11, carrito vacío), pagar (200, `pago_simulado: true`), pagar otra vez (409), otro cliente ve el pedido (404), cliente cambia estado (403), transición inválida (409), enviado y entregado (200), cancelar otro pedido devuelve el stock (6 → 4 → 6) |
| Colección de Postman | Las 32 peticiones devolvieron el código esperado, en tres corridas seguidas |
| `/api/docs/` | Carga (200) |
| Pruebas de los otros servicios | web, svc-usuarios, svc-contenido y svc-ia siguen pasando |

**No se verificó:** el flujo haciendo clic en la interfaz de Swagger desde un navegador, porque la extensión de Chrome no estaba conectada. Se probaron por HTTP las mismas peticiones que envía Swagger.

## Problemas encontrados

| Problema | Solución |
| --- | --- |
| `settings.py` no podía importar la configuración JWT: importar simplejwt exige que Django ya esté configurado | Las funciones de configuración se movieron a `agroia_comun/configuracion.py`, que no importa Django. |
| `makemigrations` desde el venv local se quedó esperando conexión a PostgreSQL | Se generaron las migraciones dentro del contenedor, que es la forma oficial. |
| drf-spectacular no reconocía `AutenticacionJWT` y Swagger no mostraba el botón Authorize | Se registró una extensión de esquema Bearer en `autenticacion.py`. |
| Al probar con `curl.exe` en Windows, el acento de "Michoacán" llegaba mal codificado y la API respondía `json_invalido` | Era un problema del cliente, no de la API (que rechazó bien el cuerpo inválido). El flujo se repitió con un script de Python que envía UTF-8. En Postman no ocurre. |
| Las peticiones a `localhost` tardaban unos 2 segundos desde Python en Windows | `localhost` intenta primero IPv6 y los puertos solo se publican en `127.0.0.1`. El entorno de Postman usa `http://127.0.0.1:8002`. |
| La colección de Postman fallaba al correrla dos veces porque el nombre de la categoría de prueba es único | Los nombres de prueba llevan `{{$timestamp}}`. |

## Commits y Pull Requests

Rama `feat/fase-2-tienda-api` → `develop`. Los commits los hace el integrante a mano; esta sección se completa con los hashes al hacer el PR.

## Pendientes y siguiente paso

- **Contrato nuevo:** avisar al equipo de `POST /pedidos/<id>/pagar/`, de las rutas precisadas del carrito y del campo `campos` en los errores de validación (ya están en la definición técnica y en Postman).
- Probar el flujo desde la interfaz de Swagger en el navegador.
- `token_version` todavía no se revisa (cerrar sesión en todos los dispositivos): necesita a svc-usuarios, fase 4.
- web, svc-usuarios y svc-contenido todavía no usan la autenticación de `comun`; se configuran en su fase con el mismo bloque de `settings.py`.
- La dirección de envío se recibe en el cuerpo del pedido; cuando svc-usuarios tenga direcciones, el gateway podrá enviar la elegida.
- **Siguiente:** pantallas de la tienda en `web` (catálogo, detalle, carrito, checkout, mis pedidos y panel de administrador).
