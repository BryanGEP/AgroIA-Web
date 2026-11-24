# Entrega 4 · IA asíncrona por eventos

**Fecha:** 22 de noviembre de 2026 · **Entregable:** Entrega 4 · **Responsable:** Bryan Gael Esquivel Pérez

## Resumen

Tercera parte de la comunicación asíncrona, sobre la [fase 1](e4-eventos-base.md) y la [fase 2](e4-eventos-negocio.md): **el chat con AgroIA y el diagnóstico por imagen ya no esperan al agente dentro de la petición.**

- **El flujo:** el gateway pide la respuesta a svc-contenido (`POST conversaciones/<id>/preguntar/` o `POST diagnosticos/solicitar/`, **202 en unos 50 ms**). svc-contenido guarda la solicitud y publica el evento. Un contenedor nuevo, **`svc-ia-worker`** (2 hilos; ver «Decisiones técnicas»), llama al agente o al clasificador y publica el resultado. `svc-contenido-eventos` lo guarda. La pantalla consulta el estado con HTMX: cada 2 s, y cada 5 s después de 20 s.
- **Reintentos y fallas:** el worker reintenta 2 veces (5 y 10 s) el tiempo agotado, la falta de conexión, los 5xx y el 429. Al agotarlos publica la fallida y el chat ofrece «Reintentar» sin esperar al vencimiento de 180 s. Lo que no vale la pena repetir (otro 4xx, una respuesta vacía) falla al momento.
- **La librería de eventos se reforzó** para todos los streams:
  - **Latido:** el hilo que procesa renueva la propiedad del mensaje, así un manejador lento ya no se reclama ni se procesa dos veces.
  - `Ocupado` no cuenta como intento.
  - La espera se mide desde el fallo.
  - Política de reintentos y retención por stream.
  - Gancho `al_agotar`.
  - Fallidos sin los campos no registrables.
  - Varios hilos por proceso.
  - Borrado de los consumidores viejos.
- **Privacidad:**
  - las preguntas y respuestas salen de Redis a las 24 h (recorte exacto por antigüedad);
  - la copia de la foto se borra en cuanto se procesa;
  - nada del texto llega a los logs ni a fallidos.
- **Clasificador de prueba** solo en desarrollo (`IA_CLASIFICADOR_PRUEBA=1` con `DEBUG=True`), con todo marcado «Resultado de prueba: no es un diagnóstico real».
- **Límite de solicitudes a la IA por usuario** (10 por minuto y 30 por hora, compartido entre preguntar, reintentar y diagnosticar; los GET no cuentan): un solo usuario ya no puede agotar el límite de tokens de Groq, que es de toda la aplicación. Al pasarse, 429 `demasiados_intentos` y la pantalla dice «Hiciste muchas preguntas seguidas», sin perder el texto ni cortar el polling.
- **`descartar`** en `python -m agroia_comun.eventos`, para borrar fallidos ya revisados.
- **Correlación en svc-ia:** la API la valida con un middleware y el worker la hereda del sobre. Una pregunta se sigue por la misma correlación en web, svc-contenido, svc-ia-worker y svc-contenido-eventos.

## Qué se construyó

### `comun` (librería de eventos)

- **`consumidor.py`, reescrito:**
  - `_Latido` renueva la propiedad cada `EVENTOS_LATIDO` (1 s) con `XCLAIM … JUSTID` al mismo consumidor. `reclamar_pendientes` solo toma lo que lleva 3 latidos sin renovarse.
  - Contador de fallos por mensaje (`agroia:fallos:<grupo>:<stream>:<id>`), con la espera medida desde el fallo.
  - `evento_procesado`, `evento_reintentado` y `evento_ocupado` registran `consumidor` (el hilo), `inicio`, `duracion_ms` y `entregas` (de `XPENDING`), para reconstruir quién atendió qué y comprobar que ningún mensaje se reclamó mientras se procesaba.
  - `Ocupado`, `al_agotar`, `correr_en_hilos` y `_borrar_viejos` (registra `consumidor_viejo_borrado`).
- **`catalogo.py`:**
  - `Politica` y `politica(stream)`: las solicitudes de IA usan 2 reintentos con 5 s de base y 24 h de retención; los resultados, 24 h de retención. Se cambian con `EVENTOS_<STREAM>_MAX_REINTENTOS` y `EVENTOS_<STREAM>_ESPERA_BASE`.
  - Los seis tipos de la IA con sus campos, listas cerradas (clases y códigos) y no registrables; los validadores `numero` y `objeto`.
