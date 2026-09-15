# -*- coding: utf-8 -*-
"""Invariantes de las tablas de enums y guarda de BSFurnitureMarkerNode.

No inventa hechos del dominio: solo verifica propiedades estructurales que el
propio módulo declara, más una guarda de regresión de un bug real y documentado
en las tres tablas TIPOS_NODO (census + skill).
"""
import unittest

from _paths import preparar_path

preparar_path()

import parser_nif as pn  # noqa: E402
import nif_nodos as nn  # noqa: E402
import censo_nif as cn  # noqa: E402


class TablasEnumTests(unittest.TestCase):
    def test_tablas_son_dicts_int_a_str_no_vacios(self) -> None:
        for nombre in ("SKYRIM_LAYERS", "HAVOK_MATERIALS", "MOTION_SYSTEMS", "SHADER_TYPES"):
            tabla = getattr(pn, nombre)
            with self.subTest(tabla=nombre):
                self.assertIsInstance(tabla, dict)
                self.assertGreater(len(tabla), 0)
                for k, v in tabla.items():
                    self.assertIsInstance(k, int)
                    self.assertIsInstance(v, str)
                    self.assertTrue(v.strip(), "etiqueta vacía en %s[%r]" % (nombre, k))

    def test_conjuntos_de_tipos_son_de_strings(self) -> None:
        self.assertIsInstance(pn.TIPOS_NODO, set)
        self.assertTrue(all(isinstance(t, str) for t in pn.TIPOS_NODO))
        for nombre in ("TIPOS_SHAPE", "TIPOS_SKIN"):
            tupla = getattr(pn, nombre)
            with self.subTest(tupla=nombre):
                self.assertIsInstance(tupla, tuple)
                self.assertTrue(all(isinstance(t, str) for t in tupla))
                self.assertGreater(len(tupla), 0)


class RegresionFurnitureMarkerTests(unittest.TestCase):
    """Guarda del bug documentado en parser_nif.py: BSFurnitureMarkerNode NO
    hereda de NiNode. Incluirlo en TIPOS_NODO rompía 123 archivos de muebles al
    leer children. Este test falla si alguien lo reintroduce."""

    def test_furniture_marker_no_es_nodo(self) -> None:
        for modulo, tabla in (
            ("census/parser_nif.py", pn.TIPOS_NODO),
            ("skills/.../nif_nodos.py", nn.TIPOS_NODO),
            ("skills/.../censo_nif.py", cn.TIPOS_NODO),
        ):
            with self.subTest(modulo=modulo):
                self.assertNotIn("BSFurnitureMarkerNode", tabla)


if __name__ == "__main__":
    unittest.main()
