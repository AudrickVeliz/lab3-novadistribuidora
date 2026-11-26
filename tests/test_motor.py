"""armar_pedido: las reglas de politicas.md aplicadas en orden sobre una interpretación."""

from datetime import date, datetime
from decimal import Decimal

from novadistribuidora.interpretacion import Interpretacion, Mencion
from novadistribuidora.motor import SIN_PEDIDO, armar_pedido
from novadistribuidora.pedido import Estado, Linea, Motivo, Pendiente, Sustitucion

# Lunes 23 de noviembre a las 15:20, como el ejemplo del Anexo: la ruta del jueves 26.
RECIBIDO = datetime(2026, 11, 23, 15, 20)


def _pedido(datos, cliente, *menciones, lo_de_siempre=False, es_pedido=True):
    interpretacion = Interpretacion(
        es_pedido=es_pedido, lo_de_siempre=lo_de_siempre, menciones=list(menciones)
    )
    return armar_pedido(interpretacion, cliente, RECIBIDO, datos)


def test_motor_ejemplo_del_anexo(datos, cliente):
    pedido = _pedido(
        datos,
        cliente,
        Mencion(texto="2 fardos de kola 600", skus=["B01"], cantidad=2),
        Mencion(texto="una caja de aceite", skus=["A06", "A07"], cantidad=1),
        Mencion(texto="48 latas de naranjita", skus=["B04"], cantidad=48, unidad="suelta"),
    )

    assert pedido.estado == Estado.REQUIERE_REVISION
    assert pedido.lineas == (
        Linea("B01", 2, Decimal("120"), 0, Decimal("240.00")),
        Linea("B04", 2, Decimal("110"), 0, Decimal("220.00")),
    )
    assert pedido.total == Decimal("460.00")
    assert pedido.fecha_entrega == date(2026, 11, 26)
    assert pedido.pendientes == (
        Pendiente(Motivo.PRODUCTO_AMBIGUO, "una caja de aceite", ("A06", "A07")),
    )
    assert pedido.motivos_revision == (Motivo.PRODUCTO_AMBIGUO,)


def test_motor_pedido_sin_problemas_queda_confirmado(datos, cliente):
    pedido = _pedido(datos, cliente, Mencion(texto="3 de kola 600", skus=["B01"], cantidad=3))

    assert pedido.estado == Estado.CONFIRMADO
    assert pedido.pendientes == ()
    assert pedido.motivos_revision == ()


def test_motor_mensaje_sin_pedido_esta_fuera_de_alcance(datos, cliente):
    # Aunque el modelo haya anotado algo, sin pedido no hay líneas, total ni fecha.
    pedido = _pedido(datos, cliente, Mencion(texto="kola", skus=["B01"]), es_pedido=False)

    assert pedido == SIN_PEDIDO
    assert pedido.total == Decimal("0.00")
    assert pedido.fecha_entrega is None


def test_motor_lo_de_siempre_con_sustituto_y_agotado(datos, cliente):
    # Último pedido entregado: A07 (agotado, sustituto A06), P04 (agotado sin sustituto) y B04.
    pedido = _pedido(datos, cliente, lo_de_siempre=True)

    assert [(linea.sku, linea.cantidad) for linea in pedido.lineas] == [("A06", 1), ("B04", 3)]
    assert pedido.sustituciones == (Sustitucion("A07", "A06", 1),)
    assert pedido.pendientes == (
        Pendiente(Motivo.AGOTADO_SIN_SUSTITUTO, "Desodorante Fresco roll-on 50 ml", ("P04",)),
    )
    assert pedido.estado == Estado.REQUIERE_REVISION


def test_motor_lo_de_siempre_sin_el_agotado_queda_confirmado(datos, cliente):
    pedido = _pedido(
        datos,
        cliente,
        Mencion(texto="sin desodorante fresco", skus=["P04"], operacion="quitar"),
        Mencion(texto="2 papitas", skus=["S05"], cantidad=2),
        lo_de_siempre=True,
    )

    assert [(linea.sku, linea.cantidad) for linea in pedido.lineas] == [
        ("A06", 1),
        ("B04", 3),
        ("S05", 2),
    ]
    assert pedido.pendientes == ()
    assert pedido.estado == Estado.CONFIRMADO


def test_motor_una_correccion_reemplaza_y_otra_mencion_suma(datos, cliente):
    pedido = _pedido(
        datos,
        cliente,
        Mencion(texto="3 fardos de kola 600", skus=["B01"], cantidad=3),
        Mencion(texto="no, mejor que sean 5", skus=["B01"], cantidad=5, operacion="corregir"),
        Mencion(texto="y otro de kola 600", skus=["B01"], cantidad=1),
    )

    assert [(linea.sku, linea.cantidad) for linea in pedido.lineas] == [("B01", 6)]


def test_motor_una_correccion_vale_aunque_la_cantidad_anterior_no_se_pudiera_convertir(
    datos, cliente
):
    pedido = _pedido(
        datos,
        cliente,
        Mencion(texto="fardo y medio de kola 600", skus=["B01"], cantidad=1.5),
        Mencion(texto="no, mejor que sean 2", skus=["B01"], cantidad=2, operacion="corregir"),
    )

    assert [(linea.sku, linea.cantidad) for linea in pedido.lineas] == [("B01", 2)]
    assert pedido.pendientes == ()
    assert pedido.estado == Estado.CONFIRMADO


