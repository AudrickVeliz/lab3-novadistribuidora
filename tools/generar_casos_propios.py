"""Genera evaluacion/casos_propios.jsonl desde la interpretación correcta escrita a mano (D-012).

python tools/generar_casos_propios.py

Cada caso de evaluacion/fuente_casos_propios.json trae el mensaje y su interpretación
correcta; la respuesta esperada la calcula el motor de reglas, que reproduce los 84 casos
publicados. El resultado tiene el formato de ejemplos/mensajes_dev.jsonl: id, tipo, entrada
y esperado. Necesita los archivos publicados en datos/.
"""

import json
from datetime import datetime
from pathlib import Path

from novadistribuidora.contrato import RespuestaInterpretar
from novadistribuidora.datos import Datos, cargar_datos
from novadistribuidora.interpretacion import Interpretacion
from novadistribuidora.motor import armar_pedido

RAIZ = Path(__file__).resolve().parents[1]
FUENTE = RAIZ / "evaluacion" / "fuente_casos_propios.json"
CASOS = RAIZ / "evaluacion" / "casos_propios.jsonl"
# Lo que la respuesta tiene y mensajes_dev.jsonl no compara: el eco del cliente y la plantilla.
SIN_COMPARAR = ("cliente_id", "mensaje_cliente")


def esperado(caso: dict, datos: Datos) -> dict:
    """La respuesta del contrato para la interpretación correcta, sin los campos no comparados."""
    entrada = caso["entrada"]
    cliente = datos.clientes[entrada["cliente_id"]]
    interpretacion = Interpretacion.model_validate(caso["interpretacion"])
    pedido = armar_pedido(
        interpretacion, cliente, datetime.fromisoformat(entrada["fecha_hora"]), datos
    )
    respuesta = RespuestaInterpretar.desde_pedido(cliente.cliente_id, pedido, "")
    return respuesta.model_dump(mode="json", exclude=set(SIN_COMPARAR))


def generar(fuente: list[dict], datos: Datos) -> str:
    lineas = [
        json.dumps(
            {
                "id": caso["id"],
                "tipo": caso["tipo"],
                "entrada": caso["entrada"],
                "esperado": esperado(caso, datos),
            },
            ensure_ascii=False,
        )
        for caso in fuente
    ]
    return "\n".join(lineas) + "\n"


def main() -> None:
    fuente = json.loads(FUENTE.read_text(encoding="utf-8"))
    contenido = generar(fuente, cargar_datos(RAIZ / "datos"))
    CASOS.write_bytes(contenido.encode("utf-8"))
    print(f"{len(fuente)} casos en {CASOS.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
