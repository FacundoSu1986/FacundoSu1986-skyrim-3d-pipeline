# -*- coding: utf-8 -*-
"""compresor_dxt.py: DXT1/DXT5 con numpy, contra valores escritos a mano y
contra Pillow.

Los valores esperados van LITERALES. Los de la paleta salen de decodificar
bloques hechos a mano con Pillow 12.3 (division entera: (2a+b)//3, (6a+b)//7).
En CI tienen que estar numpy (el compresor) y Pillow (el oraculo): sin ellos
el autotest saltea sus comparaciones y diria "OK" sin haberlas hecho.
"""
import os
import struct
import unittest

from _paths import preparar_path

preparar_path()

try:
    import numpy as np
    import compresor_dxt as cd  # noqa: E402
except ImportError:          # sin numpy no hay compresor
    np = cd = None


def _en_ci():
    return bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))


class DependenciasEnCiTests(unittest.TestCase):

    def test_en_ci_estan_numpy_y_pillow(self):
        if not _en_ci():
            self.skipTest("fuera de CI son opcionales")
        self.assertIsNotNone(np, "CI sin numpy: el compresor no se prueba")
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.fail("CI sin Pillow: el autotest saltearia las "
                      "comparaciones con su decodificador y su compresor")


@unittest.skipIf(cd is None, "compresor_dxt necesita numpy")
class DecodificadorTests(unittest.TestCase):
    """Bloques hechos a mano, decodificados a valores escritos a mano."""

    def test_565_se_expande_como_el_hardware(self):
        self.assertEqual(cd.de_565(np.array([0xFFFF]))[0].tolist(),
                         [255, 255, 255])
        self.assertEqual(cd.de_565(np.array([(1 << 11) | (1 << 5) | 1]))[0]
                         .tolist(), [8, 4, 8])

    def test_dxt1_modo_4_colores(self):
        bloque = struct.pack("<HHI", 31 << 11, 0, 0b11100100)
        pix = cd.descomprimir(bloque, 4, 4, "DXT1")
        self.assertEqual([tuple(pix[i:i + 4]) for i in range(0, 16, 4)],
                         [(255, 0, 0, 255), (0, 0, 0, 255),
                          (170, 0, 0, 255), (85, 0, 0, 255)])

    def test_dxt1_modo_3_colores_el_indice_3_es_transparente(self):
        c1 = (1 << 11) | (1 << 5) | 1
        bloque = struct.pack("<HHI", 0, c1, 0b11100100)
        pix = cd.descomprimir(bloque, 4, 4, "DXT1")
        self.assertEqual([tuple(pix[i:i + 4]) for i in range(0, 16, 4)],
                         [(0, 0, 0, 255), (8, 4, 8, 255),
                          (4, 2, 4, 255), (0, 0, 0, 0)])

    def test_dxt5_el_color_es_siempre_de_4_colores(self):
        """En DXT5 el bloque de color no tiene modo de 3 colores: con
        c0 <= c1 el indice 3 es (c0 + 2*c1) // 3, no negro transparente."""
        bloque = (bytes((255, 255)) + bytes(6)
                  + struct.pack("<HHI", 0, 31 << 11, 0b11100100))
        pix = cd.descomprimir(bloque, 4, 4, "DXT5")
        self.assertEqual([tuple(pix[i:i + 4]) for i in range(0, 16, 4)],
                         [(0, 0, 0, 255), (255, 0, 0, 255),
                          (85, 0, 0, 255), (170, 0, 0, 255)])

    def test_dxt5_alfa_modo_8(self):
        idx = sum(k << (3 * k) for k in range(8))
        bloque = (bytes((255, 0)) + idx.to_bytes(6, "little")
                  + struct.pack("<HHI", 0xFFFF, 0, 0))
        pix = cd.descomprimir(bloque, 4, 4, "DXT5")
        self.assertEqual(list(pix[3:32:4]),
                         [255, 0, 218, 182, 145, 109, 72, 36])

    def test_dxt5_alfa_modo_6_trae_0_y_255(self):
        idx = sum(k << (3 * k) for k in range(8))
        bloque = (bytes((0, 10)) + idx.to_bytes(6, "little")
                  + struct.pack("<HHI", 0xFFFF, 0, 0))
        pix = cd.descomprimir(bloque, 4, 4, "DXT5")
        self.assertEqual(list(pix[3:32:4]), [0, 10, 2, 4, 6, 8, 0, 255])


