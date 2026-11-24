# Entrega 4 · Widget flotante de AgroIA

**Fecha:** 24 de noviembre de 2026 · **Entregable:** Entrega 4 · **Responsable:** Bryan Gael Esquivel Pérez

## Resumen

Cuarta parte de la fase 3: **el chat de AgroIA en todas las páginas**, como una burbuja flotante, sobre el flujo asíncrono de la [tercera parte](e4-ia-asincrona.md).

- **Burbuja abajo a la derecha con la mascota del aguacate.** Abre un panel con:
  - el encabezado «AgroIA» y el estado «En línea»;
  - botones de silenciar, reiniciar la conversación y cerrar;
  - el saludo;
  - preguntas sugeridas según la sección;
  - el campo con micrófono y enviar;
  - «Ver historial completo» y la nota «AgroIA es orientativo…».
- **Visitantes:** el saludo y la invitación a iniciar sesión o crear cuenta, con el regreso a la página donde estaban. Sin campo de pregunta y sin llamar a ningún servicio.
- **Usuarios:** el mismo flujo asíncrono de /agroia/ (202, polling, «Reintentar», vencida, el 429 del límite por usuario), **con los mismos parciales y vistas**, que ahora comparten la página y el widget. La conversación del widget vive en la sesión del gateway y se crea con el primer mensaje; «Reiniciar» empieza otra sin borrar la anterior.
- **Carga diferida y entre páginas:**
  - cerrado y sin nada pendiente, **0 peticiones**;
  - recuerda si estaba abierto;
  - si hay una pregunta pendiente, el polling sigue en la página nueva y la burbuja avisa cuando llega la respuesta.
- **«Copiar»** en cada respuesta, también en /agroia/.
- **Dictado por voz detrás de un aviso de privacidad**, `Permissions-Policy` en el gateway y un sonido de aviso opcional.
- **Accesibilidad:**
  - modal con el foco atrapado en celular (pantalla completa) y no modal en escritorio;
  - Esc cierra y el foco vuelve a la burbuja;
  - los mensajes se anuncian con `aria-live`;
  - respeta `prefers-reduced-motion`.

## Qué se tomó del widget de `..\AgroIA` y qué cambió

Se leyó `svc-agente/web/` (`index.html`, `app.js` y `styles.css`) sin modificar nada en ese repo. **No se copió ningún archivo**: no tiene imágenes ni sonidos; la mascota es SVG en línea y el sonido, Web Audio.

| Se tomó | Cómo quedó aquí |
| --- | --- |
| La mascota del aguacate (SVG) | `templates/componentes/mascota.html`, con los colores en clases (sin estilos en línea); parpadea y flota solo con `prefers-reduced-motion: no-preference` |
| La estructura del panel, el saludo, las 4 preguntas sugeridas, el campo y la nota al pie | Los mismos textos, con daisyUI y el tema `agroia` |
| El tono de aviso con Web Audio | El mismo «pop» corto, apagado por defecto |
| El dictado con la Web Speech API | Detrás de un aviso de privacidad, con errores claros |
| Esc para cerrar | Más el manejo del foco y `aria-modal` según el tamaño |

| Allá | Aquí |
| --- | --- |
| Llama a `/chat` del agente con `fetch` | El flujo asíncrono de svc-contenido, con los parciales de /agroia/ |
| Historial en `localStorage` | En svc-contenido; en el navegador solo se recuerda abierto o cerrado, el sonido y la aceptación del aviso del micrófono |
| Markdown convertido en el navegador con `innerHTML` y animación de escritura | El filtro `markdown_seguro` del servidor, igual que en /agroia/ |
| CSS propio y fuentes de Google | daisyUI, Tailwind y las fuentes locales; CSP estricta |

## Qué se construyó

### Gateway (web)

- **Vistas** (`apps/agroia/views.py`):
  - `widget` (GET, el contenido del panel), `widget_preguntar` y `widget_reiniciar`;
  - `preguntar` se dividió en `_respuesta_a_pregunta` y `_respuesta_a_error`, y `_pantalla` en `_contexto_de_conversacion`, que comparten la página y el widget;
  - `solicitud` quita la marca de pendiente y manda `HX-Trigger: agroia-respuesta` al llegar la respuesta o la fallida;
  - `reintentar` pone la marca.
- **`apps/agroia/servicios.py`:**
  - la conversación del widget y la marca de pendiente en la sesión;
  - dónde se muestra;
  - las sugerencias por sección;
  - el nombre del producto (normalizado y recortado a 80 caracteres);
  - la página actual a partir de `HX-Current-URL`, solo si es de este sitio.
