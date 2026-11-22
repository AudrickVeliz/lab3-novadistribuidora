"""Reglas de "Flujo de Git" en CLAUDE.md, tal como las revisan el hook commit-msg y CI."""

import pytest

from flujo_git import problema_de_la_rama, problema_del_asunto


@pytest.mark.parametrize(
    "asunto",
    [
        "feat: calcular el descuento por escala",
        "fix: aceptar fechas con segundos",
        "chore(deps): bump ruff from 0.17.6 to 0.17.7",
        "ci: fijar las acciones a un SHA",
        "Merge pull request #2 from AudrickVeliz/feat/motor-reglas-politicas",
        "Merge branch 'main' into feat/armar-pedido",
    ],
)
def test_flujo_asuntos_validos(asunto):
    assert problema_del_asunto(asunto) is None


@pytest.mark.parametrize(
    ("asunto", "motivo"),
    [
        ("Calcular el descuento", "tipo: descripción"),
        ("feature: calcular el descuento", "tipo: descripción"),
        ("feat:calcular el descuento", "tipo: descripción"),
        ("feat: calcular el descuento.", "punto"),
        ("fixup! feat: calcular el descuento", "provisional"),
        ("WIP avance", "provisional"),
        ("feat: " + "x" * 67, "73 caracteres"),
    ],
)
def test_flujo_asuntos_invalidos(asunto, motivo):
    assert motivo in problema_del_asunto(asunto)


@pytest.mark.parametrize("rama", ["feat/armar-pedido", "ci/pipeline-completo", "docs/readme"])
def test_flujo_ramas_validas(rama):
    assert problema_de_la_rama(rama) is None


@pytest.mark.parametrize("rama", ["main", "feature/x", "feat/Armar_Pedido", "feat/", "pedido"])
def test_flujo_ramas_invalidas(rama):
    assert problema_de_la_rama(rama) is not None
