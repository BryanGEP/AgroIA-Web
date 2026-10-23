# Imagen de desarrollo de web.
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
COPY web/requirements.txt web/requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

# Ejecutable de Tailwind CSS 4 con daisyUI 5 (tailwind-cli-extra), versión fija. Va en
# /opt/tailwind, fuera del volumen del código, para que el montaje no lo oculte.
ARG TAILWIND_EXTRA_VERSION=2.10.32
ENV TAILWIND_CLI_PATH=/opt/tailwind/tailwindcss-extra
RUN python -c "import os, platform, urllib.request; arquitectura = {'x86_64': 'x64', 'aarch64': 'arm64'}[platform.machine()]; os.makedirs('/opt/tailwind', exist_ok=True); url = 'https://github.com/dobicinaitis/tailwind-cli-extra/releases/download/v${TAILWIND_EXTRA_VERSION}/tailwindcss-extra-linux-' + arquitectura; urllib.request.urlretrieve(url, os.environ['TAILWIND_CLI_PATH']); os.chmod(os.environ['TAILWIND_CLI_PATH'], 0o755)"

COPY ruff.toml /ruff.toml
COPY web/ .

EXPOSE 8000

# Al arrancar: migraciones, compilar el CSS (static/css/agroia.css) y el servidor.
CMD ["sh", "-c", "python manage.py migrate && python manage.py tailwind build && python manage.py runserver 0.0.0.0:8000"]
