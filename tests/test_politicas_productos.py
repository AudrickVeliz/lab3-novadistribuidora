"""politicas.md §1 a §4: productos, cantidades, "lo de siempre" y agotados."""

from datetime import date

from novadistribuidora.datos import RegistroHistorial
from novadistribuidora.interpretacion import Mencion
from novadistribuidora.pedido import Motivo, Pendiente, Sustitucion
from novadistribuidora.politicas import (
    acumular_cantidad,
    agregar_pendiente_corregido,
    aplicar_sustitutos,
    cantidad_en_unidades_de_venta,
    descartar_cantidades_corregidas,
    descartar_dudas_aclaradas,
    lineas_de_siempre,
    quitar_producto,
    resolver_producto,
    resolver_producto_a_quitar,
)


def _mencion(texto="kola", skus=("B01",), **campos):
    return Mencion(texto=texto, skus=list(skus), **campos)


# §1 Productos y alias


def test_politica_productos_un_solo_candidato_se_resuelve(productos):
    assert resolver_producto(_mencion(skus=["B01"]), productos) == "B01"


def test_politica_productos_ambiguo_no_elige_y_lista_las_opciones(productos):
    resultado = resolver_producto(_mencion("naranjitas", ["B05", "B04"]), productos)

    assert resultado == Pendiente(Motivo.PRODUCTO_AMBIGUO, "naranjitas", ("B04", "B05"))


def test_politica_productos_las_opciones_ambiguas_incluyen_agotados(productos):
    # Caso D064: "cocas" ofrece B01, B02 y B03 aunque B03 esté agotado.
    resultado = resolver_producto(_mencion("cocas", ["B01", "B02", "B03"]), productos)

    assert resultado.opciones == ("B01", "B02", "B03")


def test_politica_productos_lo_que_no_se_vende_es_pendiente_sin_opciones(productos):
    resultado = resolver_producto(_mencion("cerveza", []), productos)

    assert resultado == Pendiente(Motivo.PRODUCTO_NO_EXISTE, "cerveza", ())


def test_politica_productos_nunca_usa_un_sku_inventado(productos):
    # El modelo propone un SKU que no existe: se descarta y queda como no vendido.
    resultado = resolver_producto(_mencion("cerveza gallo", ["Z99"]), productos)

    assert resultado.motivo == Motivo.PRODUCTO_NO_EXISTE


def test_politica_productos_un_sku_inventado_no_vuelve_ambiguo_al_real(productos):
    assert resolver_producto(_mencion(skus=["B01", "Z99"]), productos) == "B01"


def test_politica_productos_normaliza_mayusculas_y_espacios_del_modelo(productos):
    assert resolver_producto(_mencion(skus=[" b01 "]), productos) == "B01"


# §2 Cantidades


def test_politica_cantidades_sin_unidad_es_unidad_de_venta(productos):
    assert cantidad_en_unidades_de_venta(_mencion(cantidad=3), productos["B01"]) == 3


def test_politica_cantidades_sin_cantidad_es_una_unidad_de_venta(productos):
    assert cantidad_en_unidades_de_venta(_mencion(cantidad=None), productos["B01"]) == 1


def test_politica_cantidades_sueltas_se_convierten_si_es_exacto(productos):
    mencion = _mencion(cantidad=72, unidad="suelta")

    assert cantidad_en_unidades_de_venta(mencion, productos["B01"]) == 3


def test_politica_cantidades_una_docena_de_cloro_es_una_caja(productos):
    mencion = _mencion("una docena de cloro", ["L03"], cantidad=1, unidad="docena")

    assert cantidad_en_unidades_de_venta(mencion, productos["L03"]) == 1


def test_politica_cantidades_conversion_no_exacta_no_se_redondea(productos):
    mencion = _mencion("36 botellas de kola 600", cantidad=36, unidad="suelta")

    resultado = cantidad_en_unidades_de_venta(mencion, productos["B01"])

    assert resultado == Pendiente(
        Motivo.CANTIDAD_NO_CONVERTIBLE, "36 botellas de kola 600", ("B01",)
    )


def test_politica_cantidades_fraccion_de_unidad_de_venta_no_se_redondea(productos):
    mencion = _mencion("fardo y medio de kola 600", cantidad=1.5)

    resultado = cantidad_en_unidades_de_venta(mencion, productos["B01"])

    assert resultado == Pendiente(
        Motivo.CANTIDAD_NO_CONVERTIBLE, "fardo y medio de kola 600", ("B01",)
    )


def test_politica_cantidades_media_docena_de_un_empaque_de_seis_es_una_unidad(productos):
    mencion = _mencion("media docena de kola 3 L", ["B03"], cantidad=0.5, unidad="docena")

    assert cantidad_en_unidades_de_venta(mencion, productos["B03"]) == 1


def test_politica_cantidades_sueltas_fraccionarias_no_se_convierten(productos):
    mencion = _mencion("24.5 botellas de kola 600", cantidad=24.5, unidad="suelta")

    resultado = cantidad_en_unidades_de_venta(mencion, productos["B01"])

    assert isinstance(resultado, Pendiente)


