# Entrega 3 · Pantallas protegidas en el gateway

**Fecha:** 20 de noviembre de 2026 · **Entregable:** Entrega 3 · **Responsable:** Bryan Gael Esquivel Pérez

## Resumen

El gateway `web` tiene ya todas las pantallas que necesitan sesión:
- **Tienda:** carrito con contador en el menú, checkout, mis pedidos y pago simulado.
- **Chat con AgroIA:** el gateway orquesta svc-contenido y svc-ia.
- **Diagnóstico por imagen:** listo para cuando exista el modelo de visión.
- **Panel de administrador.**

Todas usan el cliente común con renovación automática, los decoradores de sesión y de rol, y HTMX y Alpine en su versión CSP, sin scripts en línea.

Además, se cambió el origen de dos datos:
- **svc-contenido:** las fotos de diagnóstico solo se sirven por un endpoint que comprueba al dueño (corrección de seguridad).
- **svc-tienda:** el pedido informa al panel sus `transiciones_permitidas`.

Todo se verificó en Docker con las cuentas de demostración.

## Qué se construyó

### Tienda (`web/apps/tienda`)

- **«Agregar al carrito»** en el detalle y en las tarjetas del catálogo (componente `agregar_carrito.html`):
  - **Con sesión:** formulario con HTMX, que también funciona sin JavaScript.
  - **Sin sesión:** «Inicia sesión para comprar», con `?next=` hacia el producto.
- **Contador del carrito** en el menú:
  - Se guarda en la sesión (`carrito_cantidad`). Se recalcula al iniciar sesión, al abrir `/carrito/` y con cada cambio.
  - Las respuestas de HTMX lo actualizan fuera de banda (`hx-swap-oob`), así no se consulta a svc-tienda en cada página.
- **`/carrito/`:** cambiar la cantidad y quitar productos con HTMX, con subtotal, envío («Gratis» si aplica) y total. `stock_insuficiente` y `producto_no_disponible` aparecen junto al producto. Las imágenes pasan por `/media/tienda/`.
- **`/checkout/`:**
  - Se elige una de las direcciones de Mi cuenta, o se agrega una en la misma pantalla.
  - El gateway trae la dirección de svc-usuarios y la manda a svc-tienda en `direccion_envio`, como pide el contrato. Si la dirección no es del usuario, no llega a svc-tienda.
  - Método de pago con la etiqueta «Pago simulado».
  - Con `403 email_no_verificado` se muestra el aviso con «Reenviar el enlace» en lugar del error, y el carrito se queda intacto.
- **`/mis-pedidos/` y su detalle:** estado, productos (las copias del pedido), dirección y totales, y «Pagar» en los pendientes.

### Chat con AgroIA (`web/apps/agroia`): orquestación en el gateway

- **Pantalla `/agroia/`:**
  - Conversaciones a un lado; en celular, en un `<details>`.
  - Conversación abierta al centro, con «Nueva conversación» (la primera pregunta es el título) y borrado con confirmación.
- **Al preguntar**, `servicios.preguntar()` hace en orden:
  1. Lee la conversación de svc-contenido.
  2. Guarda la pregunta. Si responde `409 conversacion_llena`, no llama al agente y ofrece una conversación nueva.
  3. Pide la respuesta a svc-ia con el historial anterior a la pregunta.
  4. Guarda la respuesta con sus fuentes.
- **Si el agente no responde** (503 o tiempo agotado):
  - Aparece un mensaje amable y la pregunta queda guardada.
  - «Reintentar» pide la respuesta sin volver a guardar la pregunta. El botón también aparece al abrir una conversación cuyo último mensaje es del usuario.
- **Si falla guardar la respuesta:** se muestra igual, marcada «No pudimos guardar esta respuesta en tu historial», y queda en el log como `respuesta_no_guardada` (con la conversación y el código, sin el texto). Nunca se inventa una respuesta.
- **Mientras responde:**
  - «AgroIA está escribiendo…» con `hx-indicator`.
  - El componente `Alpine.data("chat")` muestra la pregunta al instante y desactiva «Enviar».
