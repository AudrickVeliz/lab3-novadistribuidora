"""Evalúa y compara alternativas del intérprete en MLflow (D-012).

python tools/evaluar.py                               # las alternativas de D-012, 3 corridas
python tools/evaluar.py --alternativas haiku --corridas 1

Cada caso (84 publicados, 40 propios de D-012 y 15 de prueba de D-014) pasa por el mismo
camino que la API (Servicio.interpretar_pedido) y se califica con código
(novadistribuidora.calificaciones).
Cada corrida es un run del experimento "evaluacion" de MLflow, con sus trazas, tokens y costo.
Escribe evidencia/comparacion.csv y evidencia/comparacion.md. Necesita .env con la clave, los
archivos publicados y MLflow arriba (docker compose up).
"""

import argparse
import csv
import hashlib
import json
import os
import statistics
import time
from pathlib import Path

import mlflow
from dotenv import load_dotenv
from mlflow.entities import SpanType
from mlflow.genai.scorers import scorer

from novadistribuidora.calificaciones import calificar, condiciones_intactas
from novadistribuidora.configuracion import Configuracion
from novadistribuidora.contrato import SolicitudInterpretar
from novadistribuidora.datos import Datos, cargar_datos
from novadistribuidora.interprete import (
    INSTRUCCIONES,
    VERSION_INSTRUCCIONES,
    InterpreteLangChain,
    crear_cadena,
    crear_modelo,
    describir_catalogo,
)
from novadistribuidora.servicio import InterpreteNoDisponible, Servicio

RAIZ = Path(__file__).resolve().parents[1]
ALTERNATIVAS = {"haiku": "anthropic/claude-haiku-5.5", "luna": "openai/gpt-6-luna"}
CONJUNTOS = {
    "publicados": RAIZ / "ejemplos" / "mensajes_dev.jsonl",
    "propios": RAIZ / "evaluacion" / "casos_propios.jsonl",
    "prueba": RAIZ / "evaluacion" / "casos_prueba.jsonl",
}
EXPERIMENTO = "evaluacion"
EVIDENCIA = RAIZ / "evidencia"
ASPECTOS = (
    "exacto",
    "estado",
    "lineas",
    "total",
    "fecha_entrega",
    "sustituciones",
    "pendientes",
    "motivos",
)


def cargar_casos() -> dict[str, dict]:
    casos = {}
    for conjunto, ruta in CONJUNTOS.items():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            caso = json.loads(linea)
            casos[caso["id"]] = caso | {"conjunto": conjunto}
    return casos


def _respuesta(salida: dict | None) -> dict | None:
    """None si el intérprete no respondió (503): el caso cuenta como fallido."""
    return None if salida is None or "error" in salida else salida


def _calificador(aspecto: str):
    def calificacion(outputs, expectations) -> bool:
        return calificar(_respuesta(outputs), expectations["esperado"])[aspecto]

    return scorer(calificacion, name=aspecto)


def crear_calificadores(datos: Datos) -> list:
    def condiciones(outputs) -> bool:
        respuesta = _respuesta(outputs)
        return respuesta is None or condiciones_intactas(respuesta, datos.productos, datos.escalas)

    return [_calificador(aspecto) for aspecto in ASPECTOS] + [
        scorer(condiciones, name="condiciones_intactas")
    ]


def crear_servicio(modelo: str, configuracion: Configuracion, datos: Datos) -> Servicio:
    """El modelo solo, sin alterno de otro proveedor: se mide cada alternativa por sí misma."""
    estructurado = crear_modelo(modelo, configuracion)
    catalogo = describir_catalogo(datos.productos, datos.sinonimos)
    interprete = InterpreteLangChain(crear_cadena(estructurado, estructurado, catalogo), [modelo])
    return Servicio(datos, interprete)


def correr(
    nombre: str, corrida: int, servicio: Servicio, datos: Datos, casos: dict, pausa_s: float
) -> None:
    # Raíz de cada traza: el caso, la solicitud y la respuesta del contrato; dentro, LangChain.
    @mlflow.trace(name="interpretar_pedido", span_type=SpanType.CHAIN)
    def interpretar(caso: str, solicitud: dict) -> dict:
        try:
            respuesta = servicio.interpretar_pedido(SolicitudInterpretar.model_validate(solicitud))
        except InterpreteNoDisponible as error:
            return {"error": str(error)}
        return respuesta.model_dump(mode="json")

    def predecir(caso: str, solicitud: dict) -> dict:
        # La pausa respeta el límite de solicitudes por minuto de la cuenta y queda fuera de la
        # traza: no se suma a la latencia medida.
        time.sleep(pausa_s)
        return interpretar(caso, solicitud)

    filas = [
        {
            "inputs": {"caso": identificador, "solicitud": caso["entrada"]},
            "expectations": {"esperado": caso["esperado"], "conjunto": caso["conjunto"]},
        }
        for identificador, caso in casos.items()
    ]
    huella = hashlib.sha256(INSTRUCCIONES.encode("utf-8")).hexdigest()[:12]
    with mlflow.start_run(run_name=f"{nombre} {VERSION_INSTRUCCIONES} corrida {corrida}"):
        mlflow.log_params(
            {"modelo": ALTERNATIVAS[nombre], "corrida": corrida, "prompt_sha256": huella}
        )
        mlflow.set_tags(
            {"alternativa": nombre, "instrucciones": VERSION_INSTRUCCIONES, "casos": len(filas)}
        )
        mlflow.genai.evaluate(data=filas, predict_fn=predecir, scorers=crear_calificadores(datos))


