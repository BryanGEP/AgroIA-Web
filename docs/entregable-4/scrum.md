# Scrum de la Entrega 4

> **Propuesta para revisar con el equipo.** Las historias, los criterios y las fechas salen de [`docs/bitacora.md`](../bitacora.md) y del historial de git (PR #13 a #18 y la rama `docs/entregable-4`). **Los puntos son una estimación propuesta**: el equipo los revisa en la planeación y, ya acordados, se pasan a Jira.

## Fuentes

- **Bitácora:** seis entradas del Sprint 4, del 22 al 26 de noviembre de 2026, todas de Bryan Gael Esquivel Pérez.
- **Git** (solo lectura): los PR fusionados en `develop`.

| PR | Rama | Commits | Archivos | Líneas (+ / −) | Fusionado |
| --- | --- | --- | --- | --- | --- |
| #13 | `feat/e4-eventos-base` | 9 | 55 | 2588 / 58 | 22/11 |
| #14 | `feat/e4-eventos-negocio` | 10 | 58 | 2515 / 131 | 22/11 |
| #15 | `feat/e4-ia-asincrona` | 10 | 76 | 5608 / 626 | 24/11 |
| #16 | `feat/e4-widget-agroia` | 5 | 62 | 1812 / 96 | 24/11 |
| #17 | `feat/diseno-front` | 3 | 107 | 1194 / 474 | 24/11 |
| #18 | `feat/panel-admin` | 11 | 104 | 4323 / 299 | 26/11 |
| — | `docs/entregable-4` | (sin fusionar) | — | — | 26/11 |

Las fechas de los commits no sirven como inicio del trabajo: cada integrante hace los commits a mano al terminar la rama, así que todos caen en los minutos antes de su PR. **El inicio y el cierre de cada historia salen de la bitácora.**

## Sprint 4 (propuesta: un solo sprint)

- **Fechas:** del 21 al 26 de noviembre de 2026. El Sprint 3 cerró el 20 de noviembre con el PR #12, y la primera entrada del Sprint 4 en la bitácora es del 22.
- **Objetivo:** comunicación asíncrona con Redis Streams, la llamada a la IA por eventos, y la evidencia y documentación de la entrega. Además, mejorar la experiencia: widget, rediseño y panel.

| # | Historia de usuario | Criterios de aceptación | Inicio · cierre | Puntos (propuesta) |
| --- | --- | --- | --- | --- |
| HU-4.1 | **Como equipo,** queremos una base de eventos con Redis Streams para que los servicios se avisen sin esperarse. | Catálogo y sobre común documentados en `docs/eventos.md`. Librería en `comun` con publicación validada, grupos, reintentos con espera creciente, reclamo de colgados, stream de fallidos, reproceso e idempotencia. Núcleo sin Django. `usuario_registrado` llega a la bitácora por un consumidor en su propio contenedor. Prueba de punta a punta con consumidor caído y reproceso. | 22/11 · 22/11 (PR #13) | 8 |
| HU-4.2 | **Como administrador,** quiero que las acciones de negocio queden en la bitácora y que los correos salgan en segundo plano, para auditar y para que el usuario no espere. | Eventos de usuarios (verificación, rol, contraseña, sesiones) y de pedidos (creado y cada transición, también el pago), publicados después del commit. Correos por `correo_solicitado` con su consumidor, y el token generado al procesar. Riesgo B5 cerrado y medido. `X-Correlacion-Id` de punta a punta. Bitácora filtrable por usuario y correlación. | 22/11 · 22/11 (PR #14) | 8 |
| HU-4.3 | **Como productor de aguacate,** quiero preguntar a AgroIA y diagnosticar una foto sin que la página se quede esperando. | svc-contenido publica la solicitud (202). `svc-ia-worker` la procesa y publica el resultado, y svc-contenido lo guarda en MongoDB. Polling con HTMX. Reintentos por tipo de error, vencimiento de 180 s, «Reintentar» y respuestas tardías descartadas. 2 hilos con latido. Límite de 10 preguntas por minuto y 30 por hora por usuario. Sin pregunta ni respuesta en logs ni en fallidos. Matriz y prueba de punta a punta en verde. | 22/11 · 24/11 (PR #15) | 13 |
| HU-4.4 | **Como visitante o cliente,** quiero el chat de AgroIA en todas las páginas. | Widget con el mismo flujo asíncrono, conversación en la sesión y carga diferida. Invitación a iniciar sesión para visitantes. Dictado por voz con aviso y `Permissions-Policy`. Accesibilidad: foco en móvil, Esc y aria-live. 52 comprobaciones en el navegador. | 24/11 · 24/11 (PR #16) | 8 |
| HU-4.5 | **Como usuario,** quiero una interfaz clara, propia del aguacate y accesible. | Dirección «Altura» en todas las pantallas. Contraste AA en 50 pares de color en tema claro y oscuro. Foco visible. 0 errores de consola y de la CSP en 108 revisiones. Sin cambiar contratos ni vistas. | 24/11 · 24/11 (PR #17) | 8 |
| HU-4.6 | **Como administrador,** quiero ver el estado de la tienda, la bitácora y los eventos desde el panel. | Resumen con ventas por `pagado_en` en hora de México y tarjetas aisladas si un servicio falla. Bitácora legible con correlación. Estado de los eventos sin datos. Filtros, confirmaciones y detalle de usuario. 401 y 403 en los endpoints nuevos (matriz y Postman). | 26/11 · 26/11 (PR #18) | 13 |
| HU-4.7 | **Como equipo,** queremos cerrar la entrega con evidencia del flujo asíncrono. | Corrida final en verde (pytest, ruff, Postman, matriz y punta a punta). Logs por correlación sin datos sensibles. Capturas, video corto y guion del video narrado. `docs/entregable-4.md` y métricas de Scrum. | 26/11 · 26/11 (`docs/entregable-4`) | 5 |
| | | | **Total** | **63** |

**Velocidad del Sprint 4 (propuesta): 63 puntos**, todos terminados y aceptados (se fusionaron en `develop` con sus pruebas en verde). No hubo historias que pasaran al siguiente sprint.

### Por qué esos puntos

La escala es Fibonacci (1, 2, 3, 5, 8, 13), relativa a la historia de referencia HU-4.1 = 8: una librería nueva, un contenedor nuevo y una prueba de punta a punta.

| Puntos | Historias | Por qué |
| --- | --- | --- |
| 13 | HU-4.3 y HU-4.6 | Las de más incertidumbre y piezas: tocan tres o más servicios, con concurrencia y cuota externa (4.3), y endpoints nuevos en tres servicios, una migración y siete pantallas (4.6) |
| 8 | HU-4.1, HU-4.2, HU-4.4 y HU-4.5 | Tamaño parecido a la referencia: mucho trabajo, pero con un patrón ya resuelto o sin cambiar contratos (4.5) |
| 5 | HU-4.7 | Sobre todo documentación y corridas, aunque con varias partes |

## Alternativa: dividirlo en dos sprints

Si el equipo prefiere sprints más cortos y con un objetivo cada uno, la división natural es por el tipo de trabajo:

| Sprint | Fechas | Objetivo | Historias | Puntos |
| --- | --- | --- | --- | --- |
| **Sprint 4 · Eventos e IA asíncrona** | 21 al 24 de noviembre de 2026 | Lo que pide la entrega: eventos con Redis, correos en segundo plano e IA por eventos | HU-4.1, HU-4.2 y HU-4.3 | 29 |
| **Sprint 5 · Experiencia y cierre** | 24 al 26 de noviembre de 2026 | Widget, rediseño, panel de administración y evidencia de la entrega | HU-4.4, HU-4.5, HU-4.6 y HU-4.7 | 34 |

**Velocidad:** 29 y 34 puntos. Promedio: 31.5 puntos por sprint.

Con esta división, el Sprint 4 cierra con lo que pide el maestro (eventos e IA, PR #13 a #15). El Sprint 5 junta lo que mejora la experiencia y el cierre (PR #16 a #18 y la documentación). Ojo: la bitácora llama «Sprint 4» a todas las entradas del 22 al 26. Si se elige esta opción, en Jira las del 24 por la tarde y la del 26 van al Sprint 5.

## Métricas para Jira

| Métrica | Un sprint | Dos sprints |
| --- | --- | --- |
| Historias comprometidas y terminadas | 7 de 7 | 3 de 3 y 4 de 4 |
| Puntos terminados (velocidad) | 63 | 29 y 34 |
| Días del sprint | 6 (21 al 26) | 4 (21 al 24) y 3 (24 al 26) |
| PR fusionados | 6 (#13 a #18) y 1 por fusionar | 3 y 3, más 1 por fusionar |
| Pruebas automatizadas al cierre | 1124 | 1124 |

**Pruebas al cierre:** web 359, svc-usuarios 194, svc-tienda 185, svc-contenido 150, svc-ia 87, comun 137 e infra 12. Al cierre de la Entrega 3 eran 789. Detalle en [`resultados-pruebas.md`](resultados-pruebas.md).

**Retrospectiva sugerida para la reunión:**

- **Qué funcionó:**
  - planear cada fase antes de implementarla;
  - la prueba de punta a punta en Docker;
  - la correlación para seguir un flujo.
- **Qué mejorar:** la cuota gratuita de Groq limita las corridas completas. Conviene planearlas al inicio del día o usar un modelo de respaldo.
- **Acción:** dejar fijo en el calendario el orden de las corridas, y que todos los integrantes registren su trabajo en la bitácora.