- **`productor.py`:** en los streams con retención, `XADD … MINID` **exacto** a 24 h y `XTRIM MAXLEN ~10 000` en un *pipeline*.
- **`operacion.py` y `__main__.py`:**
  - `reprocesar` rechaza lo que tiene `datos_omitidos`; `estado` lo muestra.
  - `descartar [--id … | --todos] [--si]` borra fallidos sin publicarlos. Con `--todos` pide confirmación (`--si` la salta en scripts). Registra `fallidos_descartados` con cuántos y sus ids.
- **`limites.py` (nuevo):** `borrar_contadores` (antes en el comando de svc-usuarios, que ahora lo importa) y `LimitePorUsuario`.
- **`conexion.py`:** un cliente binario para la copia de la foto.

### svc-contenido

- **Conversaciones:**
  - `preguntar`, `reintentar` y `solicitud`. La solicitud vive dentro del documento de la conversación, con su id, estado, código, `creada_en` y `vence_en`.
  - Guardar la pregunta y abrir la solicitud es una sola actualización condicionada (sin otra pendiente y bajo el límite de mensajes).
  - Si Redis no responde al publicar, la solicitud queda `fallido` con `servicio_no_disponible`.
- **Diagnósticos:**
  - `diagnosticos/solicitar`: guarda la foto, crea el diagnóstico `pendiente`, deja la copia en Redis (vence con la solicitud) y publica.
  - El detalle trae `estado`, `codigo` y `es_prueba`; el historial solo lista los `listo`. Si falla, se borra la foto.
- **Consumidor:**
  - Guarda la respuesta con una actualización condicionada a que la solicitud siga pendiente y no exista ya un mensaje con ese `solicitud_id`.
  - La respuesta que llega tarde se descarta (`respuesta_tardia`); la que no cabe deja `conversacion_llena`.
  - La vencida se marca `vencida` al leerla.

- **Límite por usuario** (`config/limites.py`):
  - `preguntar`, `reintentar` y `diagnosticos/solicitar` comparten `IA_SOLICITUDES_POR_MINUTO` (10) e `IA_SOLICITUDES_POR_HORA` (30).
  - Contadores atómicos (`incr`) por ventana fija en la caché de Redis (base 0, prefijo `svc-contenido`); la rechazada devuelve su cuenta (`decr`).
  - 429 `demasiados_intentos` con `Retry-After`, antes de la vista.
  - Comando `reiniciar_limites` propio.

### svc-ia

- **`app/worker.py` (nuevo):**
  - Manejadores de pregunta y de diagnóstico, con candado por solicitud (`procesando`, después `hecho`) y `Ocupado`.
  - Una solicitud vencida no llama al agente.
  - Errores que se reintentan y que no.
  - `al_agotar` publica `agente_no_disponible` o `clasificador_fallo`.
- **`agente.py`:** `AgenteNoDisponible.reintentable`.
- **`vision.py`:** `ClasificadorDePrueba`, determinista por el hash de la imagen.
- **`config.py`:** `IA_WORKER_HILOS` e `IA_CLASIFICADOR_PRUEBA`; `validar()` rechaza el clasificador de prueba sin `DEBUG`.
- **`main.py` y `eventos.py`:** middleware de correlación y `correlacion_id` en el log `seguridad`.

### Gateway (web)

- **`apps/agroia/servicios.py`:** ya no orquesta svc-ia y svc-contenido, solo llama a svc-contenido. El docstring explica el flujo.
- **Vistas nuevas:** `solicitud` (`/agroia/<id>/solicitud/`) y `estado` (`/diagnostico/<id>/estado/`).
- **Plantillas `_espera.html` con `hx-trigger="load delay:<n>s"`:** la vista calcula el intervalo y la respuesta final no trae `hx-trigger`. `_fallida.html` trae «Reintentar» y el aviso de conversación llena. Sin JavaScript, `<noscript><meta http-equiv="refresh" content="5">`.
- **Sin scripts ni estilos en línea:** se respeta la CSP.
- **`_clasificacion.html`:** el aviso «Resultado de prueba: no es un diagnóstico real».
- **429 de svc-contenido:**
  - «Hiciste muchas preguntas seguidas. Espera N segundos y vuelve a preguntar» (en el diagnóstico, «Hiciste muchos análisis seguidos»).
  - La respuesta trae `X-Conservar-Pregunta` y el componente `chat` no vacía el campo.
  - Un «Reintentar» rechazado vuelve a mostrar su botón con el aviso.
  - Si se rechaza la primera pregunta de una conversación nueva, se borra la conversación vacía.

