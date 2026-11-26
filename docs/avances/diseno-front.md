# Diseño del frontend · Dirección «Altura»

**Fecha:** 24 de noviembre de 2026 · **Entregable:** Entrega 4 · **Responsable:** Bryan Gael Esquivel Pérez

## Resumen

Rediseño visual de todas las pantallas del gateway (`web/`) con la dirección **«Altura»**, elegida entre tres propuestas con maquetas. **Solo cambió lo visual**: plantillas, CSS y JavaScript de componentes. No cambiaron contratos, vistas, rutas ni el flujo asíncrono de la IA. Siguen la CSP estricta (sin scripts, estilos ni `hx-on` en línea), HTMX, Alpine CSP, daisyUI 5 + Tailwind 4 con `django-tailwind-cli` y las fuentes locales. **Sin dependencias nuevas.**

- Se trabajó en dos etapas, con una revisión entre ellas: primero la base (colores, curvas de nivel, encabezado, pie y widget) y el inicio; después el catálogo, el detalle, el carrito, el checkout, los pedidos, AgroIA, el diagnóstico, las cuentas, el panel de administración, los estados vacíos y las páginas de error.
- **Verificación:** 108 revisiones con Playwright (todas las pantallas en escritorio y móvil, tema claro y oscuro) con 0 observaciones. Se revisaron el contraste AA de todo el texto, el foco visible al tabular, que no haya desbordamiento horizontal, las imágenes (alt, ancho y alto, mismo dominio), que no se vea texto de plantilla, y 0 errores de consola y de la CSP.
- **Pruebas:** las del widget dan 52 de 52 y las de la burbuja 23 de 23. Pasan los 321 pytest de web (se agregó uno), `ruff` y la matriz de accesos (154 de 154). En Postman, 212 de 219 aserciones: las 7 restantes fallan solo por la cuota de Groq.

## Dirección

**«Altura»** toma su identidad de las **curvas de nivel** de la Meseta Purépecha, donde crecen las huertas de aguacate: las líneas de un mapa topográfico. Son la firma del sitio. Aparecen en el encabezado de cada sección, el hero, las «parcelas» de los productos, las categorías, el widget, los estados vacíos y las páginas de error.

Principios:

- **Bosque arriba y abajo.** El encabezado, el pie y las bandas de sección son verde Bosque con las curvas encima. El contenido va sobre Niebla, en tarjetas blancas.
- **La parcela.** Cada producto se muestra en un rectángulo 4:3 con el tinte de su categoría y sus curvas. Si tiene foto, la foto ocupa la parcela con el mismo recorte en todas las tarjetas.
- **Pulpa solo sobre oscuro.** El verde claro marca lo activo (la sección actual, los botones sobre Bosque, la insignia «Disponible»), pero nunca es texto sobre un fondo claro: ahí no llega ni a 1.6:1.
- **Sin sombras** salvo la burbuja de AgroIA y los menús. Radio de 6 px en tarjetas; 999 px solo en chips y en la burbuja.

## Paleta

| Nombre | Claro | Oscuro | Uso |
| --- | --- | --- | --- |
| Bosque | `#1E3B16` | `#0F1D0B` | Encabezado, pie, bandas de sección, hero, burbuja |
| Cáscara | `#2E5A1C` | `#9CC46A` | Primario: botones, enlaces, sección activa del panel |
| Pulpa | `#CBDB6E` | `#CBDB6E` | Acento, solo sobre fondos oscuros o como fondo con texto Bosque |
| Andosol | `#3A2E28` | `#E7ECDF` | Precios y totales |
| Niebla | `#EFF3E8` | `#131A11` | Fondo de la página |
| Tarjeta | `#FFFFFF` | `#1C2618` | Tarjetas, formularios, tablas |
| Hueso | `#6B4A2B` | — | Secundario: la insignia «Pago simulado» |
| Texto secundario | `#4D5A46` | `#B4C0A8` | Ayudas, fechas, etiquetas (sustituye a `opacity-70/80` en todo el sitio) |
| Aviso | `#7A4B00` | `#E8C45E` | Avisos en texto (sustituye a `text-warning`, que no pasaba AA sobre claro) |