def test_politica_cantidades_un_quintal_tiene_una_unidad(productos):
    mencion = _mencion("5 arroz quintal", ["A02"], cantidad=5, unidad="suelta")

    assert cantidad_en_unidades_de_venta(mencion, productos["A02"]) == 5


def test_politica_cantidades_menciones_repetidas_se_suman():
    cantidades = acumular_cantidad({"B01": 2}, "B01", 3, corrige=False)

    assert cantidades == {"B01": 5}


def test_politica_cantidades_una_correccion_reemplaza():
    # "3 fardos de kola 600, no, mejor que sean 5"
    cantidades = acumular_cantidad({"B01": 3, "A06": 1}, "B01", 5, corrige=True)

    assert cantidades == {"B01": 5, "A06": 1}
    assert list(cantidades) == ["B01", "A06"]


def test_politica_cantidades_una_correccion_descarta_la_cantidad_no_convertible_anterior():
    # "fardo y medio de kola 600, no, mejor que sean 2"
    no_convertible = Pendiente(Motivo.CANTIDAD_NO_CONVERTIBLE, "fardo y medio de kola", ("B01",))
    ambiguo = Pendiente(Motivo.PRODUCTO_AMBIGUO, "aceite", ("A06", "A07"))
    de_otro = Pendiente(Motivo.CANTIDAD_NO_CONVERTIBLE, "media caja de jugo", ("B09",))

    pendientes = descartar_cantidades_corregidas([no_convertible, ambiguo, de_otro], "B01")

    assert pendientes == [ambiguo, de_otro]


def test_politica_cantidades_una_correccion_que_repite_la_duda_no_la_duplica():
    # "media caja de aceite" y luego "perdón, mejor que sea una caja de aceite"
    anterior = Pendiente(Motivo.PRODUCTO_AMBIGUO, "aceite", ("A06", "A07"))
    corregido = Pendiente(Motivo.PRODUCTO_AMBIGUO, "el aceite", ("A06", "A07"))

    assert agregar_pendiente_corregido([anterior], corregido) == [anterior]


def test_politica_cantidades_una_correccion_con_otra_duda_se_agrega():
    aceite = Pendiente(Motivo.PRODUCTO_AMBIGUO, "aceite", ("A06", "A07"))
    naranjitas = Pendiente(Motivo.PRODUCTO_AMBIGUO, "naranjitas", ("B04", "B05"))

    assert agregar_pendiente_corregido([aceite], naranjitas) == [aceite, naranjitas]


def test_politica_cantidades_sin_opciones_la_duda_es_el_texto():
    cerveza = Pendiente(Motivo.PRODUCTO_NO_EXISTE, "cerveza", ())
    vino = Pendiente(Motivo.PRODUCTO_NO_EXISTE, "vino", ())

    assert agregar_pendiente_corregido([cerveza], cerveza) == [cerveza]
    assert agregar_pendiente_corregido([cerveza], vino) == [cerveza, vino]


def test_politica_cantidades_una_correccion_con_cantidad_aclara_la_duda():
    # "2 cajas de aceite, perdón, mejor 3 del dorado"
    aceite = Pendiente(Motivo.PRODUCTO_AMBIGUO, "aceite", ("A06", "A07"))
    naranjitas = Pendiente(Motivo.PRODUCTO_AMBIGUO, "naranjitas", ("B04", "B05"))
    mencion = _mencion("del dorado", ["A06"], cantidad=3, operacion="corregir")

    assert descartar_dudas_aclaradas([aceite, naranjitas], mencion, "A06") == [naranjitas]


def test_politica_cantidades_una_correccion_sin_cantidad_no_aclara_la_duda():
    aceite = Pendiente(Motivo.PRODUCTO_AMBIGUO, "aceite", ("A06", "A07"))
    mencion = _mencion("mejor del dorado", ["A06"], operacion="corregir")

    assert descartar_dudas_aclaradas([aceite], mencion, "A06") == [aceite]


def test_politica_cantidades_aclarar_no_toca_otros_motivos():
    no_convertible = Pendiente(Motivo.CANTIDAD_NO_CONVERTIBLE, "media caja de aceite", ("A06",))
    mencion = _mencion("del dorado", ["A06"], cantidad=3, operacion="corregir")

    assert descartar_dudas_aclaradas([no_convertible], mencion, "A06") == [no_convertible]


def test_politica_cantidades_acumular_no_modifica_el_pedido_original():
    original = {"B01": 2}

    acumular_cantidad(original, "B01", 3, corrige=False)

    assert original == {"B01": 2}


def test_politica_cantidades_quitar_elimina_la_linea():
    assert quitar_producto({"B01": 2, "S05": 1}, "S05") == {"B01": 2}


def test_politica_cantidades_quitar_resuelve_contra_lo_que_esta_en_el_pedido():
    # "sin las naranjitas" es ambiguo en el catálogo, pero solo B04 está en el pedido.
    mencion = _mencion("naranjitas", ["B04", "B05"], operacion="quitar")

    assert resolver_producto_a_quitar(mencion, {"B04": 2, "A06": 1}) == "B04"


