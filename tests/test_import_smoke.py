# -*- coding: utf-8 -*-
"""Smoke de importación: los módulos de Python puro deben cargar sin error.

Qué cubre y qué NO:
- SÍ: que cada módulo stdlib-only importe (atrapa NameError, símbolos que faltan,
  imports rotos entre census/verificar.py y census/parser_nif.py).
- NO: los scripts de Blender (`medir_parte`, `preparar_parte`) importan `bpy`,
  que no existe en CPython normal. Su validación en CI es solo de sintaxis
  (`python -m compileall`), no de import.
- NO: `--autotest` del parser, que necesita el corpus vanilla (no versionado).
"""
import unittest

from _paths import preparar_path

preparar_path()

MODULOS_PUROS = [
    "parser_nif",      # census/
    "parser_dds",      # census/
    "verificar",       # census/  (importa parser_nif)
    "agregados",       # census/
    "generar_reporte",  # census/  (importa agregados)
    "censo_nif",       # skills/modelo-ia-a-skyrim/scripts/
    "nif_nodos",       # skills/modelo-ia-a-skyrim/scripts/
    "verificar_export",  # skills/...  (importa censo_nif)
]


class ImportSmokeTests(unittest.TestCase):
    def test_los_modulos_puros_importan(self) -> None:
        for nombre in MODULOS_PUROS:
            with self.subTest(modulo=nombre):
                __import__(nombre)


if __name__ == "__main__":
    unittest.main()
