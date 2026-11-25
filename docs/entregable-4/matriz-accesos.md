# Matriz de accesos

Generada por [`infra/matriz_seguridad.py`](../../infra/matriz_seguridad.py) el 2026-11-24 19:48 contra el sistema levantado con `docker compose`, a través del gateway (`http://127.0.0.1:8000`). Duración: 109 s.

Cómo leerla: cada caso es una petición real. **Esperado** sale de las reglas de [`docs/contrato-identidad.md`](../contrato-identidad.md); **coincide** exige el mismo código HTTP y, en las denegadas, el mismo código de error del cuerpo. La matriz prueba el control de acceso, no la disponibilidad del agente: un 503 `agente_no_disponible` o `modelo_no_disponible` donde se esperaba acceso permitido cuenta como coincidencia, marcado como «permitido (servicio externo no disponible)» (✓*).

## Resumen

| Concepto | Casos |
| --- | --- |
| Combinaciones probadas | 154 |
| Permitidas (2xx esperado) | 35 |
| Denegadas (4xx esperado) | 119 |
| Coinciden con lo esperado | **154 de 154 (100 %)** |
| De ellas, permitido (servicio externo no disponible) | 3 |

## Matriz

Código obtenido por actor; ✓ coincide con lo esperado, ✓* permitido (servicio externo no disponible), ✗ no coincide, — no aplica.

| Endpoint | Anónimo | Cliente sin verificar | Cliente verificado | Administrador | Token vencido | Token de otra llave | Refresh en blacklist | Origen no permitido |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Iniciar sesión | — | 200 ✓ | 200 ✓ | 200 ✓ | — | — | — | 403 ✓ |
| Renovar el token | — | — | 200 ✓ | — | — | — | 401 ✓ | — |
| Catálogo (público) | 200 ✓ | 200 ✓ | 200 ✓ | 200 ✓ | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Crear producto (administrador) | 401 ✓ | 403 ✓ | 403 ✓ | 201 ✓ | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Ver carrito | 401 ✓ | 200 ✓ | 200 ✓ | 200 ✓ | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Crear pedido | 401 ✓ | 403 ✓ | 201 ✓ | 403 ✓ | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Cambiar estado de un pedido (administrador) | 401 ✓ | 403 ✓ | 403 ✓ | 200 ✓ | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Listar usuarios (administrador) | 401 ✓ | 403 ✓ | 403 ✓ | 200 ✓ | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Cambiar rol (administrador) | 401 ✓ | 403 ✓ | 403 ✓ | 200 ✓ | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Pregunta al agente | 401 ✓ | 503 ✓* | 503 ✓* | 503 ✓* | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Conversación propia | 401 ✓ | 200 ✓ | 200 ✓ | 200 ✓ | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Conversación ajena | 401 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Foto de diagnóstico propia | 401 ✓ | 200 ✓ | 200 ✓ | 200 ✓ | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Foto de diagnóstico ajena | 401 ✓ | 404 ✓ | 404 ✓ | 200 ✓ | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Preguntar en la conversación propia (IA por eventos) | 401 ✓ | 202 ✓ | 202 ✓ | 202 ✓ | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Preguntar en una conversación ajena | 401 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Estado de la solicitud propia | 401 ✓ | 200 ✓ | 200 ✓ | 200 ✓ | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Estado de la solicitud de otro usuario | 401 ✓ | 404 ✓ | 404 ✓ | 404 ✓ | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Solicitar un diagnóstico (IA por eventos) | 401 ✓ | 202 ✓ | 202 ✓ | 202 ✓ | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Exceso de solicitudes a la IA (límite por usuario) | 401 ✓ | 429 ✓ | 429 ✓ | 429 ✓ | 401 ✓ | 401 ✓ | 401 ✓ | 403 ✓ |
| Exceso de logins (10 por minuto por IP) | 429 ✓ | — | — | — | — | — | — | — |
| Exceso de recuperaciones (3 por hora por IP) | 429 ✓ | — | — | — | — | — | — | — |

## Detalle

### Iniciar sesión

`POST /api/usuarios/auth/login/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Cliente sin verificar | 200 | 200 | — | sí |  |
| Cliente verificado | 200 | 200 | — | sí |  |
| Administrador | 200 | 200 | — | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Renovar el token

`POST /api/usuarios/auth/token/renovar/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Cliente verificado | 200 | 200 | — | sí | refresh vigente; devuelve un par nuevo |
| Refresh en blacklist | 401 `refresh_invalido` | 401 | `refresh_invalido` | sí | el refresh ya usado, en la blacklist |

### Catálogo (público)

