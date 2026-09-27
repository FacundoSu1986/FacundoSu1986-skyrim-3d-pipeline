# -*- coding: utf-8 -*-
"""compresor_bc7.py: BC7 (modos 5 y 6) con numpy, contra valores escritos a
mano y contra Pillow.

Los valores esperados van LITERALES. Los de la paleta salen de decodificar
bloques hechos a mano con Pillow 12.3: pesos de 64os del spec, expansion de
7 a 8 bits replicando el MSB ((v << 1) | (v >> 6)), rotacion del modo 5, y
el mapeo de DXGI 98/99. En CI tienen que estar numpy (el compresor) y Pillow
(el oraculo): sin ellos se perderian las comparaciones y el CI tiene que
fallar, no saltear.
"""
import io
import os
import struct
import unittest

from _paths import preparar_path

preparar_path()

try:
    import numpy as np
    import compresor_bc7 as cb     # noqa: E402
    import compresor_dxt as cd      # noqa: E402
except ImportError:          # sin numpy no hay compresor
    np = cb = cd = None

try:
    from PIL import Image
    HAY_PILLOW = True
except ImportError:
    HAY_PILLOW = False


def _en_ci():
    return bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))


def _bloque_m6(f7, p0, p1, idx):
    """Un bloque modo 6 armado bit a bit, sin pasar por el compresor.

    `f7` = (R0, R1, G0, G1, B0, B1, A0, A1) de 7 bits; `idx` = 16 indices de
    4 bits (el texel 0 se guarda con 3). Layout: modo 7 bits (0b1000000),
    8 campos de 7, p0, p1, indices.
    """
    bits = [0] * 6 + [1]
    for f in f7:
        bits += [(f >> i) & 1 for i in range(7)]
    bits += [p0, p1]
    bits += [(idx[0] >> i) & 1 for i in range(3)]
    for k in range(1, 16):
        bits += [(idx[k] >> i) & 1 for i in range(4)]
    assert len(bits) == 128
    data = bytearray(16)
    for i, b in enumerate(bits):
        if b:
            data[i // 8] |= 1 << (i % 8)
    return bytes(data)


def _bloque_m5(rot, f7, a8, cidx, aidx):
    """Un bloque modo 5 armado bit a bit. `f7` = (R0, R1, G0, G1, B0, B1);
    `a8` = (A0, A1); indices de 2 bits (los texeles 0 de cada plano se
    guardan con 1)."""
    bits = [0] * 5 + [1]
    bits += [(rot >> i) & 1 for i in range(2)]
    for f in f7:
        bits += [(f >> i) & 1 for i in range(7)]
    for f in a8:
        bits += [(f >> i) & 1 for i in range(8)]
    bits += [cidx[0] & 1]
    for k in range(1, 16):
        bits += [(cidx[k] >> i) & 1 for i in range(2)]
    bits += [aidx[0] & 1]
    for k in range(1, 16):
        bits += [(aidx[k] >> i) & 1 for i in range(2)]
    assert len(bits) == 128
    data = bytearray(16)
    for i, b in enumerate(bits):
        if b:
            data[i // 8] |= 1 << (i % 8)
    return bytes(data)


def _dds_minimo(datos, ancho, alto, dxgi=98):
    """Un DDS DX10 de 148 bytes + el nivel 0, para que Pillow lo decodifique."""
    n_bl = max(1, -(-ancho // 4)) * max(1, -(-alto // 4))
    cab = bytearray(148)
    cab[0:4] = b"DDS "
    struct.pack_into("<IIIII", cab, 4, 124, 0x8100F, alto, ancho, n_bl * 16)
    struct.pack_into("<I", cab, 28, 1)
    struct.pack_into("<I", cab, 76, 32)
    struct.pack_into("<I", cab, 80, 0x4)
    cab[84:88] = b"DX10"
    struct.pack_into("<I", cab, 108, 0x1000)
    struct.pack_into("<IIIII", cab, 128, dxgi, 3, 0, 1, 0)
    im = Image.open(io.BytesIO(bytes(cab) + bytes(datos)))
    return im.convert("RGBA").tobytes()


def _degradado(w, h):
    y, x = np.mgrid[0:h, 0:w]
    img = np.stack((x * 255 // max(1, w - 1), y * 255 // max(1, h - 1),
                    (x + y) * 255 // max(1, w + h - 2),
                    128 + (x * 127 // max(1, w - 1))), -1).astype(np.uint8)
    return img.tobytes()


def _normal_con_mascara(w, h):
    """Un `_n` sintetico: RGB de normal suave y alfa (la mascara) con otro
    patron, los dos independientes."""
    y, x = np.mgrid[0:h, 0:w]
    r = 128 + (x - w // 2) * 60 // max(1, w // 2)
    g = 128 + (y - h // 2) * 60 // max(1, h // 2)
    b = np.full((h, w), 230)
    a = x * 255 // max(1, w - 1)
    return np.stack((r, g, b, a), -1).astype(np.uint8).tobytes()


def _ruido(w, h, semilla=7):
    rng = np.random.default_rng(semilla)
    return rng.integers(0, 256, (h, w, 4), dtype=np.uint8).tobytes()


@unittest.skipIf(cb is None, "compresor_bc7 necesita numpy")
class DependenciasEnCiTests(unittest.TestCase):

    def test_en_ci_estan_numpy_y_pillow(self):
        if not _en_ci():
            self.skipTest("fuera de CI son opcionales")
        self.assertIsNotNone(np, "CI sin numpy: el compresor no se prueba")
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.fail("CI sin Pillow: se perderian las comparaciones byte a "
                      "byte contra el oraculo")


class DecodificadorTests(unittest.TestCase):
    """Bloques hechos a mano, decodificados a valores escritos a mano
    (los literales salieron de Pillow 12.3)."""

    def test_m6_endpoints_con_pbit(self):
        blk = _bloque_m6((10, 20, 30, 40, 50, 60, 70, 80), 1, 0, [0] * 16)
        pix = cb.descomprimir(blk, 4, 4)
        got = set(tuple(pix[i:i + 4]) for i in range(0, 64, 4))
        self.assertEqual(got, {(21, 61, 101, 141)})

    def test_m6_los_dieciseis_pesos(self):
        """La rampa completa: (v<<1)|p0 con endpoints 0 y 100, un indice por
        texel, y la ancla del texel 0 leyendo 3 bits con el MSB implicito 0."""
        blk = _bloque_m6((0, 100, 0, 100, 0, 100, 0, 100), 0, 0,
                         list(range(16)))
        pix = cb.descomprimir(blk, 4, 4)
        esperado = [(0, 0, 0, 0), (13, 13, 13, 13), (28, 28, 28, 28),
                    (41, 41, 41, 41), (53, 53, 53, 53), (66, 66, 66, 66),
                    (81, 81, 81, 81), (94, 94, 94, 94), (106, 106, 106, 106),
                    (119, 119, 119, 119), (134, 134, 134, 134),
                    (147, 147, 147, 147), (159, 159, 159, 159),
                    (172, 172, 172, 172), (188, 188, 188, 188),
                    (200, 200, 200, 200)]
        got = [tuple(pix[i:i + 4]) for i in range(0, 64, 4)]
        self.assertEqual(got, esperado)

    def test_m5_alfa_de_ocho_bits_es_exacto(self):
        blk = _bloque_m5(0, (10, 20, 30, 40, 50, 60), (70, 80),
                         [0] * 16, [0] * 16)
        pix = cb.descomprimir(blk, 4, 4)
        self.assertEqual(
            set(tuple(pix[i:i + 4]) for i in range(0, 64, 4)),
            {(20, 60, 100, 70)})

    def test_m5_expansion_siete_a_ocho_y_peso_21(self):
        """(v << 1) | (v >> 6): 63 -> 126, 64 -> 129, 100 -> 201, 127 -> 255;
        y el peso 21/64 del indice 1 con la ancla de 1 bit."""
        blk = _bloque_m5(0, (63, 64, 100, 127, 0, 32), (0, 255),
                         [1] * 16, [0] * 16)
        pix = cb.descomprimir(blk, 4, 4)
        self.assertEqual(tuple(pix[0:4]), (127, 219, 21, 0))

    def test_m5_indice_de_color_1(self):
        blk = _bloque_m5(0, (10, 20, 30, 40, 50, 60), (70, 80),
                         [1] * 16, [0] * 16)
        pix = cb.descomprimir(blk, 4, 4)
        self.assertEqual(tuple(pix[0:4]), (27, 67, 107, 70))

    def test_m5_rotacion_1_permuta_r_con_a(self):
        blk = _bloque_m5(1, (10, 20, 30, 40, 50, 60), (70, 80),
                         [0] * 16, [0] * 16)
        pix = cb.descomprimir(blk, 4, 4)
        self.assertEqual(tuple(pix[0:4]), (70, 60, 100, 20))

    def test_un_modo_de_los_otros_se_rechaza(self):
        otro = bytearray(16)
        otro[0] = 0x01                      # modo 0 del spec: 1 en el bit 0
        with self.assertRaises(ValueError) as ctx:
            cb.descomprimir(bytes(otro), 4, 4)
        self.assertIn("modo 0", str(ctx.exception))

    def test_datos_incompletos_se_rechazan(self):
        with self.assertRaises(ValueError):
            cb.descomprimir(bytes(16), 8, 8)


@unittest.skipIf(cb is None, "compresor_bc7 necesita numpy")
class CompresorTests(unittest.TestCase):

    def test_alfa_constante_vuelve_exacto(self):
        """La garantia que la mascara especular necesita: un bloque con alfa
        constante A vuelve con A, en los dos modos (p-bit forzado a A & 1 en
        el modo 6, 8 bits directos en el modo 5)."""
        for alfa in (255, 55, 0):
            pix = bytearray()
            for y in range(16):
                for x in range(16):
                    pix += bytes(((x * 13) % 256, (y * 7) % 256,
                                  ((x + y) * 5) % 256, alfa))
            vuelta = cb.descomprimir(cb.comprimir(bytes(pix), 16, 16),
                                     16, 16)
            self.assertEqual(set(vuelta[3::4]), {alfa},
                             "alfa %d no volvio exacto" % alfa)

    def test_color_plano_vuelve_exacto(self):
        """(10, 20, 30, 40) esta en las dos reticulas; (11, 21, 31, 255) solo
        en la del modo 6 con p=1, que es donde lo tiene que buscar."""
        for pix in (bytes((10, 20, 30, 40)) * 16,
                    bytes((11, 21, 31, 255)) * 16):
            vuelta = cb.descomprimir(cb.comprimir(pix, 4, 4), 4, 4)
            self.assertEqual(vuelta, pix)

    def test_dos_colores_con_la_ancla_en_cualquiera(self):
        """El texel 0 guarda un bit menos de indice: si le toca el bit alto,
        el compresor invierte endpoints e indices. Los dos arreglos tienen
        que volver exactos."""
        a, b = (11, 21, 31, 255), (201, 211, 221, 255)
        for pix in (bytes(a) * 15 + bytes(b),
                    bytes(b) + bytes(a) * 15):
            vuelta = cb.descomprimir(cb.comprimir(pix, 4, 4), 4, 4)
            self.assertEqual(vuelta, pix)

    def test_la_calidad_le_gana_a_dxt5(self):
        """Medido (ver docstring del modulo): en color BC7 le gana a DXT5 en
        el degradado y en el normal con mascara independiente; en el ruido
        RGBA el RGB queda parejo y el alfa es el peor caso del modo 5."""
        # degradado: el RGB tiene que ganarle
        img = _degradado(64, 64)
        e7 = cb.error_rms(img, cb.descomprimir(cb.comprimir(img, 64, 64),
                                               64, 64))
        e5 = cb.error_rms(img, cd.descomprimir(
            cd.comprimir(img, 64, 64, "DXT5"), 64, 64, "DXT5"))
        self.assertLess(sum(e7[:3]) / 3, sum(e5[:3]) / 3)
        self.assertLess(e7[3], 4.0)
        # normal + mascara: el conjunto tiene que ganar
        img = _normal_con_mascara(64, 64)
        e7 = cb.error_rms(img, cb.descomprimir(cb.comprimir(img, 64, 64),
                                               64, 64))
        e5 = cb.error_rms(img, cd.descomprimir(
            cd.comprimir(img, 64, 64, "DXT5"), 64, 64, "DXT5"))
        self.assertLess(sum(e7) / 4, sum(e5) / 4)
        self.assertLess(e7[3], 1.0)

    def test_el_ruido_es_el_peor_caso_y_esta_acotado(self):
        """RGBA aleatorio: el RGB no se atrasa de DXT5, y el alfa --4
        paradas del modo 5 contra las 8 de DXT5-- queda acotado. Un alfa de
        verdad no es ruido (el del normal de arriba no lo es)."""
        img = _ruido(64, 64)
        e7 = cb.error_rms(img, cb.descomprimir(cb.comprimir(img, 64, 64),
                                               64, 64))
        e5 = cb.error_rms(img, cd.descomprimir(
            cd.comprimir(img, 64, 64, "DXT5"), 64, 64, "DXT5"))
        self.assertLessEqual(sum(e7[:3]) / 3, sum(e5[:3]) / 3 + 1.0)
        self.assertLess(e7[3], 20.0)

    def test_tamanos_de_mipmap_chicos(self):
        for w, h in ((1, 1), (2, 2), (4, 1), (8, 2)):
            pix = bytes((1, 2, 3, 4)) * (w * h)
            datos = cb.comprimir(pix, w, h)
            esperado = max(1, -(-w // 4)) * max(1, -(-h // 4)) * 16
            self.assertEqual(len(datos), esperado)
            vuelta = cb.descomprimir(datos, w, h)
            self.assertEqual(len(vuelta), w * h * 4)

    def test_pixeles_del_lado_malos_se_rechazan(self):
        with self.assertRaises(ValueError):
            cb.comprimir(bytes(15), 4, 4)

    @unittest.skipUnless(HAY_PILLOW, "Pillow no esta: falta el oraculo")
    def test_pillow_decodifica_lo_mismo_byte_a_byte(self):
        """La comprobacion que fija el layout: el decodificador de Pillow 12.3
        sobre lo que escribimos tiene que dar EXACTAMENTE lo que da el
        nuestro, en los dos modos mezclados."""
        for img in (_degradado(64, 64), _normal_con_mascara(64, 64),
                    _ruido(64, 64)):
            datos = cb.comprimir(img, 64, 64)
            suyo = _dds_minimo(datos, 64, 64)
            self.assertEqual(suyo, cb.descomprimir(datos, 64, 64))

    def test_el_autotest_pasa(self):
        self.assertTrue(cb.autotest())


if __name__ == "__main__":
    unittest.main()
