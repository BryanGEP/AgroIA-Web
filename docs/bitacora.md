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