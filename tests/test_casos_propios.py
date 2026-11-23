"""Los casos propios de evaluación (D-012): su fuente es válida y el .jsonl está al día."""

import json

import pytest

from casos_dev import CARPETA_DATOS, CASOS_DEV, HAY_ARCHIVOS_PUBLICADOS
from generar_casos_propios import CASOS, FUENTE, generar
from novadistribuidora.contrato import SolicitudInterpretar
from novadistribuidora.datos import cargar_datos
from novadistribuidora.interpretacion import Interpretacion

FUENTE_CASOS = json.loads(FUENTE.read_text(encoding="utf-8"))


def test_casos_propios_son_cuarenta_con_id_unico():
    identificadores = [caso["id"] for caso in FUENTE_CASOS]

    assert len(identificadores) == 40
    assert len(set(identificadores)) == 40


@pytest.mark.parametrize("caso", FUENTE_CASOS, ids=lambda caso: caso["id"])
def test_casos_propios_solicitud_e_interpretacion_validas(caso):
    SolicitudInterpretar.model_validate(caso["entrada"])
    Interpretacion.model_validate(caso["interpretacion"])


def test_casos_propios_en_el_formato_de_los_publicados():
    for linea in CASOS.read_text(encoding="utf-8").splitlines():
        assert list(json.loads(linea)) == ["id", "tipo", "entrada", "esperado"]


@pytest.mark.skipif(not HAY_ARCHIVOS_PUBLICADOS, reason="sin los archivos publicados")
def test_casos_propios_jsonl_coincide_con_su_fuente():
    """Si alguien edita la fuente o el motor, el .jsonl debe regenerarse."""
    assert generar(FUENTE_CASOS, cargar_datos(CARPETA_DATOS)) == CASOS.read_text(encoding="utf-8")


@pytest.mark.skipif(not HAY_ARCHIVOS_PUBLICADOS, reason="sin los archivos publicados")
def test_casos_propios_no_repiten_mensajes_publicados():
    publicados = {tuple(caso["entrada"]["mensajes"]) for caso in CASOS_DEV.values()}

    assert not any(tuple(caso["entrada"]["mensajes"]) in publicados for caso in FUENTE_CASOS)
