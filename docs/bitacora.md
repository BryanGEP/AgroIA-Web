# Bitácora diaria

Registro de lo que hace cada integrante en cada sesión de trabajo: qué hizo, qué sigue y qué lo bloquea.
Se cargará a Jira como evidencia de los dailies de cada sprint.

## 2026-10-22 · Sprint 2
- **Integrante:** Bryan Gael Esquivel Pérez
- **Qué se hizo:** aprobación de decisiones de arquitectura con el equipo; configuración de Claude Code (CLAUDE.md, settings); fase 0 completa (base del monorepo, cinco servicios con `/salud/`, docker-compose verificado).
- **Qué sigue:** fase 2, API de svc-tienda (modelos, CRUD, filtros, carrito y pedidos).
- **Bloqueos:** Docker y Python 3.12 no estaban instalados; se resolvió instalándolos.


## 2026-10-22 · Sprint 2
- **Integrante:** Bryan Gael Esquivel Pérez
- **Qué se hizo:** fase 2, API de svc-tienda: catálogo con filtros y paginación, carrito, pedidos con descuento de stock en transacción, pago simulado y estados; validación JWT RS256, permisos por rol y formato de errores en comun; script de tokens de desarrollo; datos de demostración, Swagger y colección de Postman. 144 pruebas en svc-tienda y 26 en comun.
- **Qué sigue:** fase 3: API de svc-contenido (MongoDB) y svc-ia (agente y modelo de visión). Avisar al equipo del endpoint nuevo POST /pedidos/<id>/pagar/.
- **Bloqueos:** Ninguno.


## 2026-10-22 · Sprint 2
- **Integrante:** Bryan Gael Esquivel Pérez
- **Qué se hizo:** fase 3: API de svc-contenido en MongoDB (conversaciones con límite de 200 mensajes, diagnósticos con imagen y bitácora, índices al arrancar); svc-ia como adaptador del agente del repo AgroIA, que corre en su propio contenedor construido desde GitHub; diagnóstico con interfaz de clasificador y 503 mientras no haya modelo. Pregunta real verificada a través de svc-ia. 69 pruebas en svc-contenido y 55 en svc-ia.
- **Qué sigue:** svc-usuarios básico (modelo Usuario, registro y perfil, sin login JWT); avisar al equipo de los cambios de contrato; en el repo AgroIA, fijar versiones del agente, aceptar historial y no acumular sesiones.
- **Bloqueos:** Ninguno.


## 2026-10-22 · Sprint 2
- **Integrante:** Bryan Gael Esquivel Pérez
- **Qué se hizo:** fase 1 básica de svc-usuarios: modelo Usuario por correo y Direccion con una sola predeterminada, registro con aviso de privacidad, perfil, direcciones, listado del administrador y comando asignar_admin; reinicio solo de usuarios_db para el modelo propio. 71 pruebas en svc-usuarios, sin regresiones en los demás servicios.
- **Qué sigue:** completar calidad de la Entrega 2 (revisión de Swagger y Postman de todos los servicios) y documentar los sprints en Jira.
- **Bloqueos:** Ninguno.


## 2026-10-22 · Sprint 2
- **Integrante:** Bryan Gael Esquivel Pérez
- **Qué se hizo:** base visual del gateway web (Tailwind 4 + daisyUI 5 sin Node, tema agroia claro y oscuro, HTMX y Alpine locales, base.html y componentes) y páginas públicas: inicio, catálogo con filtros HTMX que también funciona sin JavaScript, detalle con ficha técnica y aviso de privacidad; reenvío de imágenes desde svc-tienda. Revisado en celular, tableta y escritorio. 45 pruebas en web, sin regresiones.
- **Qué sigue:** revisión final de calidad de la Entrega 2 (Swagger y Postman de todos los servicios) y documentar los sprints en Jira.
- **Bloqueos:** Ninguno.


## 2026-11-18 · Sprint 2
- **Integrante:** Bryan Gael Esquivel Pérez
- **Qué se hizo:** revisión final de calidad de la Entrega 2: base de conocimiento del agente en un contenedor propio (agente-db con pgvector) e ingesta repetible; svc-ia manda el historial al agente y devuelve sus fuentes; Swagger con ejemplos y errores documentados en todos los servicios; colección de Postman completa en verde (95 de 95 aserciones, dos corridas); documentación corregida y documento del Entregable 2 con capturas. 418 pruebas en verde.
- **Qué sigue:** documentar los sprints de la Entrega 2 en Jira y fusionar develop en main.
- **Bloqueos:** Ninguno.


## 2026-11-19 · Sprint 3
- **Integrante:** Bryan Gael Esquivel Pérez
- **Qué se hizo:** Entrega 3, identidad en svc-usuarios: login con JWT RS256 (access 15 min, refresh 7 días), renovación con rotación y blacklist, logout y logout-todo; correos con plantillas, verificación de correo, recuperación y cambio de contraseña; cambio de rol con registro; límite de intentos con DRF + Redis y bloqueo con django-axes; log de seguridad y registro de 401/403 en todos los servicios. Id de usuario como UUID en todos los servicios, JWT_ISSUER configurable y contrato de identidad con las diferencias con ms-usuarios. Revisión de seguridad con Semgrep, CodeQL y check --deploy, sin hallazgos de gravedad alta; se corrigieron los medios y bajos aplicables. Postman con login automático y carpeta de seguridad. 534 pruebas en verde.
- **Qué sigue:** fase del gateway (sesión, enrutamiento, CORS y pantallas de login, registro y perfil).
- **Bloqueos:** Ninguno.


