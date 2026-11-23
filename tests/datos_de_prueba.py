"""Archivos publicados mínimos y válidos, escritos como parquet en una carpeta de prueba."""

from pathlib import Path

import pandas as pd


def tablas_validas() -> dict[str, pd.DataFrame]:
    return {
        "productos": pd.DataFrame(
            {
                "sku": ["B01", "B03", "B02"],
                "nombre": ["Kola Norte 600 ml", "Kola Norte 3 L", "Kola Norte 1.5 L"],
                "marca": ["Kola Norte"] * 3,
                "categoria": ["bebidas"] * 3,
                "presentacion": ["600 ml", "3 L", "1.5 L"],
                "unidad_venta": ["fardo"] * 3,
                "unidades_por_empaque": [24, 6, 12],
                "precio": [120.0, 132.0, 144.0],
                "disponible": [True, False, True],
                "sustituto_sku": [None, "B02", None],
            }
        ),
        "sinonimos": pd.DataFrame(
            {
                "sku": ["B01", "B01", "B02"],
                "alias": ["kola 600", "coca 600", "kola de litro y medio"],
            }
        ),
        "precios_escala": pd.DataFrame(
            {
                "categoria": ["bebidas", "bebidas"],
                "cantidad_minima": [10, 20],
                "descuento_pct": [3, 5],
            }
        ),
        "clientes": pd.DataFrame(
            {
                "cliente_id": ["C001"],
                "nombre_tienda": ["Tienda La Bendición"],
                "propietario": ["Marta López"],
                "municipio": ["Mixco"],
                "dias_visita": ["lunes,jueves"],
                "limite_credito": [8000],
                "saldo_pendiente": [1200],
            }
        ),
        "historial_pedidos": pd.DataFrame(
            {
                "pedido_id": ["PED-00001"],
                "cliente_id": ["C001"],
                "fecha_entrega": pd.to_datetime(["2026-10-26"]),
                "sku": ["B01"],
                "cantidad": [2],
                "estado": ["entregado"],
            }
        ),
    }


def escribir_parquet(carpeta: Path, tablas: dict[str, pd.DataFrame]) -> Path:
    for nombre, tabla in tablas.items():
        tabla.to_parquet(carpeta / f"{nombre}.parquet", index=False)
    return carpeta
