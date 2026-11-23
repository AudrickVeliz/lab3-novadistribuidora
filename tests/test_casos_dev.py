"""Regresión del motor de reglas con los 84 casos de ejemplos/mensajes_dev.jsonl.

Sin el modelo, cada caso necesita una interpretación correcta. Hay dos fuentes:
- Para todos los casos, una interpretación "ideal" reconstruida desde la respuesta esperada.
  Prueba precios, descuentos, sustitutos, pendientes, crédito, fecha y estado.
- Para los casos de "lo de siempre" y de correcciones, la interpretación escrita a mano desde
  el mensaje. Prueba además el historial, las exclusiones y las correcciones.
Se saltan si los archivos publicados no están (por ejemplo, en CI).
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from novadistribuidora.datos import cargar_datos
from novadistribuidora.interpretacion import Interpretacion, Mencion
from novadistribuidora.motor import armar_pedido
from novadistribuidora.pedido import Pedido

RAIZ = Path(__file__).resolve().parents[1]
CASOS = RAIZ / "ejemplos" / "mensajes_dev.jsonl"

pytestmark = pytest.mark.skipif(
    not (CASOS.is_file() and (RAIZ / "datos").is_dir()), reason="sin los archivos publicados"
)


def _casos() -> dict[str, dict]:
    if not CASOS.is_file():
        return {}
    with CASOS.open(encoding="utf-8") as archivo:
        return {caso["id"]: caso for caso in map(json.loads, archivo)}


CASOS_DEV = _casos()


def _m(texto, skus, cantidad=None, **campos):
    return Mencion(texto=texto, skus=skus, cantidad=cantidad, **campos)


# Interpretaciones escritas a mano desde cada mensaje.
INTERPRETACIONES = {
    "D012": (True, [_m("papel suave 4", ["L04"], 2)]),
    "D017": (True, []),
    "D025": (True, [_m("sal pacifico", ["A11"], operacion="quitar")]),
    "D030": (True, []),
    "D031": (True, [_m("galletas saladdas crac", ["S03"], 5)]),
    "D033": (True, [_m("detergente espumoso", ["L01"], 5)]),
    "D040": (
        True,
        [
            _m("lavaplatos brillo", ["L06"], 2),
            _m("desodorante fresco", ["P04"], operacion="quitar"),
        ],
    ),
    "D044": (True, [_m("kola norte 600", ["B01"], 1)]),
    "D047": (True, [_m("harina mazorca", ["A08"], 1), _m("lavaplatos brillo 450 g", ["L06"], 2)]),
    "D020": (
        False,
        [
            _m("frijol rojo", ["A04"], 4),
            _m("azúcar dulzura 5 lb", ["A05"], 2),
            _m("azúúcar dulzura 5 lb", ["A05"], 5, operacion="corregir"),
        ],
    ),
    "D021": (
        False,
        [
            _m("detergente espumoso 500 g", ["L01"], 3),
            _m("pasta bella espagueti 200 g", ["A10"], 2),
            _m("maní sallado la finca 50 g", ["S06"], 10),
            _m("deetrgente espumoso 500 g", ["L01"], 5, operacion="corregir"),
        ],
    ),
    "D041": (
        False,
        [
            _m("GALLETA CRAC", ["S03"], 6),
            _m("TE QUTZAL", ["B12"], 6),
            _m("GALLETA CRAC", ["S03"], 8, operacion="corregir"),
        ],
    ),
    "D054": (
        False,
        [
            _m("agua pura 1.5", ["B08"], 20),
            _m("papitas doradas", ["S05"], 1),
            _m("papitas doradas 40 g", ["S05"], 4, operacion="corregir"),
        ],
    ),
    "D062": (
        False,
        [
            _m("jabon lavandero", ["L02"], 15),
            _m("nutrimezcla 450 g", ["A14"], 3),
            _m("aceite dorado", ["A06"], 2),
            _m("jabón de barra lavandero 350 g", ["L02"], 16, operacion="corregir"),
        ],
    ),
    "D070": (
        False,
        [
            _m("nutrimezcla 450 g", ["A14"], 1),
            _m("aceite girasol dorado 750 ml", ["A06"], 12),
            _m("papitas doradas", ["S05"], 3),
            _m("papitas doradas", ["S05"], 6, operacion="corregir"),
        ],
    ),
    "D081": (
        False,
        [
            _m("arroz ceiba de libra", ["A01"], 5),
            _m("que sean 6", ["A01"], 6, operacion="corregir"),
            _m("frijol negro", ["A03"], 2),
        ],
    ),
}


@pytest.fixture(scope="module")
def datos():
    return cargar_datos(RAIZ / "datos")


def _interpretacion_ideal(esperado: dict) -> Interpretacion:
    """Las menciones que producen exactamente la respuesta esperada, antes de sustituir."""
    sustituciones = esperado["sustituciones"]
    menciones = []
    for linea in esperado["lineas"]:
        llegan = [s for s in sustituciones if s["sku_entregado"] == linea["sku"]]
        propia = linea["cantidad"] - sum(s["cantidad"] for s in llegan)
        if propia:
            menciones.append(_m(linea["sku"], [linea["sku"]], propia))
        menciones += [_m(s["sku_solicitado"], [s["sku_solicitado"]], s["cantidad"]) for s in llegan]
    for pendiente in esperado["pendientes"]:
        menciones.append(_m(pendiente["texto"], pendiente["opciones"], 1))
    return Interpretacion(es_pedido=esperado["estado"] != "fuera_de_alcance", menciones=menciones)


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

    obtenido = _armar(caso, _interpretacion_ideal(caso["esperado"]), datos)

    assert obtenido == caso["esperado"]


@pytest.mark.parametrize("caso_id", sorted(INTERPRETACIONES))
def test_casos_dev_con_interpretacion_del_mensaje(caso_id, datos):
    caso = CASOS_DEV[caso_id]
    lo_de_siempre, menciones = INTERPRETACIONES[caso_id]
    interpretacion = Interpretacion(
        es_pedido=True, lo_de_siempre=lo_de_siempre, menciones=menciones
    )

    obtenido = _armar(caso, interpretacion, datos)

    assert obtenido == caso["esperado"]


def test_casos_dev_estan_todos():
    assert len(CASOS_DEV) == 84
