# -*- coding: utf-8 -*-
"""Lo que se puede comprobar de un script de Blender SIN Blender.

`test_blender_sale_bien.py` cubre el contrato de salida (`correr(main)`) y el
CI cubre la sintaxis con `compileall`. Ninguna de las dos cosas ve estos dos
defectos, que son de la misma familia que las trampas del repo: no tiran error
hasta que alguien los usa, y el que los usa es una persona apurada.

  1. Un flag que el script acepta y su docstring no nombra. El docstring es la
     unica documentacion de estos scripts: un flag que no esta ahi no lo
     encuentra nadie --`render_referencia.py --frente-az` llevaba asi desde
     antes de este test--.

  2. Un nombre mal escrito al llamar a la parte PURA (`ep.enderezar_x` en vez
     de `ep.enderezar`). El script de Blender no se importa en CPython --trae
     `bpy`--, asi que ni el import smoke ni el compileall lo ven: revienta
     recien en la corrida, con la malla ya importada y soldada.

Se recorren TODOS los scripts de Blender de las dos skills: uno nuevo entra
solo. Los modulos que no se pueden importar en CPython (numpy, cuando no esta
instalado) se saltean en vez de reprobar: el test no puede depender de que
este el entorno completo.
"""
import ast
import glob
import importlib
import os
import re
import unittest

from _paths import RAIZ, preparar_path

preparar_path()

USA_BPY = re.compile(r"^\s*(import bpy|from bpy)", re.M)
FLAG = re.compile(r"^--[a-z][a-z0-9-]*$")
EN_TEXTO = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*)\b")


def _texto(ruta):
    with open(ruta, encoding="utf-8") as fh:
        return fh.read()


def scripts_de_blender():
    rutas = sorted(glob.glob(os.path.join(RAIZ, "skills", "*", "scripts",
                                          "*.py")))
    return [r for r in rutas if USA_BPY.search(_texto(r))]


def _arbol(ruta):
    return ast.parse(_texto(ruta), ruta)


def flags_del_codigo(arbol):
    """Las constantes de texto que son exactamente `--algo`.

    Leerlas del arbol y no del texto evita contar las que solo aparecen en un
    comentario o en el propio docstring.
    """
    return {n.value for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and FLAG.match(n.value)}


class LosFlagsEstanEnElDocstringTests(unittest.TestCase):

    def test_hay_scripts_que_revisar(self):
        """Cero scripts no es exito: el glob podria estar mal."""
        self.assertGreaterEqual(len(scripts_de_blender()), 5)

    def test_cada_flag_que_acepta_esta_en_su_docstring(self):
        for ruta in scripts_de_blender():
            arbol = _arbol(ruta)
            doc = ast.get_docstring(arbol) or ""
            dicho = set(EN_TEXTO.findall(doc))
            faltan = sorted(flags_del_codigo(arbol) - dicho)
            with self.subTest(script=os.path.basename(ruta)):
                self.assertEqual([], faltan,
                                 "el docstring no nombra %s" % (faltan,))

    def test_el_chequeo_ve_lo_que_dice_ver(self):
        """Un docstring sin flags y un codigo con uno: tiene que saltar."""
        falso = ast.parse('"""Uso:\n  blender -b --python x.py -- a\n"""\n'
                          'X = "--inventado"\n')
        self.assertEqual({"--inventado"}, flags_del_codigo(falso))
        self.assertEqual(set(), set(EN_TEXTO.findall(
            ast.get_docstring(falso))) - {"--python"})


class LosNombresDeLaPartePuraExistenTests(unittest.TestCase):
    """`mod.algo` en un script de Blender tiene que existir en su modulo puro.

    Es el hermano de `test_sin_definiciones_duplicadas`: aquel mira lo que se
    define, este lo que se USA.
    """

    def _alias(self, arbol):
        alias = {}
        for n in ast.walk(arbol):
            if isinstance(n, ast.Import):
                for a in n.names:
                    if a.asname:
                        alias[a.asname] = a.name
        return alias

    def test_hay_alias_que_revisar(self):
        total = sum(len(self._alias(_arbol(r)))
                    for r in scripts_de_blender())
        self.assertGreater(total, 0,
                           "ningun script importa un modulo con alias: el "
                           "barrido no estaria mirando nada")

    def test_cada_atributo_usado_existe(self):
        for ruta in scripts_de_blender():
            arbol = _arbol(ruta)
            modulos = {}
            for asname, nombre in self._alias(arbol).items():
                try:
                    modulos[asname] = importlib.import_module(nombre)
                except ImportError:
                    # numpy sin instalar, o un modulo del entorno de Blender.
                    continue
            for n in ast.walk(arbol):
                if not (isinstance(n, ast.Attribute)
                        and isinstance(n.value, ast.Name)
                        and n.value.id in modulos):
                    continue
                with self.subTest(script=os.path.basename(ruta), linea=n.lineno):
                    self.assertTrue(
                        hasattr(modulos[n.value.id], n.attr),
                        "%s.%s no existe en %s"
                        % (n.value.id, n.attr, modulos[n.value.id].__name__))

    def test_el_chequeo_ve_lo_que_dice_ver(self):
        """El mutante: un atributo que no existe tiene que faltar."""
        import enderezar_puro
        self.assertTrue(hasattr(enderezar_puro, "enderezar"))
        self.assertFalse(hasattr(enderezar_puro, "enderezar_que_no_existe"))


if __name__ == "__main__":
    unittest.main()
