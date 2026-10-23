"""Configuración de pytest para svc-ia.

Prepara las variables de entorno ANTES de importar la app: AUTH_ACTIVA=True y un par de
llaves RSA generado al vuelo, para no depender de infra/llaves/. El agente y el
clasificador se simulan; las pruebas no dependen de otros contenedores.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from tests.tokens import LLAVE_PUBLICA, encabezado, firmar_token

_RUTA = Path(tempfile.mkdtemp(prefix="agroia-ia-")) / "publica.pem"
_RUTA.write_text(LLAVE_PUBLICA, encoding="utf-8")

os.environ["AUTH_ACTIVA"] = "True"
os.environ["DEBUG"] = "False"
os.environ["JWT_PUBLIC_KEY_PATH"] = str(_RUTA)
os.environ["URL_AGENTE"] = "http://agente-de-prueba:8000"
os.environ["AGENTE_TIMEOUT"] = "30"


@pytest.fixture
def cliente_http():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.solicitudes import registro

    registro.limpiar()
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()
    registro.limpiar()


@pytest.fixture
def como_cliente() -> dict[str, str]:
    return encabezado(firmar_token(10, "cliente"))


@pytest.fixture
def como_otro_cliente() -> dict[str, str]:
    return encabezado(firmar_token(11, "cliente"))


@pytest.fixture
def como_admin() -> dict[str, str]:
    return encabezado(firmar_token(1, "administrador"))


@pytest.fixture
def sin_rol() -> dict[str, str]:
    return encabezado(firmar_token(10, None))