Los tintes de categoría (`tinte-*` en `fuente.css`) tienen tres colores: el panel, el trazo del pictograma y la curva, y el texto del nombre (`--etiqueta`, nuevo, para que el nombre pase AA sobre su panel).

Los colores propios están en `:root` de `web/static/css/fuente.css` y se exponen a Tailwind con `@theme inline`: `bg-bosque`, `text-bosque-texto`, `text-bosque-suave`, `text-andosol`, `text-suave`, `bg-tarjeta`, `text-curvas-hero` y `text-aviso`. El tema oscuro los redefine.

## Tipografía

Sigue la misma familia, servida desde `static/fonts`: **Barlow Semi Condensed** 600/700 para los títulos (`font-display`) y **Barlow** 400/500 para el texto. Lo que cambió:

- Títulos de página más grandes: de 2 a 2.8 rem en las bandas, y hasta 3.6 rem en el hero.
- Precios con cifras tabulares (`tabular-nums`) en Andosol.
- Sin mayúsculas sostenidas: se quitó la ceja «ADMINISTRACIÓN» del panel.

## Componentes nuevos o rediseñados

| Componente | Qué es |
| --- | --- |
| `static/img/curvas.svg` + clase `.curvas` | Curvas de nivel usadas como máscara de CSS: toman el color del texto y la opacidad que se les dé. Decorativas (`aria-hidden`). |
| `componentes/encabezado.html` | Barra Bosque: marca, buscador (en pantallas grandes), secciones con la activa subrayada en Pulpa, tema, carrito, cuenta y menú de celular. |
| `componentes/pie.html` | Pie Bosque en tres columnas. Con el widget deja margen abajo para que la burbuja no tape lo último. |
| `componentes/seccion.html` | Banda Bosque con curvas para el título de cada sección, con espacio opcional para una foto. |
| `componentes/foto_ambiente.html` + `{% foto_ambiente %}` | Foto de ambiente opcional bajo una capa Bosque al 85 % (ver «Espacios para fotos»). |
| `componentes/tarjeta_producto.html` | La parcela 4:3 (foto o pictograma sobre curvas), la categoría, el nombre, el precio y las existencias. En celular, el botón para agregar es un «+» redondo de 44 × 44 px con el nombre accesible «Agregar <producto> al carrito». |
| `componentes/agregar_carrito.html` | Parámetro nuevo `compacto` (para la tarjeta). Sin sesión, en celular dice «Entrar». |
| `componentes/estado_vacio.html` | Parcela con la mascota, qué pasa y la acción para seguir. |
| `componentes/error.html` | Página de error con la parcela y la mascota (la usan el 404 propio, el 500 y los avisos de cuenta). |
| `componentes/campo.html` | Los campos de archivo usan un selector propio en español (componente `selectorArchivo`); el nativo decía «Choose File». |
| Selector de foto del diagnóstico | Zona con las curvas, «Elegir una foto» y el nombre del archivo (`vistaPrevia.archivoElegido`). El input nativo queda oculto a la vista pero sigue en el orden de tabulación, y el foco se dibuja en la zona. |
| Tablas del panel (`.tabla-tarjetas`) | En celular, cada fila es una tarjeta y cada celda lleva su encabezado (`data-etiqueta`, generado desde la hoja de estilos). |
| Chips de categoría del catálogo | Atajos por categoría arriba de los resultados; en celular se desplazan de lado. |
| Widget de AgroIA | Burbuja Bosque con anillo Pulpa y encabezado del panel Bosque con curvas. Los mensajes de AgroIA llevan la mascota como avatar, en el chat y en el widget. |

### Comportamiento nuevo en el navegador (solo de presentación)

