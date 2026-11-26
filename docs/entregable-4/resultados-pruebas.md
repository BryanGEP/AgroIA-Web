# Resultados de las pruebas · Entrega 4

Corrida final del **26 de noviembre de 2026**, de 13:30 a 13:42, hora de México (19:30 a 19:42 UTC). Se hizo en la rama `docs/entregable-4`, desde `develop` en `a24dd06`, con los 13 contenedores levantados con `docker compose`.

**Antes de empezar se comprobó la cuota de Groq** con una pregunta directa al agente: respondió `listo`, con 280 caracteres y 4 fuentes.

**Orden de la corrida:**

1. pytest y ruff;
2. `reiniciar_limites` y `cargar_datos_demo`;
3. Postman;
4. la prueba de punta a punta;
5. la matriz.

La matriz va al final porque agota el límite de recuperación de contraseña.

## Resumen

| Prueba | Resultado |
| --- | --- |
| pytest (7 suites) | **1124 de 1124** |
| `ruff check` y `ruff format --check` | Sin observaciones (356 archivos) |
| Postman (Newman 6.2.1) | **159 peticiones, 258 de 258 aserciones**, 0 fallas, en 28.2 s |
| Prueba de punta a punta (`infra/prueba_eventos.py`) | **62 de 62 comprobaciones**, en 475 s |
| Matriz de accesos (`infra/matriz_seguridad.py`) | **186 de 186 casos (100 %)**, **0 marcados por servicio externo**, en 80 s |

## Pruebas automatizadas (pytest)

Dentro de los contenedores. Las de `infra` corren en el venv de la raíz.

| Suite | Pruebas | Lo que cubre de la Entrega 4 |
| --- | --- | --- |
| web | 359 | Widget y chat asíncrono (polling, «Reintentar», vencida, 429), correlación en el gateway, log por petición sin tokens, panel (resumen, bitácora y eventos) |
| svc-usuarios | 194 | Eventos de usuarios y `correo_solicitado`, consumidor de correos (token generado al procesar), cierre de B5 |
| svc-tienda | 185 | `pedido_creado` y un solo `pedido_estado_cambiado` por transición, publicados al confirmar; `pagado_en`; resumen del panel |
| svc-contenido | 150 | Bitácora idempotente por `evento_id`; solicitudes de IA (202, vencimiento, «Reintentar», respuestas tardías); límite por usuario; estado de los eventos sin datos |
| svc-ia | 87 | Worker con reintentos por tipo de error, latido, 2 hilos, clasificador de prueba solo con `DEBUG=True`; núcleo de `comun` sin Django |
| comun | 137 | Librería de eventos: catálogo, sobre, productor, consumidor (reintentos, reclamo, fallidos, idempotencia, apagado), `estado`, `reprocesar` y `descartar` |
| infra | 12 | Clasificación de la matriz (filas de servicio externo) |
| **Total** | **1124** | Al cierre de la Entrega 3 eran 789 |

Los eventos se prueban con Redis simulado (`fakeredis`) y MongoDB con `mongomock`: las pruebas no dependen de otros contenedores. Las pruebas de integración con los servicios reales son la prueba de punta a punta y la matriz.

## Prueba de punta a punta

[`infra/prueba_eventos.py`](../../infra/prueba_eventos.py) corre contra el sistema levantado, detiene y arranca contenedores, y limpia lo que crea. **Cada acción dispara eventos que afectan a otros servicios.**