### Infraestructura y scripts

- **`docker-compose.yml`:**
  - `svc-ia-worker` (13 contenedores), con `restart: unless-stopped`, `stop_grace_period: 60s`, `IA_WORKER_HILOS` e `IA_CLASIFICADOR_PRUEBA`;
  - `IA_SOLICITUD_VENCE_SEGUNDOS` en svc-contenido y su consumidor.
  - `.env.example` documenta las variables nuevas.
- **`infra/prueba_eventos.py`:**
  - pasos 8 a 11: agente real con su correlación en 4 contenedores, agente detenido, 5 preguntas a la vez y el diagnóstico en los dos modos;
  - el paso 10 imprime, por cada intento, el hilo, cuándo empezó, las entregas y lo que tardó, y el log del agente (solo estados); antes espera a que pasen 90 s sin llamadas al agente (límite por minuto de Groq) y comprueba que se atienden de N en N (N = `IA_WORKER_HILOS` del worker que corre, no un número fijo) y que ninguna tiene entregas de más;
  - el paso 9 descarta su propio fallido después de revisarlo;
  - al empezar corre `reiniciar_limites` también en svc-contenido;
  - `--solo-ia` y `--pasos=`.
- **`infra/matriz_seguridad.py`:**
  - salida por defecto en `docs/entregable-4/matriz-accesos.md` (el reporte de la Entrega 3 ya no se toca);
  - 5 filas nuevas: preguntar en la conversación propia y en una ajena, la solicitud propia y la de otro usuario, y solicitar un diagnóstico;
  - la pregunta síncrona al agente va antes de las de IA por eventos;
  - fila «Exceso de solicitudes a la IA»: cada cuenta pregunta hasta el 429 y la siguiente debe ser 429 `demasiados_intentos`; la limpieza corre `reiniciar_limites` de svc-contenido.
- **Postman:** 6 peticiones nuevas:
  - pregunta por eventos (202);
  - pregunta mientras responde (409);
  - estado de la solicitud;
  - solicitud de otro usuario (404);
  - diagnóstico por eventos (202) y su estado;
  - exceso de preguntas a la IA (429), al final de «Seguridad»: su script previo manda 10 a la vez y la 11.ª debe ser 429 con `Retry-After`.
- **Documentación:**
  - `docs/eventos.md`: diagrama completo, sección «IA asíncrona», «Cuánto duran los datos en Redis» (con el AOF), latido y política por stream;
  - `CLAUDE.md`, el README raíz y los de svc-ia, svc-contenido y web;
  - la definición técnica: 13 contenedores, contratos nuevos de svc-contenido y endpoints síncronos de svc-ia por compatibilidad.

## Decisiones técnicas

