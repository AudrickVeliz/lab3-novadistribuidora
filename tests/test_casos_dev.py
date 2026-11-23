"""Regresión del motor de reglas con los 84 casos de ejemplos/mensajes_dev.jsonl.

Prueba precios, descuentos, sustitutos, pendientes, crédito, fecha y estado; con las
interpretaciones escritas a mano, también el historial, las exclusiones y las correcciones.
Se saltan si los archivos publicados no están (por ejemplo, en CI).
"""

from datetime import datetime

import pytest

from casos_dev import (
    CARPETA_DATOS,
    CASOS_DEV,
    HAY_ARCHIVOS_PUBLICADOS,
    INTERPRETACIONES,
    interpretacion_del_mensaje,
    interpretacion_ideal,
)
from novadistribuidora.datos import cargar_datos
from novadistribuidora.interpretacion import Interpretacion
from novadistribuidora.motor import armar_pedido
from novadistribuidora.pedido import Pedido

pytestmark = pytest.mark.skipif(not HAY_ARCHIVOS_PUBLICADOS, reason="sin los archivos publicados")


@pytest.fixture(scope="module")
def datos():
    return cargar_datos(CARPETA_DATOS)


def _como_contrato(pedido: Pedido) -> dict:
    return {
        "estado": pedido.estado.value,
        "lineas": [
            {
                "sku": linea.sku,
                "cantidad": linea.cantidad,
                "precio_unitario": float(linea.precio_unitario),
                "descuento_pct": linea.descuento_pct,
                "subtotal": float(linea.subtotal),
            }
            for linea in pedido.lineas
        ],
        "total": float(pedido.total),
        "fecha_entrega": pedido.fecha_entrega.isoformat() if pedido.fecha_entrega else None,
        "sustituciones": [
            {
                "sku_solicitado": s.sku_solicitado,
                "sku_entregado": s.sku_entregado,
                "cantidad": s.cantidad,
            }
            for s in pedido.sustituciones
        ],
        "pendientes": [
            {"motivo": p.motivo.value, "texto": p.texto, "opciones": list(p.opciones)}
            for p in pedido.pendientes
        ],
        "motivos_revision": [motivo.value for motivo in pedido.motivos_revision],
    }


def _armar(caso: dict, interpretacion: Interpretacion, datos) -> dict:
    entrada = caso["entrada"]
    cliente = datos.clientes[entrada["cliente_id"]]
    recibido = datetime.fromisoformat(entrada["fecha_hora"])
    return _como_contrato(armar_pedido(interpretacion, cliente, recibido, datos))


@pytest.mark.parametrize("caso_id", sorted(CASOS_DEV))
def test_casos_dev_con_interpretacion_ideal(caso_id, datos):
    caso = CASOS_DEV[caso_id]

    obtenido = _armar(caso, interpretacion_ideal(caso["esperado"]), datos)

    assert obtenido == caso["esperado"]


@pytest.mark.parametrize("caso_id", sorted(INTERPRETACIONES))
def test_casos_dev_con_interpretacion_del_mensaje(caso_id, datos):
    caso = CASOS_DEV[caso_id]

    obtenido = _armar(caso, interpretacion_del_mensaje(caso_id), datos)

    assert obtenido == caso["esperado"]


def test_casos_dev_estan_todos():
    assert len(CASOS_DEV) == 84
