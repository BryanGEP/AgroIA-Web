"""svc-tienda simulado con httpx.MockTransport: las pruebas no dependen de otros contenedores."""

import httpx
import pytest
from clientes import tienda

from tests.tienda_falsa import TiendaFalsa


@pytest.fixture
def tienda_falsa(monkeypatch, settings) -> TiendaFalsa:
    falsa = TiendaFalsa()
    monkeypatch.setattr(
        tienda,
        "obtener_cliente",
        lambda: tienda.ClienteTienda(
            settings.URL_SVC_TIENDA, settings.TIENDA_TIMEOUT, transport=httpx.MockTransport(falsa)
        ),
    )
    return falsa
