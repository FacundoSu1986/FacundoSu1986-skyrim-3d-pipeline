# -*- coding: utf-8 -*-
"""El alfa del `_n` es la máscara especular, y saturada arruina el asset.

El hacha de Tencent llegó al juego con el 99,7 % de su máscara en blanco: todo
brillaba igual y el arma se veía de plástico, con la malla y el color ya
correctos. El síntoma se confunde con "me falta un ENB".

Lo que estos tests fijan tanto como la regla es su ALCANCE. Medida sobre las
1.201 texturas de objeto portable, la saturación total aparece en 59 (4,91 %),
y todas son materiales mate: ropa, comida, carbón, cejas. Así que la REGLA se
declara solo para armas --140 de 140 por debajo del 6,9 %-- y el resto se
informa.
"""
import os
import struct
import subprocess
import sys
import tempfile
import unittest

from _paths import preparar_path

preparar_path()

import mascara_especular as me  # noqa: E402

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "skills", "modelo-ia-a-skyrim", "scripts", "mascara_especular.py")


def _dds(alfas, ancho=64, alto=64, fourcc=b"DXT5", dxgi=None):
    cab = bytearray(128)
    cab[0:4] = b"DDS "
    struct.pack_into("<I", cab, 4, 124)
    struct.pack_into("<II", cab, 12, alto, ancho)
    cab[84:88] = fourcc
    extra = b""
    if fourcc == b"DX10":
        extra = bytearray(20)
        struct.pack_into("<I", extra, 0, dxgi)
        extra = bytes(extra)
    bw, bh = (ancho + 3) // 4, (alto + 3) // 4
    cuerpo = bytearray(bw * bh * 16)
    for i in range(bw * bh):
        a = alfas[i % len(alfas)]
        cuerpo[i * 16] = a
        cuerpo[i * 16 + 1] = a
    return bytes(cab) + extra + bytes(cuerpo)


def _archivo(datos):
    fd, ruta = tempfile.mkstemp(suffix="_n.dds")
    with os.fdopen(fd, "wb") as fh:
        fh.write(datos)
    return ruta


def _medir(alfas, **kw):
    ruta = _archivo(_dds(alfas, **kw))
    try:
        return me.medir(ruta, paso=1)
    finally:
        os.unlink(ruta)