| Decisión | Por qué |
| --- | --- |
| svc-contenido publica las solicitudes, no web | Es dueño de la conversación y del diagnóstico: guarda la solicitud y publica en el mismo servicio. web no toca Redis |
| El estado de la solicitud vive en el documento de la conversación o del diagnóstico | Se lee junto con la conversación y no hace falta otra colección ni sincronizarlas |
| Polling desde la pantalla, no un consumidor en web | Un grupo entrega cada mensaje a un solo proceso del gateway, y el usuario puede estar en otro. svc-contenido ya tiene el resultado |
| Intervalo de 2 s y de 5 s después de 20 s, calculado en el servidor | Con `hx-trigger` en el HTML no hace falta JavaScript propio ni scripts en línea (CSP). Una espera completa son unas 40 consultas |
| Foto: guardada en svc-contenido y una copia temporal en Redis | El evento no puede llevar 5 MB y svc-ia no comparte almacenamiento con svc-contenido (en la Entrega 5 será Cloud Storage) |
| Latido en vez de una espera de reintento más larga | Una espera más larga no protege de una respuesta de 30 s y retrasa los reintentos reales. El latido separa «sigue trabajando» de «murió» |
| 2 reintentos con base de 5 s en la IA | El usuario está esperando: 3 intentos en unos 15 s, más el tiempo de cada llamada, caben de sobra en 180 s |
| Fallidos sin los no registrables; `reprocesar` los rechaza | La pregunta y la respuesta son datos del usuario. «Reintentar» publica una solicitud nueva con el texto guardado en la conversación, así que no hace falta reprocesar |
| La respuesta tardía se descarta y se registra | Si la solicitud ya venció, el usuario ya vio el error; agregar la respuesta después confundiría la conversación |
| `MINID` exacto, no aproximado | Con `~`, Redis no recorta un stream chico (lo comprobó una prueba): la pregunta se quedaba más de 24 h |
| Endpoints síncronos de svc-ia por compatibilidad | Postman, la matriz y las pruebas del agente los usan; mantenerlos no cuesta nada |
| Clasificador de prueba solo con `DEBUG=True` y marcado | Permite probar el flujo completo sin presentar nunca un resultado inventado como real |
| Límite por usuario de 10 por minuto y 30 por hora, compartido entre preguntar, reintentar y diagnosticar | Una conversación normal no pasa de unas pocas preguntas por minuto; 30 por hora deja usar el chat sin que una sola persona consuma el límite de tokens de todos. Se cambian por variable |
| Contadores atómicos por ventana fija, no el historial de DRF | Con el historial, peticiones simultáneas se pisaban y entraban más de 10 (lo encontró Postman). El costo: en el cambio de minuto pueden entrar hasta 20 en pocos segundos; la ventana de una hora lo acota |
| El límite se revisa antes de la vista y la rechazada no cuenta | No se guarda la pregunta ni se publica nada: la conversación no queda a medias, y quien se pasa no pierde presupuesto |
| `reiniciar_limites` en cada servicio | Cada servicio borra solo sus contadores: svc-usuarios no toca los de svc-contenido |
| `IA_WORKER_HILOS` = 2 por defecto (empezó en 3) | Con la llave gratuita de Groq, 3 llamadas a la vez provocan `RateLimitError` y respuestas de 11 a 39 s (ver «Verificación»). Con 2 la misma prueba sale de 2 en 2 y con menos rechazos. Con una llave de pago se puede subir la variable: el worker no cambia |
| `descartar` aparte de `reprocesar` | Los fallidos de la IA no se pueden reprocesar (no guardan la pregunta); una vez revisados hay que poder quitarlos sin tocar Redis a mano |

## Verificación

Todo en Docker, el 22 de noviembre de 2026; las corridas con 2 hilos, el 24.

### Concurrencia y el reclamo mientras se procesa

- **Prueba de la librería:** `test_un_manejador_lento_con_dos_hilos_se_procesa_una_vez_sin_intentos_de_mas` (`comun/tests/test_eventos_fase3.py`) pasa.
  - El manejador tarda 0.6 s, diez veces la espera de reintento, y otro hilo del mismo grupo revisa los pendientes cada 20 ms mientras tanto.
  - Se procesa una sola vez, en el hilo 1, sin `evento_reintentado` ni `evento_fallido`, con `entregas: 1` e `intento: 1` en el log.
