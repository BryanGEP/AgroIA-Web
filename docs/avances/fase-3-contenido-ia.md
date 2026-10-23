# Fase 3 · API de contenido e IA

**Fecha:** 22 de octubre de 2026 · **Entregable:** Entrega 2 · **Responsable:** Bryan Gael Esquivel Pérez

## Resumen

Se construyó la API de `svc-contenido` (conversaciones con el agente, historial de diagnósticos y bitácora, en MongoDB) y se convirtió `svc-ia` en un adaptador que traduce el contrato de AgroIA-Web a la API del agente del repo AgroIA, que ahora corre en su propio contenedor construido desde GitHub. Una pregunta real viajó por svc-ia hasta el agente y Groq, y volvió con respuesta. El diagnóstico por imagen valida la imagen y responde 503 porque el modelo de visión todavía no existe. Se verificó todo dentro de Docker el mismo día: 69 pruebas en `svc-contenido` y 55 en `svc-ia`.

## Qué se construyó

### svc-contenido (MongoDB con pymongo)

| Pieza | Contenido |
| --- | --- |
| Autenticación y errores | El mismo bloque de `comun` que svc-tienda: JWT RS256, `IsAuthenticated` por defecto, permisos por rol, formato `{"error", "detalle"}` y esquema Bearer en Swagger. |
| `config/mongo.py` | Conexión perezosa, `ahora()` con precisión de milisegundos (la de MongoDB) y `object_id_o_404()`. |
| `config/paginacion.py` | `ConsultaMongo`: adapta una consulta de MongoDB al `PageNumberPagination` de DRF; la respuesta tiene el mismo formato que en svc-tienda. |
| `apps/conversaciones` | Crear, listar las propias (las más recientes primero, sin mensajes), ver con mensajes, borrar y `POST /conversaciones/<id>/mensajes/` (rol `usuario` o `agente`, `fuentes` solo para el agente). Límite de 200 mensajes. |
| `apps/diagnosticos` | `POST` en multipart con la imagen (JPG, PNG o WebP, máximo 5 MB, verificada con Pillow, guardada con `default_storage`) y el resultado (`clase`, `confianza`, `probabilidades`, `modelo_version`); listar y ver. |
| `apps/bitacora` | `GET` con filtros `tipo`, `desde` y `hasta`; `POST` manual. Solo administrador. |
| Comando `crear_indices` | Crea los índices de la definición técnica; se puede repetir y el contenedor lo corre al arrancar. |

### svc-ia (adaptador en FastAPI)

| Archivo | Contenido |
| --- | --- |
| `app/seguridad.py` | Validación del JWT RS256 con PyJWT (svc-ia no usa `comun`): emisor, vencimiento, `token_type: "access"`, `user_id`, rol válido, `AUTH_ACTIVA` y el candado con `DEBUG`. |
| `app/errores.py` | El mismo formato de errores; la validación responde 400 con `campos` en lugar del 422 de FastAPI. |
| `app/agente.py` | Cliente httpx del agente con `URL_AGENTE` y `AGENTE_TIMEOUT`; traducción del contrato aislada en `construir_mensaje`. |
| `app/solicitudes.py` | Registro en memoria de las últimas 1000 solicitudes para `GET /solicitudes/<id>/` (dueño o administrador). |
| `app/vision.py` | Protocolo `Clasificador` con `clasificar(imagen)` y `obtener_clasificador()`, que hoy devuelve `None`. |
| `app/main.py` | `POST /agente/preguntar/`, `POST /diagnostico/`, `GET /solicitudes/<id>/` y `GET /salud/`, con ejemplos en Swagger. |

### Contenedor `agente`

Nuevo servicio en `docker-compose.yml`, construido desde `https://github.com/BryanGEP/AgroIA.git#main:svc-agente`, sin copiar su código. Está solo en la red interna y se publica en `127.0.0.1:8005` para pruebas, con healthcheck a `/health`. Las variables del LLM (`GROQ_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL`) pasaron de svc-ia a este contenedor.

### Documentación

- Swagger con ejemplos y esquema Bearer en ambos servicios.
- Colección de Postman: carpetas `svc-contenido` (17 peticiones) y `svc-ia` (6 peticiones, con su salud), y variables `base_contenido`, `base_ia`, `conversacion_id`, `diagnostico_id` y `solicitud_id`.
- README de svc-contenido y svc-ia con matriz endpoints × rol, variables y cómo probar; README raíz con el contenedor `agente` y la llave de Groq propia de cada integrante.
- `docs/definicion-tecnica.md`: servicio `agente`, contratos de contenido e IA precisados, `probabilidades` y `modelo_version` en `/diagnostico/`, estado del diagnóstico, códigos de error nuevos, variables `URL_AGENTE` y `AGENTE_TIMEOUT`, decisión de svc-ia revisada y modelo de `diagnosticos` con `imagen` en lugar de `imagen_url`.

