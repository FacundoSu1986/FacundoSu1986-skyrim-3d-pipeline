# -*- coding: utf-8 -*-
"""El parser de plugins, contra bytes construidos a mano.

Corre en CI: no necesita la carpeta Data instalada. El autotest sobre los
plugins reales prueba otra cosa -- que el layout reproduce 1,3 millones de
records -- y ninguno reemplaza al otro.
"""
import os
import struct
import tempfile
import unittest

from _paths import preparar_path

preparar_path()

import parser_esm  # noqa: E402
import plugin_sintetico  # noqa: E402
from parser_esm import Plugin, PluginInvalido  # noqa: E402


def _archivo(datos, caso):
    fd, ruta = tempfile.mkstemp(suffix=".esp")
    with os.fdopen(fd, "wb") as fh:
        fh.write(datos)
    caso.addCleanup(lambda: os.path.exists(ruta) and os.unlink(ruta))
    return ruta


class RecorridoTests(unittest.TestCase):

    def setUp(self):
        self.datos, self.esperado = plugin_sintetico.construir()
        self.ruta = _archivo(self.datos, self)
        self.p = Plugin(self.ruta)

    def test_recupera_lo_que_el_fixture_declara(self):
        tipos = self.p.cuenta_tipos()
        self.assertEqual(self.esperado["tipos"], dict(tipos))
        self.assertEqual(self.esperado["bloques"], sum(tipos.values()))

    def test_el_tes4_de_cabecera_cuenta_como_record(self):
        """Dejarlo afuera daba conteos uno mas bajos y un tipo menos, y ese
        error se propago a la tabla del autotest antes de que lo atrapara."""
        self.assertEqual(1, self.p.cuenta_tipos()["TES4"])

    def test_los_subrecords_del_stat(self):
        off = next(o for t, o, _s, _p in self.p.recorrer() if t == "STAT")
        subs = Plugin.subrecords(self.p.datos(off))
        self.assertEqual(self.esperado["stat"]["subrecords"],
                         [k for k, _v in subs])
        d = dict(subs)
        self.assertEqual(self.esperado["stat"]["edid"],
                         d["EDID"].rstrip(b"\x00").decode("cp1252"))
        self.assertEqual(self.esperado["stat"]["modl"],
                         d["MODL"].rstrip(b"\x00").decode("cp1252"))
        self.assertEqual(self.esperado["stat"]["obnd"],
                         struct.unpack("<6h", d["OBND"]))
        self.assertEqual(self.esperado["stat"]["form_id"], self.p.form_id(off))

    def test_un_record_comprimido_se_lee_igual(self):
        datos, esperado = plugin_sintetico.construir(comprimir_stat=True)
        p = Plugin(_archivo(datos, self))
        off = next(o for t, o, _s, _pr in p.recorrer() if t == "STAT")
        subs = dict(Plugin.subrecords(p.datos(off)))
        self.assertEqual(esperado["stat"]["edid"],
                         subs["EDID"].rstrip(b"\x00").decode("cp1252"))

    def test_el_escape_xxxx_no_se_asume_pero_se_maneja(self):
        """Un subrecord de 70.000 bytes no entra en el uint16 de tamano."""
        datos, esperado = plugin_sintetico.construir(con_escape=True)
        p = Plugin(_archivo(datos, self))
        off = next(o for t, o, _s, _pr in p.recorrer() if t == "STAT")
        subs = Plugin.subrecords(p.datos(off))
        self.assertEqual(esperado["stat"]["subrecords"], [k for k, _v in subs])
        self.assertEqual(70000, len(dict(subs)["MNAM"]))


