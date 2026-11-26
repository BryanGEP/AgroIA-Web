# Evidencia en logs del flujo asíncrono

Líneas reales de `docker compose logs --timestamps` del **26 de noviembre de 2026**, entre las 13:44 y las 13:47 hora de México (19:44 a 19:47 UTC, la hora que muestran los logs). Las extrajo un script que busca la `correlacion_id` de cada paso en los contenedores `web`, `svc-usuarios`, `svc-tienda`, `svc-contenido`, `svc-ia-worker`, `svc-contenido-eventos` y `svc-usuarios-eventos` (de este último, solo sus líneas JSON), y las ordena por la marca de tiempo de Docker (milisegundos).

**Cómo se generó la correlación:** el gateway pone un `X-Correlacion-Id` (UUID) en cada petición del navegador y lo devuelve en la respuesta; los servicios la validan con `CorrelacionMiddleware`, la ponen en el sobre del evento y el consumidor la hereda al procesarlo.

**Revisión de datos sensibles** (a mano y con búsqueda en todo lo extraído): 0 tokens JWT (`eyJ…`), 0 `token=`, 0 enlaces de verificación o recuperación (solo el patrón de ruta `verificar-correo/` del gateway, sin el token), 0 correos (`@`), 0 contraseñas y 0 textos de preguntas o respuestas (ni los campos `pregunta`, `historial`, `respuesta` o `texto`). **No se incluye la salida de consola de `svc-usuarios-eventos`**, que imprime el correo de prueba con su enlace. Los `usuario_id` son UUID de las cuentas de demostración y del usuario de prueba.

Cada línea es JSON tal como la escribe el servicio; arriba de cada bloque, una tabla explica cada línea en orden.


## 1. Pregunta real a AgroIA (flujo principal)

Una pregunta desde el widget, con el agente real (Groq). Es el flujo que pide la entrega: **petición del gateway → `evento_publicado` de svc-contenido → `evento_procesado` del worker → `evento_procesado` de svc-contenido-eventos**, todas con la misma `correlacion_id`. De la publicación de la solicitud al guardado de la respuesta pasan unos 1.3 s; el navegador recibió el 202 al instante y consultó el estado con polling.


### Pregunta en el widget (POST /agroia/widget/preguntar/)

`correlacion_id`: `99df6c84-9d6b-43b4-802b-ab4159244c6f`


| # | Hora (UTC) | Contenedor | Suceso | Qué significa |
| --- | --- | --- | --- | --- |
| 1 | 19:44:40.958 | `svc-contenido` | evento_publicado · `ia_pregunta_solicitada` | svc-contenido (API) guardó la pregunta en MongoDB y publica la solicitud en `ia-solicitudes` (la pregunta viaja en el evento, pero no en el log). |
| 2 | 19:44:40.968 | `web` | peticion | El gateway registra la petición del navegador al terminarla: la ruta como patrón (`agroia/widget/preguntar/`), el estado 200 y 26 ms. Aparece después de los eventos porque se escribe al responder. |
| 3 | 19:44:42.281 | `svc-ia-worker` | evento_publicado · `ia_respuesta_generada` | El worker de svc-ia publica la respuesta del agente en `ia-resultados`, con la misma correlación. |
| 4 | 19:44:42.281 | `svc-ia-worker` | evento_procesado · `ia_pregunta_solicitada` | El worker (grupo `svc-ia`) terminó la solicitud: llamó al agente y confirmó el mensaje (`XACK`). Intento 1, 1 entrega(s), 1323 ms, consumidor `svc-ia-ec5fd32c967e-1`. |
| 5 | 19:44:42.283 | `svc-contenido-eventos` | evento_procesado · `ia_respuesta_generada` | svc-contenido-eventos (grupo `svc-contenido`) guardó la respuesta en la conversación de MongoDB y confirmó. Intento 1, 1 entrega(s), 2 ms, consumidor `svc-contenido-1a1acc8cba69`. |

