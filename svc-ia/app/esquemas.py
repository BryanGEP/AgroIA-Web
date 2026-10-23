"""Modelos de entrada y salida (Pydantic) con ejemplos para Swagger."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Salud(BaseModel):
    estado: str


class Error(BaseModel):
    error: str
    detalle: str
    campos: dict[str, list[str]] | None = None


class MensajeHistorial(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    rol: Literal["usuario", "agente"]
    texto: str = Field(min_length=1, max_length=10000)


class Pregunta(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "examples": [
                {
                    "pregunta": "¿Y cada cuánto aplico el fungicida?",
                    "historial": [
                        {"rol": "usuario", "texto": "Tengo manchas negras hundidas en el fruto."},
                        {"rol": "agente", "texto": "Parece antracnosis; revisa la humedad."},
                    ],
                }
            ]
        },
    )

    pregunta: str = Field(min_length=1, max_length=4000)
    historial: list[MensajeHistorial] = Field(
        default_factory=list,
        max_length=200,
        description="Mensajes anteriores de la conversación; se usan los últimos 10.",
    )


class RespuestaAgente(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "4f1c2b0a9d8e4c7b8a6f5e4d3c2b1a09",
                    "estado": "listo",
                    "respuesta": "Aplica un fungicida cúprico cada 15 a 21 días en lluvias.",
                    "fuentes": [],
                }
            ]
        }
    )

    id: str
    estado: Literal["listo"]
    respuesta: str
    fuentes: list[str]


class Diagnostico(BaseModel):
    model_config = ConfigDict(
        protected_namespaces=(),
        json_schema_extra={
            "examples": [
                {
                    "id": "9a8b7c6d5e4f40312a1b2c3d4e5f6071",
                    "estado": "listo",
                    "clase": "antracnosis",
                    "confianza": 0.91,
                    "probabilidades": {"sano": 0.03, "rona": 0.06, "antracnosis": 0.91},
                    "modelo_version": "v1",
                }
            ]
        },
    )

    id: str
    estado: Literal["listo"]
    clase: Literal["sano", "rona", "antracnosis"]
    confianza: float = Field(ge=0, le=1)
    probabilidades: dict[str, float]
    modelo_version: str


class Solicitud(BaseModel):
    id: str
    estado: Literal["listo"]
    tipo: Literal["agente", "diagnostico"]
    creada_en: datetime
    resultado: dict
