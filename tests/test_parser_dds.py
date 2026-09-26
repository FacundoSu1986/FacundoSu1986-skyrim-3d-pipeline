# -*- coding: utf-8 -*-
"""Tests de parser_dds con encabezados DDS construidos byte a byte.

Misma tecnica que tests/nif_sintetico.py: los bytes se generan (cero material
con copyright) y junto a cada fixture se declara lo que un parser correcto
tiene que recuperar, incluido el tamano exacto del archivo -- que es la
identidad que el autotest exige sobre el corpus real.

Los tamanos esperados de cada caso estan contados a MANO en este archivo, no
calculados con la formula del parser: si la formula cambia mal, el test canta.
Un test que calcula el esperado con el mismo codigo que verifica no prueba
nada.
"""
import contextlib
import io
import os
import struct
import tempfile
import unittest

from _paths import preparar_path

preparar_path()

import parser_dds  # noqa: E402
from parser_dds import DdsInvalido, leer  # noqa: E402

HEADER = 128
HEADER_DX10 = 148
DDSD_MIPMAPCOUNT = 0x20000
DDPF_FOURCC = 0x4
DDSCAPS2_CUBEMAP = 0x200
CARAS_CUBEMAP = (0x400, 0x800, 0x1000, 0x2000, 0x4000, 0x8000)
DDSCAPS2_VOLUME = 0x200000


def header_dds(ancho, alto, mips=0, fourcc=None, dx10=None, bits=0,
               alfa_mask=0, caps2=0, profundidad=0):
    """Cabecera DDS valida: 128 bytes, o 148 con la extension DX10."""
    b = bytearray(HEADER_DX10 if dx10 is not None else HEADER)
    b[0:4] = b"DDS "
    struct.pack_into("<I", b, 4, 124)                       # dwSize
    flags = 0x1 | 0x2 | 0x4 | 0x1000        # CAPS | HEIGHT | WIDTH | PIXELFORMAT
    if mips:
        flags |= DDSD_MIPMAPCOUNT
    struct.pack_into("<III", b, 8, flags, alto, ancho)
    struct.pack_into("<I", b, 24, profundidad)
    struct.pack_into("<I", b, 28, mips)
    struct.pack_into("<I", b, 76, 32)                       # ddspf.dwSize
    if dx10 is not None:
        struct.pack_into("<I", b, 80, DDPF_FOURCC)
        b[84:88] = b"DX10"
        struct.pack_into("<I", b, 128, dx10)
    elif fourcc is not None:
        struct.pack_into("<I", b, 80, DDPF_FOURCC)
        b[84:88] = fourcc
    else:
        struct.pack_into("<I", b, 88, bits)
        struct.pack_into("<I", b, 104, alfa_mask)
    struct.pack_into("<I", b, 112, caps2)
    return bytes(b)


def _escribir(carpeta, nombre, datos):
    ruta = os.path.join(carpeta, nombre)
    with open(ruta, "wb") as fh:
        fh.write(datos)
    return ruta


def dds(carpeta, nombre, cuerpo, **kw):
    """Cabecera + cuerpo de relleno. `cuerpo` son los bytes tras la cabecera."""
    return _escribir(carpeta, nombre, header_dds(**kw) + b"\0" * cuerpo)


