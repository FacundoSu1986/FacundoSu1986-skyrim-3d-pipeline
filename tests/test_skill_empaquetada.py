# -*- coding: utf-8 -*-
"""Cada skill, empaquetada como la instala un usuario, funciona SOLA.

POR QUE. El .skill que arma build_skill.py lleva solo la carpeta de la skill:
ni census/, ni tests/, ni la otra skill. Un script que importe algo de afuera
anda en el repo --donde todo esta a mano-- y revienta instalado. Eso se
comprobaba a mano (verificar_plugin corrido desde la .skill extraida); aca
queda automatico, y en CI porque el workflow corre la suite entera
(tests/correr_suite.py).

QUE HACE, sin listas escritas a mano:
  * empaqueta cada carpeta de skills/ que tenga SKILL.md, en un temporal;
  * la extrae en OTRO directorio vacio, lejos del repo;
  * importa cada script que no use `bpy`, con -E -s (sin PYTHONPATH ni site
    del usuario) y sin el repo en el camino;
  * corre `--autotest` de cada script que tenga un `autotest()` sin
    argumentos -- los que no necesitan el corpus vanilla.

Los scripts de Blender no se importan: `bpy` no existe fuera de Blender. Su
sintaxis la cubre el `compileall` del workflow.
"""
import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import build_skill  # noqa: E402

USA_BPY = re.compile(r"^\s*(import bpy|from bpy)", re.M)
# LITERAL, no build_skill.IGNORAR_*: lo que un paquete puede dejar afuera es un
# hecho (el bytecode), no la constante que se valida. Leyendo la constante, una
# mutacion que agregaba "references" a IGNORAR_DIR movia la sonda y el test
# seguia verde.
FUERA_DIR = {"__pycache__", ".git"}
FUERA_EXT = {".pyc", ".pyo"}
AUTOTEST_SIN_ARGS = re.compile(r"^def autotest\(\):", re.M)


def _importar(carpeta_scripts, modulo, cwd, extra=()):
    """(exit, stderr) de importar `modulo` en un proceso aislado."""
    rutas = [carpeta_scripts] + list(extra)
    codigo = "import sys; sys.path[:0] = %r; import %s" % (rutas, modulo)
    # -B: sin bytecode. Sin eso Python deja __pycache__ en la carpeta extraida
    # y el test que compara archivos pasa o falla segun el orden de los tests.
    p = subprocess.run([sys.executable, "-B", "-E", "-s", "-c", codigo],
                       cwd=cwd, capture_output=True, text=True)
    return p.returncode, p.stderr


def _skills():
    base = os.path.join(RAIZ, "skills")
    return [d for d in sorted(os.listdir(base))
            if os.path.exists(os.path.join(base, d, "SKILL.md"))]


class SkillEmpaquetadaTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp_zip = tempfile.mkdtemp()
        cls.tmp = tempfile.mkdtemp()
        cls.extraidas = {}
        for nombre in _skills():
            with contextlib.redirect_stdout(io.StringIO()):
                ruta = build_skill.empaquetar(nombre, cls.tmp_zip)
            destino = os.path.join(cls.tmp, nombre + "_extraida")
            with zipfile.ZipFile(ruta) as z:
                z.extractall(destino)
            cls.extraidas[nombre] = (ruta, os.path.join(destino, nombre))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_zip, ignore_errors=True)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _scripts(self, carpeta):
        s = os.path.join(carpeta, "scripts")
        if not os.path.isdir(s):
            return []
        return [os.path.join(s, f) for f in sorted(os.listdir(s))
                if f.endswith(".py")]

    def test_hay_skills_para_empaquetar(self):
        """Cero skills = cero comprobaciones, y eso no es exito."""
        self.assertGreaterEqual(len(self.extraidas), 2, self.extraidas)

    def test_el_paquete_no_pierde_ni_agrega_archivos(self):
        """Se compara contra el ZIP, que es el artefacto. La primera version
        comparaba contra la carpeta extraida y fallaba solo si corria despues
        de los tests que importan desde ahi: Python dejaba __pycache__."""
        for nombre, (ruta_zip, _carpeta) in self.extraidas.items():
            with self.subTest(skill=nombre):
                origen = os.path.join(RAIZ, "skills", nombre)
                esperado, obtenido = set(), set()
                for base, dirs, archivos in os.walk(origen):
                    dirs[:] = [d for d in dirs if d not in FUERA_DIR]
                    for f in archivos:
                        if os.path.splitext(f)[1] not in FUERA_EXT:
                            esperado.add(os.path.relpath(
                                os.path.join(base, f), origen))
                with zipfile.ZipFile(ruta_zip) as z:
                    prefijo = nombre + "/"
                    for n in z.namelist():
                        self.assertTrue(n.startswith(prefijo),
                                        "%s fuera de %s/" % (n, nombre))
                        obtenido.add(os.path.normpath(n[len(prefijo):]))
                esperado = set(os.path.normpath(x) for x in esperado)
                self.assertEqual(obtenido, esperado)
                self.assertIn("SKILL.md", obtenido)

    def test_cada_script_importa_desde_el_paquete(self):
        importados = 0
        for nombre, (_zip, carpeta) in self.extraidas.items():
            for ruta in self._scripts(carpeta):
                with open(ruta, encoding="utf-8") as fh:
                    if USA_BPY.search(fh.read()):
                        continue
                modulo = os.path.splitext(os.path.basename(ruta))[0]
                with self.subTest(skill=nombre, script=modulo):
                    codigo, err = _importar(os.path.dirname(ruta), modulo,
                                            cwd=self.tmp)
                    self.assertEqual(
                        codigo, 0, "%s/%s no importa desde el paquete:\n%s"
                        % (nombre, modulo, err[-800:]))
                importados += 1
        self.assertGreater(importados, 0, "no se importo ningun script")

    def test_cada_autotest_sin_corpus_pasa_desde_el_paquete(self):
        corridos = 0
        for nombre, (_zip, carpeta) in self.extraidas.items():
            for ruta in self._scripts(carpeta):
                with open(ruta, encoding="utf-8") as fh:
                    if not AUTOTEST_SIN_ARGS.search(fh.read()):
                        continue
                with self.subTest(skill=nombre,
                                  script=os.path.basename(ruta)):
                    p = subprocess.run(
                        [sys.executable, "-B", "-E", "-s", ruta, "--autotest"],
                        cwd=self.tmp, capture_output=True, text=True)
                    self.assertEqual(
                        p.returncode, 0, "%s --autotest desde el paquete:\n%s"
                        % (os.path.basename(ruta),
                           (p.stdout + p.stderr)[-800:]))
                corridos += 1
        self.assertGreater(corridos, 0, "no corrio ningun autotest")


class ElControlDetectaTests(unittest.TestCase):
    """Un control de aislamiento que nunca fallo no probo nada."""

    def test_un_import_de_census_falla_aislado_y_anda_en_el_repo(self):
        tmp = tempfile.mkdtemp()
        try:
            scripts = os.path.join(tmp, "scripts")
            os.makedirs(scripts)
            with open(os.path.join(scripts, "script_malo.py"), "w",
                      encoding="utf-8") as fh:
                fh.write("import parser_esm\n")
            codigo, err = _importar(scripts, "script_malo", cwd=tmp)
            self.assertNotEqual(codigo, 0, "el aislamiento no aislo nada")
            self.assertIn("parser_esm", err)
            # El mismo archivo, con census/ a mano -- como en el repo --, anda:
            # lo que falla es el aislamiento, no el script.
            codigo, err = _importar(scripts, "script_malo", cwd=tmp,
                                    extra=[os.path.join(RAIZ, "census")])
            self.assertEqual(codigo, 0, err)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
