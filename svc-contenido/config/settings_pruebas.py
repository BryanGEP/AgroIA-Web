"""Configuración para pytest.

Completa con valores de prueba las variables de entorno que falten, para poder
correr pytest en el venv local sin un .env. En Docker las variables ya existen y
se respetan. Estos valores no son secretos ni sirven fuera de las pruebas.
"""

import os

_VALORES_DE_PRUEBA = {
    "DJANGO_SECRET_KEY": "clave-solo-para-pruebas-no-es-secreta",
    "MONGO_URL": "mongodb://localhost:27017/contenido",
}

for _nombre, _valor in _VALORES_DE_PRUEBA.items():
    os.environ.setdefault(_nombre, _valor)

from config.settings import *  # noqa: E402, F403
