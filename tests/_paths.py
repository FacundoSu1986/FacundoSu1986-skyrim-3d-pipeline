# -*- coding: utf-8 -*-
"""Rutas a los directorios de scripts, para importarlos como módulos en tests.

Los scripts viven en dos carpetas (`census/` y la skill), fuera de cualquier
paquete instalable. Los tests los cargan agregando esas carpetas a sys.path;
no hay `pyproject`/`src` a propósito (ver docs/DECISIONS.md).
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CENSUS = os.path.join(RAIZ, "census")
SKILL_SCRIPTS = os.path.join(RAIZ, "skills", "modelo-ia-a-skyrim", "scripts")
SKILL_ASSET = os.path.join(RAIZ, "skills", "asset-nuevo-skyrim", "scripts")

# nif_nodos.py esta en las DOS carpetas de skill, byte a byte igual (lo exige
# tests/test_skill_asset_nuevo.py). Cual se importa lo decide el orden, y el
# mecanismo es al reves de lo que parece: cada vuelta hace insert(0, ...), asi
# que el ULTIMO de la tupla queda PRIMERO en sys.path. Por eso SKILL_SCRIPTS
# --modelo-ia-a-skyrim, la copia canonica-- va al final.


def preparar_path():
    """Agrega census/ y los scripts de las skills a sys.path (idempotente)."""
    for d in (CENSUS, SKILL_ASSET, SKILL_SCRIPTS):
        if d not in sys.path:
            sys.path.insert(0, d)
