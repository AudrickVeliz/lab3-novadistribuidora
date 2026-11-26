"""Contrato del Anexo: POST /v1/pedidos/interpretar y GET /health, con un intérprete falso."""

import logging

import pytest
from fastapi.testclient import TestClient

from novadistribuidora.api import MOTIVO_503, crear_app
from novadistribuidora.interpretacion import Interpretacion, Mencion
from novadistribuidora.servicio import InterpreteNoDisponible, Servicio

RUTA = "/v1/pedidos/interpretar"
CAMPOS_DEL_CONTRATO = {
    "cliente_id",
    "estado",
    "lineas",
    "total",
    "fecha_entrega",
    "sustituciones",
    "pendientes",
    "motivos_revision",
    "mensaje_cliente",
}
PEDIDO_CON_AMBIGUO = Interpretacion(
    es_pedido=True,
    menciones=[
        Mencion(texto="2 fardos de kola 600", skus=["B01"], cantidad=2),
        Mencion(texto="una caja de aceite", skus=["A06", "A07"], cantidad=1),
    ],
)


class InterpreteFalso:
    """Devuelve una interpretación fija o lanza un error, y recuerda con qué lo llamaron."""

    def __init__(self, interpretacion=PEDIDO_CON_AMBIGUO, error=None):
        self.interpretacion = interpretacion
        self.error = error
        self.llamadas = []

    def interpretar(self, mensajes):
        self.llamadas.append(list(mensajes))
        if self.error is not None:
            raise self.error
        return self.interpretacion


def _cliente_http(datos, interprete=None, chequeos=None):
    servicio = Servicio(datos, interprete or InterpreteFalso(), chequeos or {})
    return TestClient(crear_app(servicio))


def _solicitud(**cambios):
    solicitud = {
        "cliente_id": "C001",
        "fecha_hora": "2026-11-23T15:20",
        "mensajes": ["Buenas, mándeme 2 fardos de kola 600, una caja de aceite"],
    }
    return solicitud | cambios


# Respuesta 200


def test_contrato_respuesta_con_todos_los_campos_del_anexo(datos):
    respuesta = _cliente_http(datos).post(RUTA, json=_solicitud())

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert set(cuerpo) == CAMPOS_DEL_CONTRATO
    assert cuerpo["cliente_id"] == "C001"
    assert cuerpo["estado"] == "requiere_revision"
    assert cuerpo["lineas"] == [
        {
            "sku": "B01",
            "cantidad": 2,
            "precio_unitario": 120.0,
            "descuento_pct": 0,
            "subtotal": 240.0,
        }
    ]
    assert cuerpo["total"] == 240.0
    assert cuerpo["fecha_entrega"] == "2026-11-26"
    assert cuerpo["sustituciones"] == []
    assert cuerpo["pendientes"] == [
        {"motivo": "producto_ambiguo", "texto": "una caja de aceite", "opciones": ["A06", "A07"]}
    ]
    assert cuerpo["motivos_revision"] == ["producto_ambiguo"]
    assert cuerpo["mensaje_cliente"].startswith("¡Buenas tardes!")


def test_contrato_los_montos_son_numeros_json(datos):
    cuerpo = _cliente_http(datos).post(RUTA, json=_solicitud()).json()

    assert isinstance(cuerpo["total"], float)
    assert isinstance(cuerpo["lineas"][0]["precio_unitario"], float)
    assert isinstance(cuerpo["lineas"][0]["subtotal"], float)


def test_contrato_fuera_de_alcance_sin_lineas_total_cero_y_fecha_nula(datos):
    interprete = InterpreteFalso(Interpretacion(es_pedido=False))

    cuerpo = _cliente_http(datos, interprete).post(RUTA, json=_solicitud()).json()

    assert cuerpo["estado"] == "fuera_de_alcance"
    assert cuerpo["lineas"] == []
    assert cuerpo["total"] == 0
    assert cuerpo["fecha_entrega"] is None


def test_contrato_el_interprete_recibe_los_mensajes(datos):
    interprete = InterpreteFalso()
    mensajes = ["Buenas", "le encargo 2 de kola 600"]

    _cliente_http(datos, interprete).post(RUTA, json=_solicitud(mensajes=mensajes))

    assert interprete.llamadas == [mensajes]


def test_contrato_ignora_los_campos_que_no_define(datos):
    respuesta = _cliente_http(datos).post(RUTA, json=_solicitud(vendedor="Juan", precio=1))

    assert respuesta.status_code == 200


def test_contrato_acepta_segundos_en_la_fecha_hora(datos):
    respuesta = _cliente_http(datos).post(RUTA, json=_solicitud(fecha_hora="2026-11-23T15:20:59"))

    assert respuesta.status_code == 200
    assert respuesta.json()["fecha_entrega"] == "2026-11-26"


# 404 y 422


def test_contrato_cliente_inexistente_es_404_sin_llamar_al_modelo(datos):
    interprete = InterpreteFalso()

    respuesta = _cliente_http(datos, interprete).post(RUTA, json=_solicitud(cliente_id="C999"))

    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "No existe el cliente C999"}
    assert interprete.llamadas == []


