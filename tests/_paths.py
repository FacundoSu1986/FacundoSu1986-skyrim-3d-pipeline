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


def preparar_path():
    """Agrega census/ y los scripts de la skill a sys.path (idempotente)."""
    for d in (CENSUS, SKILL_SCRIPTS):
        if d not in sys.path:
            sys.path.insert(0, d)
