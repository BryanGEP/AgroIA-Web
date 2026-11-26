"""Hook de drf-spectacular que documenta las respuestas de error (agroia_comun.openapi)."""

from agroia_comun.openapi import documentar_errores


def esquema(respuestas: dict) -> dict:
    return {"paths": {"/api/v1/pedidos/": {"post": {"responses": respuestas}}}}


def ejemplos(resultado: dict, estado: str) -> dict:
    respuesta = resultado["paths"]["/api/v1/pedidos/"]["post"]["responses"][estado]
    return respuesta["content"]["application/json"]["examples"]


def test_agrega_el_esquema_comun_de_error():
    resultado = documentar_errores(
        esquema({"401": {"description": "Sin token."}}), None, None, True
    )

    error = resultado["components"]["schemas"]["Error"]
    assert error["required"] == ["error", "detalle"]
    contenido = resultado["paths"]["/api/v1/pedidos/"]["post"]["responses"]["401"]["content"]
    assert contenido["application/json"]["schema"] == {"$ref": "#/components/schemas/Error"}


def test_usa_los_codigos_de_la_descripcion():
    resultado = documentar_errores(
        esquema({"409": {"description": "`stock_insuficiente` o `producto_no_disponible`."}}),
        None,
        None,
        True,
    )

    assert list(ejemplos(resultado, "409")) == ["stock_insuficiente", "producto_no_disponible"]
    assert (
        ejemplos(resultado, "409")["stock_insuficiente"]["value"]["error"] == "stock_insuficiente"
    )


def test_sin_codigo_en_la_descripcion_usa_el_del_estado():
    resultado = documentar_errores(
        esquema({"403": {"description": "No es cliente."}, "404": {"description": "No existe."}}),
        None,
        None,
        True,
    )

    assert list(ejemplos(resultado, "403")) == ["sin_permiso"]
    assert list(ejemplos(resultado, "404")) == ["no_encontrado"]


def test_los_nombres_de_campos_no_son_codigos():
    resultado = documentar_errores(
        esquema({"400": {"description": "Datos inválidos (`validacion`, con `campos`)."}}),
        None,
        None,
        True,
    )

    assert list(ejemplos(resultado, "400")) == ["validacion"]
    assert "campos" in ejemplos(resultado, "400")["validacion"]["value"]


def test_no_toca_respuestas_correctas_ni_las_que_ya_tienen_contenido():
    propio = {"content": {"application/json": {"example": {"error": "x", "detalle": "y"}}}}
    resultado = documentar_errores(
        esquema({"201": {"description": "Creado."}, "400": propio}), None, None, True
    )

    respuestas = resultado["paths"]["/api/v1/pedidos/"]["post"]["responses"]
    assert "content" not in respuestas["201"]
    assert respuestas["400"] is propio