- **Paso 10 con el agente real**, con el log nuevo del worker (`consumidor`, `inicio`, `entregas`, `duracion_ms`). En la tabla, «empieza» cuenta desde que se mandaron las preguntas y «dura» es lo que tardó el intento en el worker.
  - **Con 2 hilos (el valor por defecto), en la corrida completa final del 24 de noviembre** (62 de 62; el paso 10 empezó después de 88 s sin llamadas al agente):

    | Pregunta | Intento | Hilo | Empieza | Entregas | Dura | Resultado |
    | --- | --- | --- | --- | --- | --- | --- |
    | 1 | 1 | 2 | 0.0 s | 1 | 2.9 s | bien |
    | 2 | 1 | 1 | 0.0 s | 1 | 1.9 s | bien |
    | 3 | 1 | 2 | 5.3 s | 1 | 28.5 s | 503 (`RateLimitError` en el agente) |
    | 3 | 2 | 2 | 38.9 s | 2 | 28.4 s | bien, 5.1 s después del fallo |
    | 4 | 1 | 1 | 1.9 s | 1 | 34.0 s | bien |
    | 5 | 1 | 2 | 2.9 s | 1 | 2.3 s | bien |

    - Las 5 respondieron: a los 4.1, 2.1, 68.5, 36.2 y 6.2 s (68.5 s en total).
    - **De 2 en 2:** las preguntas 1 y 2 empezaron juntas; cada hilo tomó la siguiente al terminar. Como mucho hubo 2 hilos ocupados a la vez.
    - **Intentos por solicitud:** 4 con un intento y la 3 con dos. Cada entrega corresponde a un intento real; ninguna se reclamó mientras se procesaba.
    - Log del agente (solo estados): 200 a los 1.9, 2.9 y 5.3 s; `RateLimitError` y 503 a los 33.8 s; 200 a los 36.0 y 67.3 s. Con 2 hilos Groq rechazó 1 llamada de 6; con 3, 2 de 7 (abajo).
  - **Con 2 hilos, el paso 10 suelto y enfriado** (el mismo día, antes de la corrida final): 5 de 5 de 2 en 2. Dos preguntas necesitaron un segundo intento, una por `RateLimitError` (el agente tardó 44.2 s en el 503) y otra por tiempo agotado (45 s). La más lenta tardó 100.7 s.
  - **Por qué se bajó a 2: con 3 hilos, corrida de las 22:29 (UTC) del 22 de noviembre, con el límite de Groq enfriado 4 minutos:**

    | Pregunta | Intento | Hilo | Empieza | Entregas | Dura | Resultado |
    | --- | --- | --- | --- | --- | --- | --- |
    | 1 | 1 | 2 | 0.0 s | 1 | 11.5 s | 503 (`RateLimitError` en el agente) |
    | 1 | 2 | 2 | 16.5 s | 2 | 6.3 s | bien, 5.0 s después del fallo |
    | 2 | 1 | 3 | 0.0 s | 1 | 3.6 s | bien |
    | 3 | 1 | 1 | 0.0 s | 1 | 2.1 s | bien |
    | 4 | 1 | 1 | 2.1 s | 1 | 22.2 s | 503 (`RateLimitError`) |
    | 4 | 2 | 1 | 29.4 s | 2 | 7.2 s | bien, 5.1 s después del fallo |
    | 5 | 1 | 3 | 3.6 s | 1 | 2.1 s | bien |

    - Las 5 respondieron: a los 24.2, 4.1, 4.1, 38.2 y 6.1 s.
    - Empezaron 3 a la vez (una por hilo) y cada hilo tomó la siguiente al terminar.
    - **Cada entrega corresponde a un intento real:** la segunda entrega solo aparece en los reintentos, 5 s después del fallo. Ningún mensaje se reclamó mientras se procesaba.
  - **De dónde salen los 76.4 s de la primera corrida (y los 38 s de esta): del límite de Groq, no del reclamo.**
    - Con 3 llamadas a la vez, Groq rechaza algunas. El agente tarda en responder 503: 11.5 s y 22.2 s en esta corrida, hasta 39 s en otra.
    - El log del agente (solo estados) lo muestra en esta corrida: 200 a los 2.1, 3.6 y 5.7 s; `RateLimitError` y 503 a los 11.5 s; 200 a los 22.8 s; `RateLimitError` y 503 a los 24.3 s; 200 a los 36.6 s.
    - Sin rechazos, una pregunta tarda de 2 a 6 s y las 5 terminan en unos 10 s.
  - **Con la cuota de Groq agotada (22 de noviembre, 3 hilos), evidencia de los reintentos y de `agente_no_disponible`:** Groq rechazaba todas las llamadas en unos 0.1 s.
    - Fueron 15 intentos (5 preguntas × 3) en los hilos 1, 2 y 3. Como mucho hubo 3 hilos ocupados a la vez y en ningún caso hubo entregas de más (entregas 1, 2 y 3 en los intentos 1, 2 y 3).
    - Los reintentos empezaron a los 5.0 a 5.3 s y a los 10.1 a 10.4 s del fallo.
    - Las 5 terminaron en `agente_no_disponible` a los 18 a 20 s, sin esperar el vencimiento.
