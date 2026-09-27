# -*- coding: utf-8 -*-
"""fixtures/prueba_en_el_juego.py: el mod de prueba de la issue #31.

El autotest arma un maestro sintetico con escritor_plugin, busca el STAT de un
NIF por su MODL, lo copia con EDID y MODL nuevos y relee el ESL. Aca se lo corre
y se le suman los casos que el autotest no mira: la linea de comandos, y que un
NIF que el vanilla no usa como STAT corte el armado en vez de inventar el record.
"""
import os
import sys
import tempfile
import unittest

from _paths import RAIZ, preparar_path

preparar_path()
sys.path.insert(0, os.path.join(RAIZ, "fixtures"))

import escritor_plugin as E  # noqa: E402
import prueba_en_el_juego as P  # noqa: E402


class PruebaEnElJuegoTests(unittest.TestCase):

    def test_el_autotest_pasa(self):
        self.assertEqual(P.autotest(), 0)

    def test_argumentos_que_no_sirven_salen_con_2(self):
        self.assertEqual(P.main([]), 2)
        self.assertEqual(P.main(["a.esm", "m", "i", "s"]), 2)
        self.assertEqual(P.main(["a.esm", "m", "i", "s", "x.nif", "--force"]), 2)

    def test_un_nif_que_no_es_stat_corta_el_armado(self):
        with tempfile.TemporaryDirectory() as d:
            esm = os.path.join(d, "Maestro.esm")
            jarra = E.record("MISC", 0x00012347, [E.sub("EDID", E.zstr("Jarra")),
                                                  E.sub("MODL", E.zstr("clutter\\jarra.nif"))])
            E.escribir(esm, [], [E.grupo("MISC", [jarra])], [0x00012347], esl=False)
            with self.assertRaises(SystemExit) as cm:
                P.armar(esm, d, d, os.path.join(d, "salida"), ["clutter/jarra.nif"])
            self.assertIn("MISC", str(cm.exception))
            self.assertFalse(os.path.exists(os.path.join(d, "salida", "prueba31.esl")),
                             "no tiene que escribir un ESL a medias")


if __name__ == "__main__":
    unittest.main()
