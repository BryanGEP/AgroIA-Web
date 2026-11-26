# Entrega 4 · Base de eventos con Redis Streams

**Fecha:** 22 de noviembre de 2026 · **Entregable:** Entrega 4 · **Responsable:** Bryan Gael Esquivel Pérez

## Resumen

Primera parte de la comunicación asíncrona entre microservicios: el diseño de los eventos y la base técnica sobre Redis.

- **Mecanismo:** Redis Streams con un grupo de consumidores por servicio. No pierde eventos si un consumidor está caído, confirma cada uno, permite reintentar y apartar los que fallan, y varios servicios pueden escuchar el mismo evento. Se comparó con pub/sub, Celery y RQ en [`docs/eventos.md`](../eventos.md).
- **Catálogo:** [`docs/eventos.md`](../eventos.md) dice qué operaciones son asíncronas y cuáles se quedan síncronas, cada evento con su productor, sus consumidores, sus datos y qué pasa si falla, el sobre común y el diagrama del flujo (el entregable 1 del maestro).
- **Librería en `comun`:** `agroia_comun.eventos`, sin Django, para que también la use svc-ia. Publica sin romper la operación si Redis no responde, y consume con reintentos de espera creciente, stream de fallidos, recuperación de mensajes colgados, idempotencia, timeouts, log y apagado limpio. Incluye los comandos `estado` y `reprocesar`.
- **Infraestructura:** Redis con persistencia y `noeviction`, los eventos en su propia base lógica, y el contenedor `svc-contenido-eventos`. Son 11 contenedores.
- **Prueba de la base:** el evento `usuario_registrado`, de svc-usuarios a la bitácora de svc-contenido, verificado de punta a punta en Docker con [`infra/prueba_eventos.py`](../../infra/prueba_eventos.py): 15 de 15 comprobaciones.

Los eventos de negocio van en la fase 2, y la IA asíncrona y el widget del chat en la fase 3.

## Qué se construyó

### Librería `agroia_comun.eventos` (núcleo de `comun`, sin Django)

| Módulo | Qué hace |
| --- | --- |
| `catalogo.py` | Cada tipo con su versión, su stream, sus campos (con tipo) y los campos **no registrables**. `validar_datos` rechaza campos que sobran, que faltan o con otro tipo. Hoy: `usuario_registrado` (`usuario_id`, `rol`) |
| `sobre.py` | Sobre común `{id, tipo, version, fecha, origen, correlacion_id, datos}` y `correlacion_valida()`: solo acepta un UUID; si no, genera uno |
| `productor.py` | `publicar()` y `publicar_sobre()`. Si Redis no responde, no lanza: registra `evento_no_publicado` con el sobre (sin los no registrables) y devuelve `None` |
| `consumidor.py` | `Consumidor(grupo, manejadores)`. Ver abajo |
| `operacion.py` y `__main__.py` | `python -m agroia_comun.eventos estado` (streams, grupos, pendientes, sin leer, consumidores y últimos fallidos) y `reprocesar --id \| --todos` (con el mismo id del sobre) |
| `conexion.py` | Clientes de Redis con timeout de 2 s (`EVENTOS_REDIS_URL`, base 1). Uno aparte para la lectura bloqueante (5 s de bloqueo y corte a los 7) |
| `registro.py` | Logger `eventos`, una línea JSON por suceso, sin datos |
| `en_django.py` | `publicar_al_confirmar()` (publica con `transaction.on_commit`) y `correlacion_de(request)` |

**El consumidor:**
- **Lectura:** lee de a un evento.
- **Idempotencia:** antes de llamar al manejador revisa la llave `agroia:procesados:<grupo>:<evento_id>`. Después de que el manejador termina bien, escribe la llave (7 días) y confirma, en una transacción de Redis.
- **Reintentos:** si el manejador falla, no confirma, y el mismo ciclo reintenta cuando el mensaje lleva `espera_base * 2 ** (entregas - 1)` segundos sin confirmarse. Con eso también recupera lo que dejó colgado otro consumidor.
- **Fallidos:** al pasar de `EVENTOS_MAX_REINTENTOS` el mensaje va a `agroia:eventos:fallidos` (sin recorte) con el motivo, y el sobre ilegible o de una versión más nueva va directo.
- **Sin Redis:** registra `consumidor_sin_redis` y espera hasta 30 s sin caerse.
- **Apagado:** con SIGTERM termina el evento en curso y sale.

