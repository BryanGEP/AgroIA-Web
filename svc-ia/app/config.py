"""Configuración del microservicio: lee variables de entorno (y .env en local).

svc-ia no llama al LLM: es un adaptador que traduce el contrato de AgroIA-Web a la API
del contenedor `agente` (repo BryanGEP/AgroIA). Las variables del LLM van a ese
contenedor, no a este.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _booleano(valor: str) -> bool:
    return valor.strip().lower() in {"1", "true", "si", "yes"}


@dataclass
class Settings:
    # Igual que DJANGO_DEBUG en los servicios Django (compose lo pasa como DEBUG).
    debug: bool = field(default_factory=lambda: _booleano(os.getenv("DEBUG", "False")))
    # True por defecto; solo el .env local puede apagarla, y solo con DEBUG=True.
    auth_activa: bool = field(default_factory=lambda: _booleano(os.getenv("AUTH_ACTIVA", "True")))
    # Llave pública para validar el JWT con PyJWT.
    jwt_public_key_path: str = field(default_factory=lambda: os.getenv("JWT_PUBLIC_KEY_PATH", ""))
    # Contenedor del agente (red interna de Docker).
    url_agente: str = field(default_factory=lambda: os.getenv("URL_AGENTE", "http://agente:8000"))
    agente_timeout: float = field(default_factory=lambda: float(os.getenv("AGENTE_TIMEOUT", "30")))


settings = Settings()


def validar(config: Settings) -> None:
    """Impide arrancar con la autenticación apagada fuera del desarrollo local."""
    if not config.auth_activa and not config.debug:
        raise RuntimeError("AUTH_ACTIVA=False solo se permite con DEBUG=True (desarrollo local).")
    if config.agente_timeout <= 0:
        raise RuntimeError("AGENTE_TIMEOUT debe ser mayor que 0.")
