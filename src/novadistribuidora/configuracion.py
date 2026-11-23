"""Configuración del servicio desde variables de entorno (.env, documentado en .env.example).

Solo la clave es obligatoria: los modelos y el tiempo límite tienen el valor de .env.example,
para que un .env con solo la clave levante el servicio (D-009).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

MODELO_POR_OMISION = "anthropic/claude-haiku-5.5"
MODELO_ALTERNO_POR_OMISION = "openai/gpt-6-luna"
CARPETA_DATOS_POR_OMISION = "datos"
# En local; docker compose lo cambia por el nombre del servicio de MLflow.
MLFLOW_POR_OMISION = "http://localhost:5000"
# Haiku responde en 1 a 3 s; 10 s deja margen sin que un proveedor colgado frene el pedido.
TIEMPO_LIMITE_POR_OMISION_S = 10.0


class ConfiguracionInvalida(Exception):
    """Falta una variable obligatoria o una tiene un valor que no sirve."""


@dataclass(frozen=True)
class Configuracion:
    # repr=False: la clave nunca aparece en un log ni en un mensaje de error.
    openrouter_api_key: str = field(repr=False)
    modelo: str
    modelo_alterno: str
    carpeta_datos: Path
    tiempo_limite_s: float
    mlflow_tracking_uri: str

    @classmethod
    def desde_entorno(cls, entorno: Mapping[str, str]) -> "Configuracion":
        clave = _valor(entorno, "OPENROUTER_API_KEY", "")
        if not clave:
            raise ConfiguracionInvalida(
                "Falta OPENROUTER_API_KEY: escríbela en .env (ver .env.example)"
            )
        return cls(
            openrouter_api_key=clave,
            modelo=_valor(entorno, "MODELO", MODELO_POR_OMISION),
            modelo_alterno=_valor(entorno, "MODELO_ALTERNO", MODELO_ALTERNO_POR_OMISION),
            carpeta_datos=Path(_valor(entorno, "CARPETA_DATOS", CARPETA_DATOS_POR_OMISION)),
            tiempo_limite_s=_segundos(_valor(entorno, "TIEMPO_LIMITE_MODELO_S", "")),
            mlflow_tracking_uri=_valor(entorno, "MLFLOW_TRACKING_URI", MLFLOW_POR_OMISION),
        )


def _valor(entorno: Mapping[str, str], nombre: str, por_omision: str) -> str:
    """Una variable vacía cuenta como ausente: así se comporta una línea "MODELO=" del .env."""
    return entorno.get(nombre, "").strip() or por_omision


def _segundos(texto: str) -> float:
    if not texto:
        return TIEMPO_LIMITE_POR_OMISION_S
    try:
        segundos = float(texto)
    except ValueError as error:
        raise ConfiguracionInvalida(
            f"TIEMPO_LIMITE_MODELO_S debe ser un número de segundos, no '{texto}'"
        ) from error
    if segundos <= 0:
        raise ConfiguracionInvalida("TIEMPO_LIMITE_MODELO_S debe ser mayor que 0")
    return segundos
