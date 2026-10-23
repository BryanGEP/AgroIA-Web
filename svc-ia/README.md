# svc-ia

Responde preguntas con el agente AgroIA y clasifica imágenes de aguacate (`sano`, `rona`, `antracnosis`). Es un **adaptador** en FastAPI: expone el contrato de AgroIA-Web y lo traduce a la API del contenedor `agente`, que se construye desde el repo [BryanGEP/AgroIA](https://github.com/BryanGEP/AgroIA) (carpeta `svc-agente`, rama `main`). No copia el código del agente: el agente sigue evolucionando en su repo.

- **Puerto local:** 8004 (dentro de Docker escucha en el 8000 y se llama `http://svc-ia:8000`).
- **Datos:** ninguno. No guarda imágenes ni resultados; eso lo hace `svc-contenido`.
- **Documentación de la API:** http://localhost:8004/api/docs/ (Swagger de FastAPI, botón **Authorize**)
- **Salud:** `GET http://localhost:8004/salud/` → `{"estado": "ok"}`

Todas las respuestas de negocio traen `id` y `estado` (hoy siempre `"listo"`), para volverse asíncronas en la Entrega 4. En la Entrega 2 svc-ia y svc-contenido no se llaman entre sí: el gateway llama a svc-ia y después guarda el resultado en svc-contenido.

```
web ──► svc-ia ──HTTP──► agente (repo AgroIA) ──► Groq (LLM)
   └──► svc-contenido (guarda conversación o diagnóstico)
```

## Endpoints × rol

| Método | Ruta | Cliente | Admin | Sin token | Sin rol |
| --- | --- | --- | --- | --- | --- |
| POST | `/agente/preguntar/` | ✓ | ✓ | 401 | 403 |
| POST | `/diagnostico/` | ✓ | ✓ | 401 | 403 |
| GET | `/solicitudes/<id>/` | ✓ (propias) | ✓ (todas) | 401 | 403 |
| GET | `/salud/`, `/api/docs/`, `/api/schema/` | público | público | — | — |

### `POST /agente/preguntar/`

```json
// recibe
{"pregunta": "¿Y cada cuánto lo aplico?",
 "historial": [{"rol": "usuario", "texto": "Tengo manchas negras en el fruto."},
               {"rol": "agente", "texto": "Parece antracnosis."}]}
// devuelve
{"id": "b61761e4…", "estado": "listo", "respuesta": "…", "fuentes": []}
```

**Traducción a la API del agente** (`app/agente.py`):

| AgroIA-Web | Agente (`POST /chat`) |
| --- | --- |
| `pregunta` + últimas **10** entradas de `historial` | `message`: el historial como bloque de contexto ("Productor: …", "AgroIA: …") seguido de "Pregunta actual: …" |
| — | `session_id`: uno **nuevo en cada petición**, para que el agente no acumule contexto propio (las conversaciones las guarda svc-contenido) |
| `respuesta` | `response` |
| `fuentes` | siempre `[]`: el agente todavía no tiene RAG |

Si el agente no responde, devuelve un error, una respuesta vacía o tarda más de `AGENTE_TIMEOUT` segundos: **503 `agente_no_disponible`**. Nunca se inventa una respuesta. El error se registra en el log sin el texto de la pregunta.

### `POST /diagnostico/`

`multipart/form-data` con `imagen` (JPG o PNG, máximo 5 MB, validada por sus primeros bytes, no por la extensión). Devuelve `{"id", "estado", "clase", "confianza", "probabilidades", "modelo_version"}`; `probabilidades` y `modelo_version` se agregaron al contrato porque svc-contenido los necesita para guardar el diagnóstico.

**Hoy no hay modelo de visión**: el modelo todavía no existe en ningún repo y llega en una entrega posterior. Después de validar la imagen, el endpoint responde **503 `modelo_no_disponible`** ("El modelo de diagnóstico se integrará en una entrega posterior."). No se generan resultados aleatorios ni falsos.

Para integrar el modelo, implementar una clase que cumpla el protocolo `Clasificador` de `app/vision.py` (`modelo_version` y `clasificar(imagen: bytes) -> ResultadoClasificacion`) y devolverla desde `obtener_clasificador()`.

### `GET /solicitudes/<id>/`

Devuelve `{"id", "estado": "listo", "tipo": "agente" | "diagnostico", "creada_en", "resultado"}` al dueño o a un administrador; para cualquier otro, 404. Las solicitudes se guardan **en la memoria del proceso** (las últimas 1000) y se pierden al reiniciar el contenedor. En la Entrega 4 pasarán a Redis, cuando svc-ia responda `pendiente` y publique el resultado como evento. Las peticiones que fallan (503) no generan solicitud.

## Autenticación

svc-ia no usa `comun` (sus clases son de DRF): valida el JWT con PyJWT en `app/seguridad.py`, con las mismas reglas:

- RS256 con la llave pública (`JWT_PUBLIC_KEY_PATH`), emisor `agroia-usuarios`, `exp` obligatorio, `token_type: "access"` y `user_id` entero.
- Sin token o token inválido: **401**. Token sin rol válido: **403**.
- `AUTH_ACTIVA=False` solo apaga la revisión de rol; el token sigue siendo obligatorio. Solo se acepta con `DEBUG=True` (compose lo toma de `DJANGO_DEBUG`); si no, el servicio no arranca. Con `AUTH_ACTIVA=True` y sin la llave pública, tampoco arranca.
- Mismo formato de errores que los servicios Django. Los errores de validación responden **400** con `campos` (FastAPI usaría 422).

Tokens de desarrollo: `python infra/emitir_token.py --usuario-id 10 --rol cliente` (ver el [README raíz](../README.md#tokens-de-desarrollo)).

## Variables de entorno

| Variable | Uso |
| --- | --- |
| `AUTH_ACTIVA` | Revisión de rol (`True` por defecto) |
| `DEBUG` | Permite `AUTH_ACTIVA=False`; compose lo toma de `DJANGO_DEBUG` |
| `JWT_PUBLIC_KEY_PATH` | Llave pública para validar el JWT |
| `URL_AGENTE` | Dirección del agente (`http://agente:8000`) |
| `AGENTE_TIMEOUT` | Segundos máximos de espera por una respuesta del agente (`30`) |

Las variables del LLM (`GROQ_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL`) ya no son de svc-ia: van al contenedor `agente`.

## El contenedor `agente`

- Se construye desde `https://github.com/BryanGEP/AgroIA.git#main:svc-agente`. Para tomar cambios nuevos del agente: `docker compose build --no-cache agente`.
- Solo está en la red interna; se publica en `127.0.0.1:8005` para probarlo (`GET /health`, `POST /chat` y su propio chat web en `/`).
- Su API: `POST /chat` `{"message", "session_id"?}` → `{"response", "session_id"}`; 503 si el LLM falla.

### Pendientes en el repo AgroIA (antes de la Entrega 5)

- **El agente acumula sesiones sin borrarlas.** Guarda memoria por `session_id` en el proceso y nunca la limpia; como svc-ia usa un `session_id` nuevo por petición, esa memoria crece mientras el contenedor siga vivo (reiniciarlo la vacía). Se resolverá en el repo AgroIA, idealmente con un `/chat` que acepte el historial y no guarde sesiones; entonces solo cambia `construir_mensaje` en `app/agente.py`.
- **Dependencias sin versión fija** (`fastapi>=0.115`, `langchain>=0.3`…): cada construcción puede instalar versiones distintas. El 22/10/2026 se instalaron fastapi 0.161.1, starlette 1.9.0, uvicorn 0.54.0, pydantic 2.14.1, langchain 1.4.7, langchain-core 1.7.0 y langchain-groq 1.1.3.

## Pruebas y estilo

```bash
docker compose exec svc-ia pytest
docker compose exec svc-ia ruff check .
docker compose exec svc-ia ruff format --check .
```

El agente se simula con `httpx.MockTransport` (respuesta correcta, error, timeout y agente caído) y el clasificador con uno falso inyectado con `dependency_overrides`; las pruebas no llaman a Groq ni a otros contenedores. Siempre corren con `AUTH_ACTIVA=True` y un par de llaves generado al vuelo (`conftest.py`, `tests/tokens.py`).

### Entorno virtual local (opcional)

Sirve para el editor y para correr ruff y pytest sin Docker. svc-ia tiene su propio venv. En Windows, con PowerShell y Python 3.12:

```powershell
cd svc-ia
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest
```

Si PowerShell no deja ejecutar `Activate.ps1`, corre una vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
