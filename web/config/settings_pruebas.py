"""Configuración para pytest.

Completa con valores de prueba las variables de entorno que falten, para poder
correr pytest en el venv local sin un .env. En Docker las variables ya existen y
se respetan. Estos valores no son secretos ni sirven fuera de las pruebas.
"""

import os
import tempfile
from pathlib import Path

from agroia_comun.pruebas import generar_par_de_llaves

# Par de llaves al vuelo: el proxy valida tokens con la pública (ver conftest.py).
LLAVE_PRIVADA_PRUEBAS, LLAVE_PUBLICA_PRUEBAS = generar_par_de_llaves()
_RUTA_LLAVE_PUBLICA = Path(tempfile.mkdtemp(prefix="agroia-web-")) / "publica.pem"
_RUTA_LLAVE_PUBLICA.write_text(LLAVE_PUBLICA_PRUEBAS, encoding="utf-8")

_VALORES_DE_PRUEBA = {
    "DJANGO_SECRET_KEY": "clave-solo-para-pruebas-no-es-secreta-ni-sirve-fuera-de-pytest-7Qx",
    "POSTGRES_DB": "web_db",
    "POSTGRES_USER": "web",
    "POSTGRES_PASSWORD": "solo-para-pruebas",
    "POSTGRES_HOST": "localhost",
}

for _nombre, _valor in _VALORES_DE_PRUEBA.items():
    os.environ.setdefault(_nombre, _valor)

os.environ["JWT_PUBLIC_KEY_PATH"] = str(_RUTA_LLAVE_PUBLICA)
os.environ["JWT_ISSUER"] = "agroia-usuarios"
os.environ["CORS_ALLOWED_ORIGINS"] = "http://app.agroia.test"

from config.settings import *  # noqa: E402, F403
