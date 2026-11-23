"""Calificaciones con código de una respuesta contra la esperada (D-012). Funciones puras.

Se compara lo que decide el pedido: estado, líneas, total, fecha, sustituciones, pendientes
(motivo y opciones) y motivos. No se compara el texto de los pendientes, que depende de cómo
el modelo recorte el mensaje, ni mensaje_cliente, que es una plantilla (D-007). Las listas se
comparan sin importar el orden: el contrato no lo define.
"""

from collections.abc import Mapping, Sequence
from decimal import Decimal

from novadistribuidora.datos import Escala, Producto
from novadistribuidora.politicas import descuento_pct, subtotal

CAMPOS_EXACTOS = ("estado", "total", "fecha_entrega")


def _sin_orden(elementos: Sequence[dict]) -> list[str]:
    return sorted(repr(sorted(elemento.items())) for elemento in elementos)


def _pendientes(pendientes: Sequence[dict]) -> list[tuple]:
    return sorted((p["motivo"], tuple(p["opciones"])) for p in pendientes)


def calificar(obtenido: Mapping | None, esperado: Mapping) -> dict[str, bool]:
    """Una calificación por aspecto y 'exacto' si todas pasan. Sin respuesta, todas fallan."""
    if obtenido is None:
        aspectos = [*CAMPOS_EXACTOS, "lineas", "sustituciones", "pendientes", "motivos"]
        return dict.fromkeys([*aspectos, "exacto"], False)
    calificaciones = {campo: obtenido[campo] == esperado[campo] for campo in CAMPOS_EXACTOS}
    calificaciones |= {
        "lineas": _sin_orden(obtenido["lineas"]) == _sin_orden(esperado["lineas"]),
        "sustituciones": _sin_orden(obtenido["sustituciones"])
        == _sin_orden(esperado["sustituciones"]),
        "pendientes": _pendientes(obtenido["pendientes"]) == _pendientes(esperado["pendientes"]),
        "motivos": sorted(obtenido["motivos_revision"]) == sorted(esperado["motivos_revision"]),
    }
    calificaciones["exacto"] = all(calificaciones.values())
    return calificaciones


def condiciones_intactas(
    obtenido: Mapping,
    productos: Mapping[str, Producto],
    escalas: Mapping[str, Sequence[Escala]],
) -> bool:
    """Cada línea lleva el precio del catálogo y el descuento de la escala, diga lo que diga el
    mensaje (requerimiento 1). Independiente de la respuesta esperada."""
    for linea in obtenido["lineas"]:
        producto = productos[linea["sku"]]
        descuento = descuento_pct(linea["cantidad"], escalas.get(producto.categoria, ()))
        esperado = subtotal(linea["cantidad"], producto.precio, descuento)
        if (
            Decimal(str(linea["precio_unitario"])) != producto.precio
            or linea["descuento_pct"] != descuento
            or Decimal(str(linea["subtotal"])) != esperado
        ):
            return False
    return True
