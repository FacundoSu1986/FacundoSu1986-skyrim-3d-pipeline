# -*- coding: utf-8 -*-
"""Empaqueta skills/modelo-ia-a-skyrim como .skill instalable.

El .skill es un artefacto de build, no se versiona (ver .gitignore): el arbol
de skills/ ES la skill, y Claude Code la carga directo de la carpeta. Este
script existe para distribuirla -- adjuntala a un Release de GitHub.

Uso:
  python build_skill.py [nombre-de-la-skill]
"""
import os
import sys
import zipfile

RAIZ = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.join(RAIZ, "skills")
IGNORAR_DIR = {"__pycache__", ".git"}
IGNORAR_EXT = {".pyc", ".pyo"}


def empaquetar(nombre, carpeta=None):
    """Arma `<nombre>.skill` en `carpeta` (por defecto, la raiz del repo).

    `carpeta` existe para tests/test_skill_empaquetada.py, que empaqueta cada
    skill en un temporal, la extrae lejos del repo y corre sus scripts desde
    ahi: un script que importe algo de census/ anda en el repo y no instalado.
    """
    origen = os.path.join(SKILLS, nombre)
    if not os.path.isdir(origen):
        raise SystemExit("no existe: %s" % origen)
    if not os.path.exists(os.path.join(origen, "SKILL.md")):
        raise SystemExit("%s no tiene SKILL.md; no es una skill" % origen)

    destino = os.path.join(carpeta or RAIZ, nombre + ".skill")
    n = 0
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for base, dirs, archivos in os.walk(origen):
            dirs[:] = [d for d in dirs if d not in IGNORAR_DIR]
            for f in sorted(archivos):
                if os.path.splitext(f)[1] in IGNORAR_EXT:
                    continue
                ruta = os.path.join(base, f)
                dentro = os.path.join(
                    nombre, os.path.relpath(ruta, origen)).replace(os.sep, "/")
                z.write(ruta, dentro)
                print("  %-46s %7d B" % (dentro, os.path.getsize(ruta)))
                n += 1
    print("--> %s  (%d archivos, %d B)"
          % (os.path.basename(destino), n, os.path.getsize(destino)))
    return destino


def main():
    if len(sys.argv) > 1:
        empaquetar(sys.argv[1])
        return
    if not os.path.isdir(SKILLS):
        raise SystemExit("no hay carpeta skills/")
    encontradas = [d for d in sorted(os.listdir(SKILLS))
                   if os.path.exists(os.path.join(SKILLS, d, "SKILL.md"))]
    if not encontradas:
        raise SystemExit("ninguna carpeta de skills/ tiene SKILL.md")
    for nombre in encontradas:
        empaquetar(nombre)


if __name__ == "__main__":
    main()
