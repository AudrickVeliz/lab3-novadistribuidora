"""Los 84 casos de mensajes_dev.jsonl de punta a punta por HTTP, con el intérprete ideal.

Prueba que la API entrega la respuesta esperada tal cual la envía el cliente del servicio,
con los montos como números JSON. Se saltan si los archivos publicados no están.
"""

import pytest
from fastapi.testclient import TestClient

from casos_dev import CARPETA_DATOS, CASOS_DEV, HAY_ARCHIVOS_PUBLICADOS, interpretacion_ideal
from novadistribuidora.api import crear_app
from novadistribuidora.datos import cargar_datos
from novadistribuidora.servicio import Servicio

pytestmark = pytest.mark.skipif(not HAY_ARCHIVOS_PUBLICADOS, reason="sin los archivos publicados")


class InterpreteIdeal:
    """Responde, para cada caso, la interpretación que reproduce su respuesta esperada."""

    def __init__(self):
        self.por_mensajes = {
            tuple(caso["entrada"]["mensajes"]): interpretacion_ideal(caso["esperado"])
            for caso in CASOS_DEV.values()
        }

    def interpretar(self, mensajes, cliente):
        return self.por_mensajes[tuple(mensajes)]


@pytest.fixture(scope="module")
def cliente_http():
    servicio = Servicio(cargar_datos(CARPETA_DATOS), InterpreteIdeal())
    return TestClient(crear_app(servicio))


@pytest.mark.parametrize("caso_id", sorted(CASOS_DEV))
def test_api_casos_dev(cliente_http, caso_id):
    caso = CASOS_DEV[caso_id]

    respuesta = cliente_http.post("/v1/pedidos/interpretar", json=caso["entrada"])

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo.pop("cliente_id") == caso["entrada"]["cliente_id"]
    assert cuerpo.pop("mensaje_cliente")
    assert cuerpo == caso["esperado"]