class MedicionTests(unittest.TestCase):

    def test_una_mascara_toda_blanca_se_mide_como_tal(self):
        m = _medir([255])
        self.assertAlmostEqual(m["blanco_pct"], 100.0, 6)
        self.assertAlmostEqual(m["media"], 255.0, 6)

    def test_una_mascara_variada_no_cuenta_blancos(self):
        m = _medir([40, 80, 120, 200])
        self.assertAlmostEqual(m["blanco_pct"], 0.0, 6)
        self.assertAlmostEqual(m["media"], 110.0, 1)

    def test_los_bloques_con_alfa_variable_no_se_cuentan_como_blancos(self):
        """Si alpha0 != alpha1 el bloque VARIA, y no está saturado aunque uno
        de los dos extremos sea 255."""
        ruta = _archivo(_dds([255]))
        try:
            with open(ruta, "rb") as fh:
                d = bytearray(fh.read())
            for i in range(0, (64 // 4) ** 2):
                d[128 + i * 16 + 1] = 7        # alpha1 distinto de alpha0
            with open(ruta, "wb") as fh:
                fh.write(bytes(d))
            m = me.medir(ruta, paso=1)
            self.assertAlmostEqual(m["blanco_pct"], 0.0, 6)
        finally:
            os.unlink(ruta)


class ReglaDeArmaTests(unittest.TestCase):
    """REGLA: en un `_n` de arma, como mucho 10 % de bloques en blanco."""

    def test_el_umbral_de_los_dos_lados(self):
        casos = [("5 %", [255] + [0] * 19, False),
                 ("15 %", [255] * 3 + [0] * 17, True)]
        for nombre, alfas, debe_reprobar in casos:
            with self.subTest(caso=nombre):
                m = _medir(alfas)
                fallas = me.juzgar(m, True)[0]
                self.assertEqual(bool(fallas), debe_reprobar,
                                 "%s: %s" % (nombre, fallas))

    def test_la_mascara_saturada_reprueba_como_arma(self):
        fallas = me.juzgar(_medir([255]), True)[0]
        self.assertTrue(fallas)
        self.assertIn("REGLA arma", fallas[0])

    def test_la_mascara_saturada_NO_reprueba_sin_declararla_arma(self):
        """59 texturas vanilla de objeto portable son así, y son materiales
        mate. Una regla universal las rechazaría."""
        fallas, notas = me.juzgar(_medir([255]), False)
        self.assertEqual(fallas, [])
        self.assertTrue(any("4,91" in n for n in notas),
                        "no informó la clase de excepción")

    def test_una_mascara_oscura_pasa(self):
        self.assertEqual(me.juzgar(_medir([0]), True)[0], [])
        self.assertEqual(me.juzgar(_medir([30, 60, 90]), True)[0], [])


class FormatoTests(unittest.TestCase):
    """Dos clases de fallo que no se pueden confundir."""

    def test_sin_alfa_es_un_defecto_del_asset(self):
        m = _medir([128], fourcc=b"DXT1")
        self.assertEqual(m.get("clase"), "sin_alfa")
        fallas = me.juzgar(m, True)[0]
        self.assertTrue(fallas)
        self.assertNotIn("NO MEDIBLE", fallas[0])

    def test_bc7_es_un_limite_de_la_herramienta_no_un_defecto(self):
        """BC7 SÍ lleva alfa. No pasa --no comprobar nada no es éxito-- pero
        el mensaje no puede decir que al archivo le falte algo."""
        m = _medir([128], fourcc=b"DX10", dxgi=98)
        self.assertEqual(m.get("clase"), "no_medible")
        fallas = me.juzgar(m, True)[0]
        self.assertTrue(fallas)
        self.assertIn("NO MEDIBLE", fallas[0])

    def test_los_dos_casos_dan_exit_1_pero_por_razones_distintas(self):
        sin_alfa = _archivo(_dds([128], fourcc=b"DXT1"))
        bc7 = _archivo(_dds([128], fourcc=b"DX10", dxgi=98))
        try:
            for ruta, marca in ((sin_alfa, "no tiene canal alfa"),
                                (bc7, "NO MEDIBLE")):
                p = subprocess.run([sys.executable, SCRIPT, "--arma", ruta],
                                   capture_output=True, text=True)
                self.assertEqual(p.returncode, 1, p.stdout)
                self.assertIn(marca, p.stdout + p.stderr)
        finally:
            os.unlink(sin_alfa)
            os.unlink(bc7)


class SinComprimirTests(unittest.TestCase):
    """El formato que escribe `pipeline/texturas.py`.

    Antes caía en "lleva alfa pero este lector no lo decodifica" y se reportaba
    como límite de la herramienta --que era falso: no hay nada que decodificar.
    Medido: 10.048 de 32.241 texturas del corpus son sin comprimir de 32 bpp.
    """

    def _sc(self, alfas, ancho=64, alto=64, bits=32):
        cab = bytearray(128)
        cab[0:4] = b"DDS "
        struct.pack_into("<I", cab, 4, 124)
        struct.pack_into("<III", cab, 8, 0x1007, alto, ancho)
        canales = bits // 8
        struct.pack_into("<I", cab, 20, ancho * canales)
        struct.pack_into("<I", cab, 28, 1)
        struct.pack_into("<I", cab, 76, 32)
        struct.pack_into("<I", cab, 80, 0x1 | 0x40)
        struct.pack_into("<I", cab, 88, bits)
        if bits == 32:
            struct.pack_into("<IIII", cab, 92,
                             0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
        else:
            struct.pack_into("<III", cab, 92,
                             0x00FF0000, 0x0000FF00, 0x000000FF)
        struct.pack_into("<I", cab, 108, 0x1000)
        cuerpo = bytearray()
        for i in range(ancho * alto):
            a = alfas[i % len(alfas)]
            cuerpo += bytes((0, 0, 0, a)) if canales == 4 else bytes((0, 0, 0))
        ruta = _archivo(bytes(cab) + bytes(cuerpo))
        self.addCleanup(lambda: os.path.exists(ruta) and os.unlink(ruta))
        try:
            return me.medir(ruta, paso=1)
        except Exception:
            raise

    def test_se_clasifica_como_sin_comprimir(self):
        self.assertEqual(self._sc([128]).get("formato"),
                         me.SIN_COMPRIMIR_32)

    def test_toda_blanca_da_cien(self):
        m = self._sc([255])
        self.assertAlmostEqual(m["blanco_pct"], 100.0, 6)
        self.assertAlmostEqual(m["media"], 255.0, 6)

    def test_toda_negra_no_cuenta_blancos(self):
        self.assertAlmostEqual(self._sc([0])["blanco_pct"], 0.0, 6)

    def test_variada_no_cuenta_blancos_y_la_media_es_exacta(self):
        """A diferencia de DXT5, acá no hay que aproximar la media: los valores
        están en el archivo."""
        m = self._sc([40, 80, 120, 200])
        self.assertAlmostEqual(m["blanco_pct"], 0.0, 6)
        self.assertAlmostEqual(m["media"], 110.0, 6)

    def test_la_saturacion_parcial_se_mide(self):
        """16 téxeles en 255 y 16 en 0 por bloque: la mitad de los bloques."""
        m = self._sc([255] * 16 + [0] * 16)
        self.assertAlmostEqual(m["blanco_pct"], 50.0, 6)

    def test_la_regla_de_arma_sigue_aplicando(self):
        self.assertTrue(me.juzgar(self._sc([255]), True)[0])
        self.assertEqual(me.juzgar(self._sc([0]), True)[0], [])

    def test_sin_declararla_arma_no_reprueba(self):
        fallas, notas = me.juzgar(self._sc([255]), False)
        self.assertEqual(fallas, [])
        self.assertTrue(any("4,91" in n for n in notas))

    def test_un_24_bpp_es_defecto_no_limite(self):
        m = self._sc([128], bits=24)
        self.assertEqual(m.get("clase"), "sin_alfa")
        fallas = me.juzgar(m, True)[0]
        self.assertTrue(fallas)
        self.assertNotIn("NO MEDIBLE", fallas[0])

    def test_por_linea_de_comandos_tambien(self):
        """El autotest del script cubre el módulo; esto cubre el camino real."""
        ruta = _archivo(_dds_sc([255]))
        try:
            p = subprocess.run([sys.executable, SCRIPT, "--arma", ruta],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 1, p.stdout)
            self.assertIn("REGLA arma", p.stdout + p.stderr)
        finally:
            os.unlink(ruta)


def _dds_sc(alfas, ancho=64, alto=64, bits=32):
    """DDS sin comprimir, solo para los tests de línea de comandos."""
    cab = bytearray(128)
    cab[0:4] = b"DDS "
    struct.pack_into("<I", cab, 4, 124)
    struct.pack_into("<III", cab, 8, 0x1007, alto, ancho)
    canales = bits // 8
    struct.pack_into("<I", cab, 20, ancho * canales)
    struct.pack_into("<I", cab, 28, 1)
    struct.pack_into("<I", cab, 76, 32)
    struct.pack_into("<I", cab, 80, 0x1 | 0x40)
    struct.pack_into("<I", cab, 88, bits)
    struct.pack_into("<IIII", cab, 92,
                     0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    struct.pack_into("<I", cab, 108, 0x1000)
    cuerpo = bytearray()
    for i in range(ancho * alto):
        cuerpo += bytes((0, 0, 0, alfas[i % len(alfas)]))
    return bytes(cab) + bytes(cuerpo)


class CeroComprobacionesTests(unittest.TestCase):
    """Medir nada no es pasar.

    Por la linea de comandos esta guarda es inalcanzable --todo archivo o se
    mide o produce una falla, asi que el exit ya es 1--, pero SI se alcanza
    llamando a revisar() como funcion. Sin este test, borrar la guarda dejaba
    los 13 tests en verde: lo pesco mutar el codigo.
    """

    def test_revisar_sin_archivos_no_devuelve_cero(self):
        self.assertEqual(me.revisar([], False), 1)
        self.assertEqual(me.revisar([], True), 1)


class LineaDeComandosTests(unittest.TestCase):

    def _correr(self, *args):
        p = subprocess.run([sys.executable, SCRIPT] + list(args),
                           capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    def test_autotest_pasa(self):
        codigo, salida = self._correr("--autotest")
        self.assertEqual(codigo, 0, salida)
        self.assertIn("0 fallas", salida)

    def test_argumentos_que_no_sirven_dan_dos(self):
        self.assertEqual(self._correr()[0], 2)
        self.assertEqual(self._correr("x.png")[0], 2)

    def test_sana_sale_cero_y_saturada_sale_uno(self):
        sana = _archivo(_dds([30, 90, 180]))
        saturada = _archivo(_dds([255]))
        try:
            self.assertEqual(self._correr("--arma", sana)[0], 0)
            codigo, salida = self._correr("--arma", saturada)
            self.assertEqual(codigo, 1, salida)
            self.assertIn("REGLA arma", salida)
            self.assertEqual(self._correr(saturada)[0], 0,
                             "sin --arma no tiene que reprobar")
        finally:
            os.unlink(sana)
            os.unlink(saturada)


if __name__ == "__main__":
    unittest.main()
