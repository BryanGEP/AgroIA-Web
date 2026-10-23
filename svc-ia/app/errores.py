"""Formato común de errores, igual que en los servicios Django (agroia_comun.errores).

`{"error": "codigo_corto", "detalle": "mensaje"}`; los errores de validación agregan
`"campos"` y responden 400 (FastAPI usaría 422).
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorApi(Exception):
    def __init__(
        self,
        status: int,
        codigo: str,
        detalle: str,
        headers: dict[str, str] | None = None,
        campos: dict[str, list[str]] | None = None,
    ):
        super().__init__(detalle)
        self.status = status
        self.codigo = codigo
        self.detalle = detalle
        self.headers = headers
        self.campos = campos


_CODIGOS_HTTP = {404: "no_encontrado", 405: "metodo_no_permitido"}


def _campos(error: RequestValidationError) -> dict[str, list[str]]:
    campos: dict[str, list[str]] = {}
    for detalle in error.errors():
        ruta = [str(parte) for parte in detalle["loc"] if parte not in ("body", "query", "path")]
        campos.setdefault(".".join(ruta) or "non_field_errors", []).append(detalle["msg"])
    return campos


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(ErrorApi)
    async def error_api(request: Request, exc: ErrorApi) -> JSONResponse:
        cuerpo = {"error": exc.codigo, "detalle": exc.detalle}
        if exc.campos:
            cuerpo["campos"] = exc.campos
        return JSONResponse(cuerpo, status_code=exc.status, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validacion(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {
                "error": "validacion",
                "detalle": "Revisa los datos enviados.",
                "campos": _campos(exc),
            },
            status_code=400,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codigo = _CODIGOS_HTTP.get(exc.status_code, "error")
        return JSONResponse(
            {"error": codigo, "detalle": str(exc.detail)},
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )
