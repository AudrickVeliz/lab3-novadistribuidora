"""API HTTP del contrato del Anexo. Es delgada: valida, delega en Servicio y traduce errores."""

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from novadistribuidora import __version__
from novadistribuidora.contrato import (
    MAXIMO_MENSAJES,
    Error,
    EstadoServicio,
    RespuestaInterpretar,
    SolicitudInterpretar,
)
from novadistribuidora.servicio import ClienteNoExiste, InterpreteNoDisponible, Servicio

# Motivos de la validación en español: el Anexo pide un mensaje que explique el motivo.
MOTIVOS_422 = {
    "missing": "falta este campo",
    "json_invalid": "no es JSON válido",
    "model_attributes_type": "debe ser un objeto JSON",
    "string_type": "debe ser texto",
    "list_type": "debe ser una lista de textos",
    "string_too_short": "no puede estar vacío",
    "too_short": "debe tener al menos un mensaje",
    "too_long": f"admite como máximo {MAXIMO_MENSAJES} mensajes",
    "datetime_from_date_parsing": "no es una fecha y hora válida (AAAA-MM-DDTHH:MM)",
    "datetime_parsing": "no es una fecha y hora válida (AAAA-MM-DDTHH:MM)",
}


def crear_app(servicio: Servicio) -> FastAPI:
    app = FastAPI(
        title="Toma de pedidos por WhatsApp · NovaDistribuidora",
        version=__version__,
        description="Convierte los mensajes de un cliente en un pedido estructurado y verificable.",
    )

    @app.exception_handler(RequestValidationError)
    async def _solicitud_invalida(_: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse({"detail": describir_errores(error.errors())}, status_code=422)

    @app.post(
        "/v1/pedidos/interpretar",
        response_model=RespuestaInterpretar,
        responses={
            404: {"model": Error, "description": "El cliente no existe."},
            422: {"model": Error, "description": "Solicitud inválida, con el motivo."},
            503: {"model": Error, "description": "El modelo no pudo interpretar el mensaje."},
        },
    )
    def interpretar(solicitud: SolicitudInterpretar) -> RespuestaInterpretar | JSONResponse:
        try:
            return servicio.interpretar_pedido(solicitud)
        except ClienteNoExiste as error:
            return JSONResponse({"detail": str(error)}, status_code=404)
        except InterpreteNoDisponible as error:
            return JSONResponse({"detail": str(error)}, status_code=503)

    @app.get("/health", response_model=EstadoServicio, response_model_exclude_none=True)
    def health() -> EstadoServicio:
        """Responde 200 aunque algo falle: el servicio atiende y el estado lo dice (Anexo)."""
        caidas = servicio.dependencias_caidas()
        if caidas:
            return EstadoServicio(estado="degradado", motivo="; ".join(caidas))
        return EstadoServicio(estado="ok")

    return app


def describir_errores(errores: Sequence[dict[str, Any]]) -> str:
    """'mensajes: debe tener al menos un mensaje; fecha_hora: ...', sin jerga de Pydantic."""
    return "; ".join(f"{_campo(error['loc'])}: {_motivo(error)}" for error in errores)


def _campo(ubicacion: Sequence[str | int]) -> str:
    partes = [parte for parte in ubicacion if parte != "body"]
    # Un error de sintaxis JSON se ubica por posición del carácter, no por campo.
    if not partes or isinstance(partes[0], int):
        return "cuerpo"
    nombre = str(partes[0])
    return nombre + "".join(f"[{parte}]" for parte in partes[1:])


def _motivo(error: dict[str, Any]) -> str:
    if error["type"] == "value_error":
        return str(error["ctx"]["error"])
    return MOTIVOS_422.get(error["type"], error["msg"])