```text
svc-contenido          {"evento": "evento_publicado", "fecha": "2026-11-26T19:44:40+00:00", "evento_id": "57d73a43-e2b0-492a-a465-992aa9f9f4a1", "tipo": "ia_pregunta_solicitada", "version": 1, "origen": "svc-contenido", "correlacion_id": "99df6c84-9d6b-43b4-802b-ab4159244c6f", "stream": "agroia:eventos:ia-solicitudes", "id_mensaje": "1795722280958-0"}
web                    {"evento": "peticion", "fecha": "2026-11-26T19:44:40+00:00", "metodo": "POST", "ruta": "agroia/widget/preguntar/", "estado": 200, "duracion_ms": 26, "correlacion_id": "99df6c84-9d6b-43b4-802b-ab4159244c6f", "usuario_id": "d1f36202-c0d6-4d89-91c9-15326684516d"}
svc-ia-worker          {"evento": "evento_publicado", "fecha": "2026-11-26T19:44:42+00:00", "evento_id": "b3c0f163-8256-40c8-b551-6dce82d81a72", "tipo": "ia_respuesta_generada", "version": 1, "origen": "svc-ia", "correlacion_id": "99df6c84-9d6b-43b4-802b-ab4159244c6f", "stream": "agroia:eventos:ia-resultados", "id_mensaje": "1795722282280-0"}
svc-ia-worker          {"evento": "evento_procesado", "fecha": "2026-11-26T19:44:42+00:00", "grupo": "svc-ia", "stream": "agroia:eventos:ia-solicitudes", "id_mensaje": "1795722280958-0", "evento_id": "57d73a43-e2b0-492a-a465-992aa9f9f4a1", "tipo": "ia_pregunta_solicitada", "version": 1, "origen": "svc-contenido", "correlacion_id": "99df6c84-9d6b-43b4-802b-ab4159244c6f", "intento": 1, "consumidor": "svc-ia-ec5fd32c967e-1", "entregas": 1, "inicio": "2026-11-26T19:44:40.958+00:00", "duracion_ms": 1323}
svc-contenido-eventos  {"evento": "evento_procesado", "fecha": "2026-11-26T19:44:42+00:00", "grupo": "svc-contenido", "stream": "agroia:eventos:ia-resultados", "id_mensaje": "1795722282280-0", "evento_id": "b3c0f163-8256-40c8-b551-6dce82d81a72", "tipo": "ia_respuesta_generada", "version": 1, "origen": "svc-ia", "correlacion_id": "99df6c84-9d6b-43b4-802b-ab4159244c6f", "intento": 1, "consumidor": "svc-contenido-1a1acc8cba69", "entregas": 1, "inicio": "2026-11-26T19:44:42.281+00:00", "duracion_ms": 2}
```

## 2. Fallo y reintento (agente detenido)

Con `docker compose stop agente`, la misma pregunta desde el widget en el celular. El worker reintenta dos veces (5 y 10 s después de cada fallo; la llamada sin conexión tarda unos segundos), publica la fallida y el evento queda en fallidos. Con el agente de vuelta, «Reintentar» crea **otra solicitud con otra correlación** (es otra petición del navegador) para la misma pregunta, y ahora sí llega la respuesta.


### Pregunta con el agente detenido

`correlacion_id`: `5de2407a-f4e0-459e-9c61-89e9e820a718`


| # | Hora (UTC) | Contenedor | Suceso | Qué significa |
| --- | --- | --- | --- | --- |
| 1 | 19:45:10.776 | `svc-contenido` | evento_publicado · `ia_pregunta_solicitada` | svc-contenido (API) guardó la pregunta en MongoDB y publica la solicitud en `ia-solicitudes` (la pregunta viaja en el evento, pero no en el log). |
| 2 | 19:45:10.780 | `web` | peticion | El gateway registra la petición del navegador al terminarla: la ruta como patrón (`agroia/widget/preguntar/`), el estado 200 y 19 ms. Aparece después de los eventos porque se escribe al responder. |
| 3 | 19:45:18.783 | `svc-ia-worker` | evento_reintentado · `ia_pregunta_solicitada` | El agente no responde: el manejador falló (`AgenteNoDisponible: sin_conexion`) y el evento queda pendiente para reintentarse con espera creciente (intento 1). |
| 4 | 19:45:31.846 | `svc-ia-worker` | evento_reintentado · `ia_pregunta_solicitada` | El agente no responde: el manejador falló (`AgenteNoDisponible: sin_conexion`) y el evento queda pendiente para reintentarse con espera creciente (intento 2). |
| 5 | 19:45:49.916 | `svc-ia-worker` | evento_publicado · `ia_respuesta_fallida` | El worker de svc-ia agotó los reintentos y publica la fallida (`al_agotar`) para que el usuario no espere al vencimiento. |
| 6 | 19:45:49.917 | `svc-ia-worker` | evento_fallido · `ia_pregunta_solicitada` | Agotó los reintentos: el evento se copia al stream de fallidos sin la pregunta ni el historial (`datos_omitidos`). |
| 7 | 19:45:49.918 | `svc-contenido-eventos` | evento_procesado · `ia_respuesta_fallida` | svc-contenido-eventos (grupo `svc-contenido`) marcó la solicitud como `fallido`: la pantalla ofrece «Reintentar». Intento 1, 1 entrega(s), 1 ms, consumidor `svc-contenido-1a1acc8cba69`. |

