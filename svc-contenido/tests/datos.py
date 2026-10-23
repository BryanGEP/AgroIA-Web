"""Datos de ejemplo compartidos por las pruebas."""

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

CLIENTE_ID = 10
OTRO_CLIENTE_ID = 11
ADMIN_ID = 1

PROBABILIDADES = {"sano": 0.03, "rona": 0.06, "antracnosis": 0.91}


def imagen(nombre: str = "hoja.png", formato: str = "PNG") -> SimpleUploadedFile:
    contenido = BytesIO()
    Image.new("RGB", (8, 8), "green").save(contenido, format=formato)
    tipo = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[formato]
    return SimpleUploadedFile(nombre, contenido.getvalue(), content_type=tipo)