**Empaque:**
- **Núcleo:** depende solo de PyJWT, cryptography y redis. simplejwt pasó al extra `[django]`.
- **Instalación:** los servicios Django instalan `-e "/comun[django]"`; svc-ia, `-e /comun`.
- **Pruebas:** una comprueba en un proceso aparte que el núcleo no importa Django, y otra en svc-ia que ahí ni siquiera está instalado.

### svc-usuarios (productor)

- `registrar_usuario()` publica `usuario_registrado` con `publicar_al_confirmar`, con solo el `usuario_id` y el rol; si la transacción se revierte, no publica nada.
- La vista pasa la correlación de `X-Correlacion-Id`, validada como UUID.

### svc-contenido (consumidor)

- `apps/bitacora/eventos.py`: el grupo `svc-contenido` y su manejador.
- `servicios.registrar_desde_evento()` guarda el evento con `evento_id` y `correlacion_id`, y es idempotente gracias al índice único y disperso (`unique`, `sparse`) de `evento_id`, que crea `crear_indices`.
- Comando `consumir_eventos`: crea los índices y consume.
- La API de la bitácora devuelve además `evento_id` y `correlacion_id` (campos nuevos, de solo lectura; no rompen el contrato).

### Infraestructura

- **redis:**
  - `--appendonly yes --appendfsync everysec` y el volumen `redis_datos`;
  - `--maxmemory-policy noeviction` explícita: con otra política podría borrar eventos sin procesar, porque comparten instancia con la caché del límite de intentos;
  - eventos en la base 1 y caché en la 0.
- **Contenedor nuevo `svc-contenido-eventos`:** misma imagen y código montado que svc-contenido, comando `python manage.py consumir_eventos`, `restart: unless-stopped` y `stop_grace_period: 20s`.
- **Variables nuevas:** `EVENTOS_REDIS_URL`, `EVENTOS_MAX_REINTENTOS` y `EVENTOS_ESPERA_BASE`, en `docker-compose.yml` (para svc-usuarios, svc-contenido, el consumidor y svc-ia) y en `.env.example`.
- **svc-ia:** instala el núcleo de `comun`, y `docker-compose.yml` lo monta.

### Pruebas y script de punta a punta

- **`comun/tests/test_eventos.py` (33 pruebas, con fakeredis):**
  - **Catálogo y publicación:** catálogo, sobre, correlación inválida y Redis caído.
  - **Campos no registrables:** con un tipo de prueba que lleva una «pregunta».
  - **Consumo:** procesar y marcar, lo publicado antes de crear el grupo, duplicados, tipos ignorados, reintentos con espera creciente, fallidos, sobre ilegible, versión más nueva y recuperación de colgados.
  - **Idempotencia, los dos casos:** el manejador que falla no marca; si el proceso muere entre el manejador y la marca, el manejador idempotente evita el duplicado.
  - **Operación:** SIGTERM a la mitad de un evento, Redis caído en el consumidor y timeouts.
  - **Estado y reproceso:** `estado`; `reprocesar`, que conserva el id, así que el otro grupo lo salta; fallidos sin recorte; y que el núcleo no importe Django.
- **svc-usuarios (5):**
  - el registro publica después del commit, sin correo ni nombre;
  - la correlación inválida se reemplaza;
  - un registro inválido o una transacción revertida no publican;
  - **con Redis caído el registro responde 201 y queda `evento_no_publicado`**.
- **svc-contenido (4):** el evento llega a la bitácora con sus ids; el manejador es idempotente aunque se llame dos veces; los registros manuales sin `evento_id` no chocan con el índice; y `crear_indices` crea el índice único.
- **svc-ia (2):** Django no está instalado y la librería publica y consume ahí.
- **`infra/prueba_eventos.py`:** prueba de punta a punta contra Docker, con salida legible para evidencia (ver «Verificación»).

### Documentación

- **Nuevo:** [`docs/eventos.md`](../eventos.md).
- **`CLAUDE.md`:**
  - `comun` ahora también tiene eventos;
  - svc-ia instala el núcleo de `comun` sin DRF;
  - 11 contenedores;
  - la regla de llamadas entre servicios (síncrono para lo que necesita respuesta y eventos para lo demás) y las reglas de los eventos;
  - fakeredis en las pruebas.

  `usuario_id` ya decía UUID.
- **README raíz:** sección «Eventos entre servicios» (operación y cómo correr `prueba_eventos.py`), los 11 contenedores, `down -v` también borra los eventos, y la estructura y la documentación.
- **Definición técnica:** Redis como bróker, el servicio `svc-contenido-eventos`, la regla entre servicios, la bitácora, los volúmenes, las variables, la Entrega 4 en el plan y la decisión del bróker.
- **Otros README:** `comun` (núcleo y extra `[django]`, módulos de eventos), svc-usuarios, svc-contenido y svc-ia, y los docstrings de svc-ia que decían «no usa comun».

