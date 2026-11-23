"""Prueba de humo del producto levantado con compose (D-011): local con Podman, CI con Docker.

python tools/prueba_de_humo.py --pedido 200               # con la clave real
python tools/prueba_de_humo.py --pedido 503               # con una clave falsa, como en CI
python tools/prueba_de_humo.py --pedido 503 --mlflow-detenido

Revisa /health, el contrato (422, 404 y un pedido válido) y que la solicitud quede trazada en
MLflow; con --mlflow-detenido, que /health diga degradado y la API siga atendiendo igual.
Solo usa la biblioteca estándar: corre con cualquier Python, sin instalar el proyecto.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

EXPERIMENTO = "toma-de-pedidos"
ESPERA_MAXIMA_S = 180
PEDIDO = {
    "cliente_id": "C001",
    "fecha_hora": "2026-11-23T15:20",
    "mensajes": ["Buenas, mándeme 2 fardos de kola 600"],
}
# Una solicitud inválida no llama al modelo: su latencia mide solo a la API.
LATENCIA_MAXIMA_422_S = 1.0


def _pedir(url: str, cuerpo: dict | None = None, tiempo_limite: float = 60) -> tuple[int, dict]:
    datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
    solicitud = urllib.request.Request(  # noqa: S310 - URL de la línea de comandos
        url, data=datos, headers={"content-type": "application/json"}
    )
    try:
        with urllib.request.urlopen(solicitud, timeout=tiempo_limite) as respuesta:  # noqa: S310
            return respuesta.status, json.loads(respuesta.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def _esperar_salud(api: str, estado: str) -> dict:
    limite = time.monotonic() + ESPERA_MAXIMA_S
    while time.monotonic() < limite:
        try:
            _, salud = _pedir(f"{api}/health", tiempo_limite=5)
            if salud.get("estado") == estado:
                return salud
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2)
    raise AssertionError(f"/health no llegó a '{estado}' en {ESPERA_MAXIMA_S} s")


def _revisar(condicion: bool, descripcion: str) -> None:
    print(("OK    " if condicion else "FALLA ") + descripcion, flush=True)
    if not condicion:
        raise SystemExit(1)


def _contrato(api: str, codigo_pedido: int) -> None:
    ruta = f"{api}/v1/pedidos/interpretar"
    inicio = time.perf_counter()
    codigo, cuerpo = _pedir(ruta, PEDIDO | {"mensajes": []})
    latencia = time.perf_counter() - inicio
    _revisar(codigo == 422 and "mensajes" in cuerpo.get("detail", ""), f"422 con motivo: {cuerpo}")
    _revisar(latencia < LATENCIA_MAXIMA_422_S, f"422 en {latencia:.2f} s")
    codigo, cuerpo = _pedir(ruta, PEDIDO | {"cliente_id": "C999"})
    _revisar(codigo == 404, f"404 para un cliente inexistente: {cuerpo}")
    inicio = time.perf_counter()
    codigo, cuerpo = _pedir(ruta, PEDIDO)
    latencia = time.perf_counter() - inicio
    _revisar(codigo == codigo_pedido, f"pedido válido: {codigo} en {latencia:.2f} s")


def _trazas_en_mlflow(mlflow: str) -> int:
    _, experimento = _pedir(
        f"{mlflow}/api/2.0/mlflow/experiments/get-by-name?experiment_name={EXPERIMENTO}"
    )
    identificador = experimento.get("experiment", {}).get("experiment_id")
    if identificador is None:
        return 0
    _, trazas = _pedir(f"{mlflow}/api/2.0/mlflow/traces?experiment_ids={identificador}")
    return len(trazas.get("traces", []))


def _esperar_trazas(mlflow: str) -> None:
    limite = time.monotonic() + 60
    cantidad = 0
    while time.monotonic() < limite and cantidad == 0:
        time.sleep(2)
        cantidad = _trazas_en_mlflow(mlflow)
    _revisar(cantidad > 0, f"{cantidad} traza(s) en el experimento {EXPERIMENTO} de MLflow")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # 127.0.0.1 y no localhost: en Windows con Podman, ::1 no responde y Python espera 21 s.
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--mlflow", default="http://127.0.0.1:5000")
    parser.add_argument("--pedido", type=int, choices=[200, 503], required=True)
    parser.add_argument("--mlflow-detenido", action="store_true")
    argumentos = parser.parse_args()

    if argumentos.mlflow_detenido:
        salud = _esperar_salud(argumentos.api, "degradado")
        _revisar("mlflow" in salud.get("motivo", ""), f"/health degradado: {salud}")
        _contrato(argumentos.api, argumentos.pedido)
    else:
        _revisar(_esperar_salud(argumentos.api, "ok") == {"estado": "ok"}, "/health ok")
        _contrato(argumentos.api, argumentos.pedido)
        _esperar_trazas(argumentos.mlflow)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
