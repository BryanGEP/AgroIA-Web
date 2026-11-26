"""Servicios simulados con httpx.MockTransport: las pruebas no dependen de otros contenedores."""

import httpx
import pytest
from clientes import api, tienda

from tests.servicios_falsos import ServiciosFalsos, par
from tests.tienda_falsa import TiendaFalsa


@pytest.fixture
def tienda_falsa(monkeypatch, settings) -> TiendaFalsa:
    falsa = TiendaFalsa()
    monkeypatch.setattr(
        tienda,
        "obtener_cliente",
        lambda: tienda.ClienteTienda(
            settings.URL_SVC_TIENDA,
            settings.SERVICIOS_TIMEOUT,
            transport=httpx.MockTransport(falsa),
        ),
    )
    return falsa


@pytest.fixture
def servicios(monkeypatch) -> ServiciosFalsos:
    """Los cuatro servicios simulados para el cliente común (clientes/api.py)."""
    falsos = ServiciosFalsos()
    monkeypatch.setattr(api, "obtener_transporte", lambda: httpx.MockTransport(falsos))
    return falsos


@pytest.fixture
def con_sesion(client, db):
    """El navegador con una sesión iniciada (los tokens solo viven en web_db)."""

    def iniciar(rol: str = "cliente", verificado: bool = True, nombre: str = "Juan") -> dict:
        tokens = par(rol, verificado)
        sesion = client.session
        sesion["access"] = tokens["access"]
        sesion["refresh"] = tokens["refresh"]
        sesion["usuario"] = {
            "id": "c1e2a3b4-0000-4000-8000-000000000010",
            "nombre": nombre,
            "rol": rol,
            "email_verificado": verificado,
        }
        sesion.save()
        return tokens

    return iniciar
