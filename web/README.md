# web

Gateway de AgroIA-Web: el punto de entrada único. Renderiza las páginas con plantillas de Django, guarda la sesión del navegador, enruta las peticiones a los servicios internos y valida el JWT. Tiene las páginas públicas, las de cuenta (inicio de sesión, registro, verificación, recuperación, mi cuenta) y el proxy `/api/<servicio>/`; el carrito, el chat y el diagnóstico llegan después.

- **Puerto local:** 8000 (dentro de Docker escucha en el 8000 y se llama `http://web:8000`).
- **Datos:** no lee la base de ningún servicio. Tiene `web_db` para las sesiones (con los JWT dentro); las páginas públicas sin sesión no la tocan (los mensajes de Django van en cookie).
- **Salud:** `GET http://localhost:8000/salud/` → `{"estado": "ok"}`

## Punto de entrada único

web es el único servicio que habla con el navegador y con los clientes externos. Tiene dos caras:

1. **Páginas** (plantillas de Django): la sesión del navegador vive en el servidor y web llama a los servicios en su nombre.
2. **Proxy de API** `/api/<servicio>/<ruta>` para clientes que no son navegador (Postman, una app móvil):

| Ruta del gateway | Servicio interno |
| --- | --- |
| `/api/usuarios/<ruta>` | `svc-usuarios` `/api/v1/<ruta>` |
| `/api/tienda/<ruta>` | `svc-tienda` `/api/v1/<ruta>` |
| `/api/contenido/<ruta>` | `svc-contenido` `/api/v1/<ruta>` |
| `/api/ia/<ruta>` | `svc-ia` `/<ruta>` (sin `/api/v1/`, como su contrato) |

