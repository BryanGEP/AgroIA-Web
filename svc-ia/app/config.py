"""Configuración del microservicio: lee variables de entorno (y .env en local).

Sigue el mismo patrón que app/config.py del agente de AgroIA para que, en la fase 3,
su código se copie sin cambios: ahí se agregan groq_api_key, llm_provider y llm_model.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _booleano(valor: str) -> bool:
    return valor.strip().lower() in {"1", "true", "si", "yes"}


@dataclass
class Settings:
    # True por defecto; solo el .env local puede apagarla.
    auth_activa: bool = _booleano(os.getenv("AUTH_ACTIVA", "True"))
    # Llave pública para validar el JWT con PyJWT (fase 4).
    jwt_public_key_path: str = os.getenv("JWT_PUBLIC_KEY_PATH", "")


settings = Settings()
