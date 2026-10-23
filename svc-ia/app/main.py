"""Microservicio FastAPI de AgroIA-Web: agente conversacional y diagnóstico por imagen.

svc-ia es un adaptador: expone el contrato de AgroIA-Web y traduce las preguntas a la
API del contenedor `agente` (repo BryanGEP/AgroIA), sin copiar su código. No guarda
nada: las conversaciones y los diagnósticos los guarda svc-contenido, y en la Entrega 2
el gateway orquesta ambas llamadas. Cada respuesta trae `id` y `estado` para volverse
asíncrona en la Entrega 4.
"""

from fastapi import Depends, FastAPI, File, UploadFile
from fastapi.openapi.utils import get_openapi

from app import config
from app.agente import AgenteNoDisponible, ClienteAgente, obtener_agente
from app.errores import ErrorApi, registrar_manejadores
from app.esquemas import Diagnostico, Error, Pregunta, RespuestaAgente, Salud, Solicitud
from app.seguridad import Usuario, llave_publica, usuario_con_rol
from app.solicitudes import registro
from app.vision import Clasificador, obtener_clasificador

config.validar(config.settings)
llave_publica()  # con AUTH_ACTIVA, sin llave pública el servicio no arranca

TAMANO_MAXIMO_IMAGEN = 5 * 1024 * 1024  # 5 MB
FIRMAS_IMAGEN = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")  # JPG, PNG

app = FastAPI(
    title="AgroIA-Web · svc-ia",
    description="Agente conversacional y clasificación de imágenes de aguacate.",
    version="0.2.0",
    docs_url="/api/docs/",
    openapi_url="/api/schema/",
    redoc_url=None,
    swagger_ui_parameters={"persistAuthorization": True},
)
registrar_manejadores(app)


def _respuestas(*codigos: int, **ejemplos) -> dict:
    descripciones = {
        400: "Datos inválidos (`validacion`, con `campos`).",
        401: "Sin token o token inválido.",
        403: "El token no trae un rol válido.",
        404: "No existe, no es tuya o ya no está en memoria.",
        503: "Servicio no disponible.",
    }
    respuestas = {}
    for codigo in codigos:
        respuesta = {"model": Error, "description": descripciones[codigo]}
        if f"e{codigo}" in ejemplos:
            respuesta["content"] = {"application/json": {"example": ejemplos[f"e{codigo}"]}}
        respuestas[codigo] = respuesta
    return respuestas


@app.get("/salud/", response_model=Salud, summary="Estado del servicio", tags=["infraestructura"])
def salud() -> Salud:
    """Comprobación de estado para Docker y el gateway. No requiere autenticación."""
    return Salud(estado="ok")


@app.post(
    "/agente/preguntar/",
    response_model=RespuestaAgente,
    summary="Preguntar al agente AgroIA",
    tags=["agente"],
    responses=_respuestas(
        400,
        401,
        403,
        503,
        e503={
            "error": "agente_no_disponible",
            "detalle": "El agente no está disponible en este momento; intenta más tarde.",
        },
    ),
)
def preguntar(
    datos: Pregunta,
    usuario: Usuario = Depends(usuario_con_rol),
    agente: ClienteAgente = Depends(obtener_agente),
) -> RespuestaAgente:
    """Envía la pregunta y las últimas 10 entradas del historial al agente.

    Si el agente no responde, falla o tarda más que `AGENTE_TIMEOUT`, responde 503
    `agente_no_disponible`: nunca se inventa una respuesta. `fuentes` llega vacío hasta
    que el agente tenga RAG.
    """
    historial = [mensaje.model_dump() for mensaje in datos.historial]
    try:
        resultado = agente.preguntar(datos.pregunta, historial)
    except AgenteNoDisponible as error:
        raise ErrorApi(
            503,
            "agente_no_disponible",
            "El agente no está disponible en este momento; intenta más tarde.",
        ) from error
    contenido = {"respuesta": resultado.respuesta, "fuentes": resultado.fuentes}
    solicitud = registro.guardar("agente", usuario, contenido)
    return RespuestaAgente(id=solicitud["id"], estado="listo", **contenido)


@app.post(
    "/diagnostico/",
    response_model=Diagnostico,
    summary="Diagnosticar una imagen de aguacate",
    tags=["diagnostico"],
    responses=_respuestas(
        400,
        401,
        403,
        503,
        e503={
            "error": "modelo_no_disponible",
            "detalle": "El modelo de diagnóstico se integrará en una entrega posterior.",
        },
    ),
)
def diagnosticar(
    imagen: UploadFile = File(description="Imagen JPG o PNG, máximo 5 MB."),
    usuario: Usuario = Depends(usuario_con_rol),
    clasificador: Clasificador | None = Depends(obtener_clasificador),
) -> Diagnostico:
    """Clasifica la imagen en `sano`, `rona` o `antracnosis`.

    Primero valida la imagen. **Hoy no hay modelo de visión**: responde 503
    `modelo_no_disponible` hasta que se integre en una entrega posterior. No guarda la
    imagen ni el resultado (eso lo hace svc-contenido).
    """
    contenido = imagen.file.read(TAMANO_MAXIMO_IMAGEN + 1)
    if len(contenido) > TAMANO_MAXIMO_IMAGEN:
        raise _imagen_invalida("La imagen no puede pesar más de 5 MB.")
    if not contenido.startswith(FIRMAS_IMAGEN):
        raise _imagen_invalida("Solo se aceptan imágenes JPG o PNG.")
    if clasificador is None:
        raise ErrorApi(
            503,
            "modelo_no_disponible",
            "El modelo de diagnóstico se integrará en una entrega posterior.",
        )

    resultado = clasificador.clasificar(contenido)
    datos = {
        "clase": resultado.clase,
        "confianza": resultado.confianza,
        "probabilidades": resultado.probabilidades,
        "modelo_version": clasificador.modelo_version,
    }
    solicitud = registro.guardar("diagnostico", usuario, datos)
    return Diagnostico(id=solicitud["id"], estado="listo", **datos)


def _imagen_invalida(mensaje: str) -> ErrorApi:
    return ErrorApi(400, "validacion", "Revisa los datos enviados.", campos={"imagen": [mensaje]})


@app.get(
    "/solicitudes/{id_solicitud}/",
    response_model=Solicitud,
    summary="Estado de una solicitud",
    tags=["solicitudes"],
    responses=_respuestas(401, 403, 404),
)
def ver_solicitud(id_solicitud: str, usuario: Usuario = Depends(usuario_con_rol)) -> Solicitud:
    """En la Entrega 2 siempre `listo`. Dueño o administrador.

    Las solicitudes se guardan en memoria (las últimas 1000) y se pierden al reiniciar;
    en la Entrega 4 pasarán a Redis.
    """
    solicitud = registro.obtener(id_solicitud, usuario)
    if solicitud is None:
        raise ErrorApi(404, "no_encontrado", "No se encontró la solicitud.")
    return Solicitud(**solicitud)


def _esquema_openapi() -> dict:
    """Quita la respuesta 422 que FastAPI agrega sola: aquí la validación responde 400."""
    if app.openapi_schema:
        return app.openapi_schema
    esquema = get_openapi(
        title=app.title, version=app.version, description=app.description, routes=app.routes
    )
    for operaciones in esquema["paths"].values():
        for operacion in operaciones.values():
            operacion.get("responses", {}).pop("422", None)
    for nombre in ("HTTPValidationError", "ValidationError"):
        esquema.get("components", {}).get("schemas", {}).pop(nombre, None)
    app.openapi_schema = esquema
    return esquema


app.openapi = _esquema_openapi