- **La burbuja en celular se oculta al bajar** por la página y vuelve al subir o al detenerse (700 ms). No se oculta con el panel abierto ni con una respuesta nueva sin leer, y si recibe el foco con el teclado vuelve a aparecer: se oculta con `transform` y `opacity`, nunca con `visibility`. Con `prefers-reduced-motion` aparece y desaparece sin animación. Está en `widgetAgroia` (`vigilarDesplazamiento`, `burbujaEscondida`) y en `.burbuja-agroia` de `fuente.css`.
- **Listas que se desplazan de lado** (`data-desplazar-al-foco`: categorías del inicio y chips del catálogo): el elemento que recibe el foco se desplaza hasta quedar completo a la vista, sin animación con `prefers-reduced-motion`. Es un oyente de `focusin` en `componentes.js`.

## Contraste (WCAG 2.1)

Mínimo 4.5:1 para texto normal; 3:1 para texto grande (24 px o más, o 18.7 px o más en negrita), componentes y foco. **Ninguno de los 50 pares falla.** Pulpa como texto sobre fondos claros daría 1.34:1 sobre Niebla y 1.51:1 sobre blanco, por eso no se usa así.

### Tema claro

| Uso | Texto | Fondo | Contraste |
| --- | --- | --- | --- |
| Texto sobre Niebla (fondo) | `#1F2B1B` | `#EFF3E8` | 13.14:1 |
| Texto sobre blanco (tarjetas) | `#1F2B1B` | `#FFFFFF` | 14.79:1 |
| Texto secundario sobre Niebla | `#4D5A46` | `#EFF3E8` | 6.51:1 |
| Texto secundario sobre blanco | `#4D5A46` | `#FFFFFF` | 7.33:1 |
| Pestaña inactiva y encabezado de tabla sobre Niebla | `#4D5A46` | `#EFF3E8` | 6.51:1 |
| Enlace Cáscara sobre Niebla | `#2E5A1C` | `#EFF3E8` | 7.19:1 |
| Enlace Cáscara sobre blanco | `#2E5A1C` | `#FFFFFF` | 8.09:1 |
| Botón primario: blanco sobre Cáscara | `#FFFFFF` | `#2E5A1C` | 8.09:1 |
| Precio Andosol sobre blanco | `#3A2E28` | `#FFFFFF` | 13.11:1 |
| Hueso sobre blanco (insignia «Pago simulado») | `#6B4A2B` | `#FFFFFF` | 7.96:1 |
| Error sobre blanco | `#A63A2B` | `#FFFFFF` | 6.44:1 |
| Error sobre Niebla | `#A63A2B` | `#EFF3E8` | 5.72:1 |
| Aviso sobre blanco | `#7A4B00` | `#FFFFFF` | 7.41:1 |
| Aviso sobre Niebla | `#7A4B00` | `#EFF3E8` | 6.58:1 |
| Insignia «Disponible»: Bosque sobre Pulpa | `#1E3B16` | `#CBDB6E` | 8.21:1 |
| Insignia «Quedan N»: texto sobre ámbar | `#2B2008` | `#E2B33C` | 8.19:1 |
| Insignia «Activo» / «Verificado»: blanco sobre verde | `#FFFFFF` | `#2E6B34` | 6.42:1 |
| Categoría Fertilizantes | `#4E5A10` | `#EEF2CF` | 6.53:1 |
| Categoría Fungicidas | `#2E5A1C` | `#DFE9D3` | 6.45:1 |
| Categoría Herramientas | `#5C3F24` | `#EFE4D8` | 7.65:1 |
| Categoría Protección | `#474C3F` | `#E6E7DF` | 7.10:1 |
| Categoría Riego | `#1F5752` | `#D9EBE6` | 6.67:1 |
| Burbuja de AgroIA (componente): Bosque contra Niebla | `#1E3B16` | `#EFF3E8` | 11.02:1 (mín. 3) |
| Foco: anillo Pulpa con borde de tinta, contra Niebla | `#1F2B1B` | `#EFF3E8` | 13.14:1 (mín. 3) |

### Bosque (los dos temas)

