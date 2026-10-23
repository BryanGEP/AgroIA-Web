"""Filtros de plantilla: precios en pesos y ficha técnica legible."""

import pytest

from apps.catalogo.templatetags.agroia import ficha_filas, pesos, tinte


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("1250.00", "$1,250.00"), ("85", "$85.00"), ("1234567.5", "$1,234,567.50"), ("0.5", "$0.50")],
)
def test_pesos(valor, esperado):
    assert pesos(valor) == esperado


def test_pesos_con_valor_invalido():
    assert pesos("no es número") == ""
    assert pesos(None) == ""


def test_ficha_filas_legibles():
    filas = ficha_filas(
        {
            "ingrediente_activo": "Azoxistrobina",
            "dosis": "0.5 L/ha",
            "composicion": {"N": "17%", "P2O5": "17%"},
            "incluye_cartuchos": False,
            "piezas": 50,
            "uso": "Fertirriego",
        }
    )

    assert filas[0] == {"etiqueta": "Ingrediente activo", "valor": "Azoxistrobina"}
    assert filas[1] == {"etiqueta": "Dosis", "valor": "0.5 L/ha"}
    assert filas[2] == {"etiqueta": "Composición", "lista": [("N", "17%"), ("P2O5", "17%")]}
    assert filas[3] == {"etiqueta": "Incluye cartuchos", "valor": "No"}
    assert filas[4] == {"etiqueta": "Piezas", "valor": "50"}
    assert filas[5] == {"etiqueta": "Uso", "valor": "Fertirriego"}


def test_ficha_vacia_o_invalida():
    assert ficha_filas({}) == []
    assert ficha_filas(None) == []
    assert ficha_filas("texto") == []


def test_tinte_por_categoria():
    assert tinte("riego") == "riego"
    assert tinte("semillas") == "general"
