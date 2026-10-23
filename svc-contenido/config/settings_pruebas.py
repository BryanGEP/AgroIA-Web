"""Configuración para pytest.

Completa con valores de prueba las variables de entorno que falten, para poder
correr pytest en el venv local sin un .env. En Docker las variables ya existen y
se respetan. Estos valores no son secretos ni sirven fuera de las pruebas.

Las pruebas siempre corren con AUTH_ACTIVA=True, con un par de llaves RSA generado al
vuelo y con MongoDB simulado por mongomock (ver conftest.py).
"""

import os
import tempfile
from pathlib import Path

from agroia_comun.pruebas import generar_par_de_llaves

LLAVE_PRIVADA_PRUEBAS, _LLAVE_PUBLICA_PRUEBAS = generar_par_de_llaves()
_RUTA_LLAVE_PUBLICA = Path(tempfile.mkdtemp(prefix="agroia-pruebas-")) / "publica.pem"
_RUTA_LLAVE_PUBLICA.write_text(_LLAVE_PUBLICA_PRUEBAS, encoding="utf-8")

_VALORES_DE_PRUEBA = {
    "DJANGO_SECRET_KEY": "clave-solo-para-pruebas-no-es-secreta",
    "MONGO_URL": "mongodb://localhost:27017/contenido",
}

for _nombre, _valor in _VALORES_DE_PRUEBA.items():
    os.environ.setdefault(_nombre, _valor)

# Estas se fuerzan aunque el .env diga otra cosa.
os.environ["AUTH_ACTIVA"] = "True"
os.environ["JWT_PUBLIC_KEY_PATH"] = str(_RUTA_LLAVE_PUBLICA)

from config.settings import *  # noqa: E402, F403

# Las imágenes subidas en pruebas van a una carpeta temporal, no a svc-contenido/media/.
MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="agroia-media-"))