| Uso | Texto | Fondo | Contraste |
| --- | --- | --- | --- |
| Texto claro sobre Bosque (encabezado, pie, bandas) | `#EEF4E4` | `#1E3B16` | 11.05:1 |
| Texto secundario sobre Bosque | `#C9D8B8` | `#1E3B16` | 8.27:1 |
| Pulpa sobre Bosque (sección activa) | `#CBDB6E` | `#1E3B16` | 8.21:1 |
| Botón Pulpa: Bosque sobre Pulpa | `#1E3B16` | `#CBDB6E` | 8.21:1 |
| Texto claro sobre una foto bajo la capa Bosque al 85 % | `#EEF4E4` | `#24411B` | 10.12:1 |

### Tema oscuro (`agroia-oscuro`)

| Uso | Texto | Fondo | Contraste |
| --- | --- | --- | --- |
| Texto sobre el fondo | `#E7ECDF` | `#131A11` | 14.75:1 |
| Texto sobre tarjeta | `#E7ECDF` | `#1C2618` | 13.03:1 |
| Texto secundario sobre el fondo | `#B4C0A8` | `#131A11` | 9.33:1 |
| Texto secundario sobre tarjeta | `#B4C0A8` | `#1C2618` | 8.24:1 |
| Enlace primario sobre el fondo | `#9CC46A` | `#131A11` | 8.89:1 |
| Botón primario: texto sobre verde claro | `#12200C` | `#9CC46A` | 8.50:1 |
| Precio sobre tarjeta | `#E7ECDF` | `#1C2618` | 13.03:1 |
| Error sobre el fondo | `#EF8F80` | `#131A11` | 7.53:1 |
| Aviso sobre el fondo | `#E8C45E` | `#131A11` | 10.55:1 |
| Aviso sobre tarjeta | `#E8C45E` | `#1C2618` | 9.32:1 |
| Insignia «Disponible»: Bosque sobre Pulpa | `#1E3B16` | `#CBDB6E` | 8.21:1 |
| Insignia «Activo» / «Verificado» | `#0E2410` | `#8CC68F` | 8.28:1 |
| Texto claro sobre el encabezado oscuro | `#EEF4E4` | `#0F1D0B` | 15.57:1 |
| Pulpa sobre el encabezado oscuro | `#CBDB6E` | `#0F1D0B` | 11.57:1 |
| Categoría Fungicidas | `#CFE0B4` | `#22311B` | 9.83:1 |
| Categoría Fertilizantes | `#DFE8A6` | `#2C3014` | 10.54:1 |
| Categoría Herramientas | `#E6CFB5` | `#31261B` | 9.80:1 |
| Categoría Riego | `#BFE1DA` | `#1B2F2B` | 10.08:1 |
| Categoría Protección | `#D9DCC8` | `#2A2C22` | 10.14:1 |
| Foco: anillo Pulpa contra el fondo | `#CBDB6E` | `#131A11` | 11.74:1 (mín. 3) |

Además de la tabla, Playwright midió el contraste del texto tal como se ve en cada pantalla (con la opacidad y el fondo reales). Encontró dos fallas que la tabla no mostraba: las pestañas inactivas del panel (2.95:1) y los encabezados de tabla (4.07:1), que daisyUI aclara con opacidad. Se corrigieron con el texto secundario del tema.

## Espacios para fotos

Las fotos son opcionales: **sin foto, cada pantalla se ve igual** (Bosque con curvas). Todas llevan `alt`, `width` y `height` (sin saltos de diseño) y `loading="lazy"`, salvo la de arriba de la página, que carga con `fetchpriority="high"`. Siempre se sirven desde `static/` o desde el almacenamiento, nunca desde otro dominio (CSP `img-src 'self'`).

| Archivo en `web/static/img/ambiente/` | Dónde | Tamaño recomendado |
| --- | --- | --- |
| `inicio.webp` | Hero del inicio | 1600 × 900, hasta ~250 KB |
| `agroia.webp` | Tarjeta «Pregúntale a AgroIA» del inicio | 800 × 300, hasta ~80 KB |
| `diagnostico.webp` | Tarjeta «Diagnóstico por imagen» del inicio | 800 × 300, hasta ~80 KB |
| `iniciar_sesion.webp` | Panel lateral del login | 1200 × 1600, hasta ~200 KB |
| `registro.webp` | Panel lateral del registro | 1200 × 1600, hasta ~200 KB |