@unittest.skipIf(cd is None, "compresor_dxt necesita numpy")
class CompresorTests(unittest.TestCase):

    def test_color_plano_representable_da_bytes_fijos(self):
        """(132, 130, 66) es 565 exacto: (16, 32, 8). color0 == color1 y
        todos los indices en 0."""
        pix = bytes((132, 130, 66, 255)) * 16
        datos = cd.comprimir(pix, 4, 4, "DXT1")
        c = (16 << 11) | (32 << 5) | 8
        self.assertEqual(datos, struct.pack("<HHI", c, c, 0))

    def test_alfa_constante_da_a0_igual_a1(self):
        """Lo que mascara_especular lee como bloque constante."""
        pix = bytes((10, 20, 30, 55)) * 16
        datos = cd.comprimir(pix, 4, 4, "DXT5")
        self.assertEqual(datos[:8], bytes((55, 55, 0, 0, 0, 0, 0, 0)))

    def test_dxt1_escribe_siempre_color0_mayor(self):
        """Con color0 <= color1 el indice 3 es negro transparente."""
        rng = np.random.default_rng(3)
        pix = rng.integers(0, 256, (32, 32, 4), dtype=np.uint8).tobytes()
        bl = np.frombuffer(cd.comprimir(pix, 32, 32, "DXT1"),
                           np.uint8).reshape(-1, 8)
        c0 = bl[:, 0:2].copy().view("<u2")[:, 0]
        c1 = bl[:, 2:4].copy().view("<u2")[:, 0]
        self.assertTrue(bool((c0 >= c1).all()))
        vuelta = cd.descomprimir(bl.tobytes(), 32, 32, "DXT1")
        self.assertEqual(set(vuelta[3::4]), {255})

    def _imagen(self):
        """128x128, degradado con ruido aritmetico: sin generador aleatorio,
        para que el numero no dependa de la version de numpy."""
        y, x = np.mgrid[0:128, 0:128]
        ruido = ((x * 7919 + y * 104729 + x * y * 31) % 13) - 6
        return np.clip(np.stack((x * 2 + ruido, y * 2 - ruido,
                                 (x + y) + 2 * ruido, 255 - x + ruido), -1),
                       0, 255).astype(np.uint8).tobytes()

    def test_la_calidad_no_empeora(self):
        """Medido: RMS RGB 2,65 y alfa 0,62. Sin los minimos cuadrados el RGB
        sube a 3,04; con el alfa en modo de 6 valores, a 0,73."""
        img = self._imagen()
        e = cd.error_rms(img, cd.descomprimir(cd.comprimir(
            img, 128, 128, "DXT5"), 128, 128, "DXT5"))
        self.assertLess(sum(e[:3]) / 3, 2.8)
        self.assertLess(e[3], 0.7)

    def test_el_alfa_variable_va_en_modo_de_8_valores(self):
        bl = np.frombuffer(cd.comprimir(self._imagen(), 128, 128, "DXT5"),
                           np.uint8).reshape(-1, 16)
        variables = bl[:, 0] != bl[:, 1]
        self.assertTrue(bool(variables.any()))
        self.assertTrue(bool((bl[variables, 0] > bl[variables, 1]).all()))

    def test_un_mipmap_de_2x2_se_completa_repitiendo_el_borde(self):
        """Dos colores que 565 representa, en 2x2: vuelven exactos. Rellenar
        con negro metia un tercer color y corria los extremos."""
        a = [int(v) for v in cd.de_565(cd.a_565(np.array([[250, 10, 30]])))[0]]
        b = [int(v) for v in cd.de_565(cd.a_565(np.array([[8, 200, 90]])))[0]]
        pix = bytes(a + [255] + b + [255] + b + [255] + a + [255])
        self.assertEqual(cd.descomprimir(cd.comprimir(pix, 2, 2, "DXT1"),
                                         2, 2, "DXT1"), pix)

    def test_tamanos_de_mipmap_chicos(self):
        for w, h in ((1, 1), (2, 2), (2, 1)):
            pix = bytes((1, 2, 3, 4)) * (w * h)
            self.assertEqual(len(cd.comprimir(pix, w, h, "DXT1")), 8)
            self.assertEqual(len(cd.comprimir(pix, w, h, "DXT5")), 16)
            self.assertEqual(len(cd.descomprimir(cd.comprimir(
                pix, w, h, "DXT5"), w, h, "DXT5")), w * h * 4)

    def test_formato_desconocido_se_rechaza(self):
        with self.assertRaises(ValueError):
            cd.comprimir(bytes(64), 4, 4, "BC7")

    def test_el_autotest_pasa(self):
        self.assertTrue(cd.autotest())


if __name__ == "__main__":
    unittest.main()