def test_motor_una_correccion_no_convertible_quita_la_cantidad_anterior(datos, cliente):
    pedido = _pedido(
        datos,
        cliente,
        Mencion(texto="3 fardos de kola 600", skus=["B01"], cantidad=3),
        Mencion(
            texto="no, mejor 36 botellas",
            skus=["B01"],
            cantidad=36,
            unidad="suelta",
            operacion="corregir",
        ),
    )

    assert pedido.lineas == ()
    assert pedido.pendientes == (
        Pendiente(Motivo.CANTIDAD_NO_CONVERTIBLE, "no, mejor 36 botellas", ("B01",)),
    )
    assert pedido.estado == Estado.REQUIERE_REVISION


def test_motor_una_correccion_de_un_producto_ambiguo_deja_un_solo_pendiente(datos, cliente):
    aceite = Pendiente(Motivo.PRODUCTO_AMBIGUO, "aceite", ("A06", "A07"))
    pedido = _pedido(
        datos,
        cliente,
        Mencion(texto="aceite", skus=["A06", "A07"], cantidad=0.5),
        Mencion(texto="aceite", skus=["A06", "A07"], cantidad=1, operacion="corregir"),
    )

    assert pedido.pendientes == (aceite,)


def test_motor_una_correccion_que_aclara_el_producto_confirma_el_pedido(datos, cliente):
    pedido = _pedido(
        datos,
        cliente,
        Mencion(texto="aceite", skus=["A06", "A07"], cantidad=2),
        Mencion(texto="del dorado", skus=["A06"], cantidad=3, operacion="corregir"),
    )

    assert [(linea.sku, linea.cantidad) for linea in pedido.lineas] == [("A06", 3)]
    assert pedido.pendientes == ()
    assert pedido.estado == Estado.CONFIRMADO


def test_motor_dos_menciones_ambiguas_sin_corregir_dejan_dos_pendientes(datos, cliente):
    # Sin corrección son dos pedidos del cliente; el asesor resuelve cada uno.
    pedido = _pedido(
        datos,
        cliente,
        Mencion(texto="aceite", skus=["A06", "A07"], cantidad=2),
        Mencion(texto="aceite", skus=["A06", "A07"], cantidad=3),
    )

    assert len(pedido.pendientes) == 2


def test_motor_una_mencion_especifica_sin_corregir_no_aclara_la_duda(datos, cliente):
    # Como D008, "pasta: 2, seis fardos de espagueti bella": la duda de "pasta" queda.
    pedido = _pedido(
        datos,
        cliente,
        Mencion(texto="naranjitas", skus=["B04", "B05"], cantidad=2),
        Mencion(texto="naranjita 1.5", skus=["B05"], cantidad=6),
    )

    assert [pendiente.motivo for pendiente in pedido.pendientes] == [Motivo.PRODUCTO_AMBIGUO]


def test_motor_credito_excedido_calcula_las_lineas_igual(datos, cliente):
    # 60 fardos × Q120 con 5 % = Q6,840; con Q1,200 de saldo supera el límite de Q8,000.
    pedido = _pedido(datos, cliente, Mencion(texto="60 kola 600", skus=["B01"], cantidad=60))

    assert pedido.lineas == (Linea("B01", 60, Decimal("120"), 5, Decimal("6840.00")),)
    assert pedido.motivos_revision == (Motivo.CREDITO_EXCEDIDO,)
    assert pedido.estado == Estado.REQUIERE_REVISION


def test_motor_solo_pendientes_requiere_revision_sin_lineas(datos, cliente):
    pedido = _pedido(datos, cliente, Mencion(texto="cerveza", skus=[], cantidad=5))

    assert pedido.lineas == ()
    assert pedido.total == Decimal("0.00")
    assert pedido.estado == Estado.REQUIERE_REVISION
    assert pedido.fecha_entrega == date(2026, 11, 26)


def test_motor_cantidad_no_convertible_es_pendiente(datos, cliente):
    pedido = _pedido(
        datos,
        cliente,
        Mencion(texto="36 botellas de kola 600", skus=["B01"], cantidad=36, unidad="suelta"),
    )

    assert pedido.pendientes == (
        Pendiente(Motivo.CANTIDAD_NO_CONVERTIBLE, "36 botellas de kola 600", ("B01",)),
    )
    assert pedido.lineas == ()


def test_motor_quitar_algo_ambiguo_del_pedido_es_pendiente(datos, cliente):
    pedido = _pedido(
        datos,
        cliente,
        Mencion(texto="naranjita 600", skus=["B04"], cantidad=1),
        Mencion(texto="naranjita 1.5", skus=["B05"], cantidad=1),
        Mencion(texto="sin las naranjitas", skus=["B04", "B05"], operacion="quitar"),
    )

    assert pedido.pendientes == (
        Pendiente(Motivo.PRODUCTO_AMBIGUO, "sin las naranjitas", ("B04", "B05")),
    )


def test_motor_pedido_que_se_queda_sin_nada_esta_fuera_de_alcance(datos, cliente):
    pedido = _pedido(
        datos,
        cliente,
        Mencion(texto="kola 600", skus=["B01"], cantidad=2),
        Mencion(texto="mejor no me mande la kola", skus=["B01"], operacion="quitar"),
    )

    assert pedido == SIN_PEDIDO


def test_motor_la_fecha_sale_de_la_solicitud_y_no_del_reloj(datos, cliente):
    interpretacion = Interpretacion(
        es_pedido=True, menciones=[Mencion(texto="kola", skus=["B01"], cantidad=1)]
    )

    pedido = armar_pedido(interpretacion, cliente, datetime(2030, 1, 7, 9, 0), datos)

    assert pedido.fecha_entrega == date(2030, 1, 10)
