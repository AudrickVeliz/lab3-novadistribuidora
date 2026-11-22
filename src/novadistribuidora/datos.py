"""Carga y valida los archivos publicados de `datos/`.

Se validan al cargar para que un archivo incompleto falle al arrancar el servicio,
con un mensaje que diga qué revisar, y no a mitad de un pedido (D-005).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

# Mismo número que date.weekday(): así la fecha de entrega se calcula sin traducir nombres.
DIAS_SEMANA = {
    "lunes": 0,
    "martes": 1,
    "miércoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sábado": 5,
    "domingo": 6,
}

COLUMNAS = {
    "productos": (
        "sku",
        "nombre",
        "categoria",
        "unidad_venta",
        "unidades_por_empaque",
        "precio",
        "disponible",
        "sustituto_sku",
    ),
    "precios_escala": ("categoria", "cantidad_minima", "descuento_pct"),
    "clientes": (
        "cliente_id",
        "nombre_tienda",
        "propietario",
        "dias_visita",
        "limite_credito",
        "saldo_pendiente",
    ),
    "historial_pedidos": ("pedido_id", "cliente_id", "fecha_entrega", "sku", "cantidad", "estado"),
}
# Un producto sin sustituto lo tiene vacío (politicas.md §4).
PUEDEN_ESTAR_VACIAS = {"sustituto_sku"}


class DatosInvalidos(Exception):
    """Un archivo publicado falta o no tiene la forma que esperan las políticas."""


@dataclass(frozen=True)
class Producto:
    sku: str
    nombre: str
    categoria: str
    unidad_venta: str
    unidades_por_empaque: int
    precio: Decimal
    disponible: bool
    sustituto_sku: str | None


@dataclass(frozen=True)
class Escala:
    cantidad_minima: int
    descuento_pct: int


@dataclass(frozen=True)
class Cliente:
    cliente_id: str
    nombre_tienda: str
    propietario: str
    dias_visita: frozenset[int]
    limite_credito: Decimal
    saldo_pendiente: Decimal


@dataclass(frozen=True)
class RegistroHistorial:
    pedido_id: str
    cliente_id: str
    fecha_entrega: date
    sku: str
    cantidad: int
    estado: str


@dataclass(frozen=True)
class Datos:
    productos: dict[str, Producto]
    escalas: dict[str, tuple[Escala, ...]]
    clientes: dict[str, Cliente]
    historial: tuple[RegistroHistorial, ...]


def cargar_datos(carpeta: Path) -> Datos:
    """Lee los cuatro parquet que usan las políticas. Lanza DatosInvalidos si algo no cuadra."""
    return Datos(
        productos=_productos(_leer(carpeta, "productos")),
        escalas=_escalas(_leer(carpeta, "precios_escala")),
        clientes=_clientes(_leer(carpeta, "clientes")),
        historial=_historial(_leer(carpeta, "historial_pedidos")),
    )


def _leer(carpeta: Path, nombre: str) -> pd.DataFrame:
    ruta = carpeta / f"{nombre}.parquet"
    if not ruta.is_file():
        raise DatosInvalidos(f"No existe {ruta}: coloca los archivos publicados en {carpeta}")
    tabla = pd.read_parquet(ruta)
    faltantes = [columna for columna in COLUMNAS[nombre] if columna not in tabla.columns]
    if faltantes:
        raise DatosInvalidos(f"{ruta} no tiene las columnas {faltantes}")
    vacias = [
        columna
        for columna in COLUMNAS[nombre]
        if columna not in PUEDEN_ESTAR_VACIAS and tabla[columna].isna().any()
    ]
    if vacias:
        raise DatosInvalidos(f"{ruta} tiene valores vacíos en {vacias}")
    return tabla


def _sin_repetidos(tabla: pd.DataFrame, columna: str, archivo: str) -> None:
    repetidos = sorted(tabla.loc[tabla[columna].duplicated(), columna].unique())
    if repetidos:
        raise DatosInvalidos(f"{archivo}.parquet repite {columna}: {repetidos}")


def _productos(tabla: pd.DataFrame) -> dict[str, Producto]:
    _sin_repetidos(tabla, "sku", "productos")
    productos = {
        fila.sku: Producto(
            sku=fila.sku,
            nombre=fila.nombre,
            categoria=fila.categoria,
            unidad_venta=fila.unidad_venta,
            unidades_por_empaque=int(fila.unidades_por_empaque),
            # str() evita arrastrar el error binario del float: 120.0 → Decimal("120.0").
            precio=Decimal(str(fila.precio)),
            disponible=bool(fila.disponible),
            sustituto_sku=None if pd.isna(fila.sustituto_sku) else fila.sustituto_sku,
        )
        for fila in tabla.itertuples(index=False)
    }
    for producto in productos.values():
        if producto.unidades_por_empaque < 1:
            raise DatosInvalidos(f"{producto.sku}: unidades_por_empaque debe ser al menos 1")
        if producto.sustituto_sku is not None and producto.sustituto_sku not in productos:
            raise DatosInvalidos(
                f"{producto.sku}: el sustituto {producto.sustituto_sku} no está en el catálogo"
            )
    return productos


def _escalas(tabla: pd.DataFrame) -> dict[str, tuple[Escala, ...]]:
    escalas: dict[str, list[Escala]] = {}
    for fila in tabla.itertuples(index=False):
        escala = Escala(int(fila.cantidad_minima), int(fila.descuento_pct))
        escalas.setdefault(fila.categoria, []).append(escala)
    return {categoria: tuple(lista) for categoria, lista in escalas.items()}


def _clientes(tabla: pd.DataFrame) -> dict[str, Cliente]:
    _sin_repetidos(tabla, "cliente_id", "clientes")
    return {
        fila.cliente_id: Cliente(
            cliente_id=fila.cliente_id,
            nombre_tienda=fila.nombre_tienda,
            propietario=fila.propietario,
            dias_visita=_dias_visita(fila.cliente_id, fila.dias_visita),
            limite_credito=Decimal(str(fila.limite_credito)),
            saldo_pendiente=Decimal(str(fila.saldo_pendiente)),
        )
        for fila in tabla.itertuples(index=False)
    }


def _dias_visita(cliente_id: str, texto: str) -> frozenset[int]:
    nombres = [nombre.strip().lower() for nombre in texto.split(",") if nombre.strip()]
    desconocidos = [nombre for nombre in nombres if nombre not in DIAS_SEMANA]
    if not nombres or desconocidos:
        raise DatosInvalidos(
            f"{cliente_id}: dias_visita '{texto}' debe listar días de {list(DIAS_SEMANA)}"
        )
    return frozenset(DIAS_SEMANA[nombre] for nombre in nombres)


def _historial(tabla: pd.DataFrame) -> tuple[RegistroHistorial, ...]:
    return tuple(
        RegistroHistorial(
            pedido_id=fila.pedido_id,
            cliente_id=fila.cliente_id,
            fecha_entrega=pd.Timestamp(fila.fecha_entrega).date(),
            sku=fila.sku,
            cantidad=int(fila.cantidad),
            estado=fila.estado,
        )
        for fila in tabla.itertuples(index=False)
    )
