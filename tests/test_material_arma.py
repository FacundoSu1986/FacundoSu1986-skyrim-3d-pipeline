# -*- coding: utf-8 -*-
"""El material de un arma contra el de las armas vanilla.

El hacha de Tencent llegó al juego con el shader `Default` y glossiness 20, el
valor que deja PyNifly cuando no se fija. La pieza principal de 16 de las 17
hachas a dos manos vanilla usa `EnvMap`, y la glossiness mediana de las armas
es 80. Ningún otro verificador miraba el material.

Estos tests leen NIF construidos byte a byte (`nif_sintetico.
construir_con_material`), con el bloque de shader escrito desde nif.xml y no
desde el lector: si los dos salieran del mismo código, un campo corrido en los
dos lados pasaría igual.
"""
import io
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from _paths import preparar_path

preparar_path()

import censo_nif  # noqa: E402
import material_arma as ma  # noqa: E402
from nif_sintetico import construir_con_material  # noqa: E402

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "skills", "modelo-ia-a-skyrim", "scripts", "material_arma.py")

SIN_CUBEMAP = ("a.dds", "a_n.dds", "", "", "", "a_m.dds", "", "", "")


class _ConNif(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def nif(self, nombre="pruebabattleaxe.nif", datos=None, **kw):
        if datos is None:
            datos, _esp = construir_con_material(**kw)
        ruta = os.path.join(self.tmp.name, nombre)
        with open(ruta, "wb") as fh:
            fh.write(datos)
        return ruta

    def revisar(self, ruta):
        salida = io.StringIO()
        with redirect_stdout(salida):
            codigo = ma.revisar(ruta)
        return codigo, salida.getvalue()


class LecturaTests(_ConNif):

    def test_recupera_lo_que_escribio_el_fixture(self):
        datos, esp = construir_con_material(glossiness=64.0, spec_str=1.25,
                                            env_scale=0.75)
        lista, otros = ma.piezas(censo_nif.Nif(self.nif(datos=datos)))
        self.assertEqual(otros, [])
        self.assertEqual(len(lista), 1)
        nombre, tri, m = lista[0]
        self.assertEqual(nombre, esp["pieza"])
        self.assertEqual(tri, 1)
        self.assertTrue(m["cierra"])
        self.assertTrue(m["texset_cierra"])
        self.assertEqual(m["tipo_nombre"], "EnvMap")
        self.assertEqual(m["gloss"], 64.0)
        self.assertEqual(m["spec_str"], 1.25)
        self.assertEqual(m["env_scale"], 0.75)
        self.assertEqual(m["alfa"], 1.0)
        self.assertEqual(m["rutas"], esp["rutas"])

    def test_default_y_glow_cierran_sin_campo_extra(self):
        for tipo, f2 in ((0, 0), (2, 0x40)):
            with self.subTest(tipo=tipo):
                ruta = self.nif(tipo=tipo, flags1=0, flags2=f2)
                (_n, _t, m), = ma.piezas(censo_nif.Nif(ruta))[0]
                self.assertTrue(m["cierra"])
                self.assertIsNone(m["env_scale"])

    def test_una_pieza_sin_shader_se_cuenta_aparte(self):
        lista, otros = ma.piezas(censo_nif.Nif(self.nif(con_shader=False)))
        self.assertEqual(lista, [])
        self.assertEqual(otros, ["HojaDePrueba"])


class ReglasTests(_ConNif):

    def test_un_envmap_completo_pasa(self):
        codigo, texto = self.revisar(self.nif())
        self.assertEqual(codigo, 0, texto)
        self.assertIn("4 comprobaciones, 0 fallas", texto)

    def test_envmap_sin_el_flag_reprueba(self):
        codigo, texto = self.revisar(self.nif(flags1=0))
        self.assertEqual(codigo, 1)
        self.assertIn("REGLA envmap", texto)

    def test_envmap_sin_cubemap_reprueba(self):
        codigo, texto = self.revisar(self.nif(rutas=SIN_CUBEMAP))
        self.assertEqual(codigo, 1)
        self.assertIn("REGLA cubemap", texto)

    def test_glow_y_su_flag_van_juntos(self):
        casos = ((2, 0x00, 1), (0, 0x40, 1), (2, 0x40, 0))
        for tipo, f2, esperado in casos:
            with self.subTest(tipo=tipo, flags2=f2):
                codigo, texto = self.revisar(
                    self.nif(tipo=tipo, flags1=0, flags2=f2))
                self.assertEqual(codigo, esperado, texto)
                if esperado:
                    self.assertIn("REGLA glow", texto)

    def test_un_bloque_que_no_cierra_reprueba_y_no_se_juzga_el_resto(self):
        """Un Default relabelado como EnvMap: le faltan los 4 bytes de la
        escala del reflejo. Lo que se lea despues seria basura, asi que la
        unica falla tiene que ser la del cierre."""
        datos, _esp = construir_con_material(tipo=0, flags1=0)
        nif = censo_nif.Nif(self.nif(datos=datos))
        _t, o, _s = nif.bloques[2]
        datos = bytearray(datos)
        struct.pack_into("<I", datos, o, 1)
        codigo, texto = self.revisar(self.nif("roto.nif", datos=bytes(datos)))
        self.assertEqual(codigo, 1)
        self.assertIn("REGLA cierre", texto)
        self.assertEqual(texto.count("FALLA"), 1, texto)

    def test_sin_material_no_es_pasar(self):
        codigo, texto = self.revisar(self.nif(con_shader=False))
        self.assertEqual(codigo, 1)
        self.assertIn("no hay material que medir", texto)


class ObservacionesTests(_ConNif):

    def test_el_hacha_de_tencent(self):
        """Default con glossiness 20: pasa las reglas, y las observaciones
        dicen lo que le faltaba -- el numero de su clase y de donde sale el
        20."""
        codigo, texto = self.revisar(
            self.nif(tipo=0, flags1=0, glossiness=20.0))
        self.assertEqual(codigo, 0, texto)
        self.assertIn("de su clase (hacha2m), 16 de 17", texto)
        self.assertIn("glossiness 20: entre min (6) y p10 (30)", texto)
        self.assertIn("PyNifly", texto)

    def test_la_pieza_principal_es_la_de_mas_triangulos(self):
        """El tipo de shader se compara contra la PIEZA PRINCIPAL de las armas
        vanilla, asi que tiene que salir de la pieza principal de esta: una
        empunadura Default no dice nada si la hoja es EnvMap."""
        rutas = ("a.dds", "a_n.dds", "", "",
                 "textures\\cubemaps\\shinydull_e.dds", "a_m.dds")
        hoja = ("Hoja", 5000, ma._mat(1, 0x80, 0, rutas))
        mango = ("Mango", 300, ma._mat(0, 0, 0))
        for orden in ((hoja, mango), (mango, hoja)):
            with self.subTest(primera=orden[0][0]):
                fallas, notas, _n = ma.juzgar(list(orden), "hacha2m")
                self.assertEqual(fallas, [])
                texto = "\n".join(notas)
                self.assertIn("-- Hoja (5000 tri, principal): shader EnvMap",
                              texto)
                self.assertIn("-- Mango (300 tri): shader Default", texto)
                self.assertIn("OBS shader EnvMap en la pieza principal",
                              texto)
                self.assertNotIn("OBS shader Default en la pieza principal",
                                 texto)
                # La tabla es de piezas principales: el mango no se ubica
                # en ella. Una sola glossiness ubicada, la de la hoja.
                self.assertIn("(pieza secundaria: la tabla vanilla es de "
                              "piezas principales)", texto)
                self.assertEqual(texto.count("OBS glossiness 80: igual a"), 1,
                                 texto)

    def test_envmap_sin_mascara_se_informa_y_no_reprueba(self):
        rutas = ("a.dds", "a_n.dds", "", "",
                 "textures\\cubemaps\\shinydull_e.dds", "", "", "", "")
        codigo, texto = self.revisar(self.nif(rutas=rutas))
        self.assertEqual(codigo, 0, texto)
        self.assertIn("sin mascara _m", texto)

    def test_un_cubemap_propio_se_informa(self):
        rutas = ("a.dds", "a_n.dds", "", "",
                 "textures\\weapons\\mio\\reflejo_e.dds", "a_m.dds", "", "",
                 "")
        codigo, texto = self.revisar(self.nif(rutas=rutas))
        self.assertEqual(codigo, 0, texto)
        self.assertIn("no esta en una carpeta cubemaps", texto)


class TablaTests(unittest.TestCase):
    """Los numeros de las reglas, LITERALES. Si --censo los cambia, este test
    obliga a revisar tambien el docstring y SKILL.md, que los citan."""

    def test_los_numeros_del_corpus(self):
        self.assertEqual(ma.CORPUS, {
            "archivos": 22393, "bloques": 74489, "envmap": 6843,
            "envmap_cubemap": 6829, "glow": 1396, "sin_glow": 73093})

    def test_los_numeros_de_las_armas(self):
        self.assertEqual(ma.ARMAS["n"], 198)
        self.assertEqual(ma.ARMAS["tipos"],
                         {"EnvMap": 149, "Default": 46, "Glow": 3})
        self.assertEqual(ma.ARMAS["envmap_con_mascara"], 143)
        self.assertEqual(ma.ARMAS["envmap_con_cubemap"], 149)
        self.assertEqual(ma.ARMAS["clases"]["hacha2m"], (16, 17))
        self.assertEqual(ma.ARMAS["gloss"][3], 80.0)

    def test_el_docstring_cita_los_mismos_numeros(self):
        doc = ma.__doc__
        for n in (22393, 74489, 6843, 6829, 1396, 73093):
            with self.subTest(n=n):
                self.assertIn("{:,}".format(n).replace(",", "."), doc)

    def test_la_poblacion_suma(self):
        self.assertEqual(sum(ma.ARMAS["tipos"].values()), ma.ARMAS["n"])
        self.assertEqual(sum(t for _e, t in ma.ARMAS["clases"].values()),
                         ma.ARMAS["n"])
        self.assertEqual(sum(e for e, _t in ma.ARMAS["clases"].values()),
                         ma.ARMAS["tipos"]["EnvMap"])


class LineaDeComandosTests(unittest.TestCase):

    def _correr(self, *args):
        return subprocess.run([sys.executable, "-B", SCRIPT] + list(args),
                              capture_output=True, text=True)

    def test_autotest(self):
        r = self._correr("--autotest")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(" 0 fallas", r.stdout)

    def test_argumentos_que_no_sirven(self):
        self.assertEqual(self._correr().returncode, 2)
        self.assertEqual(self._correr("algo.txt").returncode, 2)


if __name__ == "__main__":
    unittest.main()
