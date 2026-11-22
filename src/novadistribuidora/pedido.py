"""Las piezas del pedido que propone el servicio, con los nombres y valores del contrato del Anexo."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class Motivo(StrEnum):
    PRODUCTO_AMBIGUO = "producto_ambiguo"
    PRODUCTO_NO_EXISTE = "producto_no_existe"
    AGOTADO_SIN_SUSTITUTO = "agotado_sin_sustituto"
    CANTIDAD_NO_CONVERTIBLE = "cantidad_no_convertible"
    # Solo aparece en motivos_revision, nunca en un pendiente (Anexo).
    CREDITO_EXCEDIDO = "credito_excedido"


class Estado(StrEnum):
    CONFIRMADO = "confirmado"
    REQUIERE_REVISION = "requiere_revision"
    FUERA_DE_ALCANCE = "fuera_de_alcance"


@dataclass(frozen=True)
class Linea:
    sku: str
    cantidad: int
    precio_unitario: Decimal
    descuento_pct: int
    subtotal: Decimal


@dataclass(frozen=True)
class Sustitucion:
    sku_solicitado: str
    sku_entregado: str
    cantidad: int


@dataclass(frozen=True)
class Pendiente:
    motivo: Motivo
    texto: str
    opciones: tuple[str, ...]