## Cómo se traduce el contrato al agente

| AgroIA-Web (`svc-ia`) | Agente (`POST /chat`) |
| --- | --- |
| `pregunta` + últimas 10 entradas de `historial` | `message`: el historial como bloque de contexto ("Productor: …", "AgroIA: …") seguido de "Pregunta actual: …" |
| — | `session_id` nuevo en cada petición |
| `{"id", "estado": "listo", "respuesta", "fuentes"}` | `response`; `fuentes` siempre `[]` (el agente no tiene RAG) |
| 503 `agente_no_disponible` | sin conexión, timeout, respuesta no 2xx, no JSON o vacía |

## Decisiones técnicas

| Decisión | Por qué |
| --- | --- |
| svc-ia como adaptador y el agente en su propio contenedor desde GitHub | El agente sigue evolucionando en el repo AgroIA; copiar su código crearía dos versiones que se desincronizan. Revisa la decisión anterior ("svc-ia copia el agente"). |
| `session_id` nuevo por petición y el historial como contexto | El agente no recibe historial y guarda memoria propia por sesión; las conversaciones son de svc-contenido y svc-ia no guarda nada. La traducción vive en una sola función para cambiarla cuando el agente acepte historial. |
| svc-contenido y svc-ia no se llaman entre sí | En la Entrega 2 orquesta el gateway; en la Entrega 4, eventos por Redis. |
| Conversaciones privadas, también para el administrador (404) | Así lo dice el contrato ("dueño"). Los diagnósticos sí los lista y ve el administrador, y la bitácora es solo suya. |
| ObjectId mal formado, inexistente o ajeno → 404 | No se revela si el recurso existe. |
| Límite de 200 mensajes dentro del mismo `update` de MongoDB | Se respeta aunque lleguen dos mensajes al mismo tiempo; al llegar al límite, 409 `conversacion_llena`. |
| En diagnósticos se guarda el nombre del archivo, no la URL | La URL se calcula al responder; así sigue funcionando cuando se pase a Cloud Storage (Entrega 5). |
| Validación del resultado del diagnóstico (tres clases, suma 1, `confianza` = probabilidad de `clase`) | Evita guardar resultados incoherentes en el historial. |
| `probabilidades` y `modelo_version` en la respuesta de `/diagnostico/` | svc-contenido los necesita para guardar el diagnóstico; se actualizó el contrato. |
| Sin modelo: 503 `modelo_no_disponible`, nunca resultados falsos | El modelo de visión todavía no existe. La imagen se valida antes, así el endpoint ya está listo para el modelo. |
| svc-ia valida la imagen por sus primeros bytes (JPG/PNG), sin Pillow | No agrega una dependencia que el servicio todavía no necesita. svc-contenido sí usa Pillow porque guarda la imagen. |
| Solicitudes en memoria (últimas 1000) | En la Entrega 2 todo nace `listo`; en la Entrega 4 pasarán a Redis. Se pierden al reiniciar el contenedor. |
| Agente simulado con `httpx.MockTransport` | Viene con httpx; no hizo falta agregar respx. |
| `AGENTE_TIMEOUT` de 30 segundos | El modelo `gpt-oss-120b` puede tardar varios segundos. |
| `DEBUG` de svc-ia tomado de `DJANGO_DEBUG` | Una sola variable en el `.env` para el candado de `AUTH_ACTIVA`. |

## Verificación

Se hizo el 22 de octubre de 2026 dentro de Docker, con las imágenes reconstruidas.