- **Paso 10 en la corrida completa anterior** (antes de corregir el análisis): 4 de 5 con respuesta y la cuarta agotó sus 3 intentos por `RateLimitError`. El script marcó dos fallas que eran errores suyos y que se corrigieron:
  - no contaba el `evento_fallido` del último intento;
  - medía la concurrencia sumando intervalos, y dos intentos seguidos del mismo hilo «se tocaban» por el redondeo a milisegundos.

  Ahora cuenta hilos distintos ocupados y comprueba que un hilo nunca tenga dos intentos encimados.

### Límite de preguntas por usuario

- **Pruebas de svc-contenido:**
  - la 11.ª solicitud del minuto da 429 `demasiados_intentos` con `Retry-After` y sin guardar la pregunta;
  - otro usuario sigue pudiendo preguntar;
  - 100 GET de estado no cuentan;
  - preguntar, reintentar y diagnosticar comparten el presupuesto;
  - la ventana de un minuto se libera y la de una hora no (los rechazados no cuentan, así que entran 30);
  - `reiniciar_limites` vacía los contadores y no corre sin `DEBUG`;
  - 20 hilos a la vez: entran exactamente 10.
- **Contra el Redis real:** 30 peticiones simultáneas del mismo usuario, tres rondas: entran 10 en cada una.
- **Pruebas de web:**
  - el mensaje «Hiciste muchas preguntas seguidas. Espera 42 segundos» sin códigos técnicos y con `X-Conservar-Pregunta`;
  - el polling de la pregunta anterior sigue;
  - una conversación nueva rechazada se borra;
  - un «Reintentar» rechazado conserva su botón;
  - el mensaje del diagnóstico.
- **Postman** («Exceso de preguntas a la IA → 429») y la **matriz** (fila «Exceso de solicitudes a la IA»: 429 para las tres cuentas, 401 o 403 para los demás actores) lo comprueban por el sistema levantado.

### Corridas completas

- **pytest: 1001 en verde.**

  | Servicio | Pruebas |
  | --- | --- |
  | web | 288 (antes de la fase, 271) |
  | svc-usuarios | 186 |
  | svc-tienda | 169 |
  | svc-contenido | 139 (antes 102) |
  | svc-ia | 87 (antes 65) |
  | comun | 133 (antes 116) |

  Además de lo de arriba, las pruebas nuevas cubren:
  - **Librería:**
    - el mensaje de un consumidor muerto se reclama pasada la ventana del latido;
    - `Ocupado` no cuenta y la espera se mide desde el fallo;
    - `al_agotar` corre antes de fallidos;
    - fallidos sin no registrables y no reprocesables;
    - política por stream, retención por antigüedad, hilos en paralelo y consumidores viejos;
    - `descartar` por id y con `--todos` (confirmación, `--si`, respuesta negativa).
  - **svc-contenido:**
    - preguntar, reintentar y la solicitud (202, 409, 404 ajena, 401 y 403);
    - el vencimiento;
    - la respuesta guardada una vez, la tardía descartada y la que no coincide con la solicitud;
    - Redis caído;
    - el diagnóstico solicitado, su copia temporal, el resultado, la fallida (con la foto borrada) y `es_prueba`.
  - **svc-ia-worker:**
    - respuesta correcta y la correlación heredada;
    - idempotencia y `Ocupado`;
    - 503, 429, timeout y sin conexión se reintentan; 422 y la respuesta vacía no;
    - reintentos agotados;
    - vencida sin llamar al agente;
    - nada del texto en los logs;
    - 5 preguntas con 3 hilos en paralelo;
    - el diagnóstico en sus casos;
    - el clasificador de prueba no se permite sin `DEBUG`;
    - la correlación en la API.
  - **web:**
    - el polling con su intervalo creciente;
    - la respuesta final sin `hx-trigger`;
    - las fallidas con «Reintentar»;
    - la pantalla pendiente con su `noscript`;
    - 90 consultas sin 429;
    - el aviso de resultado de prueba.
- **ruff:** `ruff check` y `ruff format --check` en verde en los cinco servicios, `comun` e `infra/`.
- **OpenAPI:** `spectacular --validate --fail-on-warn` sale con código 0 y sin avisos en web, svc-usuarios, svc-tienda y svc-contenido.
  - En web aplica, pero el esquema solo tiene `/salud/`: sus páginas son vistas de plantillas y el proxy `/api/<servicio>/` es una vista de Django que reenvía; cada servicio documenta sus rutas.
  - Los docs de svc-ia (FastAPI) responden 200.
