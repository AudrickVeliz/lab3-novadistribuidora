from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from novadistribuidora.datos import DatosInvalidos, cargar_datos

DATOS_PUBLICADOS = Path(__file__).resolve().parents[1] / "datos"


def _tablas_validas() -> dict[str, pd.DataFrame]:
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


def _escribir(carpeta: Path, tablas: dict[str, pd.DataFrame]) -> Path:
    for nombre, tabla in tablas.items():
        tabla.to_parquet(carpeta / f"{nombre}.parquet", index=False)
    return carpeta


def test_carga_los_datos_con_sus_tipos(tmp_path):
    datos = cargar_datos(_escribir(tmp_path, _tablas_validas()))

    kola = datos.productos["B01"]
    assert kola.precio == Decimal("120.0")
    assert kola.unidades_por_empaque == 24
    assert kola.sustituto_sku is None
    assert datos.productos["B03"].sustituto_sku == "B02"
    assert datos.productos["B03"].disponible is False
    assert [escala.descuento_pct for escala in datos.escalas["bebidas"]] == [3, 5]
    cliente = datos.clientes["C001"]
    assert cliente.dias_visita == {0, 3}
    assert cliente.limite_credito == Decimal("8000")
    assert datos.historial[0].fecha_entrega == date(2026, 10, 26)


def test_falla_si_falta_un_archivo(tmp_path):
    tablas = _tablas_validas()
    del tablas["clientes"]

    with pytest.raises(DatosInvalidos, match=r"clientes\.parquet"):
        cargar_datos(_escribir(tmp_path, tablas))


def test_falla_si_falta_una_columna(tmp_path):
    tablas = _tablas_validas()
    tablas["productos"] = tablas["productos"].drop(columns="precio")

    with pytest.raises(DatosInvalidos, match="precio"):
        cargar_datos(_escribir(tmp_path, tablas))


def test_falla_si_un_valor_obligatorio_esta_vacio(tmp_path):
    tablas = _tablas_validas()
    tablas["productos"].loc[0, "precio"] = None

    with pytest.raises(DatosInvalidos, match="vacíos"):
        cargar_datos(_escribir(tmp_path, tablas))


def test_falla_si_un_sku_se_repite(tmp_path):
    tablas = _tablas_validas()
    tablas["productos"].loc[2, "sku"] = "B01"
    tablas["productos"].loc[1, "sustituto_sku"] = None

    with pytest.raises(DatosInvalidos, match="repite sku"):
        cargar_datos(_escribir(tmp_path, tablas))


def test_falla_si_el_sustituto_no_esta_en_el_catalogo(tmp_path):
    tablas = _tablas_validas()
    tablas["productos"].loc[1, "sustituto_sku"] = "Z99"

    with pytest.raises(DatosInvalidos, match="Z99"):
        cargar_datos(_escribir(tmp_path, tablas))


def test_falla_si_un_empaque_no_tiene_unidades(tmp_path):
    tablas = _tablas_validas()
    tablas["productos"].loc[0, "unidades_por_empaque"] = 0

    with pytest.raises(DatosInvalidos, match="unidades_por_empaque"):
        cargar_datos(_escribir(tmp_path, tablas))


def test_falla_si_un_dia_de_visita_no_existe(tmp_path):
    tablas = _tablas_validas()
    tablas["clientes"].loc[0, "dias_visita"] = "lunes,juebes"

    with pytest.raises(DatosInvalidos, match="juebes"):
        cargar_datos(_escribir(tmp_path, tablas))


@pytest.mark.skipif(not DATOS_PUBLICADOS.is_dir(), reason="sin los datos publicados")
def test_carga_los_datos_publicados():
    datos = cargar_datos(DATOS_PUBLICADOS)

    assert len(datos.productos) == 44
    assert len(datos.clientes) == 40
    assert datos.productos["A07"].sustituto_sku == "A06"
