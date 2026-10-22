# Imagen de desarrollo de svc-ia (FastAPI). Mismo Python que el agente de AgroIA.
# El build context es la raíz del repo (ver docker-compose.yml). svc-ia no instala comun/:
# valida el JWT con PyJWT.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Incluye las dependencias de desarrollo para correr pytest y ruff dentro del contenedor.
COPY svc-ia/requirements.txt svc-ia/requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

COPY ruff.toml /ruff.toml
COPY svc-ia/ .

EXPOSE 8000

# --reload porque en desarrollo el código se monta como volumen.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