```text
svc-contenido          {"evento": "evento_publicado", "fecha": "2026-11-26T19:45:10+00:00", "evento_id": "0d5a269f-c15d-424a-bc14-3df49691c2d2", "tipo": "ia_pregunta_solicitada", "version": 1, "origen": "svc-contenido", "correlacion_id": "5de2407a-f4e0-459e-9c61-89e9e820a718", "stream": "agroia:eventos:ia-solicitudes", "id_mensaje": "1795722310776-0"}
web                    {"evento": "peticion", "fecha": "2026-11-26T19:45:10+00:00", "metodo": "POST", "ruta": "agroia/widget/preguntar/", "estado": 200, "duracion_ms": 19, "correlacion_id": "5de2407a-f4e0-459e-9c61-89e9e820a718", "usuario_id": "d1f36202-c0d6-4d89-91c9-15326684516d"}
svc-ia-worker          {"evento": "evento_reintentado", "fecha": "2026-11-26T19:45:18+00:00", "grupo": "svc-ia", "stream": "agroia:eventos:ia-solicitudes", "id_mensaje": "1795722310776-0", "evento_id": "0d5a269f-c15d-424a-bc14-3df49691c2d2", "tipo": "ia_pregunta_solicitada", "version": 1, "origen": "svc-contenido", "correlacion_id": "5de2407a-f4e0-459e-9c61-89e9e820a718", "intento": 1, "consumidor": "svc-ia-ec5fd32c967e-1", "entregas": 1, "inicio": "2026-11-26T19:45:10.777+00:00", "duracion_ms": 8006, "motivo": "AgenteNoDisponible: sin_conexion", "siguiente_en_segundos": 5.0}
svc-ia-worker          {"evento": "evento_reintentado", "fecha": "2026-11-26T19:45:31+00:00", "grupo": "svc-ia", "stream": "agroia:eventos:ia-solicitudes", "id_mensaje": "1795722310776-0", "evento_id": "0d5a269f-c15d-424a-bc14-3df49691c2d2", "tipo": "ia_pregunta_solicitada", "version": 1, "origen": "svc-contenido", "correlacion_id": "5de2407a-f4e0-459e-9c61-89e9e820a718", "intento": 2, "consumidor": "svc-ia-ec5fd32c967e-1", "entregas": 2, "inicio": "2026-11-26T19:45:23.841+00:00", "duracion_ms": 8005, "motivo": "AgenteNoDisponible: sin_conexion", "siguiente_en_segundos": 10.0}
svc-ia-worker          {"evento": "evento_publicado", "fecha": "2026-11-26T19:45:49+00:00", "evento_id": "b9a3ae12-33d6-4fab-aeb6-2173f756fd09", "tipo": "ia_respuesta_fallida", "version": 1, "origen": "svc-ia", "correlacion_id": "5de2407a-f4e0-459e-9c61-89e9e820a718", "stream": "agroia:eventos:ia-resultados", "id_mensaje": "1795722349916-0"}
svc-ia-worker          {"evento": "evento_fallido", "fecha": "2026-11-26T19:45:49+00:00", "grupo": "svc-ia", "stream": "agroia:eventos:ia-solicitudes", "id_mensaje": "1795722310776-0", "evento_id": "0d5a269f-c15d-424a-bc14-3df49691c2d2", "tipo": "ia_pregunta_solicitada", "version": 1, "origen": "svc-contenido", "correlacion_id": "5de2407a-f4e0-459e-9c61-89e9e820a718", "intento": 3, "consumidor": "svc-ia-ec5fd32c967e-1", "entregas": 3, "inicio": "2026-11-26T19:45:41.907+00:00", "duracion_ms": 8008, "intentos": 3, "motivo": "AgenteNoDisponible: sin_conexion"}
svc-contenido-eventos  {"evento": "evento_procesado", "fecha": "2026-11-26T19:45:49+00:00", "grupo": "svc-contenido", "stream": "agroia:eventos:ia-resultados", "id_mensaje": "1795722349916-0", "evento_id": "b9a3ae12-33d6-4fab-aeb6-2173f756fd09", "tipo": "ia_respuesta_fallida", "version": 1, "origen": "svc-ia", "correlacion_id": "5de2407a-f4e0-459e-9c61-89e9e820a718", "intento": 1, "consumidor": "svc-contenido-1a1acc8cba69", "entregas": 1, "inicio": "2026-11-26T19:45:49.917+00:00", "duracion_ms": 1}
```

### «Reintentar» con el agente de vuelta

`correlacion_id`: `41ff58d7-cfe9-40a2-b7cb-c7c054368a92`


| # | Hora (UTC) | Contenedor | Suceso | Qué significa |
| --- | --- | --- | --- | --- |
| 1 | 19:46:04.676 | `svc-contenido` | evento_publicado · `ia_pregunta_solicitada` | svc-contenido (API) guardó la pregunta en MongoDB y publica la solicitud en `ia-solicitudes` (la pregunta viaja en el evento, pero no en el log). |
| 2 | 19:46:04.681 | `web` | peticion | El gateway registra la petición del navegador al terminarla: la ruta como patrón (`agroia/<str:conversacion_id>/reintentar/`), el estado 200 y 25 ms. Aparece después de los eventos porque se escribe al responder. |
| 3 | 19:46:05.544 | `svc-ia-worker` | evento_publicado · `ia_respuesta_generada` | El worker de svc-ia publica la respuesta del agente en `ia-resultados`, con la misma correlación. |
| 4 | 19:46:05.544 | `svc-ia-worker` | evento_procesado · `ia_pregunta_solicitada` | El worker (grupo `svc-ia`) terminó la solicitud: llamó al agente y confirmó el mensaje (`XACK`). Intento 1, 1 entrega(s), 867 ms, consumidor `svc-ia-ec5fd32c967e-1`. |
| 5 | 19:46:05.546 | `svc-contenido-eventos` | evento_procesado · `ia_respuesta_generada` | svc-contenido-eventos (grupo `svc-contenido`) guardó la respuesta en la conversación de MongoDB y confirmó. Intento 1, 1 entrega(s), 2 ms, consumidor `svc-contenido-1a1acc8cba69`. |

