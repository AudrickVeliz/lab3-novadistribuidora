"""Revisa las reglas de Git de CLAUDE.md ("Flujo de Git") en el hook commit-msg y en CI.

python tools/flujo_git.py --mensaje ARCHIVO    asunto de un commit (hook commit-msg)
python tools/flujo_git.py --rango BASE..HEAD   asuntos de los commits de un PR
python tools/flujo_git.py --rama NOMBRE        prefijo de la rama
python tools/flujo_git.py --finales-de-linea   todos los archivos versionados en LF

Solo usa la biblioteca estándar: corre con cualquier Python, también antes de crear el entorno.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

TIPOS = ("feat", "fix", "chore", "docs", "test", "ci", "refactor")
MAXIMO_ASUNTO = 72
ASUNTO = re.compile(rf"^({'|'.join(TIPOS)})(\([a-z0-9-]+\))?: \S")
PROVISIONALES = ("fixup!", "squash!", "amend!", "wip")
# Los merges los crea GitHub al integrar un PR, o git al actualizar una rama.
MERGE = re.compile(r"^Merge (pull request|branch|remote-tracking branch) ")


def problema_del_asunto(asunto: str) -> str | None:
    if MERGE.match(asunto):
        return None
    if asunto.lower().startswith(PROVISIONALES):
        return "es un commit provisional: intégralo antes de abrir el PR"
    if not ASUNTO.match(asunto):
        return f"debe empezar con 'tipo: descripción', con tipo en {', '.join(TIPOS)}"
    if len(asunto) > MAXIMO_ASUNTO:
        return f"tiene {len(asunto)} caracteres; el máximo es {MAXIMO_ASUNTO}"
    if asunto.endswith("."):
        return "no termina en punto"
    return None


def problema_de_la_rama(rama: str) -> str | None:
    if re.fullmatch(rf"({'|'.join(TIPOS)})/[a-z0-9][a-z0-9-]*", rama):
        return None
    return f"debe llamarse tipo/descripcion-corta, con tipo en {', '.join(TIPOS)}"


def _git(*argumentos: str) -> str:
    resultado = subprocess.run(  # noqa: S603 - argumentos fijos, sin shell
        ["git", *argumentos],  # noqa: S607 - git se toma del PATH, como en cualquier hook
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return resultado.stdout


def _revisar_mensaje(archivo: str) -> list[str]:
    asunto = Path(archivo).read_text(encoding="utf-8").splitlines()[0].strip()
    problema = problema_del_asunto(asunto)
    return [f"'{asunto}': {problema}"] if problema else []


def _revisar_rango(rango: str) -> list[str]:
    errores = []
    for linea in _git("log", "--format=%h %s", rango).splitlines():
        sha, asunto = linea.split(" ", 1)
        problema = problema_del_asunto(asunto)
        if problema:
            errores.append(f"{sha} '{asunto}': {problema}")
    return errores


def _revisar_rama(rama: str) -> list[str]:
    problema = problema_de_la_rama(rama)
    return [f"rama '{rama}': {problema}"] if problema else []


def _revisar_finales_de_linea() -> list[str]:
    # Cada línea: "i/lf w/crlf attr/... <tab>ruta". Los binarios dicen "-text".
    return [
        f"{linea.split(chr(9))[-1]}: tiene CRLF; el proyecto usa LF (.gitattributes)"
        for linea in _git("ls-files", "--eol").splitlines()
        if "crlf" in linea.split(chr(9))[0]
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--mensaje", metavar="ARCHIVO")
    grupo.add_argument("--rango", metavar="BASE..HEAD")
    grupo.add_argument("--rama", metavar="NOMBRE")
    grupo.add_argument("--finales-de-linea", action="store_true")
    argumentos = parser.parse_args()

    if argumentos.mensaje:
        errores = _revisar_mensaje(argumentos.mensaje)
    elif argumentos.rango:
        errores = _revisar_rango(argumentos.rango)
    elif argumentos.rama:
        errores = _revisar_rama(argumentos.rama)
    else:
        errores = _revisar_finales_de_linea()

    # En Windows la salida de un hook usa cp1252 y desfigura los acentos.
    sys.stderr.reconfigure(encoding="utf-8")
    for error in errores:
        print(f"flujo_git: {error}", file=sys.stderr)
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
