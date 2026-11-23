"""Casos de ejemplos/mensajes_dev.jsonl y sus interpretaciones, para probar sin el modelo.

Sin el modelo, cada caso necesita una interpretación correcta. Hay dos fuentes:
- Para todos los casos, una interpretación "ideal" reconstruida desde la respuesta esperada.
- Para los casos de "lo de siempre" y de correcciones, la interpretación escrita a mano desde
  el mensaje, que prueba además el historial, las exclusiones y las correcciones.
"""

import json
from pathlib import Path

from novadistribuidora.interpretacion import Interpretacion, Mencion

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_DATOS = RAIZ / "datos"
ARCHIVO_CASOS = RAIZ / "ejemplos" / "mensajes_dev.jsonl"
HAY_ARCHIVOS_PUBLICADOS = ARCHIVO_CASOS.is_file() and CARPETA_DATOS.is_dir()


def _casos() -> dict[str, dict]:
    if not ARCHIVO_CASOS.is_file():
        return {}
    with ARCHIVO_CASOS.open(encoding="utf-8") as archivo:
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


def interpretacion_ideal(esperado: dict) -> Interpretacion:
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


def interpretacion_del_mensaje(caso_id: str) -> Interpretacion:
    lo_de_siempre, menciones = INTERPRETACIONES[caso_id]
    return Interpretacion(es_pedido=True, lo_de_siempre=lo_de_siempre, menciones=menciones)