- **`apps/agroia/context_processors.py`:** `widget_agroia` (`mostrar`, `con_sesion`, `pendiente`) para `base.html`.
- **Parciales nuevos:**
  - `_widget` (la burbuja y el panel vacío), `_widget_panel`, `_widget_saludo`, `_widget_pie`;
  - `_conversacion` y `_formulario` (extraídos de `chat.html`);
  - `_microfono` y `_microfono_avisos`.
  - `_turno` aprendió `en_widget` y `quitar_sugerencias`; `mensaje_chat` trae «Copiar».
- **`static/js/componentes.js`:**
  - `widgetAgroia`, `copiar` y `microfono`;
  - `chat` busca su lista dentro de su componente (no por id) y envía con Enter.
- **`base.html`:**
  - el bloque `widget_agroia`, que las páginas de error vacían;
  - el bloque `widget_contexto`, que llena el detalle de un producto;
  - espacio inferior en celular para que la burbuja no tape lo último de la página;
  - `attributesToSettle` sin `style`.
- **`config/seguridad.py`:** `Permissions-Policy: microphone=(self), camera=(), geolocation=(), payment=(), usb=()`.
- **Registro:** pasa el `?next=` al enlace «Iniciar sesión» que muestra al terminar. Es un cambio fuera de `apps/agroia`, en `apps/cuentas`, necesario para «crear cuenta» con regreso.
- **Aviso de privacidad, versión 2026-11:**
  - la sección «Dictado por voz» y un «Historial de versiones» al final, con qué tenía la 2026-10 y qué se agregó;
  - `VERSION_AVISO_PRIVACIDAD` sube a `2026-11` en svc-usuarios (configuración, `docker-compose.yml`, `.env.example`, pruebas y el ejemplo de OpenAPI del perfil).
- **README:** en Windows, reiniciar los servicios después de cambiar de rama o hacer `pull` (el autorreload puede quedarse con código viejo; síntoma: una ruta nueva responde 404).

### Preguntas sugeridas por sección

| Sección | Preguntas |
| --- | --- |
| General | «¿Cada cuánto debo regar mi aguacate?», «¿Qué es la antracnosis?», «Consejos para el suelo», «¿Cómo detecto la roña?» |
| Catálogo | «¿Qué fungicida conviene contra la antracnosis?», «¿Qué fertilizante uso antes de la floración?», «¿Cómo elijo un insumo para mi huerta?» |
| Detalle de un producto | «¿Cómo y cuándo se aplica {producto}?», «¿Qué precauciones debo tener con {producto}?», «¿Para qué problemas del aguacate sirve {producto}?» |
| Diagnóstico | «¿Cómo distingo la roña de la antracnosis?», «¿Qué hago si mi aguacate tiene antracnosis?», «¿Cómo prevengo la roña?», «¿Qué daño causa el trips en el fruto?» |
| Tienda (carrito, checkout, pedidos) | «¿Qué insumos necesito para la temporada de lluvias?», «¿Cuánto fungicida necesito por hectárea?», más 2 generales |

## Decisiones técnicas

| Decisión | Por qué |
| --- | --- |
| La conversación del widget en la sesión del gateway, creada con el primer mensaje | Abrir el widget no crea conversaciones vacías y no se mezcla con lo que el usuario abre en /agroia/. «Reiniciar» solo olvida cuál era |
| La marca de pendiente en la sesión | `base.html` sabe, sin pedir nada a svc-contenido, si debe cargar el panel para seguir el polling en la página nueva |
| Abierto o cerrado por pestaña (`sessionStorage`); sonido y aviso del micrófono en `localStorage` | Cada pestaña decide si muestra el panel; las preferencias son del navegador. No se guarda texto de la conversación en el navegador |
| Sin widget en /agroia/, en las pantallas de acceso, en el panel de administración ni en las páginas de error | Ahí ya está el chat, distrae del formulario, tapa tablas y acciones, o la página ya falló y no debe hacer más peticiones |
| Modal solo en celular | A pantalla completa no se ve nada más: el foco no debe salir. En escritorio el panel flota junto a la página y se puede seguir usándola |
| Micrófono detrás de un aviso, solo si el navegador tiene la API | En Chrome el audio va a Google (en Edge a Microsoft, en Safari a Apple) y Firefox no lo trae. AgroIA no recibe el audio, pero un tercero sí, y eso se avisa antes y está en el aviso de privacidad |
| El texto dictado no se envía solo | El reconocimiento se equivoca; el usuario lo revisa |
| Sonido apagado por defecto y con Web Audio | Sin archivos; el `AudioContext` solo arranca con un gesto del usuario (política de reproducción automática) |
| «Copiar» con la Clipboard API, sin alternativa | Sin contexto seguro el botón no aparece: no se usa `execCommand` |
| El nombre del producto del navegador se recorta a 80 caracteres y lo escapa el autoescape | Viene de un campo que el navegador puede cambiar |
| `attributesToSettle` sin `style` | HTMX copiaba el `style` del campo viejo al nuevo (mismo id) y la CSP lo bloqueaba |
| Subir el aviso a 2026-11 sin pantalla para volver a aceptarlo | La versión se guarda solo al registrarse: los usuarios existentes conservan la 2026-10 que aceptaron (no quedan como si hubieran aceptado la nueva) y los registros nuevos guardan la 2026-11. Pedir a los existentes que acepten la nueva exige construir algo que no existe (ver «Pendientes») |
| Sin dependencias nuevas | El foco atrapado y el sonido van en `componentes.js`; HTMX, Alpine (CSP) y `persist` ya estaban |