```text
svc-contenido          {"evento": "evento_publicado", "fecha": "2026-11-26T19:46:04+00:00", "evento_id": "cb9bf4f4-9a06-412e-ba20-8ead8e2ab546", "tipo": "ia_pregunta_solicitada", "version": 1, "origen": "svc-contenido", "correlacion_id": "41ff58d7-cfe9-40a2-b7cb-c7c054368a92", "stream": "agroia:eventos:ia-solicitudes", "id_mensaje": "1795722364676-0"}
web                    {"evento": "peticion", "fecha": "2026-11-26T19:46:04+00:00", "metodo": "POST", "ruta": "agroia/<str:conversacion_id>/reintentar/", "estado": 200, "duracion_ms": 25, "correlacion_id": "41ff58d7-cfe9-40a2-b7cb-c7c054368a92", "usuario_id": "d1f36202-c0d6-4d89-91c9-15326684516d"}
svc-ia-worker          {"evento": "evento_publicado", "fecha": "2026-11-26T19:46:05+00:00", "evento_id": "59bd08a7-a195-486e-a67d-c64e2ac30fc8", "tipo": "ia_respuesta_generada", "version": 1, "origen": "svc-ia", "correlacion_id": "41ff58d7-cfe9-40a2-b7cb-c7c054368a92", "stream": "agroia:eventos:ia-resultados", "id_mensaje": "1795722365543-0"}
svc-ia-worker          {"evento": "evento_procesado", "fecha": "2026-11-26T19:46:05+00:00", "grupo": "svc-ia", "stream": "agroia:eventos:ia-solicitudes", "id_mensaje": "1795722364676-0", "evento_id": "cb9bf4f4-9a06-412e-ba20-8ead8e2ab546", "tipo": "ia_pregunta_solicitada", "version": 1, "origen": "svc-contenido", "correlacion_id": "41ff58d7-cfe9-40a2-b7cb-c7c054368a92", "intento": 1, "consumidor": "svc-ia-ec5fd32c967e-1", "entregas": 1, "inicio": "2026-11-26T19:46:04.676+00:00", "duracion_ms": 867}
svc-contenido-eventos  {"evento": "evento_procesado", "fecha": "2026-11-26T19:46:05+00:00", "grupo": "svc-contenido", "stream": "agroia:eventos:ia-resultados", "id_mensaje": "1795722365543-0", "evento_id": "59bd08a7-a195-486e-a67d-c64e2ac30fc8", "tipo": "ia_respuesta_generada", "version": 1, "origen": "svc-ia", "correlacion_id": "41ff58d7-cfe9-40a2-b7cb-c7c054368a92", "intento": 1, "consumidor": "svc-contenido-1a1acc8cba69", "entregas": 1, "inicio": "2026-11-26T19:46:05.544+00:00", "duracion_ms": 2}
```

## 3. Flujo de negocio: registro → verificación → pedido → pago

Un usuario de prueba (con el formato de correo de prueba que reconoce y borra `limpiar_datos_prueba`) se registra, verifica su correo con el enlace, compra y paga. Cada acción es una petición con su propia correlación, y cada una dispara eventos que afectan a otro servicio: svc-contenido los guarda en la bitácora y el consumidor de correos envía el correo.


### Registro (POST /registro/)

`correlacion_id`: `d9f2f213-dec3-4cf4-8618-a7f549b1618f`


| # | Hora (UTC) | Contenedor | Suceso | Qué significa |
| --- | --- | --- | --- | --- |
| 1 | 19:44:44.470 | `svc-usuarios` | evento_publicado · `correo_solicitado` | svc-usuarios pide el correo de verificación al consumidor de correos (sin el token, que se genera al procesar). |
| 2 | 19:44:44.471 | `svc-usuarios` | evento_publicado · `usuario_registrado` | svc-usuarios publica el registro, después del commit, para la bitácora. |
| 3 | 19:44:44.473 | `svc-contenido-eventos` | evento_procesado · `usuario_registrado` | svc-contenido-eventos (grupo `svc-contenido`) guardó el evento en la bitácora (índice único de `evento_id`). Intento 1, 1 entrega(s), 1 ms, consumidor `svc-contenido-1a1acc8cba69`. |
| 4 | 19:44:44.477 | `svc-usuarios-eventos` | evento_procesado · `correo_solicitado` | El consumidor de correos (grupo `svc-usuarios`) envió el correo (en desarrollo, a la consola; esa salida no se incluye). Intento 1, 1 entrega(s), 6 ms, consumidor `svc-usuarios-5f118d3a0d6c`. |
| 5 | 19:44:44.478 | `web` | peticion | El gateway registra la petición del navegador al terminarla: la ruta como patrón (`registro/`), el estado 201 y 137 ms. Aparece después de los eventos porque se escribe al responder. |

