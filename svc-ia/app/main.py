"""Microservicio FastAPI de AgroIA-Web: agente conversacional y diagnóstico por imagen.

En la fase 0 solo expone GET /salud/. En la fase 3 se copia el agente del repo AgroIA
(app/agent.py, app/memory.py, app/prompt.py) y se agregan /agente/preguntar/,
/diagnostico/ y /solicitudes/<id>/. Este servicio no guarda nada: los resultados los
guarda svc-contenido.
"""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="AgroIA-Web · svc-ia",
    description="Agente conversacional y clasificación de imágenes de aguacate.",
    version="0.1.0",
    docs_url="/api/docs/",
    openapi_url="/api/schema/",
    redoc_url=None,
)


class Salud(BaseModel):
    estado: str


@app.get("/salud/", response_model=Salud, summary="Estado del servicio")
def salud() -> Salud:
    """Comprobación de estado para Docker y el gateway. No requiere autenticación."""
    return Salud(estado="ok")