## Verificación

Todo en Docker, el 24 de noviembre de 2026.

### Playwright (Chromium): 52 de 52, 0 errores de consola y 0 de la CSP

Con la cuenta demo del cliente y el agente real; el micrófono, con un reconocimiento de voz simulado (inyectado antes de cargar la página).

- **Visitante (escritorio y móvil):**
  - la burbuja con su nombre accesible;
  - cerrado, 0 peticiones;
  - al abrir, una sola petición, la invitación con `?next=/catalogo/` y sin campo de pregunta.
- **Usuario en escritorio:**
  - **página y apertura:** con el widget cerrado, 0 peticiones. Al abrirlo con el teclado (Enter en la burbuja) el foco entra al campo, y el panel no es modal. Muestra el saludo y las 4 sugerencias generales;
  - **pregunta:** la respuesta del agente real llegó en 2.4 s y el panel quedó en el último mensaje;
  - **«Copiar»:** muestra «Copiado» y lo pegado es el texto plano de la respuesta, sin HTML ni fuentes;
  - **foco:** Tab desde el último elemento sale del panel (no lo atrapa). Esc cierra y el foco vuelve a la burbuja;
  - **pregunta pendiente al cambiar de página, con el panel cerrado:** la página nueva sigue el polling (4 consultas), la burbuja avisa «hay una respuesta nueva» y, al abrirla, la respuesta está ahí;
  - **entre páginas:** abierto se recuerda y muestra la conversación;
  - **sonido:** el botón cambia (`aria-pressed`) y la preferencia se recuerda;
  - **micrófono:**
    - aparece solo con la API;
    - el primer uso muestra el aviso;
    - «Escuchando…» se ve y se anuncia (`aria-live`);
    - el texto dictado queda en el campo sin enviarse;
    - el botón vuelve a su estado normal;
    - una vez aceptado, no vuelve a pedir el aviso;
  - **reiniciar:** vuelven el saludo y las sugerencias, y la conversación anterior sigue en /agroia/;
  - **/agroia/:** no aparece el widget, y las respuestas también traen «Copiar»;
  - **diagnóstico:** sugerencias sobre enfermedades; tocar una la envía y llega la respuesta;
  - **detalle de un producto:** «¿Cómo y cuándo se aplica Malla sombra 50%, 4 x 25 m?».
- **Errores del micrófono:**
  - con el permiso negado aparece «No diste permiso para usar el micrófono…» y el botón deja de escuchar;
  - sin la API, el botón no aparece.
- **Móvil (390 × 844):**
  - el panel ocupa la pantalla (390 × 844), es modal y la burbuja se oculta;
  - el foco entra al campo, y 25 Tab y 25 Mayús+Tab no salen del panel;
  - pregunta y respuesta del agente;
  - Esc cierra y el foco vuelve a la burbuja.
- **Botones de pagar y confirmar (móvil, con la página hasta abajo):** la burbuja (desde y = 764) no tapa ninguno, y un clic de prueba de Playwright confirma que nada los cubre.

  | Pantalla | Botón | Posición (y) |
  | --- | --- | --- |
  | Carrito | «Continuar» | 482–522 |
  | Checkout | «Confirmar» | 506–546 |
  | Detalle del pedido | «Pagar» | 96–136 |
