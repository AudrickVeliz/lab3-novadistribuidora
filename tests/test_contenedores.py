"""Reglas de los contenedores (D-011) que se pueden revisar sin construirlos."""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
COMPOSE = (RAIZ / "compose.yaml").read_text(encoding="utf-8")
CONTAINERFILES = sorted(RAIZ.glob("Containerfile*"))


def test_contenedores_docker_lee_las_mismas_exclusiones_que_podman():
    # Podman lee .containerignore; Docker solo .dockerignore. Si difieren, Docker podría
    # meter .env o los datos en el contexto de construcción.
    containerignore = (RAIZ / ".containerignore").read_bytes()

    assert (RAIZ / ".dockerignore").read_bytes() == containerignore


def test_contenedores_el_contexto_solo_incluye_el_paquete():
    reglas = (RAIZ / ".containerignore").read_text(encoding="utf-8").split()

    assert reglas[reglas.index("*") :][:3] == ["*", "!pyproject.toml", "!src/"]


def test_contenedores_imagenes_base_con_version_fija():
    origenes = [
        linea.split()[1]
        for archivo in CONTAINERFILES
        for linea in archivo.read_text(encoding="utf-8").splitlines()
        if linea.startswith("FROM ")
    ]
    externas = re.findall(r"image: (?!localhost/)(\S+)", COMPOSE)

    assert len(origenes) == 2
    for imagen in origenes + externas:
        assert re.search(r":v?\d+\.\d+", imagen), f"{imagen} no fija la versión"
        assert "/" in imagen.split(":")[0], f"{imagen}: Podman necesita el nombre completo"


def test_contenedores_la_api_corre_sin_privilegios():
    api = (RAIZ / "Containerfile").read_text(encoding="utf-8")

    assert re.search(r"^USER novadistribuidora$", api, re.MULTILINE)


def test_contenedores_mlflow_solo_se_publica_en_la_maquina():
    assert '"127.0.0.1:5000:5000"' in COMPOSE
    assert '"8000:8000"' in COMPOSE


def test_contenedores_la_api_no_espera_a_mlflow():
    servicio_api = COMPOSE.split("\n  api:\n")[1].split("\n  mlflow:\n")[0]

    assert "depends_on:" not in servicio_api
    assert "env_file: .env" in servicio_api
    assert "./datos:/datos:ro" in servicio_api


def test_contenedores_la_base_de_mlflow_no_sale_de_la_red_interna():
    servicio_bd = COMPOSE.split("\n  bd-mlflow:\n")[1].split("\nnetworks:\n")[0]

    assert "ports:" not in servicio_bd
    assert "- interna-mlflow" in servicio_bd
    assert "internal: true" in COMPOSE