`GET /api/tienda/productos/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 200 | 200 | — | sí |  |
| Cliente sin verificar | 200 | 200 | — | sí |  |
| Cliente verificado | 200 | 200 | — | sí |  |
| Administrador | 200 | 200 | — | sí |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Crear producto (administrador)

`POST /api/tienda/productos/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `no_autenticado` | 401 | `no_autenticado` | sí |  |
| Cliente sin verificar | 403 `sin_permiso` | 403 | `sin_permiso` | sí |  |
| Cliente verificado | 403 `sin_permiso` | 403 | `sin_permiso` | sí |  |
| Administrador | 201 | 201 | — | sí |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Ver carrito

`GET /api/tienda/carrito/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `no_autenticado` | 401 | `no_autenticado` | sí |  |
| Cliente sin verificar | 200 | 200 | — | sí |  |
| Cliente verificado | 200 | 200 | — | sí |  |
| Administrador | 200 | 200 | — | sí |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Crear pedido

`POST /api/tienda/pedidos/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `no_autenticado` | 401 | `no_autenticado` | sí |  |
| Cliente sin verificar | 403 `email_no_verificado` | 403 | `email_no_verificado` | sí |  |
| Cliente verificado | 201 | 201 | — | sí |  |
| Administrador | 403 `sin_permiso` | 403 | `sin_permiso` | sí |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Cambiar estado de un pedido (administrador)

`PATCH /api/tienda/pedidos/<id>/estado/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `no_autenticado` | 401 | `no_autenticado` | sí |  |
| Cliente sin verificar | 403 `sin_permiso` | 403 | `sin_permiso` | sí |  |
| Cliente verificado | 403 `sin_permiso` | 403 | `sin_permiso` | sí |  |
| Administrador | 200 | 200 | — | sí |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Listar usuarios (administrador)

`GET /api/usuarios/usuarios/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `no_autenticado` | 401 | `no_autenticado` | sí |  |
| Cliente sin verificar | 403 `sin_permiso` | 403 | `sin_permiso` | sí |  |
| Cliente verificado | 403 `sin_permiso` | 403 | `sin_permiso` | sí |  |
| Administrador | 200 | 200 | — | sí |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Cambiar rol (administrador)

`PATCH /api/usuarios/usuarios/<id>/rol/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `no_autenticado` | 401 | `no_autenticado` | sí |  |
| Cliente sin verificar | 403 `sin_permiso` | 403 | `sin_permiso` | sí |  |
| Cliente verificado | 403 `sin_permiso` | 403 | `sin_permiso` | sí |  |
| Administrador | 200 | 200 | — | sí |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Pregunta al agente

`POST /api/ia/agente/preguntar/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `no_autenticado` | 401 | `no_autenticado` | sí |  |
| Cliente sin verificar | 200 | 503 | `agente_no_disponible` | sí, permitido (servicio externo no disponible) |  |
| Cliente verificado | 200 | 503 | `agente_no_disponible` | sí, permitido (servicio externo no disponible) |  |
| Administrador | 200 | 503 | `agente_no_disponible` | sí, permitido (servicio externo no disponible) |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Conversación propia

`GET /api/contenido/conversaciones/<propia>/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `no_autenticado` | 401 | `no_autenticado` | sí |  |
| Cliente sin verificar | 200 | 200 | — | sí |  |
| Cliente verificado | 200 | 200 | — | sí |  |
| Administrador | 200 | 200 | — | sí |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Conversación ajena

`GET /api/contenido/conversaciones/<ajena>/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `no_autenticado` | 401 | `no_autenticado` | sí |  |
| Cliente sin verificar | 404 `no_encontrado` | 404 | `no_encontrado` | sí |  |
| Cliente verificado | 404 `no_encontrado` | 404 | `no_encontrado` | sí |  |
| Administrador | 404 `no_encontrado` | 404 | `no_encontrado` | sí |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Foto de diagnóstico propia

`GET /api/contenido/diagnosticos/<propio>/imagen/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `no_autenticado` | 401 | `no_autenticado` | sí |  |
| Cliente sin verificar | 200 | 200 | — | sí |  |
| Cliente verificado | 200 | 200 | — | sí |  |
| Administrador | 200 | 200 | — | sí |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Foto de diagnóstico ajena

`GET /api/contenido/diagnosticos/<ajeno>/imagen/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `no_autenticado` | 401 | `no_autenticado` | sí |  |
| Cliente sin verificar | 404 `no_encontrado` | 404 | `no_encontrado` | sí |  |
| Cliente verificado | 404 `no_encontrado` | 404 | `no_encontrado` | sí |  |
| Administrador | 200 | 200 | — | sí |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Preguntar en la conversación propia (IA por eventos)

`POST /api/contenido/conversaciones/<propia>/preguntar/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `no_autenticado` | 401 | `no_autenticado` | sí |  |
| Cliente sin verificar | 202 | 202 | — | sí |  |
| Cliente verificado | 202 | 202 | — | sí |  |
| Administrador | 202 | 202 | — | sí |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Preguntar en una conversación ajena

`POST /api/contenido/conversaciones/<ajena>/preguntar/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `no_autenticado` | 401 | `no_autenticado` | sí |  |
| Cliente sin verificar | 404 `no_encontrado` | 404 | `no_encontrado` | sí |  |
| Cliente verificado | 404 `no_encontrado` | 404 | `no_encontrado` | sí |  |
| Administrador | 404 `no_encontrado` | 404 | `no_encontrado` | sí |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Estado de la solicitud propia