## 2026-11-20 · Sprint 3
- **Integrante:** Bryan Gael Esquivel Pérez
- **Qué se hizo:** gateway web de la Entrega 3: sesión con los JWT guardados en el servidor y renovación automática; proxy /api/<servicio>/ que valida el token antes de reenviar (defensa en dos capas) y pone la IP real del cliente; CORS con rechazo de orígenes no permitidos; CSP estricta sin unsafe-inline ni unsafe-eval (Alpine en su versión CSP); pantallas de login, registro, verificación de correo, recuperación y restablecimiento de contraseña, mi cuenta con direcciones, cambio de contraseña y cierre de sesión. Flujo verificado en el navegador sin violaciones de la CSP. Postman con carpeta Gateway (180 aserciones, 0 fallas en dos corridas). 634 pruebas en verde.
- **Qué sigue:** pantallas protegidas (carrito, checkout, mis pedidos, chat con AgroIA, diagnóstico y panel de administrador).
- **Bloqueos:** Docker Desktop se detuvo dos veces durante la sesión; se reinició sin pérdida de datos.


## 2026-11-20 · Sprint 3
- **Integrante:** Bryan Gael Esquivel Pérez
- **Qué se hizo:** pantallas protegidas de la Entrega 3: carrito con contador en el menú, checkout con direcciones y aviso de correo sin verificar, mis pedidos con pago simulado; chat con AgroIA orquestado por el gateway (svc-contenido + svc-ia) con fuentes, reintento y manejo de fallos; diagnóstico con vista previa y flujo listo para el modelo; panel de administrador (productos, categorías, pedidos con transiciones que da svc-tienda y usuarios). Correcciones de seguridad: fotos de diagnóstico solo para su dueño o un administrador, redirección sin validar en el cambio de rol y filtro de Markdown del chat probado contra XSS. Timeout del agente a 45 s. 768 pruebas en verde.
- **Qué sigue:** cierre de la Entrega 3: documento de arquitectura de seguridad y matriz de pruebas de acceso permitido y denegado.
- **Bloqueos:** Ninguno.


## 2026-11-20 · Sprint 3
- **Integrante:** Bryan Gael Esquivel Pérez
- **Qué se hizo:** cierre de la Entrega 3: verificación completa desde cero (10 contenedores, 789 pruebas en verde, Postman sin fallas); matriz de accesos automatizada a través del gateway con 106 de 106 casos correctos (26 permitidos y 80 denegados); análisis estático de todo el código con CodeQL y Semgrep sin hallazgos reales; documento del Entregable 3 con la arquitectura de seguridad, diagramas de secuencia, evidencia y capturas; comandos de desarrollo para limpiar datos de prueba y reiniciar límites; documentación alineada con el código.
- **Qué sigue:** fusionar develop en main (v3.0) y empezar la Entrega 4 (comunicación asíncrona entre microservicios).
- **Bloqueos:** Ninguno.


## 2026-11-22 · Sprint 4

**Integrante:** Bryan Gael Esquivel Pérez

**Qué se hizo:**
- Diseño de la comunicación asíncrona: catálogo de eventos, sobre común y diagrama del flujo en `docs/eventos.md`.
- Librería de eventos en `comun` sobre Redis Streams con grupos de consumidores: publicación validada, confirmación, reintentos con espera creciente, reclamo de mensajes colgados, stream de fallidos, reproceso e idempotencia. El núcleo no depende de Django, así que también lo usa `svc-ia`.
- Redis con persistencia (`appendonly`) y `noeviction`; eventos separados de la caché del límite de intentos.
- Primer evento real: `usuario_registrado`, de `svc-usuarios` a la bitácora de `svc-contenido`, con un contenedor consumidor propio (11 contenedores).
- Prueba de punta a punta en Docker (`infra/prueba_eventos.py`): flujo completo, consumidor caído, evento fallido y reproceso, y apagado limpio.

**Qué sigue:**
- Fase 2: eventos de negocio (`correo_verificado`, `rol_cambiado`, eventos de pedidos y `correo_solicitado`) y `correlacion_id` generado por el gateway.

**Bloqueos:** Ninguno.


## 2026-11-22 · Sprint 4

**Integrante:** Bryan Gael Esquivel Pérez

**Qué se hizo:**
- Eventos de negocio: `correo_verificado`, `rol_cambiado`, `password_cambiada` y `sesiones_cerradas` (svc-usuarios); `pedido_creado` y `pedido_estado_cambiado` (svc-tienda). Todos se registran en la bitácora de svc-contenido. El pago es una transición más y publica un solo evento.
- Correos de verificación, recuperación y aviso de contraseña en segundo plano con `correo_solicitado` y un consumidor propio (`svc-usuarios-eventos`). El token se genera al procesar y nunca viaja en el evento.
- Riesgo B5 cerrado: la recuperación tarda lo mismo con un correo que existe y con uno que no (15 contra 17 ms; antes, 10 s y 504 contra 57 ms).
- `correlacion_id` de punta a punta: lo genera el gateway, viaja entre servicios y aparece en logs y en la bitácora. Log por petición en el gateway sin tokens.
- Filtros de la bitácora por usuario y correlación; prueba de punta a punta ampliada (37 de 37) y 12 contenedores.

**Qué sigue:**
- Fase 3: IA asíncrona (pregunta y diagnóstico por eventos con svc-ia como worker) y el widget flotante del chat en todas las páginas.

**Bloqueos:** Ninguno.