- **Capturas:**
  - escritorio: [visitante](img/e4-widget-visitante.png), [abierto](img/e4-widget-escritorio-abierto.png), [respuesta](img/e4-widget-escritorio-respuesta.png), [respuesta nueva con el panel cerrado](img/e4-widget-respuesta-nueva.png), [reiniciado](img/e4-widget-reiniciado.png);
  - micrófono: [aviso](img/e4-widget-microfono-aviso.png), [permiso negado](img/e4-widget-microfono-error.png);
  - móvil: [chat](img/e4-widget-movil.png), [visitante](img/e4-widget-movil-visitante.png), [carrito](img/e4-widget-movil-carrito.png), [checkout](img/e4-widget-movil-checkout.png), [pagar](img/e4-widget-movil-pagar.png).

### Corridas completas

- **pytest: 1034 en verde.**

  | Servicio | Pruebas |
  | --- | --- |
  | web | 320 (antes 288) |
  | svc-usuarios | 186 |
  | svc-tienda | 169 |
  | svc-contenido | 139 |
  | svc-ia | 87 |
  | comun | 133 |

  Las 32 nuevas de web (`apps/agroia/tests/test_widget.py`) cubren:
  - **visitante:** el saludo y la invitación sin llamar a servicios; el `next` solo de este sitio; el registro lleva el regreso; no puede preguntar;
  - **página y exclusiones:** la página solo trae la burbuja y el panel vacío (carga diferida); no aparece en las pantallas de acceso, en un 404, en /agroia/, en el panel ni en una página que falló;
  - **cabeceras:** Permissions-Policy, y HTMX sin asentar `style`;
  - **preguntar:**
    - el saludo, las sugerencias y el campo;
    - la primera pregunta crea la conversación y espera, y la página siguiente sabe que hay algo pendiente sin pedir nada;
    - la segunda usa la misma conversación; si se borró, empieza otra;
    - el 429 no deja una conversación vacía y conserva el texto;
    - la conversación llena ofrece empezar otra;
  - **volver a abrir:** muestra los mensajes y sigue esperando; al llegar la respuesta se quita la marca y se avisa al widget; «Reiniciar» no borra la anterior;
  - **sugerencias:** por sección y con el nombre del producto; **un nombre con HTML se escapa y se recorta a 80 caracteres**;
  - **«Copiar»:** en las respuestas de /agroia/ y no en las preguntas.
  - Las pruebas de /agroia/ siguen igual con los parciales compartidos.
- **ruff:** `ruff check` y `ruff format --check` en verde en los cinco servicios, `comun` e `infra/`. `spectacular --validate --fail-on-warn` de web, sin avisos.
- **Postman** (después de `cargar_datos_demo` y `reiniciar_limites`): **128 peticiones (139 con las del script previo) y 219 aserciones, 0 fallas.**
  - Una primera corrida dio 3 fallas en «svc-ia / Preguntar al agente» (503) y su «Estado de la solicitud».
  - Fue el límite de Groq: `RateLimitError` en el log del agente, justo después de las preguntas de Playwright.
  - Con dos minutos sin llamadas, en verde.
- **Matriz de accesos:** **154 de 154**, en [`docs/entregable-4/matriz-accesos.md`](../entregable-4/matriz-accesos.md).
- **`infra/prueba_eventos.py`: 62 de 62** en 406 s:
  - el paso 8 respondió en 4.1 s;
  - el 10 esperó 89 s sin llamadas al agente y atendió de 2 en 2.
- **Al final:** `limpiar_datos_prueba` en los tres servicios y `cargar_datos_demo` (Playwright creó un pedido del cliente demo para probar «Pagar»). `estado`: 0 pendientes y 0 fallidos.

### Versión del aviso de privacidad (2026-11)

- **Qué pasa al cambiar `VERSION_AVISO_PRIVACIDAD` (revisado en el código):**
  - se guarda en `Usuario.version_privacidad`, junto con `acepto_privacidad_en`, solo en `servicios.registrar_usuario`;
  - nada compara la versión de un usuario con la vigente;
  - los usuarios existentes no cambian;
  - las cuentas demo se crean sin versión (vacía);
  - Postman y la matriz no la revisan.
- **Después de subirla:**
  - svc-usuarios usa `2026-11` (`printenv` en el contenedor: el `.env` local no la fija);
  - el usuario que registró Postman quedó con `2026-11` y las cuentas demo siguen vacías;
  - pytest de svc-usuarios: 186 en verde, con las pruebas de la versión en `2026-11`;
  - web: 320;
  - ruff en verde y OpenAPI de svc-usuarios sin avisos.