- **Valida el JWT antes de reenviar** (`agroia_comun.tokens.validar_access`): firma RS256, `JWT_ISSUER`, `exp`, `token_type` y `user_id` UUID. Sin token en una ruta privada: 401 `no_autenticado`; token inválido: 401 `token_invalido`. Responde sin llegar al servicio y lo registra en el log `seguridad` (`capa: gateway`).
- **Rutas públicas** (pasan sin token): `POST` de `usuarios/auth/login|registro|token/renovar|verificar-correo|reenviar-verificacion|recuperar|restablecer/` y `GET` de `tienda/categorias` y `tienda/productos`. Si traen token, se valida igual.
- **Nunca toma el token de la sesión.** Solo acepta `Authorization: Bearer <access>`; una petición con cookie de sesión y sin ese encabezado es anónima. Por eso no necesita CSRF.
- **Reenvía** método, cuerpo y query string. De entrada solo pasan `Authorization`, `Content-Type`, `Accept` y `Accept-Language` (nunca `Cookie`, `Host`, los de salto ni un `X-Forwarded-For` del cliente); de salida, `Content-Type`, `Retry-After`, `WWW-Authenticate` y `Content-Disposition`. Las redirecciones del servicio se traducen a la ruta del proxy.
- **Rechaza** rutas con `.` o `..` (no se puede alcanzar `/admin/` de un servicio) y servicios que no existen (404).
- **Si el servicio no responde:** 502 `servicio_no_disponible`; si tarda más de `SERVICIOS_TIMEOUT` (`IA_TIMEOUT` para svc-ia): 504 `tiempo_agotado`.
- **Dos capas:** el gateway autentica; cada servicio vuelve a validar el token y decide los roles (ver [`docs/contrato-identidad.md`](../docs/contrato-identidad.md#dos-capas-de-validación)).

Los puertos directos de los servicios (8001 a 8005) son solo para desarrollo; la API pública es la del gateway.

### `X-Forwarded-For`

web es el borde: el cliente común (`clientes/api.py`) pone en `X-Forwarded-For` la `REMOTE_ADDR` de la conexión y **nunca** reenvía la que mande el cliente. Así el límite de intentos, el bloqueo de axes y el log de seguridad de los servicios cuentan por la IP real del navegador, también en el login desde `/iniciar-sesion/`.

## Sesión del navegador

- Los JWT se guardan en la sesión de Django en `web_db` (`access`, `refresh` y `usuario`: id, nombre, rol y `email_verificado`); el navegador solo recibe la cookie `sessionid`, `HttpOnly`, `SameSite=Lax`, 7 días y `Secure` con `DJANGO_DEBUG=False`. `cycle_key()` al iniciar sesión.
- `SesionApi` (`clientes/api.py`) agrega el token a cada llamada. Si un servicio responde 401, renueva una sola vez con el refresh y repite la petición. Si la renovación falla, vacía la sesión y `SesionExpiradaMiddleware` manda a `/iniciar-sesion/?next=<ruta>` con «Tu sesión expiró» (`HX-Redirect` en peticiones de HTMX). Si dos peticiones renuevan a la vez, la segunda adopta el par que la primera guardó en la base.
- `@login_requerido` y `@rol_requerido("administrador")` en `apps/cuentas/decoradores.py`; el context processor `apps.cuentas.context_processors.usuario` da `usuario` a todas las plantillas (menú y banner).

## Páginas

| Ruta | Página | Datos |
| --- | --- | --- |
| `/` | Inicio: buscador, servicios, categorías y productos recién llegados | svc-tienda (si no responde, la página se muestra igual sin esas secciones) |
| `/catalogo/` | Catálogo con filtros: categoría, precio mínimo y máximo, solo con existencias, búsqueda y orden; paginado de 20 | svc-tienda |
| `/catalogo/<slug>/` | Detalle: imagen, precio, unidad, existencias, descripción y ficha técnica | svc-tienda |
| `/aviso-de-privacidad/` | Aviso de privacidad (sección 14 de los requerimientos de autenticación) | — |
| `/media/tienda/<ruta>` | Reenvío de imágenes de productos | svc-tienda |
| `/iniciar-sesion/` | Inicio de sesión con `?next=` (solo rutas de este sitio) | svc-usuarios |
| `/registro/` | Crear cuenta, con la casilla del aviso de privacidad | svc-usuarios |
| `/verificar-correo/?token=` | El enlace del correo de verificación: verificado, ya verificado, vencido o inválido | svc-usuarios |
| `/reenviar-verificacion/`, `/recuperar/` | Pedir otro enlace (mensaje genérico) | svc-usuarios |
| `/restablecer/<uid>/<token>/` | El enlace del correo de recuperación | svc-usuarios |
| `/mi-cuenta/` | Datos y direcciones (agregar, borrar, predeterminada; con HTMX y sin JavaScript) | svc-usuarios |
| `/mi-cuenta/contrasena/` | Cambiar contraseña; la sesión sigue con el par nuevo | svc-usuarios |
| `/cerrar-sesion/` | Solo `POST` con CSRF | svc-usuarios |

- **Producto inexistente o inactivo:** página 404 con enlace al catálogo.
- **svc-tienda sin responder:** página 503 "El catálogo no está disponible en este momento" con botón para reintentar; el error se registra en el log, sin trazas en la página.

## Cómo está hecho

| Pieza | Dónde |
| --- | --- |
| Estilos | Tailwind CSS 4 + daisyUI 5 con `django-tailwind-cli` (sin Node). Entrada: `static/css/fuente.css`; salida generada: `static/css/agroia.css` (no se sube al repo) |
| Temas | `agroia` (claro, por defecto) y `agroia-oscuro` (sigue la preferencia del sistema). El botón de la luna/el sol cambia de tema y lo recuerda (Alpine + `$persist`) |
| Tipografía | Barlow y Barlow Semi Condensed (OFL), servidas desde `static/fonts/` |
| Interactividad | HTMX 2.0.11 y Alpine 3.17.4 en su versión CSP (`@alpinejs/csp`) desde `static/vendor/`, sin CDN. La lógica que necesita JavaScript completo está en `static/js/componentes.js` como `Alpine.data()` |
| Seguridad | `config/seguridad.py`: Content-Security-Policy sin `unsafe-inline` ni `unsafe-eval` (sin scripts, estilos ni `hx-on` en línea) y 403 `origen_no_permitido` en `/api/`; `X-Content-Type-Options`, `Referrer-Policy: same-origin` y `X-Frame-Options: DENY`. CORS con django-cors-headers solo para `/api/` |
| Plantillas | `templates/base.html`, `templates/componentes/` (tarjeta de producto, paginador, estado vacío, carga, error, ilustración por categoría, disponibilidad, selector de tema), `templates/<módulo>/` y `templates/catalogo/parciales/_resultados.html` |
| Cliente común | `clientes/api.py`: un solo cliente httpx para los cuatro servicios, con timeout, `X-Forwarded-For` real y, con `SesionApi`, el token de la sesión y la renovación automática. `clientes/tienda.py` (catálogo, sin token) se apoya en él |
| Formato | `apps/catalogo/templatetags/agroia.py`: `|pesos` ($1,250.00), `|ficha_filas` (ficha técnica legible), `|tinte` (color e ilustración por categoría) |

### Diseño

Paleta del aguacate Hass: cáscara `#2E5A1C` (primario), hueso `#6B4A2B` (secundario, café tierra), pulpa `#CBDB6E` (acento) y fondo `#F5F8EF`. La tarjeta de producto funciona como una etiqueta de insumo: una franja y un panel con el tinte de su categoría y, si no hay foto, una ilustración SVG de la categoría. Todos los pares de texto y fondo pasan WCAG AA en los dos temas (ver `docs/avances/web-base-catalogo.md`).

### Catálogo con HTMX y sin JavaScript

- El formulario de filtros es un `GET` normal: sin JavaScript se filtra con el botón **Filtrar** y la paginación son enlaces. Los campos vacíos se quitan de la URL con una redirección.
- Con HTMX, cada cambio (y la búsqueda, 400 ms después de escribir) pide `hx-get` con `hx-push-url`: solo se reemplaza `#resultados`, la URL se puede compartir y el botón atrás funciona.
- La vista devuelve `catalogo/parciales/_resultados.html` si `request.htmx` y la página completa si no (también cuando HTMX reconstruye el historial). Responde con `Vary: HX-Request`.

### Imágenes de productos

svc-tienda devuelve URLs con su dirección interna (`http://svc-tienda:8000/media/...`), que el navegador no alcanza. El cliente las reescribe a `/media/tienda/...` y esa ruta del gateway pide el archivo a svc-tienda y lo devuelve. Solo acepta rutas bajo `productos/` y archivos `image/*`; agrega `Cache-Control: public, max-age=3600`. svc-tienda sigue sin publicarse hacia afuera. Cuando las imágenes pasen a Cloud Storage, sus URLs serán públicas y el cliente las dejará como vienen.

## CSS

El contenedor compila el CSS al arrancar (`migrate` → `tailwind build` → `runserver`). Si cambias plantillas o `fuente.css` con el contenedor arriba:

```bash
docker compose exec web python manage.py tailwind build
```

El ejecutable de Tailwind (tailwind-cli-extra 2.10.32: Tailwind 4.3.3 + daisyUI 5.7.47) se descarga al construir la imagen en `/opt/tailwind`. En el venv local, `python manage.py tailwind build` lo descarga la primera vez en `web/.django_tailwind_cli/` (ignorado por git).

## Variables de entorno

| Variable | Uso |
| --- | --- |
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | Django |
| `AUTH_ACTIVA` | Activa JWT y roles (`True` por defecto) |
| `JWT_PUBLIC_KEY_PATH` | Llave pública para validar los JWT en el proxy (sin ella no arranca) |
| `JWT_ISSUER` | Emisor esperado en el claim `iss` (`agroia-usuarios`) |
| `CORS_ALLOWED_ORIGINS` | Orígenes que pueden usar `/api/` desde un navegador, separados por coma; vacío por defecto, nunca `*` |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | `web_db` para las sesiones |
| `URL_SVC_USUARIOS`, `URL_SVC_TIENDA`, `URL_SVC_CONTENIDO`, `URL_SVC_IA` | Direcciones internas de los servicios |
| `SERVICIOS_TIMEOUT`, `IA_TIMEOUT` | Segundos máximos de espera a un servicio (`10`) y a svc-ia (`35`, el agente tarda hasta 30) |
| `REDIS_URL` | Redis (caché y throttling) |

## Pruebas y estilo

```bash
docker compose exec web pytest
docker compose exec web ruff check .
docker compose exec web ruff format --check .
```

Los servicios se simulan con `httpx.MockTransport` (`tests/servicios_falsos.py` y `tests/tienda_falsa.py`), así que las pruebas no dependen de otros contenedores. Cubren el proxy (rutas públicas, sin token, token inválido, reenvío, encabezados que no pasan, `X-Forwarded-For`, servicio caído o lento, rutas fuera de la API), la sesión (renovación, sesión expirada, peticiones simultáneas, que el JWT no llegue al navegador), los decoradores, CORS y origen, la CSP, las pantallas de cuenta (página completa, errores por campo, bloqueo y 429) y, como antes, inicio, catálogo (página completa, parcial HTMX, historial, filtros válidos e inválidos, paginación, URL limpia), detalle, 404, error con svc-tienda caído, reenvío de imágenes, formato de precios y ficha técnica, y que ninguna página muestre comentarios de plantilla ni lenguaje del proyecto escolar.
