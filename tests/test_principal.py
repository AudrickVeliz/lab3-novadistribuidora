"""Arranque del servicio desde el entorno, como lo hace uvicorn, sin llamar al modelo."""

import pytest
from fastapi.testclient import TestClient

from datos_de_prueba import escribir_parquet, tablas_validas
from novadistribuidora.configuracion import ConfiguracionInvalida
from novadistribuidora.datos import DatosInvalidos
from novadistribuidora.principal import crear_app_desde_entorno


def test_arranca_con_la_clave_y_los_datos(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("CARPETA_DATOS", str(escribir_parquet(tmp_path, tablas_validas())))

    respuesta = TestClient(crear_app_desde_entorno()).get("/health")

    assert respuesta.json() == {"estado": "ok"}


def test_sin_clave_no_arranca(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ConfiguracionInvalida, match="OPENROUTER_API_KEY"):
        crear_app_desde_entorno()


def test_sin_datos_publicados_no_arranca(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("CARPETA_DATOS", str(tmp_path))

    with pytest.raises(DatosInvalidos, match=r"productos\.parquet"):
        crear_app_desde_entorno()
