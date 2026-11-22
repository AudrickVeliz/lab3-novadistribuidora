"""politicas.md §5 a §8: precios y descuentos, crédito, fecha de entrega y estado."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from novadistribuidora.datos import Cliente, Escala
from novadistribuidora.pedido import Estado, Linea, Motivo, Pendiente
from novadistribuidora.politicas import (
    calcular_lineas,
    descuento_pct,
    estado_pedido,
    excede_credito,
    fecha_entrega,
    motivos_revision,
    subtotal,
    total,
)

BEBIDAS = (Escala(10, 3), Escala(20, 5))
LUNES, JUEVES, SABADO, DOMINGO = 0, 3, 5, 6


# §5 Precios y descuentos


@pytest.mark.parametrize(
    ("cantidad", "esperado"), [(9, 0), (10, 3), (19, 3), (20, 5), (48, 5)]
)
def test_politica_descuento_mayor_escala_alcanzada(cantidad, esperado):
    assert descuento_pct(cantidad, BEBIDAS) == esperado


def test_politica_descuento_categoria_sin_escalas_no_tiene_descuento():
    assert descuento_pct(100, ()) == 0


def test_politica_descuento_no_depende_del_orden_de_las_escalas():
    assert descuento_pct(25, tuple(reversed(BEBIDAS))) == 5


def test_politica_subtotal_aplica_el_descuento():
    # 24 fardos de Kola 600 a Q120 con 5 %: 24 × 120 × 0.95.
    assert subtotal(24, Decimal("120"), 5) == Decimal("2736.00")


def test_politica_subtotal_redondea_mitad_hacia_arriba():
    # 1 × 12.50 × 0.97 = 12.125: mitad hacia arriba da 12.13 (el redondeo bancario daría 12.12).
    assert subtotal(1, Decimal("12.50"), 3) == Decimal("12.13")


def test_politica_precios_las_lineas_usan_precio_y_escala_del_catalogo(productos, escalas):
    lineas = calcular_lineas({"B01": 24, "A06": 2}, productos, escalas)

    assert lineas == [
        Linea("B01", 24, Decimal("120"), 5, Decimal("2736.00")),
        Linea("A06", 2, Decimal("228"), 0, Decimal("456.00")),
    ]


def test_politica_precios_total_suma_los_subtotales(productos, escalas):
    lineas = calcular_lineas({"B01": 24, "A06": 2}, productos, escalas)

    assert total(lineas) == Decimal("3192.00")


def test_politica_precios_total_sin_lineas_es_cero():
    assert total([]) == Decimal("0.00")


# §6 Crédito


def _cliente(limite="8000", saldo="1200", dias=frozenset({LUNES, JUEVES})):
    return Cliente("C001", "Tienda", "Dueña", dias, Decimal(limite), Decimal(saldo))


def test_politica_credito_llegar_justo_al_limite_no_lo_excede():
    assert not excede_credito(_cliente(), Decimal("6800.00"))


def test_politica_credito_pasar_el_limite_lo_excede():
    assert excede_credito(_cliente(), Decimal("6800.01"))


# §7 Fecha de entrega


def test_politica_entrega_ejemplo_del_anexo():
    # Lunes 23 a las 15:20, ruta lunes y jueves: se entrega el jueves 26.
    assert fecha_entrega(datetime(2026, 11, 23, 15, 20), frozenset({LUNES, JUEVES})) == date(
        2026, 11, 26
    )


def test_politica_entrega_es_estrictamente_posterior_a_la_recepcion():
    # Lunes 10:00 con visita los lunes: el camión de hoy ya no lo lleva.
    assert fecha_entrega(datetime(2026, 11, 23, 10, 0), frozenset({LUNES})) == date(2026, 11, 30)


def test_politica_entrega_antes_del_corte_cuenta_desde_hoy():
    assert fecha_entrega(datetime(2026, 11, 25, 13, 59), frozenset({JUEVES})) == date(2026, 11, 26)


def test_politica_entrega_a_las_14_00_cuenta_desde_manana():
    # Miércoles 14:00 equivale a jueves: el jueves 26 ya no es posterior.
    assert fecha_entrega(datetime(2026, 11, 25, 14, 0), frozenset({JUEVES})) == date(2026, 12, 3)


def test_politica_entrega_caso_d001():
    # Sábado 28 a las 14:53 con ruta solo de sábado: cuenta como domingo y se entrega el sábado 5.
    assert fecha_entrega(datetime(2026, 11, 28, 14, 53), frozenset({SABADO})) == date(2026, 12, 5)


def test_politica_entrega_cruza_el_fin_de_semana():
    assert fecha_entrega(datetime(2026, 11, 28, 20, 30), frozenset({DOMINGO})) == date(
        2026, 12, 6
    )


def test_politica_entrega_sin_dias_de_visita_falla_con_motivo():
    with pytest.raises(ValueError, match="dias_visita"):
        fecha_entrega(datetime(2026, 11, 23, 10, 0), frozenset())


# §8 Estado del pedido


AMBIGUO = Pendiente(Motivo.PRODUCTO_AMBIGUO, "aceite", ("A06", "A07"))
AGOTADO = Pendiente(Motivo.AGOTADO_SIN_SUSTITUTO, "Galletas Dulcitas Chocolate", ("S02",))
LINEA = Linea("B01", 2, Decimal("120"), 0, Decimal("240.00"))


def test_politica_estado_motivos_sin_repetir_y_en_orden():
    pendientes = [AGOTADO, AMBIGUO, AGOTADO]

    assert motivos_revision(pendientes, credito_excedido=False) == [
        Motivo.AGOTADO_SIN_SUSTITUTO,
        Motivo.PRODUCTO_AMBIGUO,
    ]


def test_politica_estado_el_credito_es_motivo_sin_pendiente():
    assert motivos_revision([AMBIGUO], credito_excedido=True) == [
        Motivo.PRODUCTO_AMBIGUO,
        Motivo.CREDITO_EXCEDIDO,
    ]


def test_politica_estado_confirmado_con_lineas_y_sin_motivos():
    assert estado_pedido(True, [LINEA], []) == Estado.CONFIRMADO


def test_politica_estado_requiere_revision_con_algun_motivo():
    assert estado_pedido(True, [LINEA], [Motivo.CREDITO_EXCEDIDO]) == Estado.REQUIERE_REVISION


def test_politica_estado_requiere_revision_aunque_no_haya_lineas():
    assert estado_pedido(True, [], [Motivo.PRODUCTO_AMBIGUO]) == Estado.REQUIERE_REVISION


def test_politica_estado_mensaje_sin_pedido_esta_fuera_de_alcance():
    assert estado_pedido(False, [], []) == Estado.FUERA_DE_ALCANCE


def test_politica_estado_pedido_sin_lineas_ni_motivos_esta_fuera_de_alcance():
    assert estado_pedido(True, [], []) == Estado.FUERA_DE_ALCANCE
