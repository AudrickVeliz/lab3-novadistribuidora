"""Las reglas de politicas.md, una función por regla y con la sección que implementa.

Son funciones puras: no leen archivos, no llaman al modelo ni consultan el reloj. Las
cantidades de un pedido en construcción son un dict sku → unidades de venta cuyo orden
es el de aparición, que es el orden de las líneas en la respuesta (D-003).
"""

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from novadistribuidora.datos import Cliente, Escala, Producto, RegistroHistorial
from novadistribuidora.interpretacion import Mencion, Unidad
from novadistribuidora.pedido import Estado, Linea, Motivo, Pendiente, Sustitucion

Cantidades = dict[str, int]

UNIDADES_POR_DOCENA = 12
ESTADO_ENTREGADO = "entregado"
CENTAVOS = Decimal("0.01")
HORA_CORTE = time(14, 0)
DIAS_POR_SEMANA = 7


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
    """§2: sin cantidad es 1 unidad de venta; lo demás, solo si da unidades de venta enteras.

    Todo se lleva a sueltas, así que "fardo y medio" o "media caja" tampoco se redondean (D-015).
    """
    if mencion.cantidad is None:
        return 1
    # str() evita el error binario del float: 1.5 llega como Decimal("1.5").
    sueltas = Decimal(str(mencion.cantidad)) * _sueltas_por_unidad(mencion.unidad, producto)
    unidades, resto = divmod(sueltas, producto.unidades_por_empaque)
    if resto:
        return Pendiente(Motivo.CANTIDAD_NO_CONVERTIBLE, mencion.texto, (producto.sku,))
    return int(unidades)


def _sueltas_por_unidad(unidad: Unidad, producto: Producto) -> int:
    if unidad == "venta":
        return producto.unidades_por_empaque
    return UNIDADES_POR_DOCENA if unidad == "docena" else 1


def acumular_cantidad(cantidades: Cantidades, sku: str, cantidad: int, corrige: bool) -> Cantidades:
    """§2: las menciones repetidas se suman; una corrección reemplaza la cantidad anterior."""
    nuevas = dict(cantidades)
    nuevas[sku] = cantidad if corrige else nuevas.get(sku, 0) + cantidad
    return nuevas


def descartar_cantidades_corregidas(pendientes: Sequence[Pendiente], sku: str) -> list[Pendiente]:
    """§2: vale la corrección; la cantidad que el producto no pudo convertir antes ya no cuenta."""
    corregido = (Motivo.CANTIDAD_NO_CONVERTIBLE, (sku,))
    return [p for p in pendientes if (p.motivo, p.opciones) != corregido]


def agregar_pendiente_corregido(
    pendientes: Sequence[Pendiente], pendiente: Pendiente
) -> list[Pendiente]:
    """§2: vale la corrección; si repite la duda de la mención anterior, el asesor la ve una vez."""
    if any(_misma_duda(anterior, pendiente) for anterior in pendientes):
        return list(pendientes)
    return [*pendientes, pendiente]


def _misma_duda(anterior: Pendiente, nuevo: Pendiente) -> bool:
    # Las opciones identifican la duda; sin opciones (producto inexistente), solo queda el texto.
    misma_duda = (anterior.motivo, anterior.opciones) == (nuevo.motivo, nuevo.opciones)
    return misma_duda and (bool(nuevo.opciones) or anterior.texto == nuevo.texto)


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


def descuento_pct(cantidad: int, escalas: Sequence[Escala]) -> int:
    """§5: el mayor porcentaje de la categoría cuyo mínimo alcanza la cantidad de la línea."""
    return max(
        (escala.descuento_pct for escala in escalas if cantidad >= escala.cantidad_minima),
        default=0,
    )


def subtotal(cantidad: int, precio: Decimal, descuento: int) -> Decimal:
    """§5: cantidad × precio × (1 − descuento/100), a 2 decimales con mitad hacia arriba."""
    bruto = cantidad * precio * (1 - Decimal(descuento) / 100)
    return bruto.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def calcular_lineas(
    cantidades: Cantidades,
    productos: Mapping[str, Producto],
    escalas: Mapping[str, Sequence[Escala]],
) -> list[Linea]:
    """§5: precio del catálogo y descuento por escala; nada viene del mensaje."""
    lineas = []
    for sku, cantidad in cantidades.items():
        producto = productos[sku]
        descuento = descuento_pct(cantidad, escalas.get(producto.categoria, ()))
        lineas.append(
            Linea(
                sku=sku,
                cantidad=cantidad,
                precio_unitario=producto.precio,
                descuento_pct=descuento,
                subtotal=subtotal(cantidad, producto.precio, descuento),
            )
        )
    return lineas


def total(lineas: Iterable[Linea]) -> Decimal:
    """§5: la suma de los subtotales ya redondeados."""
    return sum((linea.subtotal for linea in lineas), Decimal("0.00"))


def excede_credito(cliente: Cliente, total_pedido: Decimal) -> bool:
    """§6: saldo pendiente + total por encima del límite manda el pedido a revisión."""
    return cliente.saldo_pendiente + total_pedido > cliente.limite_credito


def fecha_entrega(recibido: datetime, dias_visita: frozenset[int]) -> date:
    """§7: primera visita de la ruta estrictamente posterior a la recepción.

    Recibido a las 14:00 o después, cuenta como recibido al día siguiente. Sin feriados.
    """
    recepcion = recibido.date()
    if recibido.time() >= HORA_CORTE:
        recepcion += timedelta(days=1)
    for dias in range(1, DIAS_POR_SEMANA + 1):
        candidata = recepcion + timedelta(days=dias)
        if candidata.weekday() in dias_visita:
            return candidata
    raise ValueError("El cliente no tiene días de visita: revisa dias_visita en clientes.parquet")


def motivos_revision(pendientes: Iterable[Pendiente], credito_excedido: bool) -> list[Motivo]:
    """§8: un motivo por tipo, en el orden en que aparecen; el crédito va al final (D-004)."""
    motivos = list(dict.fromkeys(pendiente.motivo for pendiente in pendientes))
    if credito_excedido:
        motivos.append(Motivo.CREDITO_EXCEDIDO)
    return motivos


def estado_pedido(es_pedido: bool, lineas: Sequence[Linea], motivos: Sequence[Motivo]) -> Estado:
    """§8: fuera de alcance si no hay pedido; revisión si hay algún motivo; si no, confirmado.

    Un pedido que se queda sin líneas y sin motivos (p. ej., quitó todo) no tiene nada que
    entregar ni revisar: se trata como fuera de alcance (D-004).
    """
    if not es_pedido:
        return Estado.FUERA_DE_ALCANCE
    if motivos:
        return Estado.REQUIERE_REVISION
    if lineas:
        return Estado.CONFIRMADO
    return Estado.FUERA_DE_ALCANCE