- **Postman** (después de `cargar_datos_demo` y de `reiniciar_limites` en svc-usuarios y svc-contenido): **128 peticiones (139 contando las del script previo del caso del límite) y 219 aserciones, 0 fallas.**
  - Una corrida anterior falló en el caso nuevo: con 10 preguntas en paralelo, la 11.ª no dio 429. Ver «Problemas encontrados».
- **Matriz de accesos:** **154 de 154**, en [`docs/entregable-4/matriz-accesos.md`](../entregable-4/matriz-accesos.md). `docs/entregable-3/matriz-accesos.md` no cambió.
  - Antes, una corrida dio 143 de 146: las preguntas por eventos agotaban el límite de Groq antes de la pregunta síncrona, que se movió antes de ellas.
- **`infra/prueba_eventos.py` completa:**
  - **Primera corrida de la fase (antes del límite por usuario): 59 de 59** en 321 s.
  - **Corrida final, con 2 hilos y la cuota renovada (24 de noviembre): 62 de 62** en 409 s. Son 62 y no 56 porque el paso 9 ahora comprueba `descartar` y el paso 10 suma la concurrencia y las entregas.
  - **Antes de la pausa del paso 10 (también con 2 hilos): 61 de 62** en 464 s. Falló «las 5 terminaron con respuesta»: el paso 10 empezaba justo después de los pasos 8 y 9, que gastan el límite de tokens por minuto de Groq. El agente tardó unos 40 s en cada 503, los reintentos esperaron hilo libre y 3 preguntas vencieron a los 180 s. Los 2 hilos, las entregas y los reintentos se comportaron bien. Por eso el paso 10 espera ahora 90 s sin llamadas al agente.
  - **Con la cuota agotada (22 de noviembre, 3 hilos): 52 de 56** en 345 s. Queda como evidencia de los reintentos y de `agente_no_disponible`:
    - Los pasos 1 a 7 y el 11 pasan.
    - En el 9 pasan la fallida con 2 reintentos a los 40.2 s, fallidos sin la pregunta, `reprocesar` que la rechaza y `descartar` que la borra.
    - En el 10 pasan el 202, los hilos y las entregas.
    - **Las 4 fallas son de Groq,** que rechazó todas las llamadas (`RateLimitError` en el log del agente, 503 en unos 0.1 s): la respuesta del paso 8, la respuesta al reintentar del paso 9 (y, por eso, «la pregunta no se repitió», que espera la respuesta en la conversación) y las 5 respuestas del paso 10.
    - Con la cuota disponible, esos mismos pasos pasan: es la corrida de 62 de 62.
- **En Chromium:**
  - **conversación nueva:** espera visible, respuesta en 2.5 s y el polling se detuvo;
  - **segunda pregunta por HTMX:** sin recargar, y las consultas no crecieron después de la respuesta;
  - **diagnóstico sin modelo:** «estará disponible pronto»;
  - **0 errores de consola y 0 de CSP.**
  - Capturas: [esperando](img/e4-chat-esperando.png), [respuesta](img/e4-chat-respuesta.png), [diagnóstico](img/e4-diagnostico-sin-modelo.png).
- **Al final:**
  - `descartar` borró los 5 fallidos de prueba de las corridas anteriores (por id), los 8 de la corrida con la cuota agotada y los 2 de la de 61 de 62 (todos `ia_pregunta_solicitada` con `agente_no_disponible` por Groq, revisados uno por uno). La de 62 de 62 descartó sola el suyo (paso 9);
  - `limpiar_datos_prueba` en los tres servicios;
  - **`estado`: 0 pendientes y 0 fallidos.**

## Problemas encontrados

