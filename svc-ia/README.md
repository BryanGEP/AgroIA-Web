# svc-ia

Responde preguntas con el agente AgroIA y clasifica imágenes de aguacate (`sano`, `rona`, `antracnosis`). Hecho con FastAPI, reutilizando el agente del repo [AgroIA](https://github.com/BryanGEP/AgroIA).

- **Puerto local:** 8004 (dentro de Docker escucha en el 8000 y se llama `http://svc-ia:8000`).
- **Datos:** ninguno. No guarda imágenes ni resultados; eso lo hace `svc-contenido`.
- **Documentación de la API:** http://localhost:8004/api/docs/ (Swagger de FastAPI)
- **Salud:** `GET http://localhost:8004/salud/` → `{"estado": "ok"}`

Contratos en [`docs/definicion-tecnica.md`](../docs/definicion-tecnica.md). Todas las respuestas de negocio traen `id` y `estado` (hoy siempre `"listo"`), para volverse asíncronas en la Entrega 4.

## Compatibilidad con el agente de AgroIA

El esqueleto sigue la estructura de `svc-agente` para que en la fase 3 su código se copie sin rehacer nada:

| Aspecto | Valor |
| --- | --- |
| Python | 3.12 (`python:3.12-slim`, igual que el `Dockerfile` del agente) |
| Arranque | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Estructura | paquete `app/` (`main.py`, `config.py`) y `conftest.py` en la raíz del servicio |
| Configuración | `app/config.py` con un `dataclass` y `load_dotenv()`, como el agente |
| Pruebas | `TestClient` de FastAPI; el LLM siempre se simula con `unittest.mock` |

Versiones que usa hoy el agente (instaladas en su venv, con las que pasan sus pruebas):

| Paquete | Versión | En `requirements.txt` |
| --- | --- | --- |
| fastapi | 0.141.1 | desde la fase 0 |
| starlette | 1.7.0 (fijada aparte porque fastapi acepta un rango) | desde la fase 0 |
| uvicorn[standard] | 0.53.0 | desde la fase 0 |
| pydantic | 2.13.5 | desde la fase 0 |
| python-dotenv | 1.2.3 | desde la fase 0 |
| langchain | 1.4.2 | fase 3 |
| langchain-core | 1.6.4 | fase 3 |
| langchain-groq | 1.1.3 (trae groq 0.37.1) | fase 3 |
| pytest / httpx / httpx2 | 9.1.1 / 0.28.1 / 2.13.1 (`httpx2` lo usa el `TestClient` de starlette) | `requirements-dev.txt` |

Al copiar el agente en la fase 3 hay que ajustar:

- `GET /health` → `{"status": "ok"}` del agente se reemplaza por el `GET /salud/` → `{"estado": "ok"}` que ya existe aquí.
- Se quitan el `CORSMiddleware` abierto y el frontend estático montado en `/`: el navegador solo habla con `web`.
- `POST /chat` se adapta al contrato `POST /agente/preguntar/` (`{"pregunta", "historial"}` → `{"id", "estado", "respuesta", "fuentes"}`). La memoria del agente pasa a venir en `historial`, porque las conversaciones las guarda `svc-contenido`.
- Los cambios del agente se hacen primero en el repo AgroIA.

## Variables de entorno

Salen del `.env` de la raíz (ver [`.env.example`](../.env.example)). Son las mismas del agente, más las de autenticación.

| Variable | Uso |
| --- | --- |
| `AUTH_ACTIVA` | Activa la validación del JWT (`True` por defecto) |
| `JWT_PUBLIC_KEY_PATH` | Llave pública para validar el JWT con PyJWT (fase 4) |
| `GROQ_API_KEY` | Clave del proveedor del LLM (fase 3) |
| `LLM_PROVIDER`, `LLM_MODEL` | `groq` y `openai/gpt-oss-120b` (fase 3) |

## Pruebas y estilo

La forma oficial es dentro del contenedor:

```bash
docker compose exec svc-ia pytest
docker compose exec svc-ia ruff check .
docker compose exec svc-ia ruff format --check .
```

### Entorno virtual local (opcional)

Sirve para el editor y para correr ruff y pytest sin Docker; no para levantar el sistema. svc-ia tiene su propio venv porque sus dependencias no son las de los servicios Django. En Windows, con PowerShell y Python 3.12 instalado:

```powershell
cd svc-ia
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pytest
```

Si PowerShell no deja ejecutar `Activate.ps1`, corre una vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## Endpoints

| Método | Ruta | Acceso | Fase |
| --- | --- | --- | --- |
| GET | `/salud/` | público | 0 |
| GET | `/api/docs/`, `/api/schema/` | público | 0 |
| POST | `/agente/preguntar/` | autenticado | 3 |
| POST | `/diagnostico/` | autenticado | 3 |
| GET | `/solicitudes/<id>/` | autenticado | 3 |