- **Productos:** si el producto tiene imagen (el campo que ya existía), se muestra dentro de la parcela con `object-cover` 4:3, el mismo recorte en las tarjetas, el detalle y el carrito. Si no tiene, queda el pictograma de su categoría.
- **Cómo agregar una foto:** ver «Fotos de ambiente» en el [README](../../README.md). Antes de subirla, se registra en [créditos de imágenes](../creditos-imagenes.md). Las fotos de roña y antracnosis solo pueden ser reales y con licencia libre, nunca generadas por IA.

## Capturas de antes y después

Desktop a 1280 px y celular a 390 px (recortadas a la parte de arriba). El antes es el estado de `develop` en 31a61e6.

| Pantalla | Antes | Después |
| --- | --- | --- |
| Inicio | ![](img/diseno-inicio-antes-escritorio.png) | ![](img/diseno-inicio-despues-escritorio.png) |
| Catálogo | ![](img/diseno-catalogo-antes-escritorio.png) | ![](img/diseno-catalogo-despues-escritorio.png) |
| Detalle | ![](img/diseno-detalle-antes-escritorio.png) | ![](img/diseno-detalle-despues-escritorio.png) |
| Carrito | ![](img/diseno-carrito-antes-escritorio.png) | ![](img/diseno-carrito-despues-escritorio.png) |
| Checkout | ![](img/diseno-checkout-antes-escritorio.png) | ![](img/diseno-checkout-despues-escritorio.png) |
| AgroIA | ![](img/diseno-agroia-antes-escritorio.png) | ![](img/diseno-agroia-despues-escritorio.png) |
| Diagnóstico | ![](img/diseno-diagnostico-antes-escritorio.png) | ![](img/diseno-diagnostico-despues-escritorio.png) |
| Login | ![](img/diseno-login-antes-escritorio.png) | ![](img/diseno-login-despues-escritorio.png) |
| Panel | ![](img/diseno-panel-antes-escritorio.png) | ![](img/diseno-panel-despues-escritorio.png) |

Las versiones de celular están junto a estas, con el sufijo `-movil` (por ejemplo, `img/diseno-panel-despues-movil.png`, con la tabla en tarjetas).

## Decisiones técnicas

- **Las curvas son una máscara de CSS** (`mask: url(curvas.svg)` con `background-color: currentColor`), no un `<img>`. Así un solo SVG sirve para todos los colores y opacidades, y es decorativo por definición. Se carga desde el mismo origen, lo que permite la CSP.
- **Las clases que cambian con JavaScript no se generan con Tailwind**, que solo lee las plantillas. Por eso el estado oculto de la burbuja es un atributo (`data-escondida`) con su regla en `fuente.css`.
- **Encabezados de celda en el panel con `attr()` desde la hoja de estilos**, no con `<span>` duplicados en la plantilla. La CSP permite el contenido generado por CSS.
- **Dos etiquetas para el input de archivo** (el título y la zona). El nombre accesible incluye las dos. Es más largo, pero el input nativo sigue siendo el control real: funciona sin JavaScript y con el teclado.
- **Visitante en celular:** en la tarjeta, el enlace al login dice «Entrar», con el nombre del producto para lectores de pantalla.

## Verificación

### Playwright (Chromium)

- **Todas las pantallas** (`verificar.py`, 108 revisiones): 29 pantallas en escritorio y móvil con el tema claro y 25 con el oscuro (la compra y el pago se recorren solo en claro, para no crear más pedidos).
  - Pantallas: inicio, catálogo (normal, por categoría y vacío), detalle, login, registro, recuperar, aviso de privacidad, 404 propio (producto inexistente), carrito vacío y con productos, checkout, pedido pendiente y pagado, mis pedidos, AgroIA, diagnóstico, mis diagnósticos, mi cuenta, cambiar contraseña, widget abierto y el panel (productos, pedidos, usuarios, categorías, producto nuevo, editar producto y detalle de pedido).
  - En cada una se revisó: contraste AA de todo el texto visible, foco visible en los primeros 30 elementos al tabular, sin desbordamiento horizontal, imágenes con alt, ancho y alto y del mismo dominio, sin texto de plantilla a la vista, y errores de consola y de la CSP (`securitypolicyviolation`).
  - **Resultado: 0 observaciones y 0 errores.**
  - En móvil, el botón «+» de la tarjeta mide 44 × 44 px y se llama «Agregar Malla sombra 50%, 4 x 25 m al carrito». «Confirmar pedido» (316 × 48) y «Pagar» (314 × 48) se pulsaron y el pedido quedó «Pagado».