def runs_guardados() -> list:
    """Las corridas registradas, para regenerar la evidencia sin volver a llamar al modelo.

    Solo las que llevan la versión de las instrucciones (D-014): las de D-012 no la tienen y no
    incluyen el conjunto de prueba, así que quedan en MLflow como historial."""
    experimento = mlflow.get_experiment_by_name(EXPERIMENTO)
    runs = mlflow.search_runs(
        [experimento.experiment_id],
        filter_string="attributes.status = 'FINISHED'",
        output_format="list",
    )
    return sorted(
        (run for run in runs if "instrucciones" in run.data.tags),
        key=lambda run: (
            run.data.tags["alternativa"],
            run.data.tags["instrucciones"],
            int(run.data.params["corrida"]),
        ),
    )


def resumir_corrida(run, casos: dict, datos: Datos) -> list[dict]:
    """Por conjunto: calidad por aspecto, latencia y costo, leídos de las trazas del run."""
    trazas = mlflow.search_traces(
        locations=[run.info.experiment_id], run_id=run.info.run_id, max_results=len(casos)
    )
    por_conjunto: dict[str, list[dict]] = {}
    for traza in trazas.itertuples():
        caso = casos[traza.request["caso"]]
        respuesta = _respuesta(traza.response)
        costo = json.loads(traza.trace_metadata.get("mlflow.trace.cost", "{}"))
        por_conjunto.setdefault(caso["conjunto"], []).append(
            {
                "caso": traza.request["caso"],
                "tipo": caso["tipo"],
                "calificaciones": calificar(respuesta, caso["esperado"]),
                "error": respuesta is None,
                "intactas": respuesta is None
                or condiciones_intactas(respuesta, datos.productos, datos.escalas),
                "latencia_s": traza.execution_duration / 1000,
                "costo": costo.get("total_cost", 0.0),
            }
        )
    return [_resumen(conjunto, filas) for conjunto, filas in sorted(por_conjunto.items())]


def _resumen(conjunto: str, filas: list[dict]) -> dict:
    latencias = sorted(fila["latencia_s"] for fila in filas)
    resumen = {
        "conjunto": conjunto,
        "casos": len(filas),
        "errores": sum(fila["error"] for fila in filas),
        "condiciones_intactas": sum(fila["intactas"] for fila in filas) / len(filas),
        "latencia_p50_s": statistics.median(latencias),
        "latencia_p95_s": latencias[max(0, round(0.95 * len(latencias)) - 1)],
        "costo_por_pedido_usd": sum(fila["costo"] for fila in filas) / len(filas),
        "fallidos": sorted(fila["caso"] for fila in filas if not fila["calificaciones"]["exacto"]),
    }
    for aspecto in ASPECTOS:
        resumen[aspecto] = sum(fila["calificaciones"][aspecto] for fila in filas) / len(filas)
    return resumen


def escribir_evidencia(filas: list[dict], casos: dict) -> None:
    EVIDENCIA.mkdir(exist_ok=True)
    columnas = [c for c in filas[0] if c != "fallidos"] + ["fallidos"]
    with (EVIDENCIA / "comparacion.csv").open("w", encoding="utf-8", newline="\n") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas, lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(fila | {"fallidos": " ".join(fila["fallidos"])} for fila in filas)
    (EVIDENCIA / "comparacion.md").write_bytes(_informe(filas, casos).encode("utf-8"))


def _media(valores: list[float], formato: str) -> str:
    media = statistics.fmean(valores)
    desviacion = statistics.stdev(valores) if len(valores) > 1 else 0.0
    return f"{media:{formato}} ± {desviacion:{formato}}"


