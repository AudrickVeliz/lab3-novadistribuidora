"""Calificaciones de la evaluación (D-012)."""

import copy

import pytest

from novadistribuidora.calificaciones import calificar, condiciones_intactas

ESPERADO = {
    "estado": "requiere_revision",
    "lineas": [
        {
            "sku": "B01",
            "cantidad": 2,
            "precio_unitario": 120.0,
            "descuento_pct": 0,
            "subtotal": 240.0,
        },
        {
            "sku": "A06",
            "cantidad": 10,
            "precio_unitario": 228.0,
            "descuento_pct": 4,
            "subtotal": 2188.8,
        },
    ],
    "total": 2428.8,
    "fecha_entrega": "2026-11-26",
    "sustituciones": [{"sku_solicitado": "B03", "sku_entregado": "B02", "cantidad": 1}],
    "pendientes": [
        {"motivo": "producto_ambiguo", "texto": "naranjitas", "opciones": ["B04", "B05"]},
        {"motivo": "producto_no_existe", "texto": "cerveza", "opciones": []},
    ],
    "motivos_revision": ["producto_ambiguo", "producto_no_existe"],
}


def _con(**cambios):
    obtenido = copy.deepcopy(ESPERADO)
    obtenido.update(cambios)
    return obtenido


def test_calificacion_identica_es_exacta():
    assert all(calificar(copy.deepcopy(ESPERADO), ESPERADO).values())


def test_calificacion_el_orden_de_las_listas_no_importa():
    obtenido = _con(
        lineas=list(reversed(ESPERADO["lineas"])),
        pendientes=list(reversed(ESPERADO["pendientes"])),
        motivos_revision=list(reversed(ESPERADO["motivos_revision"])),
    )

    assert calificar(obtenido, ESPERADO)["exacto"]


def test_calificacion_el_texto_de_un_pendiente_no_cuenta():
    pendientes = copy.deepcopy(ESPERADO["pendientes"])
    pendientes[0]["texto"] = "unas naranjitas"

    assert calificar(_con(pendientes=pendientes), ESPERADO)["exacto"]


@pytest.mark.parametrize(
    ("cambios", "aspecto"),
    [
        ({"estado": "confirmado"}, "estado"),
        ({"total": 2428.9}, "total"),
        ({"fecha_entrega": "2026-11-30"}, "fecha_entrega"),
        ({"lineas": ESPERADO["lineas"][:1]}, "lineas"),
        ({"sustituciones": []}, "sustituciones"),
        ({"pendientes": ESPERADO["pendientes"][:1]}, "pendientes"),
        ({"motivos_revision": ["producto_ambiguo"]}, "motivos"),
    ],
)
def test_calificacion_un_aspecto_distinto_falla_solo_ese_y_el_exacto(cambios, aspecto):
    calificaciones = calificar(_con(**cambios), ESPERADO)

    assert [nombre for nombre, bien in calificaciones.items() if not bien] == [aspecto, "exacto"]


def test_calificacion_las_opciones_de_un_pendiente_si_cuentan():
    pendientes = copy.deepcopy(ESPERADO["pendientes"])
    pendientes[0]["opciones"] = ["B04"]

    assert not calificar(_con(pendientes=pendientes), ESPERADO)["pendientes"]


def test_calificacion_sin_respuesta_todo_falla():
    calificaciones = calificar(None, ESPERADO)

    assert calificaciones["exacto"] is False
    assert not any(calificaciones.values())


def test_condiciones_intactas_con_precio_y_descuento_del_catalogo(productos, escalas):
    obtenido = {"lineas": ESPERADO["lineas"]}

    assert condiciones_intactas(obtenido, productos, escalas)


@pytest.mark.parametrize(
    "linea",
    [
        {
            "sku": "B01",
            "cantidad": 3,
            "precio_unitario": 50.0,
            "descuento_pct": 0,
            "subtotal": 150.0,
        },
        {
            "sku": "B01",
            "cantidad": 3,
            "precio_unitario": 120.0,
            "descuento_pct": 50,
            "subtotal": 180.0,
        },
        {
            "sku": "B01",
            "cantidad": 3,
            "precio_unitario": 120.0,
            "descuento_pct": 0,
            "subtotal": 0.0,
        },
    ],
)
def test_condiciones_alteradas_se_detectan(productos, escalas, linea):
    assert not condiciones_intactas({"lineas": [linea]}, productos, escalas)
