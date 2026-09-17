# -*- coding: utf-8 -*-
"""Tres desacuerdos entre dos lecturas del mismo formato (issues #18, #19, #20).

El repo tiene tres parsers de NIF: el completo (`census/parser_nif.py`), la
semilla de la skill (`censo_nif.py`) y el lector de nodos (`nif_nodos.py`).
Cuando dos leen el mismo campo distinto, uno de los dos esta mal y el corpus no
siempre lo delata -- por eso hay tests, y por eso estan escritos para enumerar
la familia en vez de fijar el caso que ya encontramos.
"""
import os
import struct
import tempfile
import unittest

from _paths import preparar_path

preparar_path()

import censo_nif  # noqa: E402
import nif_nodos  # noqa: E402
import parser_nif  # noqa: E402
import nif_sintetico  # noqa: E402


def _con_bs(datos, bs):
    """Los mismos bytes con otra BS version. El campo esta despues de la linea
    magica: version(4) + endian(1) + user(4) + n_bloques(4)."""
    i = datos.index(bytes([10])) + 1 + 4 + 1 + 4 + 4
    b = bytearray(datos)
    struct.pack_into("<I", b, i, bs)
    return bytes(b)


def _archivo(datos):
    fd, ruta = tempfile.mkstemp(suffix=".nif")
    with os.fdopen(fd, "wb") as fh:
        fh.write(datos)
    return ruta


class TiposDeShapeTests(unittest.TestCase):
    """#19: la semilla iteraba solo BSTriShape."""

    def test_las_dos_listas_de_tipos_de_shape_son_la_misma(self):
        """No compara contra una lista escrita a mano: compara los dos parsers
        entre si. Si manana aparece un cuarto tipo y se agrega a uno solo, cae
        aca, que es el modo en que se rompio la primera vez."""
        self.assertEqual(
            tuple(censo_nif.TIPOS_SHAPE), tuple(parser_nif.TIPOS_SHAPE),
            "censo_nif y parser_nif no coinciden en que bloques son shapes: "
            "el que se quede corto reporta n_shapes=0 sin avisar")

    def test_bsdynamictrishape_cuenta_como_shape(self):
        """3.803 archivos del corpus (17 %) traen BSDynamicTriShape y ningun
        BSTriShape. La semilla los reportaba con n_shapes = 0."""
        self.assertIn("BSDynamicTriShape", censo_nif.TIPOS_SHAPE)


class VersionBsNoValidadaTests(unittest.TestCase):
    """#18: dos lecturas distintas de la cabecera para BS>=130, ninguna
    validada -- el corpus tiene 22.393 con BS=100, uno con BS=83 y cero con
    BS>=130. Adivinar el largo de un campo de cabecera corre TODOS los offsets
    de bloque, que es la familia del bug de 'pesos por vertice = 1035'."""

    def setUp(self):
        self.datos, _ = nif_sintetico.construir()
        self.rutas = []

    def tearDown(self):
        for r in self.rutas:
            try:
                os.unlink(r)
            except OSError:
                pass

    def _ruta(self, datos):
        r = _archivo(datos)
        self.rutas.append(r)
        return r

    def test_bs_100_se_lee_en_los_tres(self):
        """El par del test de abajo: si los tres rechazaran todo, el otro test
        pasaria sin probar nada."""
        ruta = self._ruta(self.datos)
        self.assertTrue(parser_nif.Nif(ruta).bloques)
        self.assertTrue(censo_nif.Nif(ruta).bloques)
        self.assertTrue(nif_nodos.leer(ruta))

    def test_ningun_parser_adivina_la_cabecera_de_bs_130(self):
        """Enumera los tres puntos de entrada. Un cuarto parser que copie el
        patron y no ponga la guarda cae aca en cuanto se agregue a la lista."""
        entradas = (
            ("census/parser_nif.py", lambda r: parser_nif.Nif(r)),
            ("skills/.../censo_nif.py", lambda r: censo_nif.Nif(r)),
            ("skills/.../nif_nodos.py", lambda r: nif_nodos.leer(r)),
        )
        for bs in (130, 155):
            ruta = self._ruta(_con_bs(self.datos, bs))
            for nombre, abrir in entradas:
                with self.assertRaises(Exception, msg=nombre) as cm:
                    abrir(ruta)
                self.assertIn(
                    "130", str(cm.exception),
                    "%s con BS=%d no explica por que no lee: %s"
                    % (nombre, bs, cm.exception))


class UmbralDeRigidBodyTests(unittest.TestCase):
    """#20: el parser leia campos con s >= 246 y el verificador exige
    s == 250 + 4*numConstraints. La identidad se cumple en 14.586 de 14.586
    bloques del corpus y no existe ninguno entre 246 y 249: el 246 era
    permisivo sin que ningun archivo lo justificara."""

    def test_el_parser_no_es_mas_permisivo_que_el_verificador(self):
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "census", "parser_nif.py")
        with open(ruta, encoding="utf-8") as fh:
            fuente = fh.read()
        self.assertNotIn(
            "if s >= 246:", fuente,
            "parser_nif vuelve a leer bloques que verificar marca como cortos")
        self.assertIn("if s >= 250:", fuente)


if __name__ == "__main__":
    unittest.main()
