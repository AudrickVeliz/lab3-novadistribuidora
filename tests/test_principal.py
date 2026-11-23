"""Arranque del servicio desde el entorno, como lo hace uvicorn, sin llamar al modelo."""

import threading

import mlflow
import pytest
from fastapi.testclient import TestClient

from datos_de_prueba import escribir_parquet, tablas_validas
from novadistribuidora import trazas
from novadistribuidora.configuracion import ConfiguracionInvalida
from novadistribuidora.datos import DatosInvalidos
from novadistribuidora.principal import crear_app_desde_entorno


@pytest.fixture
def entorno_completo(tmp_path, monkeypatch, mlflow_de_prueba):
    """Clave, datos y un MLflow de prueba; el chequeo de salud de MLflow se reemplaza."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("CARPETA_DATOS", str(escribir_parquet(tmp_path, tablas_validas())))
    monkeypatch.setenv("MLFLOW_TRACKING_URI", mlflow_de_prueba)
    chequeos = []
    monkeypatch.setattr(trazas, "verificar_mlflow", chequeos.append)
    yield chequeos
    mlflow.langchain.autolog(disable=True)


def _esperar_experimento():
    """El hilo que crea el experimento en el MLflow de prueba, si todavía no terminó."""
    for hilo in threading.enumerate():
        if hilo.name == "mlflow-experimento":
            hilo.join(timeout=30)


def test_arranca_con_la_clave_y_los_datos(entorno_completo):
    app = crear_app_desde_entorno()
    _esperar_experimento()

    respuesta = TestClient(app).get("/health")

    assert respuesta.json() == {"estado": "ok"}


def test_health_consulta_el_mlflow_configurado(entorno_completo, mlflow_de_prueba):
    app = crear_app_desde_entorno()
    _esperar_experimento()

    TestClient(app).get("/health")

    assert entorno_completo
    assert set(entorno_completo) == {mlflow_de_prueba}


def test_las_solicitudes_quedan_trazadas(entorno_completo):
    cliente_http = TestClient(crear_app_desde_entorno())
    anterior = mlflow.get_last_active_trace_id()

    cliente_http.post("/v1/pedidos/interpretar", json={})

    assert mlflow.get_last_active_trace_id() != anterior


def test_sin_clave_no_arranca(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ConfiguracionInvalida, match="OPENROUTER_API_KEY"):
        crear_app_desde_entorno()


def test_sin_datos_publicados_no_arranca(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("CARPETA_DATOS", str(tmp_path))

    with pytest.raises(DatosInvalidos, match=r"productos\.parquet"):
        crear_app_desde_entorno()