`GET /api/contenido/conversaciones/<propia>/solicitud/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `no_autenticado` | 401 | `no_autenticado` | sí |  |
| Cliente sin verificar | 200 | 200 | — | sí |  |
| Cliente verificado | 200 | 200 | — | sí |  |
| Administrador | 200 | 200 | — | sí |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Estado de la solicitud de otro usuario

`GET /api/contenido/conversaciones/<ajena>/solicitud/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `no_autenticado` | 401 | `no_autenticado` | sí |  |
| Cliente sin verificar | 404 `no_encontrado` | 404 | `no_encontrado` | sí |  |
| Cliente verificado | 404 `no_encontrado` | 404 | `no_encontrado` | sí |  |
| Administrador | 404 `no_encontrado` | 404 | `no_encontrado` | sí |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Solicitar un diagnóstico (IA por eventos)

`POST /api/contenido/diagnosticos/solicitar/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `no_autenticado` | 401 | `no_autenticado` | sí |  |
| Cliente sin verificar | 202 | 202 | — | sí |  |
| Cliente verificado | 202 | 202 | — | sí |  |
| Administrador | 202 | 202 | — | sí |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Exceso de solicitudes a la IA (límite por usuario)

`POST /api/contenido/conversaciones/<propia>/preguntar/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `no_autenticado` | 401 | `no_autenticado` | sí |  |
| Cliente sin verificar | 429 `demasiados_intentos` | 429 | `demasiados_intentos` | sí |  |
| Cliente verificado | 429 `demasiados_intentos` | 429 | `demasiados_intentos` | sí |  |
| Administrador | 429 `demasiados_intentos` | 429 | `demasiados_intentos` | sí |  |
| Token vencido | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Token de otra llave | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Refresh en blacklist | 401 `token_invalido` | 401 | `token_invalido` | sí |  |
| Origen no permitido | 403 `origen_no_permitido` | 403 | `origen_no_permitido` | sí |  |

### Login fallido con el mismo correo

`POST /api/usuarios/auth/login/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 401 `credenciales_invalidas` | 401 | `credenciales_invalidas` | sí | intentos 1 a 4: 401, 401, 401, 401 |
| Anónimo | 403 `cuenta_bloqueada_temporalmente` | 403 | `cuenta_bloqueada_temporalmente` | sí | intento 5: bloqueo de 15 minutos |

### Exceso de logins (10 por minuto por IP)

`POST /api/usuarios/auth/login/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 429 `demasiados_intentos` | 429 | `demasiados_intentos` | sí | 429 en el login 11 del minuto, Retry-After: 59 s |

### Exceso de recuperaciones (3 por hora por IP)

`POST /api/usuarios/auth/recuperar/`

| Actor | Esperado | Obtenido | Código de error | Coincide | Nota |
| --- | --- | --- | --- | --- | --- |
| Anónimo | 429 `demasiados_intentos` | 429 | `demasiados_intentos` | sí | aceptadas antes del 429 en esta corrida (200 genérico): 2, Retry-After: 3469 s |

## Qué capa decide

- **Gateway** (`web`, primera capa): sin token (401 `no_autenticado`), token vencido, de otra llave o un refresh usado como access (401 `token_invalido`), y un `Origin` ajeno (403 `origen_no_permitido`). Esas peticiones no llegan al servicio. Las rutas públicas (catálogo, login) también validan el token si viene.
- **Servicio** (segunda capa): el rol (403 `sin_permiso`), el correo verificado (403 `email_no_verificado`), los recursos de otro usuario (404 `no_encontrado`, para no revelar que existen), los límites de intentos de svc-usuarios y el de solicitudes a la IA por usuario de svc-contenido (429 `demasiados_intentos`).
- **Recursos propios y ajenos:** las conversaciones son privadas para todos, también para el administrador; los diagnósticos los puede ver el administrador.

## Limpieza

La matriz borra lo que creó: las conversaciones por la API, y el pedido, el producto y los diagnósticos (que la API no deja borrar) con el `manage.py` de su servicio. Resultado de esta corrida:

- Carrito del cliente restaurado: 0 de 0 productos.
- Conversaciones borradas por la API: 3 de 3.
- Borrado con `manage.py` de svc-tienda: pedido y producto de la matriz.
- Borrado con `manage.py` de svc-contenido: 6 diagnósticos y sus fotos.
- Borrado con `manage.py` de svc-usuarios: bloqueo del correo de prueba.
- Borrado con `manage.py` de svc-contenido: contadores del límite de la IA.
- Sesiones de la matriz cerradas (logout, 205): 3 de 3.
