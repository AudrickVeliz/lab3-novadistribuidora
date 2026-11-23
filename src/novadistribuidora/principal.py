"""Punto de entrada del servicio:

uvicorn novadistribuidora.principal:crear_app_desde_entorno --factory --port 8000
"""

import os

from fastapi import FastAPI

from novadistribuidora.api import crear_app
from novadistribuidora.configuracion import Configuracion
from novadistribuidora.datos import cargar_datos
from novadistribuidora.interprete import crear_interprete
from novadistribuidora.servicio import Servicio


def crear_app_desde_entorno() -> FastAPI:
    """Falla al arrancar, con el motivo, si falta la clave o los datos publicados (D-005)."""
    configuracion = Configuracion.desde_entorno(os.environ)
    datos = cargar_datos(configuracion.carpeta_datos)
    return crear_app(Servicio(datos, crear_interprete(configuracion, datos)))
