"""Atiende 5 pedidos con un MLflow que acepta conexiones y nunca responde, como en producción.

python tests/mlflow_colgado.py CARPETA ESCENARIO
  ESCENARIO: "desde_el_arranque" o "despues_del_experimento" (MLflow respondió al arrancar,
  se creó el experimento y después se colgó).
Imprime la latencia de la primera solicitud, la peor de las demás, en segundos, y el estado de
/health. Lo usa tests/test_trazas.py en un
proceso aparte para no heredar el estado de MLflow de las demás pruebas.
"""

import os
import socket
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import mlflow
from fastapi.testclient import TestClient

from datos_de_prueba import escribir_parquet, tablas_validas
from novadistribuidora import trazas
from novadistribuidora.api import crear_app
from novadistribuidora.datos import cargar_datos
from novadistribuidora.interpretacion import Interpretacion, Mencion
from novadistribuidora.servicio import Servicio

SOLICITUD = {"cliente_id": "C001", "fecha_hora": "2026-11-23T15:20", "mensajes": ["2 kola 600"]}
PEDIDO = Interpretacion(es_pedido=True, menciones=[Mencion(texto="kola", skus=["B01"], cantidad=2)])


class InterpreteFijo:
    def interpretar(self, mensajes):
        return PEDIDO


def main(carpeta: Path, escenario: str) -> None:
    mudo = socket.socket()
    mudo.bind(("127.0.0.1", 0))
    mudo.listen()
    uri = f"http://127.0.0.1:{mudo.getsockname()[1]}"
    verificar_real = trazas.verificar_mlflow
    if escenario == "despues_del_experimento":
        # MLflow respondió al arrancar: el experimento se crea y deja MLFLOW_EXPERIMENT_ID.
        os.environ["MLFLOW_EXPERIMENT_ID"] = "1"
        mlflow.set_experiment = lambda nombre: SimpleNamespace(experiment_id="1")
        trazas.verificar_mlflow = lambda uri: None
    chequeo = trazas.activar_trazas(uri)
    if escenario == "despues_del_experimento":
        hilo = next(h for h in threading.enumerate() if h.name == "mlflow-experimento")
        hilo.join(timeout=5)
        # Y después se cuelga.
        trazas.verificar_mlflow = verificar_real

    datos = cargar_datos(escribir_parquet(carpeta, tablas_validas()))
    app = crear_app(Servicio(datos, InterpreteFijo(), {"mlflow": chequeo}))
    trazas.instrumentar(app)
    cliente = TestClient(app)
    latencias = []
    for _ in range(5):
        inicio = time.perf_counter()
        assert cliente.post("/v1/pedidos/interpretar", json=SOLICITUD).status_code == 200
        latencias.append(time.perf_counter() - inicio)
    estado = cliente.get("/health").json()["estado"]
    print(latencias[0], max(latencias[1:]), estado, flush=True)
    # Sin esperar a que la cola agote sus reintentos contra el MLflow colgado.
    os._exit(0)


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
