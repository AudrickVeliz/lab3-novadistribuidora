from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from datos_de_prueba import escribir_parquet, tablas_validas
from novadistribuidora.datos import DatosInvalidos, cargar_datos

DATOS_PUBLICADOS = Path(__file__).resolve().parents[1] / "datos"


def test_carga_los_datos_con_sus_tipos(tmp_path):
    datos = cargar_datos(escribir_parquet(tmp_path, tablas_validas()))

    kola = datos.productos["B01"]
    assert kola.precio == Decimal("120.0")
    assert kola.unidades_por_empaque == 24
    assert kola.sustituto_sku is None
    assert datos.productos["B03"].sustituto_sku == "B02"
    assert datos.productos["B03"].disponible is False
    assert datos.sinonimos["B01"] == ("kola 600", "coca 600")
    assert [escala.descuento_pct for escala in datos.escalas["bebidas"]] == [3, 5]
    cliente = datos.clientes["C001"]
    assert cliente.dias_visita == {0, 3}
    assert cliente.limite_credito == Decimal("8000")
    assert datos.historial[0].fecha_entrega == date(2026, 10, 26)


def test_falla_si_falta_un_archivo(tmp_path):
    tablas = tablas_validas()
    del tablas["clientes"]

    with pytest.raises(DatosInvalidos, match=r"clientes\.parquet"):
        cargar_datos(escribir_parquet(tmp_path, tablas))


def test_falla_si_falta_una_columna(tmp_path):
    tablas = tablas_validas()
    tablas["productos"] = tablas["productos"].drop(columns="precio")

    with pytest.raises(DatosInvalidos, match="precio"):
        cargar_datos(escribir_parquet(tmp_path, tablas))


def test_falla_si_un_valor_obligatorio_esta_vacio(tmp_path):
    tablas = tablas_validas()
    tablas["productos"].loc[0, "precio"] = None

    with pytest.raises(DatosInvalidos, match="vacíos"):
        cargar_datos(escribir_parquet(tmp_path, tablas))


def test_falla_si_un_sku_se_repite(tmp_path):
    tablas = tablas_validas()
    tablas["productos"].loc[2, "sku"] = "B01"
    tablas["productos"].loc[1, "sustituto_sku"] = None

    with pytest.raises(DatosInvalidos, match="repite sku"):
        cargar_datos(escribir_parquet(tmp_path, tablas))


def test_falla_si_el_sustituto_no_esta_en_el_catalogo(tmp_path):
    tablas = tablas_validas()
    tablas["productos"].loc[1, "sustituto_sku"] = "Z99"

    with pytest.raises(DatosInvalidos, match="Z99"):
        cargar_datos(escribir_parquet(tmp_path, tablas))


def test_falla_si_un_sinonimo_nombra_un_sku_inexistente(tmp_path):
    tablas = tablas_validas()
    tablas["sinonimos"].loc[0, "sku"] = "Z99"

    with pytest.raises(DatosInvalidos, match="Z99"):
        cargar_datos(escribir_parquet(tmp_path, tablas))


def test_falla_si_un_empaque_no_tiene_unidades(tmp_path):
    tablas = tablas_validas()
    tablas["productos"].loc[0, "unidades_por_empaque"] = 0

    with pytest.raises(DatosInvalidos, match="unidades_por_empaque"):
        cargar_datos(escribir_parquet(tmp_path, tablas))


def test_falla_si_un_dia_de_visita_no_existe(tmp_path):
    tablas = tablas_validas()
    tablas["clientes"].loc[0, "dias_visita"] = "lunes,juebes"

    with pytest.raises(DatosInvalidos, match="juebes"):
        cargar_datos(escribir_parquet(tmp_path, tablas))


@pytest.mark.skipif(not DATOS_PUBLICADOS.is_dir(), reason="sin los datos publicados")
def test_carga_los_datos_publicados():
    datos = cargar_datos(DATOS_PUBLICADOS)

    assert len(datos.productos) == 44
    assert len(datos.clientes) == 40
    assert datos.productos["A07"].sustituto_sku == "A06"
