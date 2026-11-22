"""Verificación local: la misma puerta de calidad que corre GitHub Actions (D-006).

python tools/verificar.py                 todo: revisiones, pruebas con cobertura y auditoría
python tools/verificar.py --sin-pruebas   solo las revisiones rápidas, antes de cada commit

Se corre con el Python del entorno del proyecto, que tiene instalado el extra dev.
"""

import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PY = sys.executable
FLUJO = str(RAIZ / "tools" / "flujo_git.py")
RAMA_PRINCIPAL = "main"


def _actionlint() -> str:
    # actionlint-py instala el ejecutable junto a los scripts del entorno, no como módulo.
    ruta = shutil.which("actionlint", path=sysconfig.get_path("scripts")) or shutil.which(
        "actionlint"
    )
    if ruta is None:
        sys.exit("No se encontró actionlint: instala el extra dev con pip install -e '.[dev]'")
    return ruta


def _rama_actual() -> str:
    return subprocess.run(
        ["git", "branch", "--show-current"],  # noqa: S607 - git se toma del PATH
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _revisiones() -> list[tuple[str, list[str]]]:
    revisiones = [
        ("Formato", [PY, "-m", "ruff", "format", "--check", "."]),
        ("Lint, seguridad y complejidad", [PY, "-m", "ruff", "check", "."]),
        ("Workflows de GitHub", [_actionlint()]),
        ("Finales de línea LF", [PY, FLUJO, "--finales-de-linea"]),
    ]
    rama = _rama_actual()
    if rama and rama != RAMA_PRINCIPAL:
        revisiones += [
            ("Nombre de la rama", [PY, FLUJO, "--rama", rama]),
            ("Commits de la rama", [PY, FLUJO, "--rango", f"origin/{RAMA_PRINCIPAL}..HEAD"]),
        ]
    return revisiones


def _pruebas_y_auditoria() -> list[tuple[str, list[str]]]:
    return [
        ("Pruebas", [PY, "-m", "coverage", "run", "-m", "pytest", "-q", "-rs"]),
        ("Cobertura", [PY, "-m", "coverage", "report"]),
        ("Vulnerabilidades de dependencias", [PY, "-m", "pip_audit", "--skip-editable"]),
    ]


def _correr(nombre: str, comando: list[str]) -> bool:
    print(f"\n== {nombre}", flush=True)
    return subprocess.run(comando, cwd=RAIZ, check=False).returncode == 0  # noqa: S603 - comandos fijos


def main() -> int:
    pasos = _revisiones()
    if "--sin-pruebas" not in sys.argv[1:]:
        pasos += _pruebas_y_auditoria()
    fallidos = [nombre for nombre, comando in pasos if not _correr(nombre, comando)]
    print("\nResultado:", "todo correcto" if not fallidos else "falló " + ", ".join(fallidos))
    return 1 if fallidos else 0


if __name__ == "__main__":
    sys.exit(main())