def _informe(filas: list[dict], casos: dict) -> str:
    lineas = [
        "# Comparación de alternativas del intérprete",
        "",
        "Generado por `tools/evaluar.py` (D-012, D-014). Media ± desviación estándar entre "
        "corridas.",
        "",
        "| Alternativa | Instrucciones | Conjunto | Corridas | Exactos | Estado | Líneas | "
        "Pendientes | "
        "Condiciones intactas | Errores | Latencia p50 (s) | Latencia p95 (s) | "
        "Costo por pedido (US$) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    grupos: dict[tuple[str, str, str], list[dict]] = {}
    for fila in filas:
        clave = (fila["alternativa"], fila["instrucciones"], fila["conjunto"])
        grupos.setdefault(clave, []).append(fila)
    for (alternativa, instrucciones, conjunto), corridas in grupos.items():

        def valores(clave, corridas=corridas):
            return [corrida[clave] for corrida in corridas]

        lineas.append(
            f"| {alternativa} | {instrucciones} | {conjunto} ({corridas[0]['casos']}) "
            f"| {len(corridas)} "
            f"| {_media(valores('exacto'), '.1%')} | {_media(valores('estado'), '.1%')} "
            f"| {_media(valores('lineas'), '.1%')} | {_media(valores('pendientes'), '.1%')} "
            f"| {_media(valores('condiciones_intactas'), '.0%')} "
            f"| {_media(valores('errores'), '.1f')} "
            f"| {_media(valores('latencia_p50_s'), '.2f')} "
            f"| {_media(valores('latencia_p95_s'), '.2f')} "
            f"| {_media(valores('costo_por_pedido_usd'), '.5f')} |"
        )
    lineas += [
        "",
        "## Casos fallidos",
        "",
        "| Alternativa | Instrucciones | Caso | Tipo | Corridas fallidas |",
        "|---|---|---|---|---|",
    ]
    for (alternativa, instrucciones, _), corridas in grupos.items():
        fallos: dict[str, int] = {}
        for corrida in corridas:
            for caso in corrida["fallidos"]:
                fallos[caso] = fallos.get(caso, 0) + 1
        for caso, veces in sorted(fallos.items()):
            lineas.append(
                f"| {alternativa} | {instrucciones} | {caso} | {casos[caso]['tipo']} "
                f"| {veces} de {len(corridas)} |"
            )
    return "\n".join(lineas) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--alternativas", nargs="+", choices=ALTERNATIVAS, default=[*ALTERNATIVAS])
    parser.add_argument("--corridas", type=int, default=3)
    # La cuenta de OpenRouter de desarrollo es nueva: con más concurrencia, GPT-6 Luna da 429.
    parser.add_argument("--hilos", type=int, default=2)
    # Con GPT-6 Luna en esa cuenta: --hilos 1 --pausa 3 (D-012). La pausa no cuenta en la latencia.
    parser.add_argument("--pausa", type=float, default=0.0, help="segundos antes de cada caso")
    # 127.0.0.1 y no localhost: en Windows con Podman, ::1 no responde y Python espera 21 s.
    parser.add_argument("--mlflow", default="http://127.0.0.1:5000")
    parser.add_argument(
        "--resumir", action="store_true", help="solo regenera la evidencia desde los runs de MLflow"
    )
    argumentos = parser.parse_args()

    load_dotenv(RAIZ / ".env")
    os.environ["MLFLOW_GENAI_EVAL_MAX_WORKERS"] = str(argumentos.hilos)
    configuracion = Configuracion.desde_entorno(os.environ)
    datos = cargar_datos(RAIZ / "datos")
    casos = cargar_casos()
    mlflow.set_tracking_uri(argumentos.mlflow)
    mlflow.set_experiment(EXPERIMENTO)
    mlflow.langchain.autolog()

    if not argumentos.resumir:
        for nombre in argumentos.alternativas:
            servicio = crear_servicio(ALTERNATIVAS[nombre], configuracion, datos)
            for corrida in range(1, argumentos.corridas + 1):
                correr(nombre, corrida, servicio, datos, casos, argumentos.pausa)
    filas = []
    for run in runs_guardados():
        nombre, corrida = run.data.tags["alternativa"], int(run.data.params["corrida"])
        instrucciones = run.data.tags["instrucciones"]
        for resumen in resumir_corrida(run, casos, datos):
            filas.append(
                {
                    "alternativa": nombre,
                    "instrucciones": instrucciones,
                    "corrida": corrida,
                    "run_id": run.info.run_id,
                }
            )
            filas[-1] |= resumen
            print(
                f"{nombre} {instrucciones} corrida {corrida} {resumen['conjunto']}: "
                f"{resumen['exacto']:.1%} exactos, {resumen['errores']} errores",
                flush=True,
            )
    escribir_evidencia(filas, casos)
    print(f"Evidencia en {EVIDENCIA.relative_to(RAIZ)}/comparacion.md")


if __name__ == "__main__":
    main()
