# -*- coding: utf-8 -*-
"""Plugins de Bethesda: leer y escribir.

Un .nif en disco no es un mod. Falta el record que lo referencia, y eso vive en
un plugin. Esto lo lee y lo escribe, con la misma disciplina que el resto: la
estructura se recorre entera y tiene que caer exacto en el fin del archivo.

Los plugins se construyen byte a byte, asi que corre en CI sin Skyrim.
"""
import os
import struct
import tempfile
import unittest

from _paths import preparar_path

preparar_path()

import escritor_plugin as ep  # noqa: E402
import parser_plugin  # noqa: E402


def _archivo(datos, caso, sufijo=".esl"):
    fd, ruta = tempfile.mkstemp(suffix=sufijo)
    with os.fdopen(fd, "wb") as fh:
        fh.write(datos)
    caso.addCleanup(lambda: os.path.exists(ruta) and os.unlink(ruta))
    return ruta


class EscribirYReleerTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name

    def _mod(self, nombre="m.esl", esl=True, ids=(0x01000800, 0x01000801)):
        r1 = ep.record("ARMO", ids[0], [
            ep.sub("EDID", ep.zstr("Prueba")),
            ep.sub("MODL", struct.pack("<I", ids[1])),
            ep.sub("DATA", struct.pack("<If", 450, 6.0))])
        r2 = ep.record("ARMA", ids[1], [ep.sub("EDID", ep.zstr("PruebaAA"))])
        return ep.escribir(os.path.join(self.dir, nombre), ["Skyrim.esm"],
                           [ep.grupo("ARMO", [r1]), ep.grupo("ARMA", [r2])],
                           list(ids), esl=esl)

    def test_el_recorrido_cae_en_el_fin_del_archivo(self):
        """La identidad que se cumple en los 6 plugins de la instalacion,
        1.176.548 records incluido Skyrim.esm."""
        p = parser_plugin.Plugin(self._mod())
        self.assertEqual({"TES4": 1, "ARMO": 1, "ARMA": 1}, p.cuenta_tipos())
        self.assertEqual(2, len(p.grupos))

    def test_el_maestro_y_la_bandera_vuelven(self):
        p = parser_plugin.Plugin(self._mod())
        self.assertEqual(["Skyrim.esm"], p.maestros())
        self.assertTrue(p.es_esl)
        self.assertFalse(p.es_esm)

    def test_sin_esl_la_bandera_no_esta(self):
        """El par del de arriba: si la bandera se pusiera siempre, el test
        anterior pasaria sin probar que el parametro hace algo."""
        p = parser_plugin.Plugin(self._mod("m.esp", esl=False))
        self.assertFalse(p.es_esl)
        self.assertEqual(0, p.banderas)

    def test_los_subrecords_vuelven_en_orden_y_con_su_contenido(self):
        p = parser_plugin.Plugin(self._mod())
        for tipo, off, _t, _f in p.records:
            if tipo != "ARMO":
                continue
            subs = p.subrecords(off)
            self.assertEqual(["EDID", "MODL", "DATA"], [s[0] for s in subs])
            so, sn = subs[2][1], subs[2][2]
            valor, peso = struct.unpack_from("<If", p.d, so)
            self.assertEqual(450, valor)
            self.assertAlmostEqual(6.0, peso, places=5)
            return
        self.fail("no aparecio el ARMO")

    def test_un_tamano_de_record_corrido_se_detecta(self):
        """El recorrido es la falsificacion: si un dataSize miente, no se cae
        en el fin del archivo."""
        ruta = self._mod()
        # El offset se pide al parser: buscar b"ARMO" a mano encuentra la
        # ETIQUETA del grupo, no el record, y ahi el +4 cae sobre groupType.
        # Parchear un campo que no es el tamano no desalinea nada y el test
        # pasaba sin probar lo que dice probar.
        previo = parser_plugin.Plugin(ruta)
        off = next(o for t, o, _tam, _f in previo.records if t == "ARMO")
        with open(ruta, "rb") as fh:
            crudo = bytearray(fh.read())
        tam, = struct.unpack_from("<I", crudo, off + 4)
        struct.pack_into("<I", crudo, off + 4, tam + 4)
        with self.assertRaises(parser_plugin.PluginInvalido):
            parser_plugin.Plugin(_archivo(bytes(crudo), self))

    def test_un_tamano_de_grupo_corrido_se_detecta(self):
        """El GRUP cuenta sus propios 24 bytes y el record no: son dos
        convenciones distintas en el mismo archivo y confundirlas desalinea
        todo lo que sigue."""
        with open(self._mod(), "rb") as fh:
            crudo = bytearray(fh.read())
        i = crudo.index(b"GRUP")
        tam, = struct.unpack_from("<I", crudo, i + 4)
        struct.pack_into("<I", crudo, i + 4, tam - 4)
        with self.assertRaises(parser_plugin.PluginInvalido):
            parser_plugin.Plugin(_archivo(bytes(crudo), self))

    def test_algo_que_no_es_un_plugin_se_rechaza(self):
        with self.assertRaises(parser_plugin.PluginInvalido):
            parser_plugin.Plugin(_archivo(b"esto no es un plugin", self))


class RestriccionEslTests(unittest.TestCase):
    """La parte de objeto del FormID tiene que entrar en 12 bits.

    No es una convencion: los otros 12 bits del FormID se usan para numerar el
    propio ESL dentro del indice FE, asi que un record que se pase no se puede
    direccionar.
    """

    def test_el_limite_exacto_pasa(self):
        ep.comprobar_esl([0x01000FFF])

    def test_uno_mas_se_rechaza(self):
        with self.assertRaises(ep.ErrorPlugin):
            ep.comprobar_esl([0x01001000])

    def test_el_mensaje_dice_cual(self):
        with self.assertRaises(ep.ErrorPlugin) as cm:
            ep.comprobar_esl([0x01000800, 0x01002000])
        self.assertIn("0x01002000", str(cm.exception))
        self.assertNotIn("0x01000800", str(cm.exception))

    def test_sin_esl_no_se_exige(self):
        """Un ESP no tiene la restriccion, y el escritor no debe inventarla."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        r = ep.record("ARMO", 0x01009999, [ep.sub("EDID", ep.zstr("X"))])
        ruta = ep.escribir(os.path.join(tmp.name, "g.esp"), ["Skyrim.esm"],
                           [ep.grupo("ARMO", [r])], [0x01009999], esl=False)
        self.assertTrue(os.path.exists(ruta))


class SubrecordsTests(unittest.TestCase):

    def test_un_tipo_que_no_mide_cuatro_se_rechaza(self):
        with self.assertRaises(ep.ErrorPlugin):
            ep.sub("EDI", b"x")

    def test_lo_que_no_entra_en_un_u16_se_rechaza(self):
        with self.assertRaises(ep.ErrorPlugin):
            ep.sub("EDID", b"x" * 70000)

    def test_el_limite_de_65535_pasa(self):
        """El par del de arriba: si rechazara por cualquier tamano grande, el
        test anterior no probaria donde esta el limite."""
        s = ep.sub("EDID", b"x" * 0xFFFF)
        self.assertEqual(6 + 0xFFFF, len(s))


if __name__ == "__main__":
    unittest.main()