- **Widget**: las 52 comprobaciones de la verificación del widget dan 52 de 52, incluidas «la burbuja no tapa Continuar, Confirmar ni Pagar» en móvil. El script se ajustó en dos cosas: espera a que la burbuja vuelva tras desplazarse, y el selector del primer producto ya no toma los chips de categoría.
- **Burbuja** (`burbuja.py`, 23 de 23):
  - se oculta al bajar y vuelve al subir y al detenerse;
  - con `prefers-reduced-motion`, sin animación;
  - sigue siendo enfocable mientras está oculta y vuelve al recibir el foco;
  - no se oculta con una respuesta nueva ni con el panel abierto, y nunca en escritorio;
  - cada categoría enfocada queda completa a la vista, con y sin animación.

### Corridas completas

| Prueba | Resultado |
| --- | --- |
| `pytest` de web | 321 de 321. **Ninguna prueba existente se modificó.** Se agregó una: ninguna plantilla tiene un comentario `{# #}` partido en varias líneas. |
| `ruff check` y `ruff format --check` (todo el repositorio) | Sin observaciones; 346 archivos con formato correcto |
| Postman (Newman) | 139 peticiones, 212 de 219 aserciones. **Las 7 que fallan son por la cuota de Groq:** el agente respondió `RateLimitError`, así que «Preguntar al agente» y «Preguntar a AgroIA (gateway)» dieron 503, y las peticiones que dependen de esa respuesta fallaron en cadena (estado de la solicitud, 404; guardar la respuesta, 400; un script que leía la respuesta). |
| Matriz de accesos ([`docs/entregable-4/matriz-accesos.md`](../entregable-4/matriz-accesos.md)) | 154 de 154. 3 marcados «permitido (servicio externo no disponible)» por la cuota de Groq. |

Los datos que dejaron las corridas (pedidos, conversaciones y el usuario de Newman) se borraron con `limpiar_datos_prueba`, y el stock se restableció con `cargar_datos_demo`.

## Problemas encontrados

- **Comentario de plantilla visible.** Un comentario `{# … #}` partido en dos líneas en el selector de foto se mostraba como texto en el diagnóstico. Se cambió a `{% comment %}`, igual que otro en `campo.html`. Se agregó una prueba que revisa todas las plantillas, y la verificación con Playwright busca texto de plantilla a la vista.
- **Contraste que daisyUI aclara con opacidad.** Las pestañas inactivas y los encabezados de tabla no pasaban AA. También fallaban `text-warning` y los `opacity-70/80` de textos en 25 plantillas. Todo pasó al texto secundario y al aviso del tema.
- **Falta de `{% load agroia %}`** en el catálogo al usar el filtro `tinte` para los chips: 12 pruebas fallaron en cadena hasta agregarlo.
- **La burbuja sobre texto en páginas largas** (el aviso de privacidad en celular): se resolvió ocultándola mientras se baja (opción aprobada en la revisión de la primera etapa).

## Commits y Pull Requests

Rama `feat/diseno-front` desde `develop` (31a61e6). Los commits los hace el equipo.

## Pendientes y siguiente paso

- Agregar las fotos de ambiente reales (con su crédito) cuando el equipo las tenga.
- Productos relacionados en el detalle: la vista no los envía; quedaría para cuando exista el contrato.
- La tabla del panel en tarjetas usa `display: block` en celular. Algunos lectores de pantalla dejan de anunciarla como tabla; cada celda lleva su encabezado como texto, así que la información no se pierde.