- **Fuentes:** van bajo cada respuesta.
- **Formato:** las respuestas del agente vienen en Markdown (negritas, listas, tablas). El filtro propio `markdown_seguro` **escapa primero todo el HTML** y después convierte ese subconjunto a etiquetas fijas, sin estilos en línea. Así una respuesta nunca puede inyectar HTML, y no se agregó ninguna dependencia.
- **Síncrono por ahora:** esta orquestación es síncrona, una petición HTTP espera al agente (que tarda de 2 a 30 s). En la Entrega 4 pasará a eventos por Redis: svc-ia responderá `estado: "pendiente"`, publicará el resultado y svc-contenido lo guardará al recibir el evento.

### Diagnóstico por imagen (`web/apps/diagnostico`)

- **`/diagnostico/`:**
  - Foto JPG o PNG de hasta 5 MB, con vista previa antes de enviarla (`Alpine.data("vistaPrevia")`, con una URL `blob:`).
  - El navegador valida tipo y tamaño, y el gateway lo vuelve a validar revisando la firma del archivo, no solo el nombre.
  - Mientras svc-ia responde `503 modelo_no_disponible` se muestra «El diagnóstico por imagen estará disponible pronto», sin detalles técnicos y sin guardar nada, con un enlace al chat.
- **Flujo completo listo** para cuando svc-ia devuelva un resultado (probado con un resultado simulado):
  - El resultado se guarda en svc-contenido (`multipart`) y se muestran la clase, la confianza y las probabilidades en barras `<progress>`.
  - **Productos sugeridos:** hasta 4 fungicidas con existencias para `rona` y `antracnosis`, y un consejo de prevención para `sano`.
  - Si falla el guardado, se muestra igual y queda en el log como `diagnostico_no_guardado`.
- **`/diagnostico/historial/` y su detalle:** cada uno con su foto.

### Fotos de diagnóstico: corrección de seguridad en el origen

- **Antes:** svc-contenido servía las fotos como archivos estáticos con `DEBUG=True`, sin autenticación. Cualquiera con la URL podía verlas, y la URL salía en `imagen_url`.
- **Ahora, en svc-contenido:**
  - **Endpoint nuevo:** `GET /api/v1/diagnosticos/<id>/imagen/`, autenticado. Devuelve el archivo solo al dueño o a un administrador, y 404 a cualquier otro, igual que el detalle. Lleva el tipo de imagen y `Cache-Control: private`.
  - **Sin archivos estáticos:** se quitó `static(MEDIA_URL)`, así que las fotos ya no se sirven como archivos, ni con `DEBUG=True`.
  - **`imagen_url`:** ahora apunta al endpoint, no al archivo.
- **En el gateway:** `/diagnostico/<id>/imagen/` llama a ese endpoint con el token del usuario y no conoce la ruta del archivo.
- **Pruebas en svc-contenido:** dueño, administrador, otro usuario (404), sin token (401), sin rol (403), id inválido o inexistente (404), y que `/media/...` ya no resuelve.
- **Actualizados:** Swagger, el README y el contrato de svc-contenido, la definición técnica y Postman.

### `transiciones_permitidas` en svc-tienda

- **El campo:** de solo lectura en el pedido, con la lista de estados a los que puede pasar según `TRANSICIONES`. Para clientes siempre es una lista vacía. Es un campo nuevo y no rompe el contrato.
- **En el panel:** muestra solo esos botones. La regla sigue viviendo en svc-tienda, que también la valida.
- **Pruebas:** los 5 estados en el detalle y en el listado, el cliente con la lista vacía, y la lista nueva tras cambiar el estado.
- **Swagger:** un ejemplo para administrador y `ENUM_NAME_OVERRIDES`, para que `estado` y `transiciones_permitidas` compartan el mismo conjunto de estados.

### Panel de administrador (`web/apps/panel`)

- **Acceso:** todas las vistas llevan `@rol_requerido("administrador")`, así que un cliente que entre por URL vuelve al inicio con «No tienes permiso». El menú muestra «Administración» solo a administradores.
- **Productos:**
  - Búsqueda (con HTMX) y filtros por categoría y por activo; incluye los desactivados.
  - Crear y editar, incluidas la imagen y la ficha técnica. La ficha se escribe como JSON y el gateway la valida.
  - Los datos van en JSON y la imagen en un segundo `PATCH multipart`, porque un `JSONField` no se lee bien dentro de `multipart`.
  - Desactivar, con confirmación.