def test_politica_cantidades_quitar_algo_que_no_esta_no_hace_nada():
    mencion = _mencion("papitas", ["S05"], operacion="quitar")

    assert resolver_producto_a_quitar(mencion, {"B04": 2}) is None


def test_politica_cantidades_quitar_ambiguo_dentro_del_pedido_es_pendiente():
    mencion = _mencion("naranjitas", ["B04", "B05"], operacion="quitar")

    resultado = resolver_producto_a_quitar(mencion, {"B04": 2, "B05": 1})

    assert resultado == Pendiente(Motivo.PRODUCTO_AMBIGUO, "naranjitas", ("B04", "B05"))


# §3 "Lo de siempre"


def _registro(pedido_id, fecha, sku, cantidad, estado="entregado", cliente_id="C001"):
    return RegistroHistorial(
        pedido_id, cliente_id, date.fromisoformat(fecha), sku, cantidad, estado
    )


def test_politica_lo_de_siempre_usa_el_ultimo_pedido_entregado():
    historial = [
        _registro("PED-1", "2026-11-10", "B01", 2),
        _registro("PED-2", "2026-11-17", "A06", 3),
        _registro("PED-2", "2026-11-17", "B04", 1),
    ]

    assert lineas_de_siempre(historial, "C001") == {"A06": 3, "B04": 1}


def test_politica_lo_de_siempre_ignora_los_cancelados():
    historial = [
        _registro("PED-1", "2026-11-17", "B01", 2),
        _registro("PED-2", "2026-11-20", "A06", 3, estado="cancelado"),
    ]

    assert lineas_de_siempre(historial, "C001") == {"B01": 2}


def test_politica_lo_de_siempre_solo_usa_pedidos_del_cliente():
    historial = [
        _registro("PED-1", "2026-11-17", "B01", 2),
        _registro("PED-2", "2026-11-20", "A06", 3, cliente_id="C002"),
    ]

    assert lineas_de_siempre(historial, "C001") == {"B01": 2}


def test_politica_lo_de_siempre_conserva_el_orden_del_historial():
    historial = [
        _registro("PED-1", "2026-11-17", "L01", 3),
        _registro("PED-1", "2026-11-17", "A10", 2),
    ]

    assert list(lineas_de_siempre(historial, "C001")) == ["L01", "A10"]


def test_politica_lo_de_siempre_sin_entregados_no_tiene_lineas():
    historial = [_registro("PED-1", "2026-11-17", "B01", 2, estado="cancelado")]

    assert lineas_de_siempre(historial, "C001") == {}


# §4 Productos agotados


def test_politica_agotados_disponible_no_cambia(productos):
    assert aplicar_sustitutos({"B01": 2}, productos) == ({"B01": 2}, [], [])


def test_politica_agotados_se_entrega_el_sustituto_con_la_misma_cantidad(productos):
    entregables, sustituciones, pendientes = aplicar_sustitutos({"B03": 4}, productos)

    assert entregables == {"B02": 4}
    assert sustituciones == [Sustitucion("B03", "B02", 4)]
    assert pendientes == []


def test_politica_agotados_el_sustituto_toma_el_lugar_del_agotado(productos):
    entregables, _, _ = aplicar_sustitutos({"A06": 1, "B03": 4, "B01": 2}, productos)

    assert list(entregables) == ["A06", "B02", "B01"]


def test_politica_agotados_el_sustituto_se_suma_a_su_linea(productos):
    # Caso D047: el historial trae A06 = 3 y A07 = 1; A07 se cambia por A06.
    entregables, sustituciones, _ = aplicar_sustitutos({"A06": 3, "A07": 1}, productos)

    assert entregables == {"A06": 4}
    assert sustituciones == [Sustitucion("A07", "A06", 1)]


def test_politica_agotados_sin_sustituto_es_pendiente_con_el_nombre_del_catalogo(productos):
    entregables, _, pendientes = aplicar_sustitutos({"P04": 1, "B01": 2}, productos)

    assert entregables == {"B01": 2}
    assert pendientes == [
        Pendiente(Motivo.AGOTADO_SIN_SUSTITUTO, "Desodorante Fresco roll-on 50 ml", ("P04",))
    ]


def test_politica_agotados_un_sustituto_agotado_no_sirve(productos):
    entregables, sustituciones, pendientes = aplicar_sustitutos({"X01": 2}, productos)

    assert entregables == {}
    assert sustituciones == []
    assert [pendiente.motivo for pendiente in pendientes] == [Motivo.AGOTADO_SIN_SUSTITUTO]


def test_politica_agotados_cada_agotado_deja_su_pendiente_en_orden(productos):
    # Caso D031: el historial trae dos agotados sin sustituto.
    _, _, pendientes = aplicar_sustitutos({"P04": 2, "S02": 4}, productos)

    assert [pendiente.opciones for pendiente in pendientes] == [("P04",), ("S02",)]
