"""Lo único que el modelo le entrega al código: qué productos menciona el cliente y cómo (D-001).

No hay campos para precios, descuentos, crédito ni fechas, y `extra="forbid"` rechaza
cualquier campo que el modelo agregue: un mensaje no tiene por dónde cambiar las condiciones.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Unidad = Literal["venta", "suelta", "docena"]
Operacion = Literal["agregar", "corregir", "quitar"]


class Mencion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto: str = Field(
        min_length=1,
        description="Fragmento del mensaje que nombra el producto, como lo escribió el cliente.",
    )
    skus: list[str] = Field(
        description=(
            "SKU del catálogo que pueden corresponder al texto: uno si no hay duda, "
            "varios si es ambiguo, ninguno si la distribuidora no lo vende."
        ),
    )
    cantidad: int | None = Field(
        default=None,
        gt=0,
        description="Cantidad que dice el cliente; null si no la dice.",
    )
    unidad: Unidad = Field(
        default="venta",
        description=(
            "venta: fardo, caja, display o quintal, o sin unidad; "
            "suelta: botellas, latas, bolsas, sobres, unidades o libras de un producto de 1 lb "
            "(media docena son 6 sueltas); docena: docenas enteras."
        ),
    )
    operacion: Operacion = Field(
        default="agregar",
        description=(
            "agregar: pide el producto; corregir: cambia una cantidad que ya dijo "
            "('no, mejor que sean 5'); quitar: lo saca del pedido ('sin las papitas')."
        ),
    )


class Interpretacion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    es_pedido: bool = Field(
        description="false si los mensajes no piden productos: consultas, saludos, reclamos.",
    )
    lo_de_siempre: bool = Field(
        default=False,
        description="true si pide 'lo de siempre', 'lo mismo de la otra vez' o algo equivalente.",
    )
    menciones: list[Mencion] = Field(
        default_factory=list,
        description="Productos mencionados, en el orden de los mensajes.",
    )
