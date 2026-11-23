"""Motor de reglas: de la interpretación del modelo al pedido, aplicando politicas.md en orden.

El orden importa (D-003): "lo de siempre" primero, luego cada mención en el orden del
mensaje (quitar antes de revisar agotados), sustitutos, precios, crédito, estado y fecha.
"""

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from novadistribuidora.datos import Cliente, Datos, Producto
from novadistribuidora.interpretacion import Interpretacion, Mencion
from novadistribuidora.pedido import Estado, Pedido, Pendiente
from novadistribuidora.politicas import (
    Cantidades,
    acumular_cantidad,
    aplicar_sustitutos,
    calcular_lineas,
    cantidad_en_unidades_de_venta,
    estado_pedido,
    excede_credito,
    fecha_entrega,
    lineas_de_siempre,
    motivos_revision,
    quitar_producto,
    resolver_producto,
    resolver_producto_a_quitar,
    total,
)

SIN_PEDIDO = Pedido(
    estado=Estado.FUERA_DE_ALCANCE,
    lineas=(),
    total=Decimal("0.00"),
    fecha_entrega=None,
    sustituciones=(),
    pendientes=(),
    motivos_revision=(),
)


def armar_pedido(
    interpretacion: Interpretacion, cliente: Cliente, recibido: datetime, datos: Datos
) -> Pedido:
    """Calcula el pedido completo. La fecha sale de `recibido`, nunca del reloj del sistema."""
    if not interpretacion.es_pedido:
        return SIN_PEDIDO
    cantidades: Cantidades = {}
    if interpretacion.lo_de_siempre:
        cantidades = lineas_de_siempre(datos.historial, cliente.cliente_id)
    pendientes: list[Pendiente] = []
    for mencion in interpretacion.menciones:
        cantidades, pendiente = _aplicar_mencion(cantidades, mencion, datos.productos)
        if pendiente is not None:
            pendientes.append(pendiente)

    entregables, sustituciones, agotados = aplicar_sustitutos(cantidades, datos.productos)
    pendientes += agotados
    lineas = calcular_lineas(entregables, datos.productos, datos.escalas)
    total_pedido = total(lineas)
    # Sin líneas no hay nada que cargar al crédito (D-004).
    credito_excedido = bool(lineas) and excede_credito(cliente, total_pedido)
    motivos = motivos_revision(pendientes, credito_excedido)
    estado = estado_pedido(True, lineas, motivos)
    if estado == Estado.FUERA_DE_ALCANCE:
        return SIN_PEDIDO
    return Pedido(
        estado=estado,
        lineas=tuple(lineas),
        total=total_pedido,
        fecha_entrega=fecha_entrega(recibido, cliente.dias_visita),
        sustituciones=tuple(sustituciones),
        pendientes=tuple(pendientes),
        motivos_revision=tuple(motivos),
    )


def _aplicar_mencion(
    cantidades: Cantidades, mencion: Mencion, productos: Mapping[str, Producto]
) -> tuple[Cantidades, Pendiente | None]:
    if mencion.operacion == "quitar":
        a_quitar = resolver_producto_a_quitar(mencion, cantidades)
        if isinstance(a_quitar, str):
            return quitar_producto(cantidades, a_quitar), None
        return cantidades, a_quitar
    sku = resolver_producto(mencion, productos)
    if isinstance(sku, Pendiente):
        return cantidades, sku
    cantidad = cantidad_en_unidades_de_venta(mencion, productos[sku])
    if isinstance(cantidad, Pendiente):
        return cantidades, cantidad
    corrige = mencion.operacion == "corregir"
    return acumular_cantidad(cantidades, sku, cantidad, corrige), None
