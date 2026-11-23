"""Catálogo mínimo para las pruebas de políticas: los mismos SKU y valores que los datos publicados,
para que cada caso se pueda contrastar con politicas.md sin depender de los archivos."""

from datetime import date
from decimal import Decimal

import pytest

from novadistribuidora.datos import Cliente, Datos, Escala, Producto, RegistroHistorial

# Unidad de venta de los SKU que no se venden por fardo, como en productos.parquet.
UNIDADES = {
    "A02": "quintal",
    "A06": "caja",
    "A07": "caja",
    "L03": "caja",
    "P04": "caja",
    "S02": "display",
    "S05": "display",
    "X01": "display",
}


def _producto(sku, nombre, categoria, empaque, precio, disponible=True, sustituto=None):
    return Producto(
        sku=sku,
        nombre=nombre,
        categoria=categoria,
        unidad_venta=UNIDADES.get(sku, "fardo"),
        unidades_por_empaque=empaque,
        precio=Decimal(precio),
        disponible=disponible,
        sustituto_sku=sustituto,
    )


@pytest.fixture
def productos():
    lista = [
        _producto("B01", "Kola Norte 600 ml", "bebidas", 24, "120"),
        _producto("B02", "Kola Norte 1.5 L", "bebidas", 12, "144"),
        _producto("B03", "Kola Norte 3 L", "bebidas", 6, "132", disponible=False, sustituto="B02"),
        _producto("B04", "Naranjita 600 ml", "bebidas", 24, "110"),
        _producto("B05", "Naranjita 1.5 L", "bebidas", 12, "132"),
        _producto("A02", "Arroz La Ceiba quintal", "abarrotes", 1, "480"),
        _producto("A06", "Aceite Girasol Dorado 750 ml", "abarrotes", 12, "228"),
        _producto("A07", "Aceite Palma Real 750 ml", "abarrotes", 12, "192", False, "A06"),
        _producto("L03", "Cloro Blancura 1 L", "limpieza", 12, "108"),
        _producto("P04", "Desodorante Fresco roll-on 50 ml", "cuidado_personal", 12, "216", False),
        _producto("S02", "Galletas Dulcitas Chocolate", "snacks", 12, "48", False),
        _producto("S05", "Papitas Doradas 40 g", "snacks", 12, "48"),
        # Sustituto que también está agotado: no existe en los datos publicados (D-004).
        _producto("X01", "Producto de prueba", "snacks", 12, "10", False, "S02"),
    ]
    return {producto.sku: producto for producto in lista}


@pytest.fixture
def escalas():
    return {
        "bebidas": (Escala(10, 3), Escala(20, 5)),
        "abarrotes": (Escala(5, 2), Escala(10, 4)),
    }


@pytest.fixture
def cliente():
    # Ruta de lunes y jueves (0 y 3), con Q6,800 de crédito disponible.
    return Cliente(
        "C001",
        "Tienda La Bendición",
        "Marta López",
        frozenset({0, 3}),
        Decimal(8000),
        Decimal(1200),
    )


@pytest.fixture
def datos(productos, escalas, cliente):
    historial = (
        RegistroHistorial("PED-1", "C001", date(2026, 11, 16), "B01", 2, "entregado"),
        RegistroHistorial("PED-2", "C001", date(2026, 11, 19), "A07", 1, "entregado"),
        RegistroHistorial("PED-2", "C001", date(2026, 11, 19), "P04", 2, "entregado"),
        RegistroHistorial("PED-2", "C001", date(2026, 11, 19), "B04", 3, "entregado"),
    )
    return Datos(productos, escalas, {cliente.cliente_id: cliente}, historial)
