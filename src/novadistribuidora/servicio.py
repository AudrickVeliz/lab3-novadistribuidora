"""El caso de uso del servicio: de una solicitud válida a la respuesta del contrato.

El intérprete es la única pieza que usa el modelo; llega inyectado, así que las pruebas
usan uno falso y el servicio no sabe si detrás hay LangChain u otra cosa (D-008).
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from novadistribuidora.confirmacion import redactar_confirmacion
from novadistribuidora.contrato import RespuestaInterpretar, SolicitudInterpretar
from novadistribuidora.datos import Datos
from novadistribuidora.interpretacion import Interpretacion
from novadistribuidora.motor import armar_pedido


class ClienteNoExiste(Exception):
    """El cliente_id no está en clientes.parquet: la API responde 404."""


class InterpreteNoDisponible(Exception):
    """El modelo no pudo interpretar el mensaje, ni con el principal ni con el alterno.

    La API responde 503: nunca se inventa un pedido (D-008).
    """


class Interprete(Protocol):
    def interpretar(self, mensajes: Sequence[str]) -> Interpretacion:
        """Lanza InterpreteNoDisponible si no logra una interpretación válida.

        No recibe al cliente: "lo de siempre" lo expande el código con el historial (D-001).
        """
        ...


# Cada chequeo lanza una excepción con el motivo si su dependencia no está disponible.
Chequeo = Callable[[], None]


@dataclass
class Servicio:
    datos: Datos
    interprete: Interprete
    chequeos: Mapping[str, Chequeo] = field(default_factory=dict)

    def interpretar_pedido(self, solicitud: SolicitudInterpretar) -> RespuestaInterpretar:
        cliente = self.datos.clientes.get(solicitud.cliente_id)
        if cliente is None:
            raise ClienteNoExiste(f"{solicitud.cliente_id} no está en clientes.parquet")
        interpretacion = self.interprete.interpretar(solicitud.mensajes)
        pedido = armar_pedido(interpretacion, cliente, solicitud.fecha_hora, self.datos)
        mensaje = redactar_confirmacion(pedido, self.datos.productos, solicitud.fecha_hora)
        return RespuestaInterpretar.desde_pedido(cliente.cliente_id, pedido, mensaje)

    def dependencias_caidas(self) -> list[str]:
        """Los motivos de las dependencias que fallan; vacío si todo está bien."""
        caidas = []
        for nombre, chequeo in self.chequeos.items():
            try:
                chequeo()
            except Exception as error:  # cualquier falla de una dependencia la degrada
                caidas.append(f"{nombre}: {error}")
        return caidas
