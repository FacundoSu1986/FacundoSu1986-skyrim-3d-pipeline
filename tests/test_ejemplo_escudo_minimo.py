# -*- coding: utf-8 -*-
"""examples/escudo-minimo: el caso de punta a punta sin el juego.

Sin Blender (el CI) se prueba lo que es Python solo: que la pieza de IA es un
GLB valido y siempre el mismo, que los dos planes pasan los mismos
validadores que usan los scripts de las skills, y que el orquestador sin
Blender sale con 3 ("incompleto") diciendo que falta, nunca con 0.

Con BLENDER_EXE (y PyNifly en ese Blender), la cadena entera, de cero a un
NIF verificado; la falsificacion del paso 6 --cada comprobacion, alimentada
con una expectativa cambiada, tiene que fallar--; y que un paso que falla
corta la cadena con 1. Sin BLENDER_EXE eso se saltea, y es "no se probo".
"""
import contextlib
import copy
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _paths import RAIZ, preparar_path

preparar_path()

import exportar_puro  # noqa: E402
import montaje_puro  # noqa: E402
from pipeline.glb import parsear_glb  # noqa: E402

EJEMPLO = os.path.join(RAIZ, "examples", "escudo-minimo")
CORRER = os.path.join(EJEMPLO, "correr.py")