```text
svc-usuarios           {"evento": "evento_publicado", "fecha": "2026-11-26T19:44:44+00:00", "evento_id": "42ec77f1-d83a-4b40-85ab-910ca690ef4c", "tipo": "correo_solicitado", "version": 1, "origen": "svc-usuarios", "correlacion_id": "d9f2f213-dec3-4cf4-8618-a7f549b1618f", "stream": "agroia:eventos:correos", "id_mensaje": "1795722284470-0"}
svc-usuarios           {"evento": "evento_publicado", "fecha": "2026-11-26T19:44:44+00:00", "evento_id": "f53ca30e-c260-445c-ba8a-faa2183894da", "tipo": "usuario_registrado", "version": 1, "origen": "svc-usuarios", "correlacion_id": "d9f2f213-dec3-4cf4-8618-a7f549b1618f", "stream": "agroia:eventos:usuarios", "id_mensaje": "1795722284471-0"}
svc-contenido-eventos  {"evento": "evento_procesado", "fecha": "2026-11-26T19:44:44+00:00", "grupo": "svc-contenido", "stream": "agroia:eventos:usuarios", "id_mensaje": "1795722284471-0", "evento_id": "f53ca30e-c260-445c-ba8a-faa2183894da", "tipo": "usuario_registrado", "version": 1, "origen": "svc-usuarios", "correlacion_id": "d9f2f213-dec3-4cf4-8618-a7f549b1618f", "intento": 1, "consumidor": "svc-contenido-1a1acc8cba69", "entregas": 1, "inicio": "2026-11-26T19:44:44.471+00:00", "duracion_ms": 1}
svc-usuarios-eventos   {"evento": "evento_procesado", "fecha": "2026-11-26T19:44:44+00:00", "grupo": "svc-usuarios", "stream": "agroia:eventos:correos", "id_mensaje": "1795722284470-0", "evento_id": "42ec77f1-d83a-4b40-85ab-910ca690ef4c", "tipo": "correo_solicitado", "version": 1, "origen": "svc-usuarios", "correlacion_id": "d9f2f213-dec3-4cf4-8618-a7f549b1618f", "intento": 1, "consumidor": "svc-usuarios-5f118d3a0d6c", "entregas": 1, "inicio": "2026-11-26T19:44:44.471+00:00", "duracion_ms": 6}
web                    {"evento": "peticion", "fecha": "2026-11-26T19:44:44+00:00", "metodo": "POST", "ruta": "registro/", "estado": 201, "duracion_ms": 137, "correlacion_id": "d9f2f213-dec3-4cf4-8618-a7f549b1618f", "usuario_id": null}
```

### Verificación (GET /verificar-correo/)

`correlacion_id`: `dc7db69f-5a13-499c-ab6f-f2731cc9e443`


| # | Hora (UTC) | Contenedor | Suceso | Qué significa |
| --- | --- | --- | --- | --- |
| 1 | 19:44:44.620 | `svc-usuarios` | evento_publicado · `correo_verificado` | svc-usuarios publica la verificación del correo. |
| 2 | 19:44:44.621 | `svc-contenido-eventos` | evento_procesado · `correo_verificado` | svc-contenido-eventos (grupo `svc-contenido`) guardó el evento en la bitácora (índice único de `evento_id`). Intento 1, 1 entrega(s), 1 ms, consumidor `svc-contenido-1a1acc8cba69`. |
| 3 | 19:44:44.622 | `web` | peticion | El gateway registra la petición del navegador al terminarla: la ruta como patrón (`verificar-correo/`), el estado 200 y 15 ms. Aparece después de los eventos porque se escribe al responder. |

```text
svc-usuarios           {"evento": "evento_publicado", "fecha": "2026-11-26T19:44:44+00:00", "evento_id": "0fc953f0-655a-49d2-8661-628c7c888990", "tipo": "correo_verificado", "version": 1, "origen": "svc-usuarios", "correlacion_id": "dc7db69f-5a13-499c-ab6f-f2731cc9e443", "stream": "agroia:eventos:usuarios", "id_mensaje": "1795722284620-0"}
svc-contenido-eventos  {"evento": "evento_procesado", "fecha": "2026-11-26T19:44:44+00:00", "grupo": "svc-contenido", "stream": "agroia:eventos:usuarios", "id_mensaje": "1795722284620-0", "evento_id": "0fc953f0-655a-49d2-8661-628c7c888990", "tipo": "correo_verificado", "version": 1, "origen": "svc-usuarios", "correlacion_id": "dc7db69f-5a13-499c-ab6f-f2731cc9e443", "intento": 1, "consumidor": "svc-contenido-1a1acc8cba69", "entregas": 1, "inicio": "2026-11-26T19:44:44.620+00:00", "duracion_ms": 1}
web                    {"evento": "peticion", "fecha": "2026-11-26T19:44:44+00:00", "metodo": "GET", "ruta": "verificar-correo/", "estado": 200, "duracion_ms": 15, "correlacion_id": "dc7db69f-5a13-499c-ab6f-f2731cc9e443", "usuario_id": null}
```

### Pedido (POST /checkout/)

`correlacion_id`: `9ef7a100-e289-4144-adef-65efeb34e621`


