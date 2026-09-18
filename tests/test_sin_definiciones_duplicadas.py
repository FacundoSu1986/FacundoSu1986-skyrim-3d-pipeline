# -*- coding: utf-8 -*-
"""Ninguna funcion o clase de nivel superior puede estar definida dos veces.

Python no avisa: la segunda definicion tapa a la primera en silencio. Cuando la
que queda arriba tiene otra firma, el error aparece lejos del lugar donde se
escribio.

Ya paso en este repo. El commit 84c2b38 arreglo un `medir(raiz_meshes)`
truncado que tapaba al `medir(raiz_meshes, raiz_texturas)` real en
fixtures/registrar.py -- entro en un rebase, nadie lo vio, y reventaba con
TypeError al invocarlo. Escribiendo el test de TIPOS_NODO volvi a dejar un
`_archivo` duplicado por la misma via: parchear archivos con scripts.

Este test no arregla un archivo: enumera todos. Un duplicado nuevo, en
cualquier modulo, cae aca.
"""
import ast
import io
import os
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETAS = ("census", "fixtures", "pipeline", "tests",
            os.path.join("skills", "modelo-ia-a-skyrim", "scripts"))
IGNORAR = {"__pycache__", ".git"}


def _modulos():
    for carpeta in CARPETAS:
        base = os.path.join(_RAIZ, carpeta)
        if not os.path.isdir(base):
            continue
        for dirpath, dirs, archivos in os.walk(base):
            dirs[:] = [d for d in dirs if d not in IGNORAR]
            for f in sorted(archivos):
                if f.endswith(".py"):
                    yield os.path.join(dirpath, f)


class SinDefinicionesDuplicadasTests(unittest.TestCase):

    def test_ningun_modulo_define_lo_mismo_dos_veces(self):
        duplicados = []
        revisados = 0
        for ruta in _modulos():
            try:
                arbol = ast.parse(io.open(ruta, encoding="utf-8").read(), ruta)
            except SyntaxError as e:
                self.fail("%s no parsea: %s" % (ruta, e))
            revisados += 1
            vistos = {}
            for nodo in arbol.body:
                if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef,
                                         ast.ClassDef)):
                    continue
                if nodo.name in vistos:
                    duplicados.append(
                        "%s: %s definido en la linea %d y otra vez en la %d"
                        % (os.path.relpath(ruta, _RAIZ).replace(os.sep, "/"),
                           nodo.name, vistos[nodo.name], nodo.lineno))
                vistos[nodo.name] = nodo.lineno

        self.assertEqual([], duplicados,
                         "definiciones tapadas:\n  " + "\n  ".join(duplicados))
        # El par: si el recorrido no encontrara archivos, la lista vacia de
        # arriba no probaria nada.
        self.assertGreater(revisados, 15,
                           "solo se revisaron %d modulos; el recorrido no esta "
                           "mirando donde deberia" % revisados)

    def test_el_detector_detecta(self):
        """Falsificacion en el lugar: si este test no reprobara un duplicado
        real, el de arriba seria decorativo."""
        fuente = (
            "def f():\n    return 1\n\n\n"
            "class C:\n    pass\n\n\n"
            "def f():\n    return 2\n"
        )
        arbol = ast.parse(fuente)
        vistos, duplicados = {}, []
        for nodo in arbol.body:
            if isinstance(nodo, (ast.FunctionDef, ast.ClassDef)):
                if nodo.name in vistos:
                    duplicados.append(nodo.name)
                vistos[nodo.name] = nodo.lineno
        self.assertEqual(["f"], duplicados)


if __name__ == "__main__":
    unittest.main()
