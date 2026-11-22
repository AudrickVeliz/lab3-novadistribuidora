import pytest
from pydantic import ValidationError

from novadistribuidora.interpretacion import Interpretacion, Mencion


def test_una_mencion_sin_cantidad_ni_unidad_toma_los_valores_por_omision():
    mencion = Mencion(texto="chicharritos", skus=["S04"])

    assert mencion.cantidad is None
    assert mencion.unidad == "venta"
    assert mencion.operacion == "agregar"


def test_un_mensaje_sin_productos_es_una_interpretacion_valida():
    interpretacion = Interpretacion.model_validate({"es_pedido": False})

    assert interpretacion.menciones == []
    assert interpretacion.lo_de_siempre is False


def test_regla_condiciones_el_modelo_no_puede_agregar_un_precio():
    with pytest.raises(ValidationError, match="precio"):
        Mencion.model_validate({"texto": "kola", "skus": ["B01"], "precio": 1})


def test_regla_condiciones_el_modelo_no_puede_agregar_un_descuento_al_pedido():
    with pytest.raises(ValidationError, match="descuento"):
        Interpretacion.model_validate({"es_pedido": True, "descuento": 50})


@pytest.mark.parametrize("cantidad", [0, -3])
def test_la_cantidad_debe_ser_positiva(cantidad):
    with pytest.raises(ValidationError):
        Mencion(texto="kola", skus=["B01"], cantidad=cantidad)


def test_la_unidad_solo_toma_los_valores_definidos():
    with pytest.raises(ValidationError):
        Mencion(texto="kola", skus=["B01"], unidad="paquete")