| # | Hora (UTC) | Contenedor | Suceso | Qué significa |
| --- | --- | --- | --- | --- |
| 1 | 19:44:46.294 | `svc-tienda` | evento_publicado · `pedido_creado` | svc-tienda publica el pedido creado, después de la transacción que descontó el stock. |
| 2 | 19:44:46.295 | `svc-contenido-eventos` | evento_procesado · `pedido_creado` | svc-contenido-eventos (grupo `svc-contenido`) guardó el evento en la bitácora (índice único de `evento_id`). Intento 1, 1 entrega(s), 1 ms, consumidor `svc-contenido-1a1acc8cba69`. |
| 3 | 19:44:46.299 | `web` | peticion | El gateway registra la petición del navegador al terminarla: la ruta como patrón (`checkout/`), el estado 302 y 42 ms. Aparece después de los eventos porque se escribe al responder. |

```text
svc-tienda             {"evento": "evento_publicado", "fecha": "2026-11-26T19:44:46+00:00", "evento_id": "e0a0b8e1-f2f9-4a38-ab8b-4bf4e3fc0d13", "tipo": "pedido_creado", "version": 1, "origen": "svc-tienda", "correlacion_id": "9ef7a100-e289-4144-adef-65efeb34e621", "stream": "agroia:eventos:tienda", "id_mensaje": "1795722286293-0"}
svc-contenido-eventos  {"evento": "evento_procesado", "fecha": "2026-11-26T19:44:46+00:00", "grupo": "svc-contenido", "stream": "agroia:eventos:tienda", "id_mensaje": "1795722286293-0", "evento_id": "e0a0b8e1-f2f9-4a38-ab8b-4bf4e3fc0d13", "tipo": "pedido_creado", "version": 1, "origen": "svc-tienda", "correlacion_id": "9ef7a100-e289-4144-adef-65efeb34e621", "intento": 1, "consumidor": "svc-contenido-1a1acc8cba69", "entregas": 1, "inicio": "2026-11-26T19:44:46.294+00:00", "duracion_ms": 1}
web                    {"evento": "peticion", "fecha": "2026-11-26T19:44:46+00:00", "metodo": "POST", "ruta": "checkout/", "estado": 302, "duracion_ms": 42, "correlacion_id": "9ef7a100-e289-4144-adef-65efeb34e621", "usuario_id": "bf5e9b83-af62-4715-8ad8-1038c87ccd72"}
```

### Pago (POST /mis-pedidos/104/pagar/)

`correlacion_id`: `b6212ea1-5864-4a22-902e-52b028868303`


| # | Hora (UTC) | Contenedor | Suceso | Qué significa |
| --- | --- | --- | --- | --- |
| 1 | 19:44:46.405 | `svc-tienda` | evento_publicado · `pedido_estado_cambiado` | svc-tienda publica el pago: la transición `pendiente → pagado` (un solo evento). |
| 2 | 19:44:46.406 | `svc-contenido-eventos` | evento_procesado · `pedido_estado_cambiado` | svc-contenido-eventos (grupo `svc-contenido`) guardó el evento en la bitácora (índice único de `evento_id`). Intento 1, 1 entrega(s), 1 ms, consumidor `svc-contenido-1a1acc8cba69`. |
| 3 | 19:44:46.407 | `web` | peticion | El gateway registra la petición del navegador al terminarla: la ruta como patrón (`mis-pedidos/<int:pedido_id>/pagar/`), el estado 302 y 18 ms. Aparece después de los eventos porque se escribe al responder. |

```text
svc-tienda             {"evento": "evento_publicado", "fecha": "2026-11-26T19:44:46+00:00", "evento_id": "3474c80c-2039-40ac-a070-2b3c76e65762", "tipo": "pedido_estado_cambiado", "version": 1, "origen": "svc-tienda", "correlacion_id": "b6212ea1-5864-4a22-902e-52b028868303", "stream": "agroia:eventos:tienda", "id_mensaje": "1795722286405-0"}
svc-contenido-eventos  {"evento": "evento_procesado", "fecha": "2026-11-26T19:44:46+00:00", "grupo": "svc-contenido", "stream": "agroia:eventos:tienda", "id_mensaje": "1795722286405-0", "evento_id": "3474c80c-2039-40ac-a070-2b3c76e65762", "tipo": "pedido_estado_cambiado", "version": 1, "origen": "svc-tienda", "correlacion_id": "b6212ea1-5864-4a22-902e-52b028868303", "intento": 1, "consumidor": "svc-contenido-1a1acc8cba69", "entregas": 1, "inicio": "2026-11-26T19:44:46.405+00:00", "duracion_ms": 1}
web                    {"evento": "peticion", "fecha": "2026-11-26T19:44:46+00:00", "metodo": "POST", "ruta": "mis-pedidos/<int:pedido_id>/pagar/", "estado": 302, "duracion_ms": 18, "correlacion_id": "b6212ea1-5864-4a22-902e-52b028868303", "usuario_id": "bf5e9b83-af62-4715-8ad8-1038c87ccd72"}
```

## 4. Diagnóstico por imagen sin modelo

La foto entra por svc-contenido, viaja como copia temporal en Redis y el worker responde `modelo_no_disponible` porque todavía no hay modelo de visión. Todo en unos 5 ms.


### Foto para diagnóstico (POST /diagnostico/)

`correlacion_id`: `0dafc7b2-af20-46d5-ad88-cf7ddc30243c`


