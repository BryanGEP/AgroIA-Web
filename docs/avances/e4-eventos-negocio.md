# Entrega 4 · Eventos de negocio y correos en segundo plano

**Fecha:** 22 de noviembre de 2026 · **Entregable:** Entrega 4 · **Responsable:** Bryan Gael Esquivel Pérez

## Resumen

Segunda parte de la comunicación asíncrona: los eventos de negocio sobre la base de la [fase 1](e4-eventos-base.md).

- **svc-usuarios** publica `correo_verificado`, `rol_cambiado`, `password_cambiada` y `sesiones_cerradas`; **svc-tienda**, `pedido_creado` y un solo `pedido_estado_cambiado` por cada transición, también el pago. Todos llegan a la bitácora de svc-contenido.
- **Los correos ya no se envían dentro de la petición:** las acciones publican `correo_solicitado` y un consumidor propio, el contenedor `svc-usuarios-eventos`, genera el token del enlace y envía. Eso **cierra el riesgo B5** de la Entrega 3: antes, con el servidor de correo caído, recuperar con un correo registrado respondía 504 en 10 s y con uno que no existe, 200 en 57 ms; ahora los dos responden 200 en unos 16 ms.
- **`X-Correlacion-Id` de punta a punta:**
  - **Gateway:** la genera o la valida, la reenvía a los servicios y escribe una línea por petición con la ruta como patrón (sin tokens).
  - **Servicios:** la ponen en sus eventos y en el log de seguridad.
  - **Consumidor:** la conserva al procesar.
- **La bitácora** se puede filtrar por usuario y por correlación.

Todo se verificó en Docker con [`infra/prueba_eventos.py`](../../infra/prueba_eventos.py): **37 de 37 comprobaciones**, incluido un flujo completo con su correlación y un correo que falla y se reprocesa.

## Qué se construyó

### `comun`

- **`eventos/correlacion.py` (núcleo, sin Django):** la correlación de la petición o el evento en curso, en una `ContextVar`.
  - `publicar()` la usa cuando no se le pasa una.
  - El consumidor la pone con la `correlacion_id` del sobre mientras corre cada manejador y la limpia al terminar, así un manejador que publica otro evento conserva la cadena.
- **`correlacion.py`, `CorrelacionMiddleware`:** acepta `X-Correlacion-Id` solo si es un UUID; si no, genera uno. La devuelve en la respuesta y la restablece al terminar la petición, también si hubo una excepción. Está en los cuatro servicios Django y en el gateway.
- **`seguridad.registrar_evento`:** suma `correlacion_id` al log de seguridad.
- **Catálogo:** siete tipos nuevos (ver [`docs/eventos.md`](../eventos.md)) y `valores` permitidos por campo, para que rol, estado, tipo de correo, método de pago, `via` y `motivo` no acepten cualquier texto. `correo_solicitado` va en su propio stream, `agroia:eventos:correos`.
- **`configurar_logging`:** logger `peticiones`.

### svc-usuarios

- **Eventos, siempre con `publicar_al_confirmar`:**
  - `correo_verificado`, solo si cambió (`via`: `enlace` o `recuperacion`);
  - `rol_cambiado`, con `cambiado_por` y nada si el rol no cambió;
  - `password_cambiada`, con `motivo` `cambio` o `recuperacion`;
  - `sesiones_cerradas`;
  - `correo_solicitado`.
- **`correos.py`:** si el envío falla lanza `ErrorDeEnvio`, que solo nombra la clase del error. El aviso de contraseña recibe la fecha del cambio.
- **`eventos.py` (consumidor de correos):**
  - revisa si todavía toca antes de enviar: nada a una cuenta desactivada, ni la verificación si ya está verificado;
  - genera el token al enviar;
  - guarda `CorreoEnviado(evento_id único)` para no mandar dos veces el mismo evento;
  - lo corre `python manage.py consumir_eventos` en `svc-usuarios-eventos`.
- **Migración `0002_correoenviado`;** `EMAIL_TIMEOUT` pasa a variable de entorno (10 s por defecto).

### svc-tienda