def _cargar(nombre):
    """Un modulo del ejemplo: la carpeta lleva guion y no se importa por
    nombre."""
    spec = importlib.util.spec_from_file_location(
        "ejemplo_" + nombre, os.path.join(EJEMPLO, nombre + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _plan(nombre):
    with open(os.path.join(EJEMPLO, nombre), encoding="utf-8") as fh:
        return json.load(fh)


def _correr(*args, sin_blender=False):
    env = dict(os.environ)
    if sin_blender:
        env.pop("BLENDER_EXE", None)
    return subprocess.run([sys.executable, CORRER] + list(args), env=env,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=900)


class PiezaTests(unittest.TestCase):

    def test_es_un_glb_valido_con_los_defectos_que_dice(self):
        pieza = _cargar("pieza_ia")
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "pieza.glb")
            pieza.escribir(ruta)
            m = parsear_glb(Path(ruta))
        self.assertEqual(m.triangulos, pieza.TRIANGULOS)
        prim = m.json["meshes"][0]["primitives"][0]
        pos = m.json["accessors"][prim["attributes"]["POSITION"]]
        self.assertEqual(pos["count"], 4 * 6, "sin soldar: cuatro por cara")
        for k, (lo, hi) in enumerate(((-0.375, 0.375), (0.0, 1.0), (-0.03, 0.03))):
            self.assertAlmostEqual(pos["min"][k], lo)
            self.assertAlmostEqual(pos["max"][k], hi)   # el origen en la base
        self.assertIn("TEXCOORD_0", prim["attributes"])

    def test_los_bytes_salen_siempre_iguales(self):
        pieza = _cargar("pieza_ia")
        self.assertEqual(pieza.construir(), pieza.construir())


class PlanesTests(unittest.TestCase):

    def test_pasan_los_validadores_de_las_skills(self):
        self.assertEqual(montaje_puro.validar_marco(_plan("plan_marco.json")), [])
        self.assertEqual(exportar_puro.validar_plan(_plan("plan_nif.json")), [])


class SinBlenderTests(unittest.TestCase):

    def test_sale_incompleto_y_dice_que_falta(self):
        with tempfile.TemporaryDirectory() as d:
            p = _correr("--trabajo", d, sin_blender=True)
            self.assertTrue(os.path.isfile(os.path.join(d, "pieza_ia.glb")))
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertIn("INCOMPLETO", p.stdout)
        self.assertNotIn("LISTO", p.stdout)
        self.assertRegex(p.stdout, r"0\. .* hecho")
        self.assertRegex(p.stdout, r"1\. .* salteado: requiere Blender")
        self.assertRegex(p.stdout, r"6\. .* salteado")

    def test_los_argumentos_que_no_sirven_salen_con_2(self):
        for args in (["--nada"], ["--trabajo"],
                     ["--blender", os.path.join(tempfile.gettempdir(), "no-existe", "blender.exe")]):
            with self.subTest(args=args):
                self.assertEqual(_correr(*args, sin_blender=True).returncode, 2)


@unittest.skipUnless(os.environ.get("BLENDER_EXE"),
                     "requiere BLENDER_EXE y PyNifly; no se valido")
class ConBlenderTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="escudo_minimo_")
        cls.p = _correr("--trabajo", cls.dir)
        cls.correr = _cargar("correr")
        cls.plan_marco = _plan("plan_marco.json")
        cls.plan_nif = _plan("plan_nif.json")
        cls.nif = os.path.join(cls.dir, *cls.plan_nif["salida"].split("/"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_de_cero_a_un_nif_verificado(self):
        self.assertEqual(self.p.returncode, 0, self.p.stdout + self.p.stderr)
        self.assertIn("LISTO", self.p.stdout)
        self.assertRegex(self.p.stdout, r"6\. .* hecho: \d+ comprobaciones, 0 fallas")

    def test_cada_comprobacion_del_paso_6_puede_fallar(self):
        fallas, hechas = self.correr.verificar(self.nif, self.plan_marco, self.plan_nif)
        self.assertEqual(fallas, [])
        self.assertGreater(hechas, 0)

        def marco(cambio):
            p = copy.deepcopy(self.plan_marco)
            cambio(p)
            return p, self.plan_nif

        def nif(cambio):
            p = copy.deepcopy(self.plan_nif)
            cambio(p)
            return self.plan_marco, p

        mutantes = [
            ("el tope", marco(lambda p: p["topes"].update({"+Z": 2.7})), "dorso"),
            ("el largo", marco(lambda p: p["largo"].update({"valor": 57.0})), "largo"),
            ("el ancla en X", marco(lambda p: p["ancla"]["marco"].__setitem__(0, -13.8)), "centro"),
            ("el ancla en Y", marco(lambda p: p["ancla"]["marco"].__setitem__(1, 1.0)), "centro"),
            ("la raiz", nif(lambda p: p.update({"raiz": "OtraRaiz"})), "raiz"),
            ("la pieza", nif(lambda p: p["piezas"][0].update({"shape": "Otra:0"})), "piezas"),
        ]
        for nombre, (pm, pn), trozo in mutantes:
            with self.subTest(mutante=nombre):
                fallas, _ = self.correr.verificar(self.nif, pm, pn)
                self.assertTrue(any(trozo in f for f in fallas),
                                "%s no fallo por %r: %r" % (nombre, trozo, fallas))
        with mock.patch.object(self.correr, "PRN", "WeaponSword"):
            fallas, _ = self.correr.verificar(self.nif, self.plan_marco, self.plan_nif)
        self.assertTrue(any("Prn" in f for f in fallas), fallas)

    def test_un_paso_que_falla_corta_la_cadena_con_1(self):
        roto = dict(self.plan_marco, ejes={"+Y": "+Z", "+Z": "+Z"})   # dos ejes al mismo
        self.assertNotEqual(montaje_puro.validar_marco(roto), [])
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "plan_marco_roto.json")
            with open(ruta, "w", encoding="utf-8") as fh:
                json.dump(roto, fh)
            salida = io.StringIO()
            with mock.patch.object(self.correr, "PLAN_MARCO", ruta), \
                    contextlib.redirect_stdout(salida):
                rc = self.correr.main(["--blender", os.environ["BLENDER_EXE"],
                                       "--trabajo", os.path.join(d, "trabajo")])
        texto = salida.getvalue()
        self.assertEqual(rc, 1, texto)
        self.assertRegex(texto, r"3\. .* FALLA")
        self.assertRegex(texto, r"4\. .* salteado: fallo el paso 3")
        self.assertNotIn("LISTO", texto)


if __name__ == "__main__":
    unittest.main()