| # | Hora (UTC) | Contenedor | Suceso | Qué significa |
| --- | --- | --- | --- | --- |
| 1 | 19:46:08.509 | `svc-contenido` | evento_publicado · `diagnostico_solicitado` | svc-contenido (API) guardó la foto y su copia temporal en Redis, y publica la solicitud solo con ids. |
| 2 | 19:46:08.510 | `svc-ia-worker` | evento_publicado · `diagnostico_fallido` | El worker de svc-ia no hay modelo de visión: publica `diagnostico_fallido` con `modelo_no_disponible`. |
| 3 | 19:46:08.511 | `svc-ia-worker` | evento_procesado · `diagnostico_solicitado` | El worker (grupo `svc-ia`) terminó la solicitud del diagnóstico y borró la copia de la foto. Intento 1, 1 entrega(s), 1 ms, consumidor `svc-ia-ec5fd32c967e-1`. |
| 4 | 19:46:08.513 | `web` | peticion | El gateway registra la petición del navegador al terminarla: la ruta como patrón (`diagnostico/`), el estado 200 y 20 ms. Aparece después de los eventos porque se escribe al responder. |
| 5 | 19:46:08.514 | `svc-contenido-eventos` | evento_procesado · `diagnostico_fallido` | svc-contenido-eventos (grupo `svc-contenido`) marcó el diagnóstico `fallido` y borró la foto guardada. Intento 1, 1 entrega(s), 3 ms, consumidor `svc-contenido-1a1acc8cba69`. |

```text
svc-contenido          {"evento": "evento_publicado", "fecha": "2026-11-26T19:46:08+00:00", "evento_id": "ad7f67f3-b068-4528-88a5-f2ab34b7b736", "tipo": "diagnostico_solicitado", "version": 1, "origen": "svc-contenido", "correlacion_id": "0dafc7b2-af20-46d5-ad88-cf7ddc30243c", "stream": "agroia:eventos:ia-solicitudes", "id_mensaje": "1795722368509-0"}
svc-ia-worker          {"evento": "evento_publicado", "fecha": "2026-11-26T19:46:08+00:00", "evento_id": "ee5f4980-62ea-4fc1-b0d3-e8453dcd1fb3", "tipo": "diagnostico_fallido", "version": 1, "origen": "svc-ia", "correlacion_id": "0dafc7b2-af20-46d5-ad88-cf7ddc30243c", "stream": "agroia:eventos:ia-resultados", "id_mensaje": "1795722368510-0"}
svc-ia-worker          {"evento": "evento_procesado", "fecha": "2026-11-26T19:46:08+00:00", "grupo": "svc-ia", "stream": "agroia:eventos:ia-solicitudes", "id_mensaje": "1795722368509-0", "evento_id": "ad7f67f3-b068-4528-88a5-f2ab34b7b736", "tipo": "diagnostico_solicitado", "version": 1, "origen": "svc-contenido", "correlacion_id": "0dafc7b2-af20-46d5-ad88-cf7ddc30243c", "intento": 1, "consumidor": "svc-ia-ec5fd32c967e-1", "entregas": 1, "inicio": "2026-11-26T19:46:08.509+00:00", "duracion_ms": 1}
web                    {"evento": "peticion", "fecha": "2026-11-26T19:46:08+00:00", "metodo": "POST", "ruta": "diagnostico/", "estado": 200, "duracion_ms": 20, "correlacion_id": "0dafc7b2-af20-46d5-ad88-cf7ddc30243c", "usuario_id": "d1f36202-c0d6-4d89-91c9-15326684516d"}
svc-contenido-eventos  {"evento": "evento_procesado", "fecha": "2026-11-26T19:46:08+00:00", "grupo": "svc-contenido", "stream": "agroia:eventos:ia-resultados", "id_mensaje": "1795722368510-0", "evento_id": "ee5f4980-62ea-4fc1-b0d3-e8453dcd1fb3", "tipo": "diagnostico_fallido", "version": 1, "origen": "svc-ia", "correlacion_id": "0dafc7b2-af20-46d5-ad88-cf7ddc30243c", "intento": 1, "consumidor": "svc-contenido-1a1acc8cba69", "entregas": 1, "inicio": "2026-11-26T19:46:08.510+00:00", "duracion_ms": 3}
```

## 5. Pregunta del video sin narración

La pregunta que aparece en el video corto grabado con Playwright (mismo flujo que el 1).


### Pregunta del video

`correlacion_id`: `643c8143-8c72-4b1f-b23c-781391d45308`


| # | Hora (UTC) | Contenedor | Suceso | Qué significa |
| --- | --- | --- | --- | --- |
| 1 | 19:44:51.435 | `svc-contenido` | evento_publicado · `ia_pregunta_solicitada` | svc-contenido (API) guardó la pregunta en MongoDB y publica la solicitud en `ia-solicitudes` (la pregunta viaja en el evento, pero no en el log). |
| 2 | 19:44:51.439 | `web` | peticion | El gateway registra la petición del navegador al terminarla: la ruta como patrón (`agroia/widget/preguntar/`), el estado 200 y 21 ms. Aparece después de los eventos porque se escribe al responder. |
| 3 | 19:44:52.862 | `svc-ia-worker` | evento_publicado · `ia_respuesta_generada` | El worker de svc-ia publica la respuesta del agente en `ia-resultados`, con la misma correlación. |
| 4 | 19:44:52.862 | `svc-ia-worker` | evento_procesado · `ia_pregunta_solicitada` | El worker (grupo `svc-ia`) terminó la solicitud: llamó al agente y confirmó el mensaje (`XACK`). Intento 1, 1 entrega(s), 1427 ms, consumidor `svc-ia-ec5fd32c967e-1`. |
| 5 | 19:44:52.864 | `svc-contenido-eventos` | evento_procesado · `ia_respuesta_generada` | svc-contenido-eventos (grupo `svc-contenido`) guardó la respuesta en la conversación de MongoDB y confirmó. Intento 1, 1 entrega(s), 1 ms, consumidor `svc-contenido-1a1acc8cba69`. |