| Prueba | Resultado |
| --- | --- |
| `docker compose config` | Sin errores |
| Contenedor `agente` desde GitHub | Se construyó desde `main:svc-agente`, quedó `healthy` y respondió `{"status":"ok"}` en `/health` |
| Llave de Groq | El contenedor `agente` recibe `GROQ_API_KEY` (se comprobó solo su longitud, sin leer el `.env`); svc-ia ya no recibe variables del LLM |
| Pregunta real por svc-ia | 200 en 1.4 s con respuesta del agente; con el historial de antracnosis, la respuesta habló de la frecuencia de aplicación del fungicida, es decir, usó el contexto. `GET /solicitudes/<id>/`: 200 para el dueño y el administrador, 404 para otro usuario |
| Agente detenido | `POST /agente/preguntar/` respondió 503 `agente_no_disponible` y svc-ia siguió sano |
| `POST /diagnostico/` | PNG válido: 503 `modelo_no_disponible`; GIF: 400 con `campos.imagen` |
| Flujo de svc-contenido | Conversación creada, mensajes de usuario y agente con fuentes, listado propio, 404 para otro cliente, para el administrador y para un id inválido, y borrado. Diagnóstico guardado con la imagen servida en `/media/` (200, `image/png`), visible para el dueño y el administrador y 404 para otro; confianza incoherente → 400. Bitácora: registrar y filtrar como administrador, 403 como cliente |
| Índices | `crear_indices` corrió al arrancar el contenedor y creó los cuatro índices |
| `pytest` en svc-contenido | 69 pruebas pasan: conversaciones 32 (servicios 10, endpoints 22), índices 1, diagnósticos 22, bitácora 10 y salud 4 |
| `pytest` en svc-ia | 55 pruebas pasan: seguridad 15, agente 20 (respuesta correcta, historial, 503 del agente, error 500, timeout, sin conexión, validación), diagnóstico 11 (sin clasificador 503, clasificador de prueba, formatos, tamaño), solicitudes 5 y salud 4 |
| `ruff check` y `ruff format --check` | Pasan en ambos servicios |
| Esquema OpenAPI | svc-contenido: `spectacular --validate --fail-on-warn` sin advertencias. svc-ia: esquema Bearer `jwtAuth` y sin respuestas 422. `/api/docs/` responde 200 en ambos |
| Colección de Postman | Todas las peticiones (svc-tienda, svc-contenido y svc-ia) devolvieron el código esperado |
| Sin regresiones | `comun` 26, svc-tienda 144, web 4 y svc-usuarios 4 pruebas siguen pasando |
| `git status` | No aparecen `.env`, llaves ni imágenes subidas |

## Problemas encontrados

| Problema | Solución |
| --- | --- |
| Docker Desktop no estaba corriendo al empezar la verificación | Se abrió Docker Desktop. Mientras arrancaba, las pruebas de svc-contenido (mongomock) y svc-ia se corrieron en entornos locales temporales. |
| Dos pruebas fallaron porque MongoDB guarda las fechas con precisión de milisegundos | `mongo.ahora()` trunca a milisegundos, así el documento devuelto coincide con el guardado; la prueba de orden ya no depende de la velocidad de la máquina. |
| django-filter necesita un queryset para documentar los filtros y los ViewSets de MongoDB no tienen | `filter_backends = []` en esos ViewSets; los filtros se validan con serializers y se aplican en `servicios.py`. |
| ruff ordenaba como externo el `from conftest import ...` de las pruebas de svc-ia | Los ayudantes de tokens se movieron a `tests/tokens.py`, igual que en svc-tienda. |
| El agente construido desde `main` instaló versiones distintas a las del venv local (fastapi 0.161.1, langchain 1.4.7) | Su `requirements.txt` no fija versiones. Se documentó como pendiente del repo AgroIA. |

## Commits y Pull Requests

Rama `feat/fase-3-contenido-ia` → `develop`. Los commits los hace el integrante a mano; esta sección se completa con los hashes al hacer el PR.

## Pendientes y siguiente paso

- **En el repo AgroIA, antes de la Entrega 5:** el agente acumula sesiones en memoria sin borrarlas; con un `session_id` por petición, esa memoria crece mientras el contenedor siga vivo (reiniciarlo la vacía). Conviene que `/chat` acepte el historial y no guarde sesiones, y fijar las versiones de su `requirements.txt`.
- **Contrato:** avisar al equipo de los cambios: `probabilidades` y `modelo_version` en `/diagnostico/`, conversaciones privadas también para el administrador, `fuentes` solo en mensajes del agente, `imagen` en lugar de `imagen_url` en el documento de diagnósticos y tres códigos de error nuevos.
- **Modelo de visión:** implementar un `Clasificador` y devolverlo desde `obtener_clasificador()`.
- Las solicitudes de svc-ia y la bitácora se llenarán con eventos por Redis en la Entrega 4.
- **Siguiente:** pantallas de chat y diagnóstico en `web`, con el gateway orquestando svc-ia y svc-contenido.
