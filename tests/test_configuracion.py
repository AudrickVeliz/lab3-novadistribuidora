from pathlib import Path

import pytest

from novadistribuidora.configuracion import (
    ESFUERZO_POR_OMISION,
    MLFLOW_POR_OMISION,
    MODELO_ALTERNO_POR_OMISION,
    MODELO_POR_OMISION,
    TIEMPO_LIMITE_POR_OMISION_S,
    Configuracion,
    ConfiguracionInvalida,
)

CLAVE = "clave-de-prueba"


def test_con_solo_la_clave_usa_los_valores_de_env_example():
    configuracion = Configuracion.desde_entorno({"OPENROUTER_API_KEY": CLAVE})

    assert configuracion.modelo == MODELO_POR_OMISION
    assert configuracion.esfuerzo == ESFUERZO_POR_OMISION
    assert configuracion.modelo_alterno == MODELO_ALTERNO_POR_OMISION
    assert configuracion.carpeta_datos == Path("datos")
    assert configuracion.tiempo_limite_s == TIEMPO_LIMITE_POR_OMISION_S
    assert configuracion.mlflow_tracking_uri == MLFLOW_POR_OMISION


def test_los_valores_por_omision_coinciden_con_env_example():
    ejemplo = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")

    assert f"MODELO={MODELO_POR_OMISION}\n" in ejemplo
    assert f"MODELO_ALTERNO={MODELO_ALTERNO_POR_OMISION}\n" in ejemplo
    assert f"ESFUERZO_MODELO={ESFUERZO_POR_OMISION}\n" in ejemplo
    assert f"TIEMPO_LIMITE_MODELO_S={TIEMPO_LIMITE_POR_OMISION_S:g}\n" in ejemplo
    assert f"MLFLOW_TRACKING_URI={MLFLOW_POR_OMISION}\n" in ejemplo


def test_lee_cada_variable():
    configuracion = Configuracion.desde_entorno(
        {
            "OPENROUTER_API_KEY": CLAVE,
            "MODELO": "google/gemini-3.5-flash",
            "ESFUERZO_MODELO": "low",
            "MODELO_ALTERNO": "deepseek/deepseek-v4.1-flash",
            "CARPETA_DATOS": "/datos",
            "TIEMPO_LIMITE_MODELO_S": "7.5",
            "MLFLOW_TRACKING_URI": "http://mlflow:5000",
        }
    )

    assert configuracion.modelo == "google/gemini-3.5-flash"
    assert configuracion.esfuerzo == "low"
    assert configuracion.modelo_alterno == "deepseek/deepseek-v4.1-flash"
    assert configuracion.carpeta_datos == Path("/datos")
    assert configuracion.tiempo_limite_s == 7.5
    assert configuracion.mlflow_tracking_uri == "http://mlflow:5000"


def test_una_variable_vacia_cuenta_como_ausente():
    configuracion = Configuracion.desde_entorno({"OPENROUTER_API_KEY": CLAVE, "MODELO": "  "})

    assert configuracion.modelo == MODELO_POR_OMISION


@pytest.mark.parametrize("entorno", [{}, {"OPENROUTER_API_KEY": ""}, {"OPENROUTER_API_KEY": " "}])
def test_sin_clave_falla_con_el_motivo(entorno):
    with pytest.raises(ConfiguracionInvalida, match="OPENROUTER_API_KEY"):
        Configuracion.desde_entorno(entorno)


@pytest.mark.parametrize("valor", ["diez", "0", "-3"])
def test_tiempo_limite_invalido_falla_con_el_motivo(valor):
    with pytest.raises(ConfiguracionInvalida, match="TIEMPO_LIMITE_MODELO_S"):
        Configuracion.desde_entorno({"OPENROUTER_API_KEY": CLAVE, "TIEMPO_LIMITE_MODELO_S": valor})


def test_esfuerzo_proveedor_no_pide_ninguno():
    entorno = {"OPENROUTER_API_KEY": CLAVE, "ESFUERZO_MODELO": "proveedor"}

    assert Configuracion.desde_entorno(entorno).esfuerzo is None


@pytest.mark.parametrize("valor", ["alto", "MINIMAL", "none"])
def test_esfuerzo_invalido_falla_con_las_opciones(valor):
    with pytest.raises(ConfiguracionInvalida, match="ESFUERZO_MODELO debe ser low, minimal o"):
        Configuracion.desde_entorno({"OPENROUTER_API_KEY": CLAVE, "ESFUERZO_MODELO": valor})


def test_la_clave_no_aparece_al_imprimir_la_configuracion():
    configuracion = Configuracion.desde_entorno({"OPENROUTER_API_KEY": "sk-or-secreta"})

    assert "sk-or-secreta" not in repr(configuracion)
