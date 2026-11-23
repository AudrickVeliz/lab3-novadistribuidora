"""Una traza en MLflow por cada solicitud, sin frenar ni tumbar la API si MLflow falla (D-010).

- El middleware abre la traza de la solicitud (entrada, respuesta, código y latencia) y
  `mlflow.langchain.autolog()` agrega dentro las llamadas al modelo, con tokens y reintentos.
- El envío es asíncrono: la traza se encola y un hilo la manda. Si MLflow no responde, la
  respuesta al cliente no espera; la cola reintenta y descarta lo que no logra enviar.
- El experimento se crea en segundo plano: el servicio arranca aunque MLflow esté caído.
"""

import json
import logging
import os
import threading
import time
import urllib.request
from collections.abc import Callable

import mlflow
from fastapi import FastAPI, Request, Response
from mlflow.entities import SpanType
from mlflow.entities.trace_location import MlflowExperimentLocation

EXPERIMENTO = "toma-de-pedidos"
RUTAS_TRAZADAS = "/v1/"
TIEMPO_LIMITE_SALUD_S = 1.0
# Cada cuánto se busca MLflow mientras no responde: el trazado se reanuda a lo sumo en este lapso.
ESPERA_ENTRE_INTENTOS_S = 2.0
# Por omisión, cada petición espera hasta 120 s a un MLflow colgado; 5 s acotan cuánto queda
# ocupado un hilo de envío. Los reintentos, con espera creciente, corren en esos hilos y no en
# la solicitud: con 6, las trazas de un corte de hasta unos 2 minutos llegan cuando MLflow
# vuelve (medido en D-010); con 1, se perdían.
AJUSTES_DEL_CLIENTE = {
    "MLFLOW_ENABLE_ASYNC_TRACE_LOGGING": "true",
    "MLFLOW_HTTP_REQUEST_TIMEOUT": "5",
    "MLFLOW_HTTP_REQUEST_MAX_RETRIES": "6",
}

registro = logging.getLogger(__name__)


def activar_trazas(tracking_uri: str) -> Callable[[], None]:
    """Conecta MLflow y devuelve el chequeo de salud para /health."""
    for variable, valor in AJUSTES_DEL_CLIENTE.items():
        os.environ.setdefault(variable, valor)
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.langchain.autolog()
    listo = threading.Event()
    threading.Thread(
        target=crear_experimento, args=(tracking_uri, listo), name="mlflow-experimento", daemon=True
    ).start()
    return lambda: verificar_trazado(tracking_uri, listo)


def crear_experimento(
    tracking_uri: str, listo: threading.Event, espera_s: float = ESPERA_ENTRE_INTENTOS_S
) -> None:
    """Espera a que MLflow responda y crea el experimento; hasta entonces no hay trazas.

    Primero consulta /health (1 s): set_experiment con MLflow caído tarda minutos en fallar por
    los reintentos del cliente, y el trazado no se reanudaría al volver MLflow.
    """
    while True:
        try:
            verificar_mlflow(tracking_uri)
            experimento = mlflow.set_experiment(EXPERIMENTO)
        except Exception as error:  # MLflow caído o arrancando: se reintenta, nunca se rinde
            registro.warning("MLflow no disponible para crear el experimento: %s", error)
            time.sleep(espera_s)
        else:
            # Con el destino explícito, una traza nueva no valida el experimento contra el
            # servidor; esa consulta es síncrona y con MLflow colgado frenaba 10 s cada solicitud.
            ubicacion = MlflowExperimentLocation(experiment_id=experimento.experiment_id)
            mlflow.tracing.set_destination(ubicacion)
            listo.set()
            return


def verificar_trazado(tracking_uri: str, listo: threading.Event) -> None:
    """MLflow responde y el experimento existe: solo entonces las solicitudes quedan trazadas."""
    verificar_mlflow(tracking_uri)
    if not listo.is_set():
        raise ConnectionError("responde, pero el experimento de las trazas aún no está listo")


def verificar_mlflow(tracking_uri: str) -> None:
    """Lanza ConnectionError si MLflow no responde en TIEMPO_LIMITE_SALUD_S."""
    url = f"{tracking_uri.rstrip('/')}/health"
    try:
        with urllib.request.urlopen(url, timeout=TIEMPO_LIMITE_SALUD_S):  # noqa: S310 - URL de la configuración
            return
    except OSError as error:
        raise ConnectionError(f"no responde en {tracking_uri}") from error


def instrumentar(app: FastAPI) -> None:
    """Agrega el middleware que traza cada solicitud a /v1/, incluidas las 404 y 422."""

    @app.middleware("http")
    async def trazar_solicitud(request: Request, siguiente) -> Response:
        if not request.url.path.startswith(RUTAS_TRAZADAS):
            return await siguiente(request)
        entrada = await request.body()
        nombre = f"{request.method} {request.url.path}"
        with mlflow.start_span(name=nombre, span_type=SpanType.CHAIN) as span:
            span.set_inputs(_como_json(entrada))
            respuesta = await siguiente(request)
            salida = b"".join([parte async for parte in respuesta.body_iterator])
            span.set_outputs(_como_json(salida))
            span.set_attribute("http.status_code", respuesta.status_code)
            mlflow.update_current_trace(tags=_etiquetas(respuesta.status_code, salida))
        return Response(
            content=salida,
            status_code=respuesta.status_code,
            headers=dict(respuesta.headers),
            media_type=respuesta.media_type,
        )


def _como_json(cuerpo: bytes) -> object:
    """El cuerpo como JSON si lo es; si no, como texto (una solicitud inválida también se ve)."""
    texto = cuerpo.decode("utf-8", errors="replace")
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return texto


def _etiquetas(codigo: int, salida: bytes) -> dict[str, str]:
    """Etiquetas para filtrar en MLflow: código HTTP y, si hubo pedido, su estado y cliente."""
    etiquetas = {"http.status_code": str(codigo)}
    respuesta = _como_json(salida)
    if isinstance(respuesta, dict) and "estado" in respuesta:
        etiquetas |= {"estado": respuesta["estado"], "cliente_id": respuesta["cliente_id"]}
    return etiquetas
