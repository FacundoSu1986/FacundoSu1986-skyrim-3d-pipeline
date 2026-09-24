# -*- coding: utf-8 -*-
"""horneado_puro.py: lo que el bake de la capa HD hace fuera de Blender.

Dos cosas que su autotest no puede garantizar solo:

* **Que en CI corra con numpy.** Las funciones que usa el bake real (margen,
  relleno, reducción por tipo de mapa) necesitan numpy, y sin numpy el
  autotest las salteaba y decía "OK". El CI instala numpy; este test falla si
  en CI faltara, en vez de pasar en verde sin haberlas probado.

* **Que su rasterizador de UV sea el del censo.** La skill empaquetada no
  lleva census/, así que `horneado_puro.rasterizar_uv` es una COPIA de
  `census/parser_uv.rasterizar`. Dos copias que divergen dan dos solapes
  distintos para la misma malla; acá se las obliga a coincidir.
"""
import os
import random
import unittest

from _paths import preparar_path

preparar_path()

import horneado_puro as hp  # noqa: E402
import parser_uv  # noqa: E402


class NumpyEnCiTests(unittest.TestCase):

    def test_en_ci_el_autotest_corre_con_numpy(self):
        if not (os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")):
            self.skipTest("fuera de CI numpy es opcional")
        self.assertIsNotNone(
            hp.np, "CI sin numpy: el autotest de horneado_puro saltearia "
                   "reducir_np, dilatar y rellenar_vacios, que son las que usa "
                   "el bake")

    def test_el_autotest_pasa(self):
        self.assertEqual(hp.autotest(), 0)


class RasterizadorTests(unittest.TestCase):

    def _iguales(self, tris, res=64):
        censo = dict(parser_uv.rasterizar(tris, res))
        propio = hp.rasterizar_uv(tris, res)
        self.assertEqual(propio, censo)

    def test_coincide_con_el_del_censo_en_triangulos_al_azar(self):
        rnd = random.Random(20260924)
        for _ in range(40):
            tris = [tuple((rnd.random(), rnd.random()) for _ in range(3))
                    for _ in range(rnd.randint(1, 12))]
            self._iguales(tris)

    def test_coincide_en_aristas_compartidas_y_espejadas(self):
        """Los casos de la regla top-left: una arista compartida no es solape,
        y una isla espejada invierte el giro."""
        quad = [((0.1, 0.1), (0.4, 0.1), (0.4, 0.4)),
                ((0.1, 0.1), (0.4, 0.4), (0.1, 0.4))]
        espejado = [tuple((0.5 - u, v) for u, v in t) for t in quad]
        # aristas que pasan justo por centros de celda: donde la regla decide
        c = [(k + 0.5) / 64.0 for k in (8, 24, 40, 48, 60)]
        abanico = [((c[0], c[0]), (c[1], c[0]), (c[1], c[1])),
                   ((c[0], c[0]), (c[1], c[1]), (c[0], c[1])),
                   ((c[1], c[0]), (c[2], c[0]), (c[2], c[1])),
                   ((c[1], c[0]), (c[2], c[1]), (c[1], c[1])),
                   ((c[0], c[1]), (c[1], c[1]), (c[1], c[2])),
                   ((c[0], c[1]), (c[1], c[2]), (c[0], c[2])),
                   # la arista compartida en la SEGUNDA posicion del triangulo
                   ((c[4], c[3]), (c[4], c[4]), (c[3], c[3])),
                   ((c[3], c[4]), (c[3], c[3]), (c[4], c[4]))]
        for tris in (quad, quad + espejado, quad + quad, abanico):
            with self.subTest(n=len(tris)):
                self._iguales(tris)

    def test_el_solape_es_la_solape_huella_del_censo(self):
        quad = [((0.1, 0.1), (0.4, 0.1), (0.4, 0.4)),
                ((0.1, 0.1), (0.4, 0.4), (0.1, 0.4))]
        medio = quad + quad[:1]
        for caso in (quad, quad + quad, medio):
            with self.subTest(n=len(caso)):
                uv = [p for t in caso for p in t]
                idx = [(3 * i, 3 * i + 1, 3 * i + 2) for i in range(len(caso))]
                pos = [(0.0, 0.0, 0.0)] * len(uv)
                censo = parser_uv.metricas_uv(uv, idx, pos)
                self.assertAlmostEqual(hp.solape_uv(caso),
                                       censo["solape_huella"], places=6)


if __name__ == "__main__":
    unittest.main()
