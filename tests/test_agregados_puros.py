# -*- coding: utf-8 -*-
"""Funciones puras de census/agregados.py (mediana, p90, pct).

Estas no tocan el corpus: operan sobre listas/números en memoria, así que se
pueden validar con casos armados a mano.
"""
import contextlib
import io
import unittest

from _paths import preparar_path

preparar_path()

import agregados as ag  # noqa: E402


class MedianaTests(unittest.TestCase):
    def test_lista_vacia_es_none(self) -> None:
        self.assertIsNone(ag.mediana([]))

    def test_impar_toma_el_del_medio(self) -> None:
        self.assertEqual(ag.mediana([3, 1, 2]), 2)

    def test_par_promedia_los_dos_centrales(self) -> None:
        self.assertEqual(ag.mediana([1, 2, 3, 4]), 2.5)


class P90Tests(unittest.TestCase):
    def test_p90_de_1_a_100(self) -> None:
        # impl: xs[round(0.9 * (n-1))] = xs[round(89.1)] = xs[89] = 90.
        self.assertEqual(ag.p90(list(range(1, 101))), 90)

    def test_p90_lista_vacia_es_none(self) -> None:
        self.assertIsNone(ag.p90([]))


class PctTests(unittest.TestCase):
    def test_pct_normal(self) -> None:
        self.assertEqual(ag.pct(1, 4), "25.00%")

    def test_pct_divisor_cero(self) -> None:
        self.assertEqual(ag.pct(1, 0), "-")


class SeccionSinShapesTests(unittest.TestCase):
    """mypy (issue #72 del repo) marco que sec_e indexaba `mejor` aunque
    quedara en None: sin shapes medidas, un TypeError en vez del reporte."""

    def test_sec_e_sin_shapes_lo_dice(self) -> None:
        for filas in ([], [{"vertices_por_shape": [], "ruta_relativa": "a.nif"}]):
            salida = io.StringIO()
            with contextlib.redirect_stdout(salida):
                ag.sec_e(filas)
            self.assertIn("no hay shapes medidas", salida.getvalue())


if __name__ == "__main__":
    unittest.main()