## Decisiones técnicas

### Aprobadas en el plan

| Decisión | Qué se hizo |
| --- | --- |
| Mecanismo | Redis Streams con grupos de consumidores, sin Celery ni RQ |
| Publicación | Con `on_commit`; si Redis no responde, `evento_no_publicado` y la operación sigue. Riesgo (evento perdido) y *outbox* como mejora pendiente, en `eventos.md` |
| `correo_solicitado` | En el catálogo para la fase 2, sin implementar. El token del enlace nunca viaja en el evento; en la recuperación con un correo que no existe no se publica nada, con la misma respuesta y el mismo tiempo |
| Prueba de punta a punta | Script `infra/prueba_eventos.py`, documentado en el README |
| Idempotencia | La llave de procesados se escribe solo después de que el manejador terminó bien; el hueco entre manejador y llave lo cubre la idempotencia del manejador (índice único). Probados los dos casos |
| Memoria de Redis | `noeviction` explícito y documentado; `reiniciar_limites` sigue funcionando con la persistencia |
| No registrables | Campo por tipo en el catálogo; ningún log los escribe. Probado con un tipo de prueba |
| `correlacion_id` | Solo UUID válido, si no uno nuevo, en los servicios. El gateway todavía no la genera ni la reenvía: queda escrito como regla para la fase 2 |
| Fallidos | Sin recorte; `estado` muestra cuántos hay |
| Reproceso | Conserva el id del sobre; documentado que todo manejador debe ser idempotente porque la llave vence a los 7 días |
| Apagado | Con SIGTERM termina el evento en curso y sale limpio |

### Tomadas durante la fase

- **Un solo mecanismo para reintentos y mensajes colgados:** la lista de pendientes del grupo, con la espera según las entregas que lleva cada mensaje (`XPENDING` y `XCLAIM`), en lugar de una cola de reintentos aparte.
- **Los grupos se crean desde el inicio del stream (`id 0`):** lo que se publicó antes de que existiera el grupo también se procesa. La idempotencia evita duplicados.
- **El consumidor lee de a un evento,** para que al detenerse no deje mensajes leídos sin empezar.
- **Una versión de sobre más nueva que la del catálogo va directo a fallidos,** en lugar de aplicarla con un manejador viejo.
- **El módulo de Django se llama `en_django.py`** y no `django.py`, para no confundirlo con el paquete `django`.
- **La API de la bitácora expone `evento_id` y `correlacion_id`:** sirven de evidencia y para seguir un flujo. Son de solo lectura y no rompen el contrato.
- **La prueba de punta a punta usa la configuración real** (5 reintentos de 2 a 32 s) y un fallo real: detener MongoDB. Por eso tarda unos 2 minutos.
- **Dependencias nuevas** (solo de desarrollo): `fakeredis==2.40.0` (del 14 de octubre de 2026) y su dependencia `sortedcontainers==2.4.0`, en los `requirements-dev.txt` de svc-tienda (donde corren las pruebas de `comun`), svc-usuarios, svc-contenido y svc-ia. `redis==8.1.0`, que ya usaba svc-usuarios, pasó al núcleo de `comun`.

## Verificación

Todo en Docker, el 22 de noviembre de 2026.

- **Arranque:** `docker compose up --build -d` con los **11 contenedores** arriba. Redis con `appendonly yes` y `maxmemory-policy noeviction`. El consumidor creó los índices (también `evento_id_1 (único)`) y registró `consumidor_iniciado`. En svc-ia, `agroia_comun.eventos` se importa sin Django.
- **Prueba de punta a punta** (`python infra/prueba_eventos.py`): **15 de 15 comprobaciones en 116 s**.
  1. **Punta a punta:** un registro por el gateway llegó a la bitácora en menos de 0,1 s, con `datos={'rol': 'cliente'}` (sin correo ni nombre), su `evento_id` y su `correlacion_id`.
  2. **Apagado limpio:** `docker compose stop svc-contenido-eventos` terminó en 5,4 s con **código 0**, registró `consumidor_deteniendo` y `consumidor_detenido`, y no dejó pendientes. El caso de un evento a la mitad lo cubre la prueba de SIGTERM de `comun`: termina el evento en curso, lo confirma y sale.
  3. **Consumidor caído:** con el consumidor detenido, el registro respondió 201, el evento esperó en Redis (`sin leer = 1`) y no llegó a la bitácora. Al arrancar el consumidor, lo procesó en 1,0 s.
  4. **Fallido y reproceso:**
     - Con MongoDB detenido, el evento agotó sus reintentos y llegó a `agroia:eventos:fallidos` en 89 s, con **6 intentos** (1 + 5 reintentos), el motivo `ServerSelectionTimeoutError` y **5 líneas `evento_reintentado`** en el log.
     - Con MongoDB de vuelta, `reprocesar --id` lo republicó y llegó a la bitácora **una sola vez y con el mismo `evento_id`**. El stream de fallidos volvió a su tamaño.
  5. **Limpieza:** `limpiar_datos_prueba` borró los 3 usuarios de prueba y sus 3 eventos de bitácora.