- **`pedido_creado`** al crear el pedido, con `productos` (número de renglones), `unidades`, `total` y `metodo_pago`, sin dirección ni nombres.
- **`pedido_estado_cambiado`** se publica en `_cambiar_estado_bloqueado`, la única función por la que pasan pagar y los cambios del administrador, con `cambiado_por`. `cambiar_estado` recibe ahora quién lo cambia.

### svc-contenido

- **Consumidor:** guarda en la bitácora los siete tipos con el mismo manejador idempotente; `correo_solicitado` no es suyo.
- **`GET /bitacora/`:** filtros nuevos `usuario_id` y `correlacion_id` (UUID; 400 `validacion` si no lo son), con índices `usuario_id + fecha` y `correlacion_id`.

### Gateway (web)

- **Correlación:** `CorrelacionMiddleware` y `config/peticiones.py`:
  - una línea JSON `peticion` por petición, con método, **ruta como patrón**, estado, duración, correlación y usuario (solo si la petición ya leyó la sesión, para no tocar la base en páginas públicas);
  - el filtro `SinRutasReales` descarta el log de runserver y cambia la ruta real por el patrón en `django.request`.
- **Rutas con un token o un uid en la URL:** `/restablecer/<uid>/<token>/` y `/verificar-correo/?token=`. Ningún log las escribe.
- **El cliente común** reenvía la correlación validada en cada llamada; el proxy no pasa la del cliente tal cual. `X-Correlacion-Id` está expuesto en CORS.

### Infraestructura y scripts

- **`svc-usuarios-eventos`:**
  - misma imagen y variables que svc-usuarios, `restart: unless-stopped`;
  - monta las llaves JWT **en solo lectura (`:ro`)**, porque la configuración del servicio exige la privada aunque este proceso no firma tokens. Se comprobó que `touch` sobre la llave falla con «Read-only file system».
- **svc-tienda** recibe las variables de eventos y depende de redis. Son **12 contenedores**.
- **`infra/medir_recuperacion.py`:** mide «recuperar contraseña» con un correo que existe y con uno que no (riesgo B5).
- **`infra/prueba_eventos.py` ampliado:**
  - flujo completo con correlación;
  - correlación en los logs;
  - un correo que falla y se reprocesa;
  - la limpieza también pasa por svc-tienda.
- **Postman:** tres casos nuevos en «Bitácora»: filtrar por usuario, por correlación y un filtro que no es UUID (400).

## Decisiones técnicas

| Decisión | Por qué |
| --- | --- |
| El pago es un `pedido_estado_cambiado` más, no `pedido_pagado` | Con un solo lugar que publica (`_cambiar_estado_bloqueado`), una transición nunca publica dos eventos por el camino que sea; los consumidores filtran por `estado_nuevo` |
| `correo_solicitado` en su propio stream | Es una cola de trabajo interna de svc-usuarios; la bitácora no la lee |
| Los tipos de correo son `verificacion`, `recuperacion` y `aviso_password` | `aviso_password` para no confundirlo con el evento `password_cambiada` de la bitácora |
| Ningún correo síncrono | No hay códigos de 2FA por correo (2FA responde 501 y usaría TOTP con una app) |
| `password_cambiada` y `sesiones_cerradas` en la bitácora; login, logout y renovaciones no | Son acciones de cuenta que interesan al administrador; las otras son de mucho volumen y ya están en el log de seguridad |
| Correlación en una `ContextVar` | `publicar_al_confirmar` la toma sola: las funciones de servicio no tienen que recibirla |
| Ruta como patrón en el log del gateway | Dos rutas llevan tokens; el patrón basta para seguir un flujo |
| Log por petición solo en el gateway | Es la entrada de cada flujo; en los servicios la correlación ya va en el log de seguridad y en el de eventos |
| Pantalla de bitácora en el panel | Fuera de esta fase; opcional para la fase 4 |
| Mediciones de B5 con un servidor de correo que no responde | Con el backend de consola el envío dura milisegundos y la diferencia no se ve |

**Contradicciones con los documentos (ya corregidas):**
- **`docs/eventos.md`:** listaba `pedido_pagado`, ponía `correo_solicitado` en el stream de usuarios, llamaba `password_cambiada` al tipo de correo y describía `productos` como «cantidad».
- **El docstring de `correos.py`:** decía que un envío fallido no se reintenta.
- **B5:** figuraba como aceptado en `entregable-3.md` y `e3-identidad.md`; ahora dice que el tiempo quedó cerrado en la Entrega 4, con las mediciones.
- **`requerimientos-autenticacion.md` §13:** proponía Celery; quedó una nota de implementación.
- **El comentario de la lista cerrada de encabezados del proxy:** ahora explica que la correlación se reenvía validada.
- **Dónde se ven los correos en desarrollo:** ahora en `docker compose logs svc-usuarios-eventos`, no en svc-usuarios; corregido en el README raíz y el de svc-usuarios.
- **CLAUDE.md, el README y la definición técnica:** ahora dicen 12 contenedores.

**Dependencias nuevas:** ninguna.

## Verificación

Todo en Docker, el 22 de noviembre de 2026.

- **Riesgo B5**, medido con `infra/medir_recuperacion.py` y un servidor de correo que no responde (`EMAIL_HOST=10.255.255.1`):

  | | Correo que existe | Correo que no existe |
  | --- | --- | --- |
  | Antes (3 peticiones de cada uno) | **504** en 10 016 ms (el gateway corta esperando al SMTP) | 200 en 57 ms |
  | Después (5 de cada uno) | 200 en 15 ms | 200 en 17 ms |

  Antes, el correo registrado se delataba por el tiempo y también por el código de respuesta.

  Una primera medición de «después» reutilizaba la conexión y dio 16 ms contra 58 ms, al revés de lo esperado: los 40 ms de más venían de reutilizar la conexión, no de la cuenta. La medición final usa una conexión nueva por petición y alterna cuál va primero.

  Las 5 recuperaciones de la medición quedaron reintentándose contra el SMTP caído. Al volver al backend de consola, el consumidor las envió y no quedó ninguna en fallidos.
- **`infra/prueba_eventos.py`: 37 de 37 comprobaciones en 145 s.**
  1. **Pasos 1 a 4 de la fase 1:** punta a punta, apagado limpio, consumidor caído, y fallido y reproceso con MongoDB detenido (86 s hasta fallidos), todos en verde.
  2. **Flujo completo, cada petición con su correlación:**
     - registro (201, con la misma correlación en la respuesta);
     - el consumidor envió el correo de verificación y su enlace verificó la cuenta;
     - pedido (201), pago (200) y cancelación del administrador (200; devuelve el stock).
     - **Bitácora:** cada correlación trae exactamente su evento (`usuario_registrado`, `correo_verificado`, `pedido_creado` y dos `pedido_estado_cambiado`, pagado y cancelado), con su servicio de origen. El filtro por usuario trae los 5.
  3. **Logs:** la correlación del pedido aparece en la línea `peticion` del gateway, en el `evento_publicado` de svc-tienda y en el `evento_procesado` del consumidor. El token de verificación no aparece en ningún log del gateway.
  4. **Correo que falla** (servidor de correo que no responde, timeout de 2 s, 2 reintentos):
     - la recuperación respondió 200 en 17 ms;
     - el evento llegó a fallidos con 3 intentos y el motivo `ErrorDeEnvio: No se pudo enviar el correo «recuperacion»: TimeoutError`, sin el destinatario;
     - con la consola de vuelta, `reprocesar` lo envió, y el token generado al reprocesar sirvió para restablecer la contraseña. `password_cambiada` (motivo `recuperacion`) llegó a la bitácora.
  5. **Limpieza:** se borraron los usuarios de prueba, su pedido, su carrito y sus 9 eventos de bitácora.
