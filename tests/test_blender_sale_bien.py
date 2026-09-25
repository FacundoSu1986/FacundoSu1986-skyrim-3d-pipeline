# -*- coding: utf-8 -*-
"""Un script de Blender que revienta tiene que salir con algo distinto de 0.

Medido con Blender 4.4.1 en modo -b: una excepcion sin atrapar sale con 0.
Antes de este test, los cinco scripts de Blender del repo terminaban con un
`main()` suelto: `preparar_parte.py` con un .glb inexistente salia con 0.
Todos terminan ahora con `correr(main)` (scripts/correr_en_blender.py), y este
test RECORRE los scripts: uno nuevo que importe bpy sin eso rompe la suite.

Un error de SINTAXIS tambien sale con 0 y ningun envoltorio lo ataja, porque
revienta antes de ejecutar nada: eso lo cubre el compileall del workflow.
"""
import glob
import os
import re
import unittest

from _paths import RAIZ, preparar_path

preparar_path()

import correr_en_blender  # noqa: E402

USA_BPY = re.compile(r"^\s*(import bpy|from bpy)", re.M)
MAIN_SUELTO = re.compile(r"^main\(\)\s*$", re.M)


def scripts_de_blender():
    rutas = sorted(glob.glob(os.path.join(RAIZ, "skills", "*", "scripts",
                                          "*.py")))
    return [r for r in rutas
            if USA_BPY.search(open(r, encoding="utf-8").read())]


class TodosLosScriptsDeBlenderTests(unittest.TestCase):

    def test_hay_scripts_de_blender(self):
        """Cero scripts encontrados no es exito: el glob podria estar mal."""
        self.assertGreaterEqual(len(scripts_de_blender()), 5)

    def test_cada_uno_termina_con_correr(self):
        for ruta in scripts_de_blender():
            texto = open(ruta, encoding="utf-8").read()
            with self.subTest(script=os.path.basename(ruta)):
                self.assertTrue(texto.rstrip().endswith("correr(main)"),
                                "tiene que terminar con correr(main)")
                self.assertIsNone(MAIN_SUELTO.search(texto),
                                  "tiene un main() suelto: una excepcion "
                                  "saldria con 0")
                self.assertIn("from correr_en_blender import correr", texto)


class CorrerTests(unittest.TestCase):

    def test_una_excepcion_sale_con_1(self):
        def revienta():
            raise KeyError("x")
        with self.assertRaises(SystemExit) as ctx:
            correr_en_blender.correr(revienta)
        self.assertEqual(1, ctx.exception.code)

    def test_un_systemexit_pasa_tal_cual(self):
        def sale():
            raise SystemExit(3)
        with self.assertRaises(SystemExit) as ctx:
            correr_en_blender.correr(sale)
        self.assertEqual(3, ctx.exception.code)

    def test_sin_error_no_sale(self):
        self.assertIsNone(correr_en_blender.correr(lambda: None))


if __name__ == "__main__":
    unittest.main()