| # | Escenario | Comprobaciones |
| --- | --- | --- |
| 1 | Registro por el gateway → `usuario_registrado` → bitácora de svc-contenido, sin datos personales | 2 de 2 |
| 2 | Apagado limpio del consumidor (SIGTERM): termina lo que tenía y se detiene con código 0 | 3 de 3 |
| 3 | Consumidor caído: lo publicado mientras tanto se procesa al volver | 3 de 3 |
| 4 | Fallido y reproceso: MongoDB detenido → reintentos → stream de fallidos → `reprocesar` → bitácora | 7 de 7 |
| 5 | Flujo de negocio con una correlación: registro → correo → verificación → pedido → pago, cada paso en la bitácora | 12 de 12 |
| 6 | La correlación en los logs del gateway y de los servicios, sin tokens ni rutas con datos | 4 de 4 |
| 7 | Un correo que falla, llega a fallidos y se reprocesa con un token nuevo | 6 de 6 |
| 8 | **IA asíncrona:** pregunta → `svc-ia-worker` → agente real (Groq) → respuesta guardada en la conversación de MongoDB | 8 de 8 |
| 9 | **Agente detenido:** reintentos → `ia_respuesta_fallida` → «Reintentar» al volver el agente | 8 de 8 |
| 10 | **Concurrencia:** 5 preguntas a la vez, atendidas de 2 en 2, sin entregas de más | 4 de 4 |
| 11 | **Diagnóstico asíncrono:** sin modelo (`modelo_no_disponible`) y con el clasificador de prueba (marcado como prueba) | 5 de 5 |
| | **Total** | **62 de 62** |

**Nota del escenario 10:** dos de las cinco preguntas simultáneas recibieron un `RateLimitError` de Groq. Es el límite de tokens por minuto, no la cuota diaria. El worker las reintentó (eso es lo que comprueba el escenario) y las cinco terminaron con respuesta, sin fallidas. La cuota diaria no se agotó en ningún momento de la corrida.

## Postman

[`docs/postman/`](../postman/) se corrió completa con Newman 6.2.1, después de `cargar_datos_demo`, `cargar_usuarios_demo` y `reiniciar_limites`:

| Concepto | Total | Fallas |
| --- | --- | --- |
| Peticiones | 159 | 0 |
| Scripts de prueba | 148 | 0 |
| Scripts previos | 8 | 0 |
| Aserciones | 258 | 0 |

**Carpetas de la Entrega 4:**

- **svc-contenido:**
  - «Conversaciones»: preguntar por eventos con 202, 409 mientras responde, estado de la solicitud, solicitud de otro usuario con 404;
  - «Diagnósticos»: solicitar por eventos y su estado;
  - «Bitácora»: filtros por usuario, correlación y pedido; estado de los eventos.
- **svc-ia:** endpoints síncronos por compatibilidad.
- **Seguridad:** exceso de preguntas a la IA con 429.
- **Panel:** resumen, detalle de usuario y filtros nuevos, con 401 y 403.

## Matriz de accesos

[`matriz-accesos.md`](matriz-accesos.md): 8 actores contra los endpoints de los cuatro servicios, a través del gateway.

| Concepto | Casos |
| --- | --- |
| Combinaciones probadas | 186 |
| Permitidas (2xx esperado) | 39 |
| Denegadas (4xx esperado) | 147 |
| Coinciden con lo esperado | **186 de 186 (100 %)** |
| Permitido con servicio externo no disponible (✓*) | **0** |

**Filas de la Entrega 4:**

- de la IA: preguntar en la conversación propia (202) y en una ajena (404), estado de la solicitud propia y de otro usuario, solicitar un diagnóstico (202) y el exceso de solicitudes a la IA (429 al pasar el límite por usuario);
- del panel: resumen, ver un usuario, bitácora de un pedido y estado de los eventos.

**Ninguna fila quedó marcada como servicio externo:** el agente respondió en todas.

## Cómo repetirla

```powershell
docker compose exec svc-usuarios python manage.py reiniciar_limites
docker compose exec svc-contenido python manage.py reiniciar_limites
docker compose exec svc-tienda python manage.py cargar_datos_demo
docker compose exec svc-usuarios python manage.py cargar_usuarios_demo
newman run docs/postman/AgroIA-Web.postman_collection.json -e docs/postman/local.postman_environment.json --working-dir docs/postman --env-var "token_vencido=$(python infra/emitir_token.py --vencido)"
python infra/prueba_eventos.py          # unos 8 minutos; detiene y arranca contenedores
python infra/matriz_seguridad.py        # unos 2 minutos; va al final
docker compose exec <servicio> pytest   # en cada servicio; comun: docker compose exec -w /comun svc-tienda pytest
```

Revisa primero la cuota de Groq con una pregunta. Si el agente responde 503 por la cuota, la matriz marca esas filas como servicio externo, y conviene repetir la corrida otro día.
