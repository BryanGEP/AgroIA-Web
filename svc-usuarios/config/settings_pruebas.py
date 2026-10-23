"""Configuración para pytest.

Completa con valores de prueba las variables de entorno que falten, para poder
correr pytest en el venv local sin un .env. En Docker las variables ya existen y
se respetan. Estos valores no son secretos ni sirven fuera de las pruebas.

Las pruebas siempre corren con AUTH_ACTIVA=True y con un par de llaves RSA generado
al vuelo, para no depender de infra/llaves/ (ver conftest.py).
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
    "POSTGRES_DB": "usuarios_db",
    "POSTGRES_USER": "usuarios",
    "POSTGRES_PASSWORD": "solo-para-pruebas",
    "POSTGRES_HOST": "localhost",
}

for _nombre, _valor in _VALORES_DE_PRUEBA.items():
    os.environ.setdefault(_nombre, _valor)

# Estas se fuerzan aunque el .env diga otra cosa.
os.environ["AUTH_ACTIVA"] = "True"
os.environ["JWT_PUBLIC_KEY_PATH"] = str(_RUTA_LLAVE_PUBLICA)
os.environ["VERSION_AVISO_PRIVACIDAD"] = "2026-10"

from config.settings import *  # noqa: E402, F403

# Más rápido en pruebas; la prueba de "no queda en texto plano" sigue siendo válida.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