- **Llave privada en solo lectura** en `svc-usuarios-eventos`: `touch` responde «Read-only file system».
- **pytest: 909 en verde.**

  | Servicio | Pruebas |
  | --- | --- |
  | web | 271 (antes 258) |
  | svc-usuarios | 186 (antes 163) |
  | svc-tienda | 169 (antes 160) |
  | svc-contenido | 102 (antes 89) |
  | svc-ia | 65 |
  | comun | 116 (antes 98) |

  Las pruebas nuevas cubren:
  - **Productores:** cada evento se publica al confirmar, con la correlación de la petición, y nada si la transacción se revierte o la operación falla. El pago publica uno solo, y pagar dos veces también uno.
  - **Consumidor de correos:**
    - genera el token al procesar y un reproceso tres días después da un token nuevo y vigente;
    - el mismo `evento_id` no manda dos correos;
    - no envía a una cuenta verificada (verificación) ni a una desactivada;
    - el aviso usa la fecha del sobre;
    - un envío que falla lanza el error sin el destinatario y no marca; el reintento manda un solo correo; uno que siempre falla llega a fallidos;
    - la recuperación con un correo inexistente no publica nada y responde igual.
  - **Bitácora:** los siete tipos, sin duplicar, y los filtros con su validación.
  - **Correlación:**
    - la `ContextVar` se restablece aunque falle;
    - no se arrastra entre dos peticiones;
    - el gateway genera una si no viene o no es UUID, y la reenvía validada en las llamadas internas y en el proxy;
    - la cadena se conserva en el consumidor.
  - **Logs:** **ningún log** contiene el token de verificación ni el de recuperación, ni en la ruta ni en la query, ni en el log de runserver ni en el «Not Found» de Django.
- **ruff:** `ruff check` y `ruff format --check` en verde en los cinco servicios, `comun` e `infra/`.
- **Postman** (después de `cargar_datos_demo` y `reiniciar_limites`): **121 peticiones y 204 aserciones, 0 fallas.**
  - Una primera corrida dio 12 fallas en cadena desde «Agregar al carrito» (409). El producto que usa la colección tenía stock 0: cada corrida compra 2 piezas y, a propósito, ni Postman ni `limpiar_datos_prueba` devuelven ese stock.
  - `cargar_datos_demo` lo restableció y se agregó ese paso al orden recomendado del README.
- **Matriz de accesos** (un minuto después): **106 de 106**. El reporte se restauró con `git restore docs/entregable-3/matriz-accesos.md`.
- **Al final:** `limpiar_datos_prueba` en los tres servicios; `estado` muestra 0 pendientes y 0 fallidos.

## Problemas encontrados

| Problema | Solución |
| --- | --- |
| Las pruebas de correos revisaban `mail.outbox` justo después de la petición | Fixture `entregar_correos`, que corre el consumidor real hasta vaciar la cola |
| La prueba de concurrencia de svc-tienda usaba ids enteros (20 y 21) y el catálogo rechazó el evento (`usuario_id` debe ser UUID) | La prueba usa UUID, como el token en producción |
| El log por petición leía la sesión en cada petición y tocaba la base en páginas públicas | Solo la lee si la petición ya la había cargado (`session.accessed`) |
| `docker logs --since` toma la hora sin zona como hora local; el script le pasaba la UTC sin `Z` y no encontraba los correos | Hora con `Z` |
| La primera medición de B5 «después» salió al revés (16 contra 58 ms) | Conexión nueva por petición y orden alternado (ver «Verificación») |
| Postman falló por stock agotado del catálogo de demostración | `cargar_datos_demo` antes de correr la colección, ya en el README |
| Un *heredoc* de Git Bash se rompió con un texto largo | Los scripts de cambios se escribieron en archivos |

## Commits y Pull Requests

Rama `feat/e4-eventos-negocio` desde `develop`. Los commits se proponen al cerrar la fase.

## Pendientes y siguiente paso

- **Fase 3 · IA asíncrona y widget del chat:** `ia_pregunta_solicitada` y su respuesta, con el contenedor `svc-ia-worker`. svc-ia empezará a leer `X-Correlacion-Id`.
- **Pantalla de bitácora** en el panel (opcional, fase 4).
- **Consumidores viejos en `estado`:** cada contenedor recreado deja su nombre anterior listado (sin pendientes).
- **El hueco de SMTP:** un correo puede salir dos veces si el proceso muere entre enviarlo y guardar `CorreoEnviado`. Está documentado; no se puede cerrar con SMTP.
- **Outbox:** sigue pendiente, como en la fase 1.
