"""Clasificación de los casos de la matriz de accesos (infra/matriz_seguridad.py).

La matriz prueba el control de acceso, no la disponibilidad del agente. Un 503 de servicio
externo donde se esperaba acceso permitido cuenta como coincidencia, marcado aparte; un 401
o 403 donde se esperaba permitido, o un 503 donde se esperaba 401 o 403, es una falla.

Desde la raíz, con el venv activo:

    python -m pytest infra/tests
"""

import importlib.util
from pathlib import Path

import pytest

_RUTA = Path(__file__).resolve().parent.parent / "matriz_seguridad.py"
_spec = importlib.util.spec_from_file_location("matriz_seguridad", _RUTA)
matriz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(matriz)


def caso(esperado, obtenido, codigo=None, codigo_esperado=None, actor="cliente"):
    return matriz.Caso("Pregunta al agente", actor, "POST", "/api/ia/agente/preguntar/",
                       esperado, codigo_esperado, obtenido=obtenido, codigo=codigo)  # fmt: skip


@pytest.mark.parametrize("codigo", ["agente_no_disponible", "modelo_no_disponible"])
def test_un_503_de_servicio_externo_en_una_fila_permitida_coincide_marcado(codigo):
    c = caso(200, 503, codigo)
    assert c.coincide and c.servicio_externo


def test_la_coincidencia_normal_no_se_marca():
    c = caso(200, 200)
    assert c.coincide and not c.servicio_externo


@pytest.mark.parametrize(
    ("obtenido", "codigo"),
    [(401, "no_autenticado"), (403, "sin_permiso"), (403, "email_no_verificado")],
)
def test_un_401_o_403_donde_se_esperaba_permitido_es_falla(obtenido, codigo):
    c = caso(200, obtenido, codigo)
    assert not c.coincide and not c.servicio_externo


@pytest.mark.parametrize(
    ("esperado", "codigo_esperado"), [(401, "no_autenticado"), (403, "sin_permiso")]
)
def test_un_503_donde_se_esperaba_401_o_403_es_falla(esperado, codigo_esperado):
    c = caso(esperado, 503, "agente_no_disponible", codigo_esperado)
    assert not c.coincide and not c.servicio_externo


@pytest.mark.parametrize("codigo", ["servicio_no_disponible", "tiempo_agotado", None])
def test_otro_503_o_un_502_en_una_fila_permitida_sigue_siendo_falla(codigo):
    assert not caso(200, 503, codigo).coincide
    assert not caso(202, 502, "servicio_no_disponible").coincide


def test_el_reporte_cuenta_y_marca_las_filas_de_servicio_externo():
    m = matriz.Matriz("http://localhost:8000")
    m.casos = [caso(200, 503, "agente_no_disponible", actor="cliente"),
               caso(200, 200, actor="admin"),
               caso(401, 401, "no_autenticado", "no_autenticado", actor="anonimo")]  # fmt: skip
    from datetime import datetime

    texto = m.reporte(datetime(2026, 11, 24, 12, 0), 1.0, con_limites=False)

    assert "| Coinciden con lo esperado | **3 de 3 (100 %)** |" in texto
    assert f"| De ellas, {matriz.EXTERNO} | 1 |" in texto
    assert f"sí, {matriz.EXTERNO}" in texto
    assert "503 ✓*" in texto
