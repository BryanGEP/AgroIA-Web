# Imagen de desarrollo de svc-contenido.
# El build context es la raíz del repo (ver docker-compose.yml) para poder instalar comun/.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Paquete compartido, en modo editable: docker-compose.yml monta ./comun en /comun.
COPY comun /comun
RUN pip install -e /comun

# Incluye las dependencias de desarrollo para correr pytest y ruff dentro del contenedor.
COPY svc-contenido/requirements.txt svc-contenido/requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

COPY ruff.toml /ruff.toml
COPY svc-contenido/ .

EXPOSE 8000

# Sin base relacional no hay migraciones (ver config/settings.py).
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
