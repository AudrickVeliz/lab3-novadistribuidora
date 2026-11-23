"""Solicitud y respuesta de POST /v1/pedidos/interpretar y de GET /health, según el Anexo.

Los nombres y valores se copian del Anexo: la respuesta puede agregar campos, nunca omitir
ni renombrar. Los campos que la solicitud no define se ignoran (D-008).
"""

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from novadistribuidora.pedido import Estado, Motivo, Pedido

# Muy por encima de un pedido real (los 84 ejemplos llegan a 3 mensajes y 184 caracteres);
# acotan la latencia y el costo del modelo ante solicitudes abusivas (D-008).
MAXIMO_MENSAJES = 20
MAXIMO_CARACTERES_POR_MENSAJE = 2000

# AAAA-MM-DDTHH:MM del Anexo; los segundos se toleran porque no cambian la fecha de entrega.
FECHA_HORA = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?")


class SolicitudInterpretar(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cliente_id: str = Field(min_length=1, examples=["C001"])
    fecha_hora: datetime = Field(
        description="Hora de recepción del último mensaje, AAAA-MM-DDTHH:MM, hora de Guatemala.",
        examples=["2026-11-23T15:20"],
    )
    mensajes: list[str] = Field(
        min_length=1,
        max_length=MAXIMO_MENSAJES,
        examples=[["Buenas, mándeme 2 fardos de kola 600, una caja de aceite"]],
    )

    @field_validator("cliente_id")
    @classmethod
    def _sin_espacios_alrededor(cls, cliente_id: str) -> str:
        if cliente_id != cliente_id.strip():
            raise ValueError("no debe tener espacios al inicio ni al final")
        return cliente_id

    @field_validator("fecha_hora", mode="before")
    @classmethod
    def _formato_del_anexo(cls, valor: object) -> object:
        if not isinstance(valor, str) or not FECHA_HORA.fullmatch(valor):
            raise ValueError("debe tener el formato AAAA-MM-DDTHH:MM, por ejemplo 2026-11-23T15:20")
        return valor

    @field_validator("mensajes")
    @classmethod
    def _mensajes_con_texto(cls, mensajes: list[str]) -> list[str]:
        for posicion, mensaje in enumerate(mensajes):
            if not mensaje.strip():
                raise ValueError(f"el mensaje {posicion} está vacío")
            if len(mensaje) > MAXIMO_CARACTERES_POR_MENSAJE:
                raise ValueError(
                    f"el mensaje {posicion} tiene {len(mensaje)} caracteres; "
                    f"el máximo es {MAXIMO_CARACTERES_POR_MENSAJE}"
                )
        return mensajes


class LineaRespuesta(BaseModel):
    sku: str
    cantidad: int
    precio_unitario: float
    descuento_pct: int
    subtotal: float


class SustitucionRespuesta(BaseModel):
    sku_solicitado: str
    sku_entregado: str
    cantidad: int


class PendienteRespuesta(BaseModel):
    motivo: Motivo
    texto: str
    opciones: list[str]


class RespuestaInterpretar(BaseModel):
    cliente_id: str
    estado: Estado
    lineas: list[LineaRespuesta]
    total: float
    fecha_entrega: date | None
    sustituciones: list[SustitucionRespuesta]
    pendientes: list[PendienteRespuesta]
    motivos_revision: list[Motivo]
    mensaje_cliente: str

    @classmethod
    def desde_pedido(cls, cliente_id: str, pedido: Pedido, mensaje: str) -> "RespuestaInterpretar":
        """Los montos se calculan en Decimal y salen como números JSON (el Anexo usa 120.00)."""
        return cls(
            cliente_id=cliente_id,
            estado=pedido.estado,
            lineas=[
                LineaRespuesta(
                    sku=linea.sku,
                    cantidad=linea.cantidad,
                    precio_unitario=float(linea.precio_unitario),
                    descuento_pct=linea.descuento_pct,
                    subtotal=float(linea.subtotal),
                )
                for linea in pedido.lineas
            ],
            total=float(pedido.total),
            fecha_entrega=pedido.fecha_entrega,
            sustituciones=[
                SustitucionRespuesta(
                    sku_solicitado=s.sku_solicitado,
                    sku_entregado=s.sku_entregado,
                    cantidad=s.cantidad,
                )
                for s in pedido.sustituciones
            ],
            pendientes=[
                PendienteRespuesta(motivo=p.motivo, texto=p.texto, opciones=list(p.opciones))
                for p in pedido.pendientes
            ],
            motivos_revision=list(pedido.motivos_revision),
            mensaje_cliente=mensaje,
        )


class EstadoServicio(BaseModel):
    estado: Literal["ok", "degradado"]
    motivo: str | None = Field(
        default=None, description="Qué dependencia falla, si está degradado."
    )


class Error(BaseModel):
    detail: str