```text
svc-contenido          {"evento": "evento_publicado", "fecha": "2026-11-26T19:44:51+00:00", "evento_id": "cdc628d6-af10-4f28-88bc-7c1ffcb83ca6", "tipo": "ia_pregunta_solicitada", "version": 1, "origen": "svc-contenido", "correlacion_id": "643c8143-8c72-4b1f-b23c-781391d45308", "stream": "agroia:eventos:ia-solicitudes", "id_mensaje": "1795722291435-0"}
web                    {"evento": "peticion", "fecha": "2026-11-26T19:44:51+00:00", "metodo": "POST", "ruta": "agroia/widget/preguntar/", "estado": 200, "duracion_ms": 21, "correlacion_id": "643c8143-8c72-4b1f-b23c-781391d45308", "usuario_id": "d1f36202-c0d6-4d89-91c9-15326684516d"}
svc-ia-worker          {"evento": "evento_publicado", "fecha": "2026-11-26T19:44:52+00:00", "evento_id": "ff761da1-6e03-4216-b68e-4784f2cb26a5", "tipo": "ia_respuesta_generada", "version": 1, "origen": "svc-ia", "correlacion_id": "643c8143-8c72-4b1f-b23c-781391d45308", "stream": "agroia:eventos:ia-resultados", "id_mensaje": "1795722292861-0"}
svc-ia-worker          {"evento": "evento_procesado", "fecha": "2026-11-26T19:44:52+00:00", "grupo": "svc-ia", "stream": "agroia:eventos:ia-solicitudes", "id_mensaje": "1795722291435-0", "evento_id": "cdc628d6-af10-4f28-88bc-7c1ffcb83ca6", "tipo": "ia_pregunta_solicitada", "version": 1, "origen": "svc-contenido", "correlacion_id": "643c8143-8c72-4b1f-b23c-781391d45308", "intento": 1, "consumidor": "svc-ia-ec5fd32c967e-1", "entregas": 1, "inicio": "2026-11-26T19:44:51.435+00:00", "duracion_ms": 1427}
svc-contenido-eventos  {"evento": "evento_procesado", "fecha": "2026-11-26T19:44:52+00:00", "grupo": "svc-contenido", "stream": "agroia:eventos:ia-resultados", "id_mensaje": "1795722292861-0", "evento_id": "ff761da1-6e03-4216-b68e-4784f2cb26a5", "tipo": "ia_respuesta_generada", "version": 1, "origen": "svc-ia", "correlacion_id": "643c8143-8c72-4b1f-b23c-781391d45308", "intento": 1, "consumidor": "svc-contenido-1a1acc8cba69", "entregas": 1, "inicio": "2026-11-26T19:44:52.862+00:00", "duracion_ms": 1}
```

## Límite de preguntas (429)

Con el agente detenido, el script mandó por la API preguntas del cliente demo en conversaciones distintas hasta que svc-contenido respondió **429 `demasiados_intentos`** (aceptó 8: dos del límite de 10 por minuto ya se habían usado en ese minuto). Después, la pregunta del widget recibió el aviso «Hiciste muchas preguntas seguidas…» con la cuenta regresiva ([captura](img/widget-limite-escritorio.png)). El rechazo ocurre **antes de la vista**: no se guarda la pregunta ni se publica ningún evento, así que esa correlación solo deja la línea del gateway:


```text
web                    {"evento": "peticion", "fecha": "2026-11-26T19:46:53+00:00", "metodo": "POST", "ruta": "agroia/widget/preguntar/", "estado": 200, "duracion_ms": 24, "correlacion_id": "c9cb389b-5832-4a6c-810c-d4cc55438fd8", "usuario_id": "d1f36202-c0d6-4d89-91c9-15326684516d"}
```

## Cómo reproducirlo

```powershell
# Logs en vivo, solo los sucesos de eventos (sin el correo de consola)
docker compose logs -f --no-log-prefix web svc-contenido svc-ia-worker svc-contenido-eventos |
  Select-String '"evento_publicado"|"evento_procesado"|"evento_reintentado"|"evento_fallido"|"peticion"'

# Todas las líneas de una correlación
docker compose logs --timestamps --no-log-prefix web svc-contenido svc-ia-worker svc-contenido-eventos |
  Select-String '<correlacion_id>'
```

La correlación de una petición se ve en el encabezado `X-Correlacion-Id` de la respuesta (herramientas de desarrollo del navegador) y, en los eventos de negocio, en la bitácora del panel.

