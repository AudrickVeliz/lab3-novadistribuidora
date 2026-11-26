"""API HTTP del contrato del Anexo. Es delgada: valida, delega en Servicio y traduce errores."""

import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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
# El cliente ve textos fijos; los modelos y la causa de la falla quedan en el log y la traza
# (D-008): una respuesta HTTP no muestra detalles internos de una excepción.
MOTIVO_404 = "No existe el cliente {cliente_id}"
MOTIVO_503 = "El modelo no pudo interpretar el mensaje; intente de nuevo en unos segundos"

# JSON va en UTF-8 (RFC 8259), pero una terminal de Windows manda los acentos en Windows-1252:
# se aceptan para que un pedido no falle por la codificación de quien lo envía (D-018).
CODIFICACIONES = ("utf-8", "cp1252")
MOTIVO_CODIFICACION = "cuerpo: no está en UTF-8 ni en Windows-1252"

registro = logging.getLogger(__name__)


def crear_app(servicio: Servicio) -> FastAPI:
    app = FastAPI(
        title="Toma de pedidos por WhatsApp · NovaDistribuidora",
        version=__version__,
        description="Convierte los mensajes de un cliente en un pedido estructurado y verificable.",
    )
    app.add_middleware(CuerpoEnUtf8)

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
        except ClienteNoExiste:
            motivo = MOTIVO_404.format(cliente_id=solicitud.cliente_id)
            return JSONResponse({"detail": motivo}, status_code=404)
        except InterpreteNoDisponible as error:
            registro.warning("Pedido sin interpretar (503): %s", error)
            return JSONResponse({"detail": MOTIVO_503}, status_code=503)

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


class CuerpoEnUtf8:
    """Middleware ASGI: FastAPI recibe el cuerpo en UTF-8, o la solicitud es 422 con el motivo.

    Sin él, un cuerpo en otra codificación sería un 400 con un texto en inglés de FastAPI.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        cuerpo = cuerpo_en_utf8(await _leer_cuerpo(receive))
        if cuerpo is None:
            respuesta = JSONResponse({"detail": MOTIVO_CODIFICACION}, status_code=422)
            await respuesta(scope, receive, send)
            return
        await self.app(scope, entregar_cuerpo(cuerpo, receive), send)


def cuerpo_en_utf8(cuerpo: bytes) -> bytes | None:
    """El cuerpo recodificado en UTF-8, o None si no está en ninguna de las CODIFICACIONES."""
    for codificacion in CODIFICACIONES:
        try:
            texto = cuerpo.decode(codificacion)
        except UnicodeDecodeError:
            continue  # Se prueba la siguiente; si ninguna sirve, el llamador responde 422.
        return texto.encode("utf-8")
    return None


async def _leer_cuerpo(receive: Receive) -> bytes:
    partes = []
    while True:
        mensaje = await receive()
        partes.append(mensaje.get("body", b""))
        if not mensaje.get("more_body", False):
            return b"".join(partes)


def entregar_cuerpo(cuerpo: bytes, receive: Receive) -> Receive:
    """Un receive que entrega el cuerpo ya leído y después pasa los mensajes del servidor."""
    entregado = False

    async def recibir() -> Message:
        nonlocal entregado
        if entregado:
            return await receive()
        entregado = True
        return {"type": "http.request", "body": cuerpo, "more_body": False}

    return recibir