- **Postman** (después de `cargar_datos_demo` y `reiniciar_limites`): 139 peticiones y 219 aserciones, 0 fallas.
- **Matriz, primera corrida: 151 de 154.** Las 3 diferencias eran la fila «Pregunta al agente» (la llamada síncrona a svc-ia): 503 `agente_no_disponible` para las tres cuentas, porque Groq rechazaba todas las llamadas al instante (`RateLimitError`; la cuota diaria de la llave gratuita se había agotado con las corridas del día). Las otras 151 coincidían.
- **Nuevo criterio de la matriz** (decisión del equipo): la matriz prueba el control de acceso, no la disponibilidad del agente.
  - Un 503 `agente_no_disponible` o `modelo_no_disponible` donde se esperaba acceso permitido cuenta como coincidencia, marcado «permitido (servicio externo no disponible)» (✓* en la tabla), y el resumen dice cuántas hubo.
  - Un 401 o 403 donde se esperaba permitido sigue siendo una falla, igual que un 503 donde se esperaba 401 o 403.
  - `Caso.servicio_externo` en `infra/matriz_seguridad.py`, con 12 pruebas en `infra/tests/test_matriz_seguridad.py` (`python -m pytest infra/tests`). Documentado en el README.
- **Matriz con el criterio: 154 de 154, con 3 marcadas** «permitido (servicio externo no disponible)»: las mismas 3 filas, porque la cuota de Groq seguía agotada.
  - Las preguntas por eventos de Postman y de las dos corridas de la matriz (7) agotaron sus reintentos por lo mismo. Se revisaron y se descartaron con `descartar --id`.
  - `estado` quedó en 0 pendientes y 0 fallidos.

## Problemas encontrados

| Problema | Solución |
| --- | --- |
| svc-contenido respondía 404 a `preguntar`: el proceso corría código viejo | Al cambiar de rama, el autorreload tomó una versión anterior y no vio los cambios siguientes (en Windows los volúmenes montados no avisan al contenedor). Se reiniciaron los servicios |
| La violación de la CSP «Applying inline style» al reiniciar el widget: HTMX copiaba el `style` del campo viejo al nuevo (mismo id) | `attributesToSettle` sin `style`, con su prueba. Lo localizó un escucha de `securitypolicyviolation` |
| `htmx:oobErrorNoTarget #widget-sugerencias` desde la segunda pregunta | La orden de quitar las sugerencias solo va con la primera |
| `TypeError` en `chat.terminar` al tocar una sugerencia: la respuesta quita su propio formulario y ya no tiene componente | `terminar` revisa que siga teniendo raíz; el scroll lo hace el widget |
| Dos comentarios `{# #}` de varias líneas se veían en la página | `{% comment %}`; una prueba existente lo detectó |
| Las fallas del script de Playwright: comprobaciones sin esperar a Alpine, un clic que cerraba el panel ya abierto, el enlace «Nueva conversación» tomado como conversación y el checkout sin dirección ni método de pago | Se corrigió el script; no eran del widget |
| Postman falló una vez por el límite de Groq | Se repitió con el límite enfriado |

## Commits y Pull Requests

Rama `feat/e4-widget-agroia` desde `develop`. Los commits se proponen al cerrar la fase.

## Pendientes y siguiente paso

- **Volver a aceptar el aviso: pendiente para la Entrega 5** (decisión del equipo), en la lista del punto 9 del plan de la [definición técnica](../definicion-tecnica.md#plan-de-construcción). El aviso ya no promete pedirlo: dice que los cambios se anotan en el historial de versiones con su fecha, que al registrarse se acepta la versión vigente y se guarda cuál, y que las funciones nuevas opcionales, como el dictado por voz, piden su propio consentimiento. Lo que haría falta: subir la versión no pide nada a los usuarios existentes, pero el aviso dice «te pediremos aceptarla al iniciar sesión». Haría falta:
  1. **svc-usuarios:**
     - el campo `version_privacidad` en la respuesta del login (o en el perfil);
     - un endpoint `POST /api/v1/auth/aceptar-privacidad/` que guarde la versión vigente y la fecha;
     - pruebas, Postman y la matriz.
  2. **web:**
     - al iniciar sesión, si la versión del usuario no es la vigente, una pantalla «Actualizamos el aviso de privacidad» con el resumen del cambio, el enlace al historial y «Aceptar»;
     - mientras no la acepte, un middleware que lo lleve ahí;
     - y decidir qué puede hacer si no la acepta.
  3. **Las cuentas demo:** `cargar_usuarios_demo` debería guardar la versión vigente.

- **El límite de tokens de Groq** sigue siendo de toda la aplicación (ver la [tercera parte](e4-ia-asincrona.md)).
- **Pantalla de bitácora** en el panel (opcional, fase 4) y **outbox**, como en las fases anteriores.
