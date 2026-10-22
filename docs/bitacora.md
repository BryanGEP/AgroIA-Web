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
