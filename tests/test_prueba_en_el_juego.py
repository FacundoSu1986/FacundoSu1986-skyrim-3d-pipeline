# -*- coding: utf-8 -*-
"""fixtures/prueba_en_el_juego.py: el mod de prueba de la issue #31.

El autotest arma un maestro sintetico con escritor_plugin, busca el STAT de un
NIF por su MODL, lo copia con EDID y MODL nuevos y relee el ESL. Aca se lo corre
y se le suman los casos que el autotest no mira: la linea de comandos, y que un
NIF que el vanilla no usa como STAT corte el armado en vez de inventar el record.
"""
import os
import struct
import sys
import tempfile
import unittest

from _paths import RAIZ, preparar_path

preparar_path()
sys.path.insert(0, os.path.join(RAIZ, "fixtures"))

import escritor_plugin as E  # noqa: E402
import parser_plugin  # noqa: E402
import prueba_en_el_juego as P  # noqa: E402


class PruebaEnElJuegoTests(unittest.TestCase):

    def test_el_autotest_pasa(self):
        self.assertEqual(P.autotest(), 0)

    def test_argumentos_que_no_sirven_salen_con_2(self):
        self.assertEqual(P.main([]), 2)
        self.assertEqual(P.main(["a.esm", "m", "i", "s"]), 2)
        self.assertEqual(P.main(["a.esm", "m", "i", "s", "x.nif", "--force"]), 2)

    def test_el_stat_copiado_conserva_la_version_del_vanilla(self):
        """El MODT y el DNAM de un STAT cambian de forma con la version del
        record, y los STAT de Skyrim.esm son casi todos 39. La primera version
        del mod los copio con 44: el juego leyo un hash del MODT como encabezado
        y se cerro en la pantalla de Bethesda (2026-09-27)."""
        with tempfile.TemporaryDirectory() as d:
            modt = struct.pack("<I4sI", 0x235EFA34, b"dds\x00", 0x0D8AC7C5)
            dnam = struct.pack("<fI", 90.0, 0)
            rec = E.record("STAT", 0x0003D3B8, [E.sub("EDID", E.zstr("Viejo")),
                                                 E.sub("OBND", b"\x00" * 12),
                                                 E.sub("MODL", E.zstr("a\\viejo.nif")),
                                                 E.sub("MODT", modt),
                                                 E.sub("DNAM", dnam)], version=39)
            esm = os.path.join(d, "Maestro.esm")
            E.escribir(esm, [], [E.grupo("STAT", [rec])], [0x0003D3B8], esl=False)
            for base in ("m", "i"):
                os.makedirs(os.path.join(d, base, "a"))
                open(os.path.join(d, base, "a", "viejo.nif"), "wb").close()
            salida = os.path.join(d, "salida")
            P.armar(esm, os.path.join(d, "m"), os.path.join(d, "i"), salida, ["a/viejo.nif"])
            q = parser_plugin.Plugin(os.path.join(salida, "prueba31.esl"))
            stats = [off for t, off, _n, _f in q.records if t == "STAT"]
            self.assertEqual([struct.unpack_from("<H", q.d, off + 20)[0] for off in stats],
                             [39, 39])
            for off in stats:
                subs = {t: q.d[o:o + n] for t, o, n in q.subrecords(off)}
                self.assertEqual((subs["MODT"], subs["DNAM"]), (modt, dnam))

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
