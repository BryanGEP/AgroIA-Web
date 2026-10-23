# web

Gateway de AgroIA-Web: el único servicio que habla con el navegador. Renderiza las páginas con plantillas de Django y pide los datos a los servicios internos por HTTP. Hoy tiene las páginas públicas (inicio, catálogo, detalle de producto y aviso de privacidad); el inicio de sesión, el carrito, el chat y el diagnóstico llegan después.

- **Puerto local:** 8000 (dentro de Docker escucha en el 8000 y se llama `http://web:8000`).
- **Datos:** no lee la base de ningún servicio. Tiene `web_db` para las sesiones, que se usarán con el login; las páginas públicas no la tocan (los mensajes de Django van en cookie).
- **Salud:** `GET http://localhost:8000/salud/` → `{"estado": "ok"}`

## Páginas

| Ruta | Página | Datos |
| --- | --- | --- |
| `/` | Inicio: buscador, servicios, categorías y productos recién llegados | svc-tienda (si no responde, la página se muestra igual sin esas secciones) |
| `/catalogo/` | Catálogo con filtros: categoría, precio mínimo y máximo, solo con existencias, búsqueda y orden; paginado de 20 | svc-tienda |
| `/catalogo/<slug>/` | Detalle: imagen, precio, unidad, existencias, descripción y ficha técnica | svc-tienda |
| `/aviso-de-privacidad/` | Aviso de privacidad (sección 14 de los requerimientos de autenticación) | — |
| `/media/tienda/<ruta>` | Reenvío de imágenes de productos | svc-tienda |

- **Producto inexistente o inactivo:** página 404 con enlace al catálogo.
- **svc-tienda sin responder:** página 503 "El catálogo no está disponible en este momento" con botón para reintentar; el error se registra en el log, sin trazas en la página.

## Cómo está hecho

| Pieza | Dónde |
| --- | --- |
| Estilos | Tailwind CSS 4 + daisyUI 5 con `django-tailwind-cli` (sin Node). Entrada: `static/css/fuente.css`; salida generada: `static/css/agroia.css` (no se sube al repo) |
| Temas | `agroia` (claro, por defecto) y `agroia-oscuro` (sigue la preferencia del sistema). El botón de la luna/el sol cambia de tema y lo recuerda (Alpine + `$persist`) |
| Tipografía | Barlow y Barlow Semi Condensed (OFL), servidas desde `static/fonts/` |
| Interactividad | HTMX 2.0.11 y Alpine 3.17.4 desde `static/vendor/`, sin CDN |
| Plantillas | `templates/base.html`, `templates/componentes/` (tarjeta de producto, paginador, estado vacío, carga, error, ilustración por categoría, disponibilidad, selector de tema), `templates/<módulo>/` y `templates/catalogo/parciales/_resultados.html` |
| Cliente de svc-tienda | `clientes/tienda.py` (httpx, timeout `TIENDA_TIMEOUT`, por ahora sin token) |
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
| `JWT_PUBLIC_KEY_PATH` | Llave pública para validar los JWT |
| `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | `web_db` para las sesiones |
| `URL_SVC_USUARIOS`, `URL_SVC_TIENDA`, `URL_SVC_CONTENIDO`, `URL_SVC_IA` | Direcciones internas de los servicios |
| `TIENDA_TIMEOUT` | Segundos máximos de espera a svc-tienda (`5`) |
| `REDIS_URL` | Redis (caché y throttling) |

## Pruebas y estilo

```bash
docker compose exec web pytest
docker compose exec web ruff check .
docker compose exec web ruff format --check .
```

svc-tienda se simula con `httpx.MockTransport` (`tests/tienda_falsa.py`), así que las pruebas no dependen de otros contenedores ni de la base. Cubren inicio, catálogo (página completa, parcial HTMX, historial, filtros válidos e inválidos, paginación, URL limpia), detalle, 404, error con svc-tienda caído, reenvío de imágenes, formato de precios y ficha técnica, y que ninguna página muestre comentarios de plantilla ni lenguaje del proyecto escolar.