| Problema | Solución |
| --- | --- |
| El reclamo de pendientes podía tomar un mensaje que otro hilo seguía procesando (respuesta de 30 s contra espera de 5 s) | Latido con `XCLAIM JUSTID` mientras corre el manejador; la prueba con 2 hilos lo cubre. También protegía a los correos con más de una réplica |
| Con `MINID ~` un stream chico no se recortaba | `MINID` exacto |
| Redis rechaza un `EX` de 0 o negativo y la copia de la foto fallaba con un vencimiento muy corto | `ex=max(vencimiento, 1)` |
| La ventana del latido por defecto (3 s) ocultaba las esperas cortas de las pruebas existentes | Las pruebas usan un latido de 5 ms |
| Las clases nuevas del serializador separaron un `@extend_schema_serializer` de su clase | El decorador volvió a su lugar |
| El PNG en hexadecimal de la prueba de punta a punta no era válido y svc-contenido respondió 400 (lo abre con Pillow) | El PNG de 1×1 válido de las pruebas de web |
| Con la llave gratuita de Groq, 5 preguntas justo después de otras 3 agotaron el límite: el agente respondió tarde y 4 vencieron a los 180 s | Medido y documentado (ver «Verificación»); con el límite enfriado salieron las 5. `--pasos=` permite medir un paso suelto |
| La matriz dio 143 de 146 por el mismo límite | Orden de las filas (ver «Verificación») |
| El log de los consumidores no decía qué hilo atendió un mensaje, cuándo empezó ni cuántas entregas tuvo: no se podía demostrar con datos que el reclamo ya no tomaba mensajes en curso | `consumidor`, `inicio`, `duracion_ms` y `entregas` en el log, y la tabla por intento del paso 10 |
| Con dos throttles de DRF (minuto y hora), una petición rechazada por el de un minuto quedaba contada en el de una hora | Una sola clase que solo cuenta lo que las dos ventanas permiten |
| Postman mandó 10 preguntas a la vez y la 11.ª no dio 429: el historial de DRF («leer, agregar y guardar») no es atómico y las peticiones se pisaban | Contadores con `incr`; una prueba con 20 hilos y otra contra el Redis real (30 a la vez, entran 10, tres rondas) |
| El análisis del paso 10 no contaba el `evento_fallido` del último intento y medía la concurrencia sumando intervalos (dos intentos seguidos del mismo hilo «se tocaban» por el redondeo a milisegundos): marcó dos fallas falsas | Incluye `evento_fallido`; cuenta hilos distintos ocupados y comprueba que un hilo no tenga dos intentos encimados |
| Con la cuota de Groq agotada, Groq rechazó todas las llamadas: 52 de 56 en la prueba de punta a punta | No era del sistema: se comportó como debía (fallida a los 18 a 20 s, «Reintentar», nada inventado). Con la cuota renovada: 62 de 62 |
| Con 3 hilos, la llave gratuita de Groq rechaza llamadas (`RateLimitError`) y las respuestas tardan de 11 a 39 s | `IA_WORKER_HILOS` = 2 por defecto; se puede subir con una llave de pago |
| Con 2 hilos, la corrida completa dio 61 de 62: el paso 10 heredaba el límite por minuto que gastaron los pasos 8 y 9, y 3 preguntas vencieron | El paso 10 espera a que pasen 90 s sin llamadas al agente, como la matriz espera 61 s antes de los casos de login. El paso suelto y enfriado ya daba 5 de 5 |
| `wait_for_function` de Playwright evalúa texto como JavaScript y la CSP lo bloqueó | El script usa esperas de localizador. Confirma de paso que la CSP no permite `unsafe-eval` |

## Commits y Pull Requests

Rama `feat/e4-ia-asincrona` desde `develop`. Los commits se proponen al cerrar la fase.

## Pendientes y siguiente paso

- **Widget flotante del chat:** fuera de esta fase.
- **Límite de tokens del agente:** el límite por usuario evita que uno solo lo agote, pero el de Groq sigue siendo de toda la aplicación: aun con 2 hilos rechaza alguna llamada cuando se piden varias seguidas, y la espera crece. Se resuelve con una llave de pago, y entonces se puede subir `IA_WORKER_HILOS`.
- **Pantalla de bitácora** en el panel (opcional, fase 4).
- **AOF:** una pregunta recortada de su stream sigue en el archivo hasta la siguiente reescritura (`BGREWRITEAOF`). Revisar en la Entrega 5 con Memorystore.
- **Outbox:** sigue pendiente, como en las fases 1 y 2.
- **Modelo de visión:** cuando exista, basta con que `obtener_clasificador()` lo devuelva; el flujo ya está probado de punta a punta con el clasificador de prueba.
