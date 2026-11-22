"""Las reglas de politicas.md, una función por regla y con la sección que implementa.

Son funciones puras: no leen archivos, no llaman al modelo ni consultan el reloj. Las
cantidades de un pedido en construcción son un dict sku → unidades de venta cuyo orden
es el de aparición, que es el orden de las líneas en la respuesta (D-003).
"""

from collections.abc import Iterable, Mapping

from novadistribuidora.datos import Producto, RegistroHistorial
from novadistribuidora.interpretacion import Mencion
from novadistribuidora.pedido import Motivo, Pendiente, Sustitucion

Cantidades = dict[str, int]

UNIDADES_POR_DOCENA = 12
ESTADO_ENTREGADO = "entregado"


def _skus_del_catalogo(skus: Iterable[str], catalogo: Iterable[str]) -> tuple[str, ...]:
    """Normaliza lo que propone el modelo y descarta lo que no está en el catálogo (§1)."""
    validos = set(catalogo)
    return tuple(sorted({sku.strip().upper() for sku in skus} & validos))


def resolver_producto(mencion: Mencion, productos: Mapping[str, Producto]) -> str | Pendiente:
    """§1: un solo SKU del catálogo, o un pendiente si es ambiguo o no se vende. Nunca se elige."""
    opciones = _skus_del_catalogo(mencion.skus, productos)
    if len(opciones) == 1:
        return opciones[0]
    if not opciones:
        return Pendiente(Motivo.PRODUCTO_NO_EXISTE, mencion.texto, ())
    return Pendiente(Motivo.PRODUCTO_AMBIGUO, mencion.texto, opciones)


def resolver_producto_a_quitar(mencion: Mencion, cantidades: Cantidades) -> str | Pendiente | None:
    """§2: "sin las papitas" se refiere a lo que ya está en el pedido (D-004).

    None si ninguno de los candidatos está en el pedido: no hay nada que quitar.
    """
    en_pedido = _skus_del_catalogo(mencion.skus, cantidades)
    if len(en_pedido) == 1:
        return en_pedido[0]
    if not en_pedido:
        return None
    return Pendiente(Motivo.PRODUCTO_AMBIGUO, mencion.texto, en_pedido)


def cantidad_en_unidades_de_venta(mencion: Mencion, producto: Producto) -> int | Pendiente:
    """§2: sin cantidad es 1 unidad de venta; sueltas y docenas solo si la conversión es exacta."""
    if mencion.cantidad is None:
        return 1
    if mencion.unidad == "venta":
        return mencion.cantidad
    por_unidad = UNIDADES_POR_DOCENA if mencion.unidad == "docena" else 1
    sueltas = mencion.cantidad * por_unidad
    if sueltas % producto.unidades_por_empaque:
        return Pendiente(Motivo.CANTIDAD_NO_CONVERTIBLE, mencion.texto, (producto.sku,))
    return sueltas // producto.unidades_por_empaque


def acumular_cantidad(cantidades: Cantidades, sku: str, cantidad: int, corrige: bool) -> Cantidades:
    """§2: las menciones repetidas se suman; una corrección reemplaza la cantidad anterior."""
    nuevas = dict(cantidades)
    nuevas[sku] = cantidad if corrige else nuevas.get(sku, 0) + cantidad
    return nuevas


def quitar_producto(cantidades: Cantidades, sku: str) -> Cantidades:
    """§2: "pero sin las papalinas" elimina la línea."""
    return {actual: cantidad for actual, cantidad in cantidades.items() if actual != sku}


def lineas_de_siempre(historial: Iterable[RegistroHistorial], cliente_id: str) -> Cantidades:
    """§3: las líneas del último pedido entregado del cliente; los cancelados no cuentan.

    "Último" es la fecha de entrega más reciente; el pedido_id desempata (D-003).
    """
    entregados = [
        registro
        for registro in historial
        if registro.cliente_id == cliente_id and registro.estado == ESTADO_ENTREGADO
    ]
    if not entregados:
        return {}
    ultimo = max((registro.fecha_entrega, registro.pedido_id) for registro in entregados)
    cantidades: Cantidades = {}
    for registro in entregados:
        if (registro.fecha_entrega, registro.pedido_id) == ultimo:
            cantidades[registro.sku] = cantidades.get(registro.sku, 0) + registro.cantidad
    return cantidades


def aplicar_sustitutos(
    cantidades: Cantidades, productos: Mapping[str, Producto]
) -> tuple[Cantidades, list[Sustitucion], list[Pendiente]]:
    """§4: un agotado se cambia por su sustituto disponible, con la misma cantidad.

    El sustituto ocupa el lugar del agotado o se suma a su propia línea si ya estaba
    pedida (D-003). Sin sustituto disponible queda un pendiente con el nombre del catálogo.
    """
    entregables: Cantidades = {}
    sustituciones: list[Sustitucion] = []
    pendientes: list[Pendiente] = []
    for sku, cantidad in cantidades.items():
        producto = productos[sku]
        sustituto = _sustituto_disponible(producto, productos)
        if producto.disponible:
            entregado = sku
        elif sustituto is not None:
            entregado = sustituto
            sustituciones.append(Sustitucion(sku, sustituto, cantidad))
        else:
            pendientes.append(Pendiente(Motivo.AGOTADO_SIN_SUSTITUTO, producto.nombre, (sku,)))
            continue
        entregables[entregado] = entregables.get(entregado, 0) + cantidad
    return entregables, sustituciones, pendientes


def _sustituto_disponible(producto: Producto, productos: Mapping[str, Producto]) -> str | None:
    """Un sustituto que también está agotado no sirve: el pedido va a revisión (D-004)."""
    if producto.sustituto_sku is None or not productos[producto.sustituto_sku].disponible:
        return None
    return producto.sustituto_sku