@pytest.mark.parametrize(
    ("cambios", "campo", "motivo"),
    [
        ({"cliente_id": None}, "cliente_id", "debe ser texto"),
        ({"cliente_id": ""}, "cliente_id", "no puede estar vacío"),
        ({"cliente_id": " C001"}, "cliente_id", "espacios"),
        ({"cliente_id": 1}, "cliente_id", "debe ser texto"),
        ({"mensajes": []}, "mensajes", "al menos un mensaje"),
        ({"mensajes": "hola"}, "mensajes", "lista de textos"),
        ({"mensajes": ["   "]}, "mensajes", "el mensaje 0 está vacío"),
        ({"mensajes": ["hola", 5]}, "mensajes[1]", "debe ser texto"),
        ({"mensajes": ["hola"] * 21}, "mensajes", "como máximo 20 mensajes"),
        ({"mensajes": ["x" * 2001]}, "mensajes", "2001 caracteres"),
        ({"fecha_hora": "23/11/2026 15:20"}, "fecha_hora", "AAAA-MM-DDTHH:MM"),
        ({"fecha_hora": "2026-11-23"}, "fecha_hora", "AAAA-MM-DDTHH:MM"),
        ({"fecha_hora": "2026-11-23 15:20"}, "fecha_hora", "AAAA-MM-DDTHH:MM"),
        ({"fecha_hora": "2026-11-23T15:20Z"}, "fecha_hora", "AAAA-MM-DDTHH:MM"),
        ({"fecha_hora": "2026-13-01T10:00"}, "fecha_hora", "no es una fecha y hora válida"),
        ({"fecha_hora": "2026-11-23T25:00"}, "fecha_hora", "no es una fecha y hora válida"),
        ({"fecha_hora": 20261123}, "fecha_hora", "AAAA-MM-DDTHH:MM"),
    ],
)
def test_contrato_solicitud_invalida_es_422_con_el_motivo(datos, cambios, campo, motivo):
    interprete = InterpreteFalso()

    respuesta = _cliente_http(datos, interprete).post(RUTA, json=_solicitud(**cambios))

    assert respuesta.status_code == 422
    assert f"{campo}: " in respuesta.json()["detail"]
    assert motivo in respuesta.json()["detail"]
    assert interprete.llamadas == []


@pytest.mark.parametrize("campo", ["cliente_id", "fecha_hora", "mensajes"])
def test_contrato_campo_faltante_es_422(datos, campo):
    solicitud = _solicitud()
    del solicitud[campo]

    respuesta = _cliente_http(datos).post(RUTA, json=solicitud)

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == f"{campo}: falta este campo"


def test_contrato_cuerpo_que_no_es_json_es_422(datos):
    respuesta = _cliente_http(datos).post(
        RUTA, content="no es json", headers={"content-type": "application/json"}
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == "cuerpo: no es JSON válido"


def test_contrato_cuerpo_que_no_es_objeto_es_422(datos):
    respuesta = _cliente_http(datos).post(RUTA, json=["C001"])

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == "cuerpo: debe ser un objeto JSON"


def test_contrato_la_validacion_va_antes_que_el_cliente(datos):
    respuesta = _cliente_http(datos).post(RUTA, json=_solicitud(cliente_id="C999", mensajes=[]))

    assert respuesta.status_code == 422


# 503


def test_contrato_modelo_no_disponible_es_503_sin_inventar_un_pedido(datos):
    interprete = InterpreteFalso(error=InterpreteNoDisponible("OpenRouter no respondió"))

    respuesta = _cliente_http(datos, interprete).post(RUTA, json=_solicitud())

    assert respuesta.status_code == 503
    assert respuesta.json() == {"detail": MOTIVO_503}


def test_el_503_no_muestra_la_causa_al_cliente_y_la_deja_en_el_log(datos, caplog):
    causa = "Los modelos openai/gpt-6-luna, anthropic/claude-haiku-5.5 fallaron (APITimeoutError)"
    interprete = InterpreteFalso(error=InterpreteNoDisponible(causa))

    with caplog.at_level(logging.WARNING, logger="novadistribuidora.api"):
        respuesta = _cliente_http(datos, interprete).post(RUTA, json=_solicitud())

    assert "gpt-6-luna" not in respuesta.text
    assert "APITimeoutError" not in respuesta.text
    assert causa in caplog.text


# GET /health


def test_health_ok_sin_motivo(datos):
    respuesta = _cliente_http(datos).get("/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}


def test_health_degradado_responde_200_con_el_motivo(datos):
    def mlflow_caido():
        raise ConnectionError("no responde en http://mlflow:5000")

    respuesta = _cliente_http(datos, chequeos={"mlflow": mlflow_caido}).get("/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "estado": "degradado",
        "motivo": "mlflow: no responde en http://mlflow:5000",
    }


def test_health_degradado_no_impide_atender_pedidos(datos):
    def caido():
        raise ConnectionError("caído")

    cliente_http = _cliente_http(datos, chequeos={"mlflow": caido})

    assert cliente_http.get("/health").json()["estado"] == "degradado"
    assert cliente_http.post(RUTA, json=_solicitud()).status_code == 200


def test_contrato_documentado_en_openapi(datos):
    rutas = _cliente_http(datos).get("/openapi.json").json()["paths"]

    assert set(rutas[RUTA]["post"]["responses"]) >= {"200", "404", "422", "503"}
    assert "/health" in rutas
