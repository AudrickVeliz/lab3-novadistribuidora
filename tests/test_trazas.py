"""Trazas en MLflow (D-010): qué se registra y que una caída de MLflow no afecte a la API."""

import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import mlflow
import pytest
from fastapi.testclient import TestClient

from novadistribuidora import trazas
from novadistribuidora.api import crear_app
from novadistribuidora.interpretacion import Interpretacion, Mencion
from novadistribuidora.interprete import InterpreteLangChain, crear_cadena
from novadistribuidora.servicio import Servicio
from test_interprete import ModeloFalso

RUTA = "/v1/pedidos/interpretar"
SOLICITUD = {
    "cliente_id": "C001",
    "fecha_hora": "2026-11-23T15:20",
    "mensajes": ["mándeme 2 fardos de kola 600"],
}
PEDIDO = Interpretacion(es_pedido=True, menciones=[Mencion(texto="kola", skus=["B01"], cantidad=2)])
RAIZ = Path(__file__).resolve().parents[1]


class InterpreteFijo:
    def interpretar(self, mensajes):
        return PEDIDO


@pytest.fixture
def cliente_http(datos, mlflow_de_prueba):
    app = crear_app(Servicio(datos, InterpreteFijo()))
    trazas.instrumentar(app)
    return TestClient(app)


def _ultima_traza():
    mlflow.flush_trace_async_logging()
    return mlflow.get_trace(mlflow.get_last_active_trace_id())


def _raiz(traza):
    return next(span for span in traza.data.spans if span.parent_id is None)


# Qué se registra


def test_trazas_una_solicitud_atendida_deja_entrada_respuesta_y_etiquetas(cliente_http):
    respuesta = cliente_http.post(RUTA, json=SOLICITUD)

    traza = _ultima_traza()
    raiz = _raiz(traza)
    assert raiz.name == f"POST {RUTA}"
    assert raiz.inputs == SOLICITUD
    assert raiz.outputs == respuesta.json()
    assert raiz.attributes["http.status_code"] == 200
    assert traza.info.tags["http.status_code"] == "200"
    assert traza.info.tags["estado"] == "confirmado"
    assert traza.info.tags["cliente_id"] == "C001"


def test_trazas_una_solicitud_invalida_tambien_deja_traza(cliente_http):
    respuesta = cliente_http.post(
        RUTA, content="no es json", headers={"content-type": "application/json"}
    )

    traza = _ultima_traza()
    assert respuesta.status_code == 422
    assert _raiz(traza).inputs == "no es json"
    assert _raiz(traza).outputs == {"detail": "cuerpo: no es JSON válido"}
    assert traza.info.tags["http.status_code"] == "422"
    assert "estado" not in traza.info.tags


def test_trazas_un_cuerpo_ilegible_deja_traza(cliente_http):
    cliente_http.post(RUTA, content=b"\x81", headers={"content-type": "application/json"})

    traza = _ultima_traza()
    assert traza.info.tags["http.status_code"] == "422"
    assert _raiz(traza).outputs == {"detail": "cuerpo: no está en UTF-8 ni en Windows-1252"}


def test_trazas_un_cliente_inexistente_deja_traza(cliente_http):
    cliente_http.post(RUTA, json=SOLICITUD | {"cliente_id": "C999"})

    assert _ultima_traza().info.tags["http.status_code"] == "404"


def test_trazas_health_no_deja_traza(cliente_http):
    cliente_http.post(RUTA, json=SOLICITUD)
    anterior = mlflow.get_last_active_trace_id()

    cliente_http.get("/health")

    assert mlflow.get_last_active_trace_id() == anterior


def test_trazas_el_middleware_no_cambia_la_respuesta(datos, cliente_http):
    sin_trazas = TestClient(crear_app(Servicio(datos, InterpreteFijo())))

    con, sin = cliente_http.post(RUTA, json=SOLICITUD), sin_trazas.post(RUTA, json=SOLICITUD)

    assert (con.status_code, con.json()) == (sin.status_code, sin.json())
    assert con.headers["content-type"] == sin.headers["content-type"]


def test_trazas_la_llamada_al_modelo_queda_dentro_de_la_traza(datos, mlflow_de_prueba):
    cadena = crear_cadena(
        ModeloFalso(respuesta=PEDIDO).como_runnable(), ModeloFalso().como_runnable(), "catálogo"
    )
    app = crear_app(Servicio(datos, InterpreteLangChain(cadena, ["principal", "alterno"])))
    trazas.instrumentar(app)
    mlflow.langchain.autolog()
    try:
        TestClient(app).post(RUTA, json=SOLICITUD)
    finally:
        mlflow.langchain.autolog(disable=True)

    spans = _ultima_traza().data.spans
    raiz = _raiz(_ultima_traza())
    assert len(spans) > 1
    assert all(span.trace_id == raiz.trace_id for span in spans)
    assert any(span.parent_id == raiz.span_id for span in spans)


# Disponibilidad de MLflow


class _Salud(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *argumentos):
        """Sin log en la salida de las pruebas."""