class BaseDds(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name


class FixtureDdsTests(BaseDds):
    """Lo que un parser correcto tiene que recuperar de cada caso."""

    def test_dxt1_simple_cuadra(self):
        # 8x8, 1 mip: ceil(8/4)*ceil(8/4)*8 = 32 de cuerpo + 128 = 160.
        e = leer(dds(self.dir, "a.dds", 32, ancho=8, alto=8, fourcc=b"DXT1"))
        self.assertEqual(e["formato"], "DXT1")
        self.assertTrue(e["comprimido"])
        self.assertEqual((e["ancho"], e["alto"], e["mipmaps"]), (8, 8, 1))
        self.assertEqual(e["bytes"], 160)
        self.assertEqual(e["bytes_esperados"], 160)
        self.assertTrue(e["tamano_cuadra"])
        self.assertEqual(e["mip_mas_chico"], [8, 8])
        self.assertFalse(e["srgb"])
        self.assertFalse(e["cubemap"])
        self.assertTrue(e["potencia_de_dos"])

    def test_cadena_de_mips_cuadra(self):
        # 8/4/2/1 -> 32 + 8 + 8 + 8 = 56 de cuerpo -> 184.
        e = leer(dds(self.dir, "b.dds", 56, ancho=8, alto=8, mips=4,
                     fourcc=b"DXT1"))
        self.assertEqual(e["mipmaps"], 4)
        self.assertEqual(e["bytes_esperados"], 184)
        self.assertTrue(e["tamano_cuadra"])
        self.assertEqual(e["mip_mas_chico"], [1, 1])
        self.assertFalse(e["sin_mipmaps"])

    def test_dxt5_bloque_de_16_bytes(self):
        # 16x16: 4*4*16 = 256 -> 384.
        e = leer(dds(self.dir, "c.dds", 256, ancho=16, alto=16, fourcc=b"DXT5"))
        self.assertEqual(e["formato"], "DXT5")
        self.assertTrue(e["tiene_alfa"])
        self.assertEqual(e["bytes_esperados"], 384)
        self.assertTrue(e["tamano_cuadra"])

    def test_dx10_bc7_cabecera_extra_y_srgb(self):
        # BC7 8x8: 2*2*16 = 64 de cuerpo; cabecera 148 -> 212. dxgi 99 = sRGB.
        e = leer(dds(self.dir, "d.dds", 64, ancho=8, alto=8, dx10=99))
        self.assertEqual(e["formato"], "BC7")
        self.assertTrue(e["srgb"])
        self.assertEqual(e["bytes_esperados"], 212)
        self.assertTrue(e["tamano_cuadra"])

    def test_dx10_sin_srgb(self):
        self.assertFalse(leer(dds(self.dir, "d2.dds", 64, ancho=8, alto=8,
                                  dx10=98))["srgb"])

    def test_cubemap_multiplica_por_seis(self):
        # 6 caras de 32 bytes -> 128 + 192 = 320. Sin esto, la prediccion
        # falla por un factor de 6 exacto (el hallazgo de los cubemaps).
        caps2 = DDSCAPS2_CUBEMAP
        for c in CARAS_CUBEMAP:
            caps2 |= c
        e = leer(dds(self.dir, "e.dds", 192, ancho=8, alto=8, fourcc=b"DXT1",
                     caps2=caps2))
        self.assertTrue(e["cubemap"])
        self.assertEqual(e["caras"], 6)
        self.assertEqual(e["bytes_esperados"], 320)
        self.assertTrue(e["tamano_cuadra"])

    def test_volumen_apila_profundidad(self):
        # 4x4x4 con 2 mips: (1*1*8*4) + (1*1*8*2) = 48 -> 128 + 48 = 176.
        e = leer(dds(self.dir, "f.dds", 48, ancho=4, alto=4, mips=2,
                     fourcc=b"DXT1", caps2=DDSCAPS2_VOLUME, profundidad=4))
        self.assertTrue(e["volumen"])
        self.assertEqual(e["profundidad"], 4)
        self.assertEqual(e["bytes_esperados"], 176)
        self.assertTrue(e["tamano_cuadra"])

    def test_sin_comprimir_32bpp(self):
        # 4x4 * 4 bytes/px = 64 -> 192.
        e = leer(dds(self.dir, "g.dds", 64, ancho=4, alto=4, bits=32,
                     alfa_mask=0xFF000000))
        self.assertEqual(e["formato"], "sin_comprimir_32bpp")
        self.assertFalse(e["comprimido"])
        self.assertTrue(e["tiene_alfa"])
        self.assertEqual(e["bytes_esperados"], 192)
        self.assertTrue(e["tamano_cuadra"])

    def test_sin_comprimir_24bpp_no_tiene_alfa_aunque_declare_mascara(self):
        """La mascara alfa de un header inconsistente no alcanza: en 24 bpp
        cada pixel mide 3 bytes y 0xFF000000 no puede existir. `bool(mask)`
        solo lo daba por bueno, y con eso un _n de 24 bpp pasaba la regla del
        canal alfa (review del PR #32)."""
        e = leer(dds(self.dir, "i.dds", 4 * 4 * 3, ancho=4, alto=4, bits=24,
                     alfa_mask=0xFF000000))
        self.assertEqual(e["formato"], "sin_comprimir_24bpp")
        self.assertTrue(e["tamano_cuadra"])
        self.assertFalse(e["tiene_alfa"])

    def test_mips_sin_flag_se_fuerza_a_1(self):
        # Declara 5 mips pero sin DDSD_MIPMAPCOUNT: vale 1, y el cuerpo de un
        # solo nivel (32) tiene que cuadrar.
        e = leer(dds(self.dir, "h.dds", 32, ancho=8, alto=8, fourcc=b"DXT1",
                     mips=0))
        self.assertEqual(e["mipmaps"], 1)
        self.assertTrue(e["sin_mipmaps"])
        self.assertTrue(e["tamano_cuadra"])


class ElTamanoFalsificaTests(BaseDds):
    """Un chequeo que no puede fallar no prueba nada: la identidad de tamano
    y los magic tienen que poder reventar."""

    def test_un_byte_menos_no_cuadra(self):
        e = leer(dds(self.dir, "roto.dds", 31, ancho=8, alto=8, fourcc=b"DXT1"))
        self.assertEqual(e["bytes_esperados"], 160)
        self.assertEqual(e["bytes"], 159)
        self.assertFalse(e["tamano_cuadra"])

    def test_magic_roto_rechaza(self):
        ruta = _escribir(self.dir, "m.dds", b"XXXX" + b"\0" * 200)
        with self.assertRaises(DdsInvalido):
            leer(ruta)

    def test_dwsize_roto_rechaza(self):
        h = bytearray(header_dds(8, 8, fourcc=b"DXT1"))
        struct.pack_into("<I", h, 4, 125)                   # tenia que ser 124
        ruta = _escribir(self.dir, "m2.dds", bytes(h) + b"\0" * 32)
        with self.assertRaises(DdsInvalido):
            leer(ruta)


class FuncionesPurasTests(unittest.TestCase):
    def test_ceil4(self):
        self.assertEqual(parser_dds._ceil4(8), 2)
        self.assertEqual(parser_dds._ceil4(9), 3)
        self.assertEqual(parser_dds._ceil4(1), 1)

    def test_mip_final(self):
        self.assertEqual(parser_dds._mip_final(8, 8, 1), [8, 8])
        self.assertEqual(parser_dds._mip_final(8, 8, 4), [1, 1])
        self.assertEqual(parser_dds._mip_final(256, 128, 5), [16, 8])


class AutotestDdsTests(BaseDds):
    """La puerta de entrada del censo, sin corpus: temporales."""

    def _autotest_callado(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return parser_dds.autotest(self.dir)

    def test_carpeta_vacia_NO_valida(self):
        # Antes devolvia True: "validado sobre 0 archivos" con exit 0. Cero
        # comprobaciones no es exito (la misma guarda que parser_nif).
        self.assertFalse(self._autotest_callado())

    def test_un_archivo_bueno_valida(self):
        dds(self.dir, "ok.dds", 32, ancho=8, alto=8, fourcc=b"DXT1")
        self.assertTrue(self._autotest_callado())

    def test_un_archivo_malo_no_valida(self):
        dds(self.dir, "malo.dds", 31, ancho=8, alto=8, fourcc=b"DXT1")
        self.assertFalse(self._autotest_callado())


if __name__ == "__main__":
    unittest.main()
