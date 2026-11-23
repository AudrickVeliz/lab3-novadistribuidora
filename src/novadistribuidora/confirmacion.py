"""mensaje_cliente: la confirmación para el tendero, redactada por plantilla (D-007).

Solo usa datos del pedido calculado y del catálogo: nombres de productos, cantidades, el
total y la fecha. Nunca copia texto del cliente, así que un mensaje no puede hacer que la
confirmación prometa un precio, un descuento o un producto que el pedido no tiene (§9).
"""

from collections.abc import Mapping, Sequence
from datetime import date, datetime, time

from novadistribuidora.datos import Producto
from novadistribuidora.pedido import Estado, Linea, Motivo, Pedido, Pendiente, Sustitucion

DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
FIN_DE_LA_MANANA = time(12, 0)
FIN_DE_LA_TARDE = time(19, 0)


def redactar_confirmacion(
    pedido: Pedido, productos: Mapping[str, Producto], recibido: datetime
) -> str:
    """Saludo, lo que se entrega, lo que cambia o queda pendiente, y la fecha (§9)."""
    if pedido.estado == Estado.FUERA_DE_ALCANCE:
        return (
            f"{_saludo(recibido)} Gracias por escribirnos. No encontramos un pedido en su "
            "mensaje; un asesor le responderá a la brevedad."
        )
    frases = [_saludo(recibido), _recibido(pedido.lineas, productos)]
    frases += [_sustitucion(sustitucion, productos) for sustitucion in pedido.sustituciones]
    frases += _pendientes(pedido.pendientes, productos)
    if pedido.estado == Estado.CONFIRMADO:
        frases.append(f"Total: Q{pedido.total:,.2f}.")
    else:
        frases.append("Un asesor revisará su pedido y se lo confirmará.")
    if pedido.lineas and pedido.fecha_entrega is not None:
        frases.append(f"Entrega el {_fecha_larga(pedido.fecha_entrega)}.")
    frases.append("¡Gracias!")
    return " ".join(frases)


def _saludo(recibido: datetime) -> str:
    if recibido.time() < FIN_DE_LA_MANANA:
        return "¡Buenos días!"
    if recibido.time() < FIN_DE_LA_TARDE:
        return "¡Buenas tardes!"
    return "¡Buenas noches!"


def _recibido(lineas: Sequence[Linea], productos: Mapping[str, Producto]) -> str:
    if not lineas:
        return "Recibimos su mensaje."
    return f"Recibimos su pedido: {_enumerar([_linea(linea, productos) for linea in lineas])}."


def _linea(linea: Linea, productos: Mapping[str, Producto]) -> str:
    producto = productos[linea.sku]
    unidad = producto.unidad_venta if linea.cantidad == 1 else _plural(producto.unidad_venta)
    return f"{linea.cantidad} {unidad} de {producto.nombre}"


def _sustitucion(sustitucion: Sustitucion, productos: Mapping[str, Producto]) -> str:
    agotado = productos[sustitucion.sku_solicitado].nombre
    entregado = productos[sustitucion.sku_entregado].nombre
    return f"Por ahora no tenemos {agotado}; en su lugar le enviamos {entregado}."


def _pendientes(pendientes: Sequence[Pendiente], productos: Mapping[str, Producto]) -> list[str]:
    frases = []
    for pendiente in pendientes:
        nombres = [productos[sku].nombre for sku in pendiente.opciones]
        if pendiente.motivo == Motivo.PRODUCTO_AMBIGUO:
            frases.append(f"Necesitamos confirmar si desea {_enumerar(nombres, 'o')}.")
        elif pendiente.motivo == Motivo.AGOTADO_SIN_SUSTITUTO:
            frases.append(f"Por ahora no tenemos {nombres[0]}.")
        elif pendiente.motivo == Motivo.CANTIDAD_NO_CONVERTIBLE:
            frases.append(f"La cantidad de {nombres[0]} no corresponde a empaques completos.")
    no_vendidos = sum(p.motivo == Motivo.PRODUCTO_NO_EXISTE for p in pendientes)
    if no_vendidos:
        frases.append(
            "Uno de los productos que mencionó no está en nuestro catálogo."
            if no_vendidos == 1
            else f"{no_vendidos} de los productos que mencionó no están en nuestro catálogo."
        )
    return frases


def _plural(unidad: str) -> str:
    """fardo → fardos, caja → cajas, display → displays, quintal → quintales."""
    return f"{unidad}s" if unidad[-1] in "aeiouy" else f"{unidad}es"


def _enumerar(elementos: Sequence[str], conjuncion: str = "y") -> str:
    if len(elementos) == 1:
        return elementos[0]
    return f"{', '.join(elementos[:-1])} {conjuncion} {elementos[-1]}"


def _fecha_larga(fecha: date) -> str:
    return f"{DIAS[fecha.weekday()]} {fecha.day} de {MESES[fecha.month - 1]}"