- **Categorías:** listado, crear, editar y desactivar.
- **Pedidos:** filtro por estado, detalle y cambio de estado con HTMX usando `transiciones_permitidas`. `transicion_invalida` muestra el mensaje del servicio.
- **Usuarios:** filtros por rol y búsqueda, y cambio de rol. En la fila del propio administrador no hay botón, y `auto_degradacion` muestra su mensaje.

### Menú y navegación

- Carrito (con contador), AgroIA chat y Diagnóstico dejaron de ser «Próximamente», también en el inicio.
- El menú de la cuenta suma «Mis pedidos» y «Mis diagnósticos».
- En celular el carrito queda visible fuera del menú plegable.

### Postman

- **Carpeta «Gateway»:**
  - Chat a través de `/api/`: crear una conversación, guardar la pregunta, preguntar a AgroIA y guardar la respuesta con sus fuentes.
  - Diagnóstico por `/api/ia/diagnostico/`, que hoy responde 503 `modelo_no_disponible`.
- **svc-contenido:**
  - Foto del dueño (200, imagen y `private`), del administrador (200), de otro usuario (404) y sin token (401).
  - «Ver diagnóstico» comprueba que `imagen_url` sea el endpoint protegido.
- **svc-tienda:** «Marcar enviado» y «Marcar entregado» comprueban `transiciones_permitidas`.
- No se agregaron logins, así que se mantiene el margen del 20 % antes del caso del 429.

## Decisiones técnicas

| Decisión | Por qué |
| --- | --- |
| Fotos de diagnóstico por id con comprobación de dueño, también en el origen | Son datos personales; ni el gateway ni svc-contenido deben servirlas por ruta |
| Contador del carrito en la sesión, con `hx-swap-oob`, recalculado al iniciar sesión, al abrir `/carrito/` y con cada cambio | Evita una llamada a svc-tienda en cada página |
| `transiciones_permitidas` en svc-tienda y no copiadas en el gateway | La regla vive en un solo lugar |
| Reintento del chat solo si el último mensaje es del usuario, sin volver a guardarlo | Evita preguntas duplicadas en el historial |
| `img-src 'self' data: blob:` | La vista previa de la foto usa `URL.createObjectURL`; `blob:` solo cubre imágenes generadas en el propio navegador |
| `markdown_seguro` propio, sin dependencias | Escapar primero y convertir un subconjunto fijo es seguro y no requiere `markdown` ni un sanitizador |
| Con HTMX, los errores de formulario responden 200 | HTMX 2 no reemplaza el contenido con respuestas 4xx |
| El aviso de correo sin verificar en el checkout responde 200 | Es una pantalla con la indicación, no una página de error; con 403 el navegador registraba un error en la consola |
| Productos sugeridos por clase con un mapa en `diagnostico/servicios.py` | Los fungicidas cúpricos sirven para roña y antracnosis; el mapa se ajusta sin tocar las vistas |

**Contradicciones con los documentos (ya corregidas):**
- **Frontend, regla 10:** decía que las imágenes de otros servicios se reenvían por ruta. Se aclaró que las fotos de diagnóstico van por id con permiso.
- **CSP:** la definición técnica decía `img-src 'self' data:`; se agregó `blob:`.
- **Formatos:** svc-contenido acepta WebP, pero la pantalla de diagnóstico acepta solo JPG y PNG, como svc-ia.

## Verificación

Todo en Docker, el 20 de noviembre de 2026.