class LaIdentidadPuedeFallarTests(unittest.TestCase):
    """El recorrido tiene que embaldosar el archivo exacto. Si no reprobara
    ante un layout torcido, no estaria validando nada."""

    def setUp(self):
        self.datos, _e = plugin_sintetico.construir()

    def _rompe(self, datos):
        p = Plugin(_archivo(datos, self))
        with self.assertRaises(PluginInvalido):
            p.cuenta_tipos()

    def test_un_byte_de_mas_al_final_reprueba(self):
        """Un sobrante es un hueco: la suma ya no cae en el fin del archivo."""
        self._rompe(self.datos + b"\x00")

    def test_un_record_que_declara_de_mas_reprueba(self):
        # El offset lo da el parser. Buscar b"ACTI" con index() encuentra la
        # ETIQUETA del GRUP, no el record, y el test pasaba parcheando bytes
        # que no eran un tamano -- verde sin haber probado nada.
        p = Plugin(_archivo(self.datos, self))
        i = next(o for t, o, _s, _pr in p.recorrer() if t == "ACTI")
        b = bytearray(self.datos)
        tam, = struct.unpack_from("<I", b, i + 4)
        struct.pack_into("<I", b, i + 4, tam + 64)
        self._rompe(bytes(b))

    def test_un_grup_que_declara_de_menos_reprueba(self):
        i = self.datos.index(b"GRUP")
        b = bytearray(self.datos)
        tam, = struct.unpack_from("<I", b, i + 4)
        struct.pack_into("<I", b, i + 4, tam - 8)
        self._rompe(bytes(b))

    def test_un_grup_mas_chico_que_su_cabecera_reprueba(self):
        i = self.datos.index(b"GRUP")
        b = bytearray(self.datos)
        struct.pack_into("<I", b, i + 4, 4)
        self._rompe(bytes(b))

    def test_un_subrecord_que_se_pasa_reprueba(self):
        off = next(o for t, o, _s, _p in Plugin(_archivo(self.datos, self)).recorrer()
                   if t == "STAT")
        p = Plugin(_archivo(self.datos, self))
        d = bytearray(p.datos(off))
        struct.pack_into("<H", d, 4, len(d) + 10)   # el EDID se pasa del record
        with self.assertRaises(PluginInvalido):
            Plugin.subrecords(bytes(d))

    def test_un_record_que_termina_en_un_xxxx_colgado_reprueba(self):
        """El XXXX promete el subrecord que describe. Si el record termina
        justo despues del escape, el recorrido da `p == n` limpio y antes se
        aceptaba como un record sin subrecords: un STAT corrupto pasaba el
        tercer nivel de la identidad."""
        datos = b"EDID" + struct.pack("<H", 5) + b"Hola\x00"
        datos += b"XXXX" + struct.pack("<H", 4) + struct.pack("<I", 0xFFFF)
        with self.assertRaises(PluginInvalido):
            Plugin.subrecords(datos)

    def test_lo_que_no_empieza_con_tes4_no_es_un_plugin(self):
        with self.assertRaises(PluginInvalido):
            Plugin(_archivo(b"XXXX" + self.datos[4:], self))

    def test_el_fixture_sano_no_reprueba(self):
        """El par de todos los de arriba: si el recorrido reprobara siempre,
        'reprueba ante X' no probaria nada."""
        p = Plugin(_archivo(self.datos, self))
        self.assertEqual(5, sum(p.cuenta_tipos().values()))


class AutotestTests(unittest.TestCase):

    def test_sin_plugins_no_es_exito(self):
        """Cero comprobaciones es no haber mirado nada. Es la misma guarda que
        en parser_dds y en parser_uv, donde ya se colo una vez."""
        import contextlib
        import io as _io
        with tempfile.TemporaryDirectory() as d:
            with contextlib.redirect_stdout(_io.StringIO()) as salida:
                ok = parser_esm.autotest(d)
        self.assertFalse(ok, salida.getvalue())

    def test_la_tabla_de_autotest_declara_lo_que_compara(self):
        """Cada entrada tiene que traer al menos una clave medible; una entrada
        vacia pasaria sin comprobar nada de ese archivo."""
        self.assertTrue(parser_esm.AUTOTEST)
        for nombre, esperado in parser_esm.AUTOTEST:
            self.assertTrue(nombre.lower().endswith((".esm", ".esp", ".esl")))
            self.assertTrue(esperado, "%s no declara nada que comprobar" % nombre)
            for clave in esperado:
                self.assertIn(clave, ("bytes", "bloques", "tipos", "STAT"))


if __name__ == "__main__":
    unittest.main()
