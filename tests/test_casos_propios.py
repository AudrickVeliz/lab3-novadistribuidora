"""Los casos propios de evaluación (D-012, D-014): su fuente es válida y el .jsonl está al día."""

import json

import pytest

from casos_dev import CARPETA_DATOS, CASOS_DEV, HAY_ARCHIVOS_PUBLICADOS
from generar_casos_propios import CONJUNTOS, generar
from novadistribuidora.contrato import SolicitudInterpretar
from novadistribuidora.datos import cargar_datos
from novadistribuidora.interpretacion import Interpretacion

FUENTES = {
    conjunto: json.loads(fuente.read_text(encoding="utf-8"))
    for conjunto, (fuente, _) in CONJUNTOS.items()
}
TAMANOS = {"propios": 40, "prueba": 15}


@pytest.mark.parametrize("conjunto", CONJUNTOS)
def test_casos_propios_tamano_por_conjunto(conjunto):
    assert len(FUENTES[conjunto]) == TAMANOS[conjunto]


def test_casos_propios_id_unico_entre_conjuntos():
    identificadores = [caso["id"] for fuente in FUENTES.values() for caso in fuente]

    assert len(set(identificadores)) == len(identificadores)


@pytest.mark.parametrize(
    "caso",
    [caso for fuente in FUENTES.values() for caso in fuente],
    ids=lambda caso: caso["id"],
)
def test_casos_propios_solicitud_e_interpretacion_validas(caso):
    SolicitudInterpretar.model_validate(caso["entrada"])
    Interpretacion.model_validate(caso["interpretacion"])


@pytest.mark.parametrize("conjunto", CONJUNTOS)
def test_casos_propios_en_el_formato_de_los_publicados(conjunto):
    _, casos = CONJUNTOS[conjunto]
    for linea in casos.read_text(encoding="utf-8").splitlines():
        assert list(json.loads(linea)) == ["id", "tipo", "entrada", "esperado"]


@pytest.mark.skipif(not HAY_ARCHIVOS_PUBLICADOS, reason="sin los archivos publicados")
@pytest.mark.parametrize("conjunto", CONJUNTOS)
def test_casos_propios_jsonl_coincide_con_su_fuente(conjunto):
    """Si alguien edita la fuente o el motor, el .jsonl debe regenerarse."""
    _, casos = CONJUNTOS[conjunto]
    generado = generar(FUENTES[conjunto], cargar_datos(CARPETA_DATOS))

    assert generado == casos.read_text(encoding="utf-8")


@pytest.mark.skipif(not HAY_ARCHIVOS_PUBLICADOS, reason="sin los archivos publicados")
def test_casos_propios_no_repiten_mensajes_publicados():
    publicados = {tuple(caso["entrada"]["mensajes"]) for caso in CASOS_DEV.values()}
    propios = [caso for fuente in FUENTES.values() for caso in fuente]

    assert not any(tuple(caso["entrada"]["mensajes"]) in publicados for caso in propios)