- **Navegador** (Chromium headless con Playwright 1.64.1, cuentas de demostración, en `http://localhost:8000`): **21 de 21 pasos correctos y 0 violaciones de la CSP o errores en la consola** en la corrida final.
  1. **Cliente verificado:**
     - Agregó un producto desde la tarjeta con HTMX y el contador del menú pasó a 1. Cambió la cantidad a 2 con HTMX.
     - En el checkout, agregó una dirección ahí mismo, eligió tarjeta y confirmó: se creó el pedido. Lo pagó y quedó «Pagado» con la etiqueta «Pago simulado», y aparece en Mis pedidos.
     - Al entrar a `/administracion/` recibió «No tienes permiso».
  2. **Chat:**
     - Conversación nueva con respuesta real del agente y sus fuentes.
     - Segunda pregunta con HTMX: el indicador «AgroIA está escribiendo» se vio y llegó la respuesta.
     - La respuesta en Markdown (tabla, negritas y lista numerada) se ve con formato y sin asteriscos ni `|`.
  3. **Diagnóstico:** vista previa de la foto con una URL `blob:`; al enviarla, «estará disponible pronto», sin `modelo_no_disponible` en la página.
  4. **Cliente sin verificar:** al confirmar el pedido, el aviso con «Reenviar el enlace» en lugar del error.
  5. **Administrador:**
     - El menú muestra «Administración».
     - En ese pedido pagado, solo ofrece «Enviado» y «Cancelado». Lo cambió a «Enviado» con HTMX y quedó solo «Entregado».
     - Desactivó «Manguera de goteo 16 mm, rollo 100 m»: aparece como desactivado en el panel y ya no en el catálogo. Al final lo reactivó desde el panel, para dejar los datos como estaban.
  6. **Celular (390 px):** el menú plegable tiene las opciones nuevas y el carrito queda visible fuera del menú.
- **Corridas del navegador seguidas:** en una corrida el login del celular recibió 429, porque se iniciaron 12 sesiones en menos de un minuto con el límite de 10 (el log de svc-usuarios lo confirma). Esperando un minuto entre corridas, todas pasan.
- **Fotos en el origen:** con `DJANGO_DEBUG=True`, `GET http://127.0.0.1:8003/media/diagnosticos/<archivo existente>.png` responde **404**.
- **pytest:** **715 en verde.**

  | Servicio | Pruebas |
  | --- | --- |
  | web | 205 (antes 138) |
  | svc-usuarios | 148 |
  | svc-tienda | 154 (antes 147) |
  | svc-contenido | 80 (antes 73) |
  | svc-ia | 63 |
  | comun | 65 |

- **ruff:** `ruff check` y `ruff format --check` en verde en los cinco servicios y en `comun`.
- **Swagger:** `spectacular --validate --fail-on-warn` termina con código 0 en svc-usuarios, svc-tienda y svc-contenido.
- **Postman** con Newman 6.2.1, dos corridas: **118 peticiones y 198 aserciones, 0 fallas en cada una.** «Preguntar a AgroIA (gateway)» tardó 28,3 s en la primera y 1,6 s en la segunda.
- **Capturas** en `docs/avances/img/`:
  - escritorio: `pantallas-catalogo-agregado`, `pantallas-carrito`, `pantallas-checkout`, `pantallas-pedido-pagado`, `pantallas-checkout-sin-verificar`, `pantallas-chat`, `pantallas-diagnostico`, `pantallas-panel-pedido` y `pantallas-panel-productos`;
  - celular: `pantallas-chat-celular`, `pantallas-pedidos-celular` y `pantallas-menu-celular`.

## Problemas encontrados

| Problema | Solución |
| --- | --- |
| Las clases nuevas de daisyUI (globos del chat, tabs, tablas, `progress`) no tenían estilo en las primeras capturas | El CSS se compila al arrancar el contenedor; se recompiló con `python manage.py tailwind build` |
| Las respuestas del agente se veían con `**` y `|` | Filtro `markdown_seguro`, que escapa y luego da formato |
| La página de la conversación respondió 500 después de agregar el filtro | `runserver` no registra una biblioteca de etiquetas nueva en caliente; se reinició el contenedor web |
| `diagnosticar()` leía la foto antes de revisar su firma (`StopIteration`) | `_tipo()` regresa al inicio del archivo antes de leer |
| drf-spectacular avisaba de dos nombres para el mismo conjunto de estados | `ENUM_NAME_OVERRIDES` en svc-tienda |
| El checkout de la cuenta sin verificar respondía 403 y el navegador lo registraba como error en la consola | El aviso responde 200 |
| Un parámetro `volver` sin validar en el cambio de rol permitía redirigir a otro sitio | Se quitó: siempre vuelve al listado de usuarios |
| Un heredoc de Git Bash convirtió `\x89` en un carácter real dentro de una prueba | La prueba compara la firma `PNG` sin el byte inicial |

