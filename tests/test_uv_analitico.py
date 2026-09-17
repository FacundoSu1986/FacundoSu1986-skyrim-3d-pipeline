# -*- coding: utf-8 -*-
"""Casos con respuesta calculable en papel para el rasterizador de UV.

Un medidor de area no se valida "mirando si da razonable". Se valida contra
geometrias cuya respuesta se conoce de antemano.

Estos casos ya atraparon dos defectos reales:

  * Sin regla de relleno, dos triangulos que comparten una arista contaban dos
    veces las celdas de esa arista. Un atlas de 4 islas BIEN separadas
    reportaba 816 celdas solapadas en vez de 0. Sobre una malla real son miles
    de aristas internas: el solape del censo entero habria salido inflado.

  * El criterio de convergencia exigia que el error bajara estrictamente, y
    marcaba como falla que ya fuera exactamente cero.

No necesitan el corpus, asi que corren en CI.
"""
import contextlib
import io
import tempfile
import unittest

from _paths import preparar_path

preparar_path()

import parser_uv  # noqa: E402


def cuadrado(x0, y0, x1, y1):
    return [((x0, y0), (x1, y0), (x1, y1)), ((x0, y0), (x1, y1), (x0, y1))]


def area_solapada(tris, res):
    g = parser_uv.rasterizar(tris, res)
    return sum(1.0 / (res * res) for v in g.values() if v >= 2)


class SolapeAnaliticoTests(unittest.TestCase):
    def test_dos_cuadrados_solapados_un_cuarto(self):
        """Interseccion [0.5,1]x[0.5,1] = 0.25 exacto."""
        tris = cuadrado(0, 0, 1, 1) + cuadrado(0.5, 0.5, 1.5, 1.5)
        for res in (64, 128, 256, 512):
            with self.subTest(res=res):
                self.assertAlmostEqual(area_solapada(tris, res), 0.25, places=4)

    def test_triangulos_disjuntos_no_solapan(self):
        t1 = ((0.1, 0.1), (0.4, 0.1), (0.1, 0.4))
        t2 = ((0.6, 0.6), (0.9, 0.6), (0.6, 0.9))
        self.assertEqual(area_solapada([t1, t2], 512), 0.0)

    def test_triangulo_consigo_mismo_solapa_su_area(self):
        t = ((0.1, 0.1), (0.8, 0.1), (0.1, 0.7))
        esperada = parser_uv.area2(*t)
        self.assertAlmostEqual(area_solapada([t, t], 1024), esperada, places=2)


class ReglaDeRellenoTests(unittest.TestCase):
    """La guarda del defecto que costo mas caro."""

    def test_triangulos_que_comparten_arista_no_cuentan_doble(self):
        # Un cuadrado son dos triangulos que comparten la diagonal. Sin regla
        # de relleno, las celdas sobre la diagonal las cuentan los dos.
        self.assertEqual(area_solapada(cuadrado(0.1, 0.1, 0.9, 0.9), 512), 0.0)

    def test_atlas_de_islas_separadas_no_solapa(self):
        at = []
        for (x, y) in ((0.05, 0.05), (0.55, 0.05), (0.05, 0.55), (0.55, 0.55)):
            at += cuadrado(x, y, x + 0.40, y + 0.40)
        self.assertEqual(area_solapada(at, 512), 0.0)

    def test_el_detector_detecta(self):
        """Si esto no reporta solape, los tests de arriba no valen nada."""
        self.assertGreater(area_solapada(cuadrado(0.1, 0.1, 0.9, 0.9) * 2, 512),
                           0.5)


class FirmaDelBugDeAtlasTests(unittest.TestCase):
    """N islas sobre el cuadro 0..1 entero: la firma del bug original.

    Es lo que hacia smart_project dandole el cuadro completo a CADA objeto, y
    lo que en el juego se vio como "texturas desordenadas". El exceso tiende a
    (N-1)/N.
    """

    def test_exceso_tiende_a_n_menos_uno_sobre_n(self):
        for n in (2, 5, 15):
            with self.subTest(n=n):
                tris = []
                for _ in range(n):
                    tris += cuadrado(0, 0, 1, 1)
                g = parser_uv.rasterizar(tris, 512)
                pasadas = sum(g.values())
                exceso = sum(v - 1 for v in g.values() if v >= 2)
                self.assertAlmostEqual(exceso / float(pasadas),
                                       (n - 1) / float(n), places=3)


class HalfFloatTests(unittest.TestCase):
    def test_patrones_de_bits_conocidos(self):
        import struct
        for bits, esperado in ((0x3C00, 1.0), (0xC000, -2.0), (0x0000, 0.0),
                               (0x3800, 0.5), (0xBC00, -1.0)):
            with self.subTest(bits=hex(bits)):
                v = struct.unpack("<e", struct.pack("<H", bits))[0]
                self.assertEqual(v, esperado)


class AreaTests(unittest.TestCase):
    def test_area2_formula_del_cordon(self):
        self.assertAlmostEqual(
            parser_uv.area2((0, 0), (1, 0), (0, 1)), 0.5, places=9)

    def test_area3_triangulo_en_el_espacio(self):
        # 3-4-5 en el plano XY: area = 6
        self.assertAlmostEqual(
            parser_uv.area3((0, 0, 0), (3, 0, 0), (0, 4, 0)), 6.0, places=9)

    def test_area3_no_depende_de_la_orientacion(self):
        a = parser_uv.area3((0, 0, 0), (3, 0, 0), (0, 4, 0))
        b = parser_uv.area3((0, 0, 0), (0, 3, 0), (0, 0, 4))
        self.assertAlmostEqual(a, b, places=9)


class SuiteSobreCorpusTests(unittest.TestCase):
    """Los casos del autotest que dependen del corpus tienen que poder fallar.

    No podian. El caso h calculaba "peor desvio" sobre cero shapes, dejaba
    peor=0.0 e imprimia "ok" porque 0.0 < 0.02; el caso g acumulaba los
    errores en n_err pero le sumaba a fallos un n_mal que nunca se
    incrementaba. Con la ruta equivocada, la suite imprimia "Sin fallas" y
    devolvia exit 0 habiendo comprobado nada.

    Este test no verifica una linea: verifica la propiedad que las dos
    dependian de cumplir. Si manana se agrega un caso i) sobre el corpus y se
    escribe con el mismo reflejo, cae aca tambien.
    """

    def _autotest_callado(self, raiz):
        with contextlib.redirect_stdout(io.StringIO()) as salida:
            ok = parser_uv.autotest(raiz)
        return ok, salida.getvalue()

    def test_carpeta_sin_nif_no_cuenta_como_validacion(self):
        with tempfile.TemporaryDirectory() as d:
            ok, texto = self._autotest_callado(d)
        self.assertFalse(
            ok,
            "autotest devolvio True sobre una carpeta sin un solo NIF: "
            "cero comprobaciones no es exito. Salida: " + texto)

    def test_sin_corpus_los_casos_analiticos_igual_corren(self):
        """El corpus falta, pero a..f no dependen de el y tienen que pasar:
        el test de arriba no debe poder aprobarse rompiendo la suite entera."""
        ok, texto = self._autotest_callado(None)
        self.assertTrue(ok, texto)
        for caso in ("a.", "b.", "c.", "d.", "e.", "f."):
            self.assertIn("  " + caso, texto)
        self.assertNotIn("FALLA", texto)


if __name__ == "__main__":
    unittest.main()