- **Persistencia:** después de `docker compose restart redis`, el stream de usuarios conservó sus 5 eventos y su grupo, y los contadores del límite de intentos también sobrevivieron. **`reiniciar_limites` los borró igual** («Contadores de límite borrados: 2. Intentos de axes borrados: 1.») y el login volvió a responder 401 en lugar de 429.
- **Redis reiniciado con el consumidor corriendo:** el consumidor registró `consumidor_sin_redis`, no se cayó, y un registro posterior llegó a la bitácora de inmediato.
- **pytest:** **833 en verde.**

  | Servicio | Pruebas |
  | --- | --- |
  | web | 258 |
  | svc-usuarios | 163 (antes 158) |
  | svc-tienda | 160 |
  | svc-contenido | 89 (antes 85) |
  | svc-ia | 65 (antes 63) |
  | comun | 98 (antes 65) |

  Las 33 pruebas de eventos de `comun` dependen de tiempos cortos (esperas de 0,02 y 0,1 s); se corrieron tres veces seguidas sin fallas.
- **ruff:** `ruff check` y `ruff format --check` en verde en los cinco servicios, `comun` e `infra/`.
- **Swagger:** `spectacular --validate --fail-on-warn` termina con código 0 en svc-usuarios, svc-tienda, svc-contenido y web.
- **Postman** (después de `reiniciar_limites`): **118 peticiones y 198 aserciones, 0 fallas.**
- **Matriz de accesos** (un minuto después): **106 de 106 casos coinciden**. El reporte que genera se restauró a su versión de la Entrega 3, para no mezclar esa evidencia en esta rama.
- **Estado de los eventos tras Postman y la matriz:** `agroia:eventos:usuarios` con el grupo `svc-contenido` sin pendientes ni mensajes sin leer, y 0 fallidos.
- **Limpieza al final:** `limpiar_datos_prueba` en los tres servicios dejó los datos como al principio.

## Problemas encontrados

| Problema | Solución |
| --- | --- |
| La prueba de espera creciente fallaba a veces: con una espera base de 0,02 s, dormir la espera más un margen alcanzaba ya la del intento siguiente | Esa prueba usa una espera base de 0,1 s, para que las ventanas no se encimen |
| La prueba de SIGTERM buscaba el id del segundo evento en todo el log, y aparece en su propio `evento_publicado` | Se comprueba que no haya un `evento_procesado` de ese evento |
| El script de punta a punta leía la salida de `docker` como cp1252 en Windows y fallaba con los acentos | `subprocess` con `encoding="utf-8"` |
| Al consultar versiones de paquetes, Git Bash reescribió una ruta `/tmp` y quedó una carpeta con una rueda de fakeredis dentro de `svc-usuarios/` | Se borró; era un resto de esa consulta |
| Docker Desktop estaba detenido al empezar | Se inició; respondió en unos segundos |

## Commits y Pull Requests

Rama `feat/e4-eventos-base` desde `develop`. Los commits se proponen al cerrar la fase.

## Pendientes y siguiente paso

- **Fase 2 · Eventos de negocio:**
  - `correo_verificado`, `rol_cambiado`, `correo_solicitado` (con el consumidor de correos de svc-usuarios), `pedido_creado`, `pedido_pagado` y `pedido_estado_cambiado`, todos hacia la bitácora;
  - el gateway genera y reenvía `X-Correlacion-Id`, solo si es un UUID válido.
- **Fase 3 · IA asíncrona y widget del chat:** `ia_pregunta_solicitada` y su respuesta, con el contenedor `svc-ia-worker` y la pregunta y el historial como no registrables. Hay que decidir cómo se entera web del resultado y cómo viaja la imagen del diagnóstico (alternativas en `eventos.md`).
- **Outbox:** si un evento perdido llega a tener consecuencias de negocio.
- **Postman:** no tiene casos de eventos. La evidencia de la asincronía es `prueba_eventos.py`.