## Ajustes antes de cerrar la fase

### Seguridad del filtro de Markdown

Las respuestas del agente se tratan como texto no confiable: pueden traer fragmentos de sus documentos y de lo que escribió el usuario.

- **El filtro no convierte enlaces.** `[texto](url)` queda como texto escapado y visible, así que no existe ningún `href` que un `javascript:`, `data:` o `vbscript:` pudiera usar. Tampoco genera imágenes.
- **53 pruebas nuevas** (`apps/agroia/tests/test_markdown_xss.py`), con un parser de HTML que exige que la salida tenga **solo** las etiquetas, atributos y valores de `class` que genera el propio filtro, y que cada `<` abra o cierre una de esas etiquetas. Los casos cubren:
  - `<script>` en minúsculas y mayúsculas;
  - `img` con `onerror`, `svg` con `onload`, e `iframe` y `style`;
  - atributos `on*` dentro de etiquetas que el filtro sí genera;
  - enlaces con `javascript:` (también con mayúsculas, espacios y entidades HTML), `data:`, `vbscript:` y sin esquema, más imágenes en Markdown;
  - HTML dentro de negritas, cursivas, código, encabezados, listas y tablas;
  - Markdown anidado e intentos de cerrar atributos con comillas;
  - entidades que no se decodifican dos veces.
- **En el navegador** (Playwright): guardé en una conversación del cliente demo una respuesta del agente simulada con todos esos casos, incluidas las fuentes, y abrí la pantalla real del chat. Al pasar el ratón y hacer clic sobre los mensajes:
  - en el DOM hubo 0 elementos `script`, `img`, `svg`, `iframe`, `a`, `style`, `form` o `input` y 0 atributos `on*`, `style`, `href` o `src`;
  - no se abrió ningún diálogo de `alert` y `window.__xss` siguió vacío;
  - la consola no mostró errores ni violaciones de la CSP;
  - los ataques se ven como texto. La conversación de prueba se borró al terminar.

  Captura: `pantallas-chat-xss.png`.

### Tiempo del agente

- **Valores nuevos:** `AGENTE_TIMEOUT` sube de 30 a **45 s** (svc-ia) e `IA_TIMEOUT` de 35 a **50 s** (gateway), en `docker-compose.yml`, `.env.example`, los valores por omisión del código y la documentación. Los contenedores recreados toman 45 y 50.
- **Medición:** reinicié el agente dos veces e hice tres preguntas seguidas en cada ocasión.

  | Pregunta | Corrida 1 | Corrida 2 |
  | --- | --- | --- |
  | 1.ª | 5,2 s | 5,9 s |
  | 2.ª | 2,0 s | **29,3 s** |
  | 3.ª | **21,0 s** | 5,9 s |

- **Conclusión:** la primera pregunta carga el modelo de embeddings (lo muestra el log, «Loading weights»), pero desde el volumen `modelos_hf` toma menos de un segundo. **La lentitud no es de la primera pregunta:** viene del LLM y puede tocarle a cualquiera. Así quedó escrito en el README raíz, con la recomendación de hacer una pregunta de prueba antes de una demo.

**Verificación:** pytest y ruff en web (258 pruebas, antes 205) y en svc-ia (63), en verde.

## Commits y Pull Requests

Rama `feat/e3-pantallas` desde `develop`. Los commits se proponen al cerrar la fase.

## Pendientes y siguiente paso

- **Entrega 4:** pasar la orquestación del chat y del diagnóstico a eventos por Redis (svc-ia responde `pendiente` y svc-contenido guarda el resultado).
- **Modelo de visión:** cuando svc-ia lo tenga, el flujo del diagnóstico ya está listo, probado con un resultado simulado.
- **Tiempo del agente:** en una corrida tardó 28,3 s, cerca de `AGENTE_TIMEOUT` (30 s). Conviene vigilarlo; con eventos dejará de bloquear la petición.
- **Respuestas no guardadas:** se muestran, pero no quedan en el historial; al recargar la página desaparecen.
- **Despliegue (Entrega 5):** las fotos se servirán desde Cloud Storage con URLs firmadas o a través del mismo endpoint protegido.