def _servidor(manejador):
    servidor = HTTPServer(("127.0.0.1", 0), manejador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor


def _servidor_mudo():
    """Acepta conexiones y nunca responde: el peor caso de un MLflow colgado."""
    oyente = socket.socket()
    oyente.bind(("127.0.0.1", 0))
    oyente.listen()
    return oyente


def test_trazas_verificar_mlflow_disponible():
    servidor = _servidor(_Salud)
    try:
        trazas.verificar_mlflow(f"http://127.0.0.1:{servidor.server_port}/")
    finally:
        servidor.shutdown()


def test_trazas_verificar_mlflow_caido_falla_con_el_motivo():
    with socket.socket() as libre:
        libre.bind(("127.0.0.1", 0))
        puerto = libre.getsockname()[1]

    with pytest.raises(ConnectionError, match=f"no responde en http://127.0.0.1:{puerto}"):
        trazas.verificar_mlflow(f"http://127.0.0.1:{puerto}")


def test_trazas_verificar_mlflow_colgado_no_espera_mas_del_limite():
    oyente = _servidor_mudo()
    inicio = time.perf_counter()
    try:
        with pytest.raises(ConnectionError):
            trazas.verificar_mlflow(f"http://127.0.0.1:{oyente.getsockname()[1]}")
    finally:
        oyente.close()

    assert time.perf_counter() - inicio < trazas.TIEMPO_LIMITE_SALUD_S + 1


def test_trazas_el_experimento_espera_a_mlflow_y_queda_como_destino(monkeypatch):
    consultas, intentos, destinos = [], [], []

    def verificar_mlflow(uri):
        consultas.append(uri)
        if len(consultas) < 3:
            raise ConnectionError("MLflow arrancando")

    def set_experiment(nombre):
        intentos.append(nombre)
        return SimpleNamespace(experiment_id="7")

    monkeypatch.setattr(trazas, "verificar_mlflow", verificar_mlflow)
    monkeypatch.setattr(mlflow, "set_experiment", set_experiment)
    monkeypatch.setattr(mlflow.tracing, "set_destination", destinos.append)
    listo = threading.Event()

    trazas.crear_experimento("http://mlflow:5000", listo, espera_s=0)

    # set_experiment solo se llama cuando MLflow ya responde: con MLflow caído tarda minutos.
    assert consultas == ["http://mlflow:5000"] * 3
    assert intentos == [trazas.EXPERIMENTO]
    assert [destino.experiment_id for destino in destinos] == ["7"]
    assert listo.is_set()


def test_trazas_un_fallo_al_crear_el_experimento_se_reintenta(monkeypatch):
    intentos = []

    def set_experiment(nombre):
        intentos.append(nombre)
        if len(intentos) < 2:
            raise RuntimeError("MLflow todavía migrando su base")
        return SimpleNamespace(experiment_id="7")

    monkeypatch.setattr(trazas, "verificar_mlflow", lambda uri: None)
    monkeypatch.setattr(mlflow, "set_experiment", set_experiment)
    monkeypatch.setattr(mlflow.tracing, "set_destination", lambda destino: None)

    trazas.crear_experimento("http://mlflow:5000", threading.Event(), espera_s=0)

    assert len(intentos) == 2


def test_trazas_health_degradado_hasta_que_el_experimento_esta_listo(monkeypatch):
    monkeypatch.setattr(trazas, "verificar_mlflow", lambda uri: None)
    listo = threading.Event()

    with pytest.raises(ConnectionError, match="experimento de las trazas aún no está listo"):
        trazas.verificar_trazado("http://mlflow:5000", listo)
    listo.set()
    trazas.verificar_trazado("http://mlflow:5000", listo)


def test_trazas_activar_respeta_los_ajustes_del_entorno(monkeypatch, mlflow_de_prueba):
    monkeypatch.setattr(trazas, "crear_experimento", lambda uri, listo: listo.set())
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_TIMEOUT", "9")
    monkeypatch.delenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", raising=False)
    llamadas = []
    monkeypatch.setattr(trazas, "verificar_mlflow", llamadas.append)

    chequeo = trazas.activar_trazas(mlflow_de_prueba)
    for hilo in threading.enumerate():
        if hilo.name == "mlflow-experimento":
            hilo.join(timeout=5)
    chequeo()
    mlflow.langchain.autolog(disable=True)

    assert llamadas == [mlflow_de_prueba]
    assert mlflow.get_tracking_uri() == mlflow_de_prueba
    assert trazas.os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] == "9"
    assert trazas.os.environ["MLFLOW_HTTP_REQUEST_MAX_RETRIES"] == "6"


ESPERA_DE_MLFLOW_S = float(trazas.AJUSTES_DEL_CLIENTE["MLFLOW_HTTP_REQUEST_TIMEOUT"])


@pytest.mark.parametrize("escenario", ["desde_el_arranque", "despues_del_experimento"])
def test_trazas_mlflow_colgado_no_frena_las_solicitudes(escenario, tmp_path):
    """En un proceso limpio, con envío asíncrono como en producción (tests/mlflow_colgado.py)."""
    entorno = {
        clave: valor for clave, valor in os.environ.items() if not clave.startswith("MLFLOW_")
    }
    resultado = subprocess.run(  # noqa: S603 - el mismo intérprete de las pruebas
        [sys.executable, str(RAIZ / "tests" / "mlflow_colgado.py"), str(tmp_path), escenario],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        timeout=120,
        env=entorno | {"PYTHONPATH": os.pathsep.join(["src", "tests"])},
    )

    assert resultado.returncode == 0, resultado.stderr[-2000:]
    primera, peor_de_las_demas, estado = resultado.stdout.split()
    # Esperar a MLflow costaría MLFLOW_HTTP_REQUEST_TIMEOUT (5 s) o más; la solicitud no espera.
    # La primera carga el trazado de MLflow y, con la suite completa, pasó de 1 s (1.34 s).
    assert float(primera) < ESPERA_DE_MLFLOW_S
    assert float(peor_de_las_demas) < 1.0
    assert estado == "degradado"
