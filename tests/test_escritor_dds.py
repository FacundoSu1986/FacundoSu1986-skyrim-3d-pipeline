# -*- coding: utf-8 -*-
"""El escritor de DDS, verificado con el lector que ya existia.

Nada en el repo escribia DDS. Ahora si, y la falsificacion es barata porque
`parser_dds.leer()` predice el tamano exacto del archivo a partir del
encabezado -- una prediccion que se cumple en 32.241 de 32.241 DDS de Bethesda.
Si lo que escribimos no la cumple, el encabezado miente.
"""
import os
import tempfile
import unittest

from _paths import preparar_path

preparar_path()

import escritor_dds  # noqa: E402
import parser_dds  # noqa: E402


def degradado(ancho, alto):
    pix = bytearray()
    for y in range(alto):
        for x in range(ancho):
            pix += bytes(((x * 7) % 256, (y * 11) % 256,
                          ((x + y) * 3) % 256, (x * y) % 256))
    return bytes(pix)


class EscribirYReleerTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name

    def _escribir(self, ancho, alto, mips=True):
        ruta = os.path.join(self.dir, "t_%dx%d.dds" % (ancho, alto))
        return escritor_dds.escribir(ruta, ancho, alto,
                                     degradado(ancho, alto), mips)

    def test_el_tamano_real_es_el_que_predice_el_encabezado(self):
        """La identidad que el corpus cumple 32.241 de 32.241 veces."""
        for w, h in ((4, 4), (16, 8), (64, 64), (128, 256)):
            ruta = self._escribir(w, h)
            d = parser_dds.leer(ruta)
            self.assertTrue(d["tamano_cuadra"], "%dx%d" % (w, h))
            self.assertEqual(os.path.getsize(ruta), d["bytes_esperados"])

    def test_los_pixeles_vuelven_iguales(self):
        """Que el tamano cierre NO prueba que el contenido este bien: un
        encabezado correcto sobre pixeles corridos da el mismo tamano."""
        ruta = self._escribir(32, 16)
        _d, vuelta = escritor_dds.leer_pixeles(ruta)
        self.assertEqual(degradado(32, 16), vuelta)

    def test_la_cadena_de_mipmaps_llega_a_1x1(self):
        ruta = self._escribir(64, 16)
        d = parser_dds.leer(ruta)
        self.assertEqual(7, d["mipmaps"])
        self.assertEqual([1, 1], d["mip_mas_chico"])

    def test_sin_mipmaps_queda_un_solo_nivel(self):
        """El par del de arriba: si siempre escribiera la cadena, el test
        anterior pasaria sin probar que la bandera hace algo."""
        ruta = self._escribir(64, 16, mips=False)
        d = parser_dds.leer(ruta)
        self.assertEqual(1, d["mipmaps"])

    def test_el_alfa_sobrevive(self):
        """Va aparte porque el orden en disco es BGRA y el alfa es el unico
        canal que no se mueve: un error de orden lo dejaria pasar."""
        pix = bytes((10, 20, 30, 200) * 64)
        ruta = escritor_dds.escribir(os.path.join(self.dir, "a.dds"), 8, 8, pix)
        _d, vuelta = escritor_dds.leer_pixeles(ruta)
        self.assertEqual(pix, vuelta)
        self.assertEqual(200, vuelta[3])

    def test_una_cantidad_equivocada_de_pixeles_se_rechaza(self):
        with self.assertRaises(ValueError):
            escritor_dds.escribir(os.path.join(self.dir, "x.dds"), 8, 8,
                                  b"\x00" * 10)

    def test_lo_escrito_pasa_las_reglas_del_contrato(self):
        """Lo que se genere con esto tiene que poder entrar a un asset."""
        import sys
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if os.path.join(raiz, "fixtures") not in sys.path:
            sys.path.insert(0, os.path.join(raiz, "fixtures"))
        import comparar
        ruta = self._escribir(64, 64)
        malas = {c for ok, c, _d, _e in comparar.reglas_dds(ruta) if not ok}
        self.assertEqual(set(), malas)

    def test_un_normal_sin_comprimir_pasa_la_regla_del_alfa(self):
        """El caso real: el escudo salio con normales sin comprimir de 32 bpp y
        la regla, escrita como 'formato == DXT5', lo reprobaba. Tiene los
        cuatro canales a precision completa."""
        import sys
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if os.path.join(raiz, "fixtures") not in sys.path:
            sys.path.insert(0, os.path.join(raiz, "fixtures"))
        import comparar
        ruta = escritor_dds.escribir(os.path.join(self.dir, "piedra_n.dds"),
                                     32, 32, degradado(32, 32))
        malas = {c for ok, c, _d, _e in comparar.reglas_dds(ruta) if not ok}
        self.assertNotIn("normal_con_alfa", malas)


class NivelesTests(unittest.TestCase):

    def test_la_cadena_de_una_textura_no_cuadrada(self):
        self.assertEqual([(8, 2), (4, 1), (2, 1), (1, 1)],
                         escritor_dds.niveles(8, 2))

    def test_reducir_promedia_de_a_cuatro(self):
        pix = bytes((0, 0, 0, 0)) * 2 + bytes((100, 100, 100, 100)) * 2
        chico = escritor_dds.reducir(pix, 2, 2)
        self.assertEqual(4, len(chico))
        self.assertEqual(50, chico[0])


if __name__ == "__main__":
    unittest.main()
