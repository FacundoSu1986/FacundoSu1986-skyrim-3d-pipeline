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
    # Los .py sueltos de la raiz (build_skill.py) no caen en ninguna carpeta:
    # se listan directo, sin recorrer todo el arbol (venv, docs, .skill).
    for f in sorted(os.listdir(_RAIZ)):
        if f.endswith(".py"):
            yield os.path.join(_RAIZ, f)
    for carpeta in CARPETAS:
        base = os.path.join(_RAIZ, carpeta)
        if not os.path.isdir(base):
            continue
        for dirpath, dirs, archivos in os.walk(base):
            dirs[:] = [d for d in dirs if d not in IGNORAR]
            for f in sorted(archivos):
                if f.endswith(".py"):
                    yield os.path.join(dirpath, f)


def _duplicados_de_arbol(arbol):
    """[(nombre, linea_original, linea_que_tapa)] de nivel superior.

    Lo usan los DOS tests. Una copia del bucle dentro de la falsificacion
    validaria la copia, no el detector: ya pasaba con AsyncFunctionDef, que
    estaba en el real y no en la copia.
    """
    vistos, duplicados = {}, []
    for nodo in arbol.body:
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
            continue
        if nodo.name in vistos:
            duplicados.append((nodo.name, vistos[nodo.name], nodo.lineno))
        vistos[nodo.name] = nodo.lineno
    return duplicados


class SinDefinicionesDuplicadasTests(unittest.TestCase):

    def test_ningun_modulo_define_lo_mismo_dos_veces(self):
        duplicados = []
        revisados = 0
        for ruta in _modulos():
            try:
                with io.open(ruta, encoding="utf-8") as fh:
                    arbol = ast.parse(fh.read(), ruta)
            except SyntaxError as e:
                self.fail("%s no parsea: %s" % (ruta, e))
            revisados += 1
            for nombre, primera, segunda in _duplicados_de_arbol(arbol):
                duplicados.append(
                    "%s: %s definido en la linea %d y otra vez en la %d"
                    % (os.path.relpath(ruta, _RAIZ).replace(os.sep, "/"),
                       nombre, primera, segunda))

        self.assertEqual([], duplicados,
                         "definiciones tapadas:\n  " + "\n  ".join(duplicados))
        # El par: si el recorrido no encontrara archivos, la lista vacia de
        # arriba no probaria nada.
        self.assertGreater(revisados, 15,
                           "solo se revisaron %d modulos; el recorrido no esta "
                           "mirando donde deberia" % revisados)

    def test_el_recorrido_incluye_los_modulos_de_la_raiz(self):
        """build_skill.py fue el ultimo hueco de CARPETAS: un .py de la raiz
        no cae en ninguna de las cinco carpetas y quedaba sin revisar."""
        self.assertIn(os.path.join(_RAIZ, "build_skill.py"), list(_modulos()))

    def test_el_detector_detecta(self):
        """Falsificacion en el lugar: si este test no reprobara un duplicado
        real, el de arriba seria decorativo. Llama al MISMO helper, y cubre
        tambien AsyncFunctionDef, que la copia anterior se salteaba."""
        fuente = (
            "def f():\n    return 1\n\n\n"
            "class C:\n    pass\n\n\n"
            "def f():\n    return 2\n\n\n"
            "async def g():\n    return 1\n\n\n"
            "async def g():\n    return 2\n"
        )
        arbol = ast.parse(fuente)
        self.assertEqual(
            ["f", "g"],
            [nombre for nombre, _, _ in _duplicados_de_arbol(arbol)])


if __name__ == "__main__":
    unittest.main()
