"""Datos de ejemplo compartidos por las pruebas."""

import uuid

CLIENTE_ID = uuid.UUID("c1e2a3b4-0000-4000-8000-000000000010")
OTRO_CLIENTE_ID = uuid.UUID("c1e2a3b4-0000-4000-8000-000000000011")
ADMIN_ID = uuid.UUID("a0d1e2f3-0000-4000-8000-000000000001")

DIRECCION = {
    "alias": "Huerta",
    "calle": "Camino a La Palma",
    "numero": "km 3",
    "colonia": "La Palma",
    "municipio": "Jiquilpan",
    "estado": "Michoacán",
    "codigo_postal": "59510",
    "referencias": "Portón verde",
}

REGISTRO = {
    "nombre": "María",
    "apellidos": "López Ramírez",
    "email": "maria.lopez@example.com",
    "password": "Aguacate-Hass-2026",
    "password_confirmacion": "Aguacate-Hass-2026",
    "acepto_privacidad": True,
}
