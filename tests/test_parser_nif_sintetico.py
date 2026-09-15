# -*- coding: utf-8 -*-
"""Ida y vuelta contra un NIF sintetico: los dos parsers del repo tienen que
recuperar exactamente lo que `nif_sintetico.construir()` escribio.

Cubre el hueco que dejaba la suite anterior. Comprobado: inyectando un
corrimiento de 4 bytes en la lectura de la cabecera de `census/parser_nif.py`
--i += 8 en vez de i += 4 al saltear max-string-length-- los once tests
previos seguian en verde y estos fallan.

Cada guarda de aca viene con su propio test de que puede fallar
(`test_el_detector_detecta`, `ElFixtureEsDetectorTests`). Un chequeo que no
puede fallar no prueba nada, y esta suite existe justamente por haber
encontrado uno.

Que NO cubre: geometria, skin, particiones y colision. Esos layouts se validan
solo contra archivos reales, con `python census/parser_nif.py --autotest`.
"""
import gc
import os
import tempfile
import unittest
import warnings

from _paths import preparar_path
from nif_sintetico import construir

preparar_path()

import censo_nif  # noqa: E402  (la semilla, en skills/.../scripts)
import parser_nif  # noqa: E402  (el parser del censo, en census/)


class BaseSintetico(unittest.TestCase):
    """Escribe el NIF sintetico una vez para toda la clase."""

    @classmethod
    def setUpClass(cls):
        cls.datos, cls.esperado = construir()
        fd, cls.ruta = tempfile.mkstemp(suffix=".nif", prefix="sintetico_")
        with os.fdopen(fd, "wb") as fh:
            fh.write(cls.datos)

    @classmethod
    def tearDownClass(cls):
        try:
            os.remove(cls.ruta)
        except OSError:
            pass

    def comprobar_comun(self, n):
        e = self.esperado
        self.assertEqual(n.version, e["version"])
        self.assertEqual(n.user, e["user"])
        self.assertEqual(n.bs, e["bs"])
        self.assertEqual(n.raiz(), e["raiz"])
        self.assertEqual(len(n.bloques), e["n_bloques"])
        self.assertEqual(n.cuenta_tipos(), e["cuenta_tipos"])
        self.assertEqual(n.strings, e["strings"])

        # Los offsets tienen que encadenar exactos: un bloque arranca donde
        # termina el anterior. Un corrimiento en la cabecera rompe esto.
        self.assertEqual([tam for _, _, tam in n.bloques], e["tamanos"])
        for k in range(1, len(n.bloques)):
            _, off_prev, tam_prev = n.bloques[k - 1]
            _, off, _ = n.bloques[k]
            self.assertEqual(off, off_prev + tam_prev,
                             "el bloque %d no arranca donde termina el %d"
                             % (k, k - 1))

        nombres = {v["nombre"] for v in n.nodos().values()}
        self.assertEqual(nombres, e["nombres_nodo"])


class ParserDelCensoTests(BaseSintetico):
    def test_lee_lo_que_se_escribio(self):
        n = parser_nif.Nif(self.ruta)
        self.comprobar_comun(n)
        self.assertEqual(n.header_tail, self.esperado["cola_esperada"])

    def test_bsxflags(self):
        n = parser_nif.Nif(self.ruta)
        valor, bits = n.bsxflags_info()
        self.assertEqual(valor, self.esperado["bsxflags"])
        self.assertEqual(bits, self.esperado["bsxflags_bits"])

    def test_jerarquia(self):
        n = parser_nif.Nif(self.ruta)
        nodos = n.nodos()
        raiz = [v for v in nodos.values() if v["nombre"] == "RaizDePrueba"][0]
        self.assertEqual(len(raiz["hijos"]), 1,
                         "la raiz tiene que tener exactamente un hijo")


class SemillaDeLaSkillTests(BaseSintetico):
    """La semilla de la skill parsea la misma cabecera. Si las dos
    implementaciones divergen sobre los mismos bytes, una esta mal."""

    def test_lee_lo_que_se_escribio(self):
        n = censo_nif.Nif(self.ruta)
        self.comprobar_comun(n)

    def test_bsxflags(self):
        n = censo_nif.Nif(self.ruta)
        self.assertEqual(n.bsxflags(), self.esperado["bsxflags"])

    def test_posicion_de_mundo_del_hijo(self):
        n = censo_nif.Nif(self.ruta)
        mundo = n.mundo()
        x, y, z, escala = mundo["HijoDePrueba"]
        self.assertEqual((x, y, z), self.esperado["hijo_en_mundo"])
        self.assertEqual(escala, 1.0)


class ConcordanciaEntreParsersTests(BaseSintetico):
    """Dos implementaciones escritas por separado sobre los mismos bytes."""

    def test_coinciden(self):
        a = parser_nif.Nif(self.ruta)
        b = censo_nif.Nif(self.ruta)
        self.assertEqual(a.raiz(), b.raiz())
        self.assertEqual(a.cuenta_tipos(), b.cuenta_tipos())
        self.assertEqual(a.strings, b.strings)
        self.assertEqual(a.bsxflags_info()[0], b.bsxflags())
        self.assertEqual([t for t, _, _ in a.bloques],
                         [t for t, _, _ in b.bloques])


class FurnitureMarkerTests(BaseSintetico):
    """El fixture trae un BSFurnitureMarkerNode minado.

    Es una prueba de COMPORTAMIENTO, no de pertenencia a un set: parsea el
    bloque de verdad. Un parser que lo trate como NiNode revienta leyendo
    4.294.967.280 refs de hijo, igual que con los archivos reales de
    meshes/furniture/ (30 de 76 fallaban).
    """

    def test_el_censo_lo_ignora(self):
        nodos = parser_nif.Nif(self.ruta).nodos()
        nombres = {v["nombre"] for v in nodos.values()}
        self.assertNotIn(self.esperado["nombre_marcador"], nombres)

    def test_la_semilla_lo_ignora(self):
        nodos = censo_nif.Nif(self.ruta).nodos()
        nombres = {v["nombre"] for v in nodos.values()}
        self.assertNotIn(self.esperado["nombre_marcador"], nombres)

    def test_el_sufijo_node_no_alcanza(self):
        """Guarda explicita: ningun parser puede meterlo en su tabla."""
        for mod in (parser_nif, censo_nif):
            with self.subTest(modulo=mod.__name__):
                self.assertNotIn("BSFurnitureMarkerNode", mod.TIPOS_NODO)


class SinFugasDeDescriptorTests(BaseSintetico):
    """Fugas de descriptor, comprobado de forma que PUEDA fallar.

    `python -W error::ResourceWarning` NO sirve para esto y es una trampa: el
    ResourceWarning lo emite el destructor del objeto archivo, y una excepcion
    lanzada ahi queda "unraisable" -- se imprime un traceback pero el proceso
    sale con codigo 0 y unittest reporta ok. Verificado en 3.11: un test con
    `open(__file__, "rb").read()` imprime el aviso y sale 0.

    Aca se fuerza la recoleccion con el filtro activo y se afirma sobre lo
    capturado, que si es determinista y si falla.
    """

    def _fugas_al_parsear(self, constructor):
        with warnings.catch_warnings(record=True) as capturadas:
            warnings.simplefilter("always", ResourceWarning)
            n = constructor(self.ruta)
            del n
            gc.collect()
        return [w for w in capturadas
                if issubclass(w.category, ResourceWarning)]

    def test_el_censo_no_fuga(self):
        self.assertEqual(self._fugas_al_parsear(parser_nif.Nif), [])

    def test_la_semilla_no_fuga(self):
        self.assertEqual(self._fugas_al_parsear(censo_nif.Nif), [])

    def test_el_detector_detecta(self):
        """Si este test no falla al fugar a proposito, los dos de arriba no
        valen nada."""
        def fuga(ruta):
            open(ruta, "rb").read()          # sin close, deliberado
            return object()

        self.assertNotEqual(self._fugas_al_parsear(fuga), [],
                            "el detector de fugas no detecta fugas")


class ElFixtureEsDetectorTests(BaseSintetico):
    """Un chequeo que no puede fallar no prueba nada.

    Corrompe el NIF sintetico a proposito y confirma que el parser se entera,
    en vez de devolver numeros bien formateados. Si este test empieza a
    fallar, el parser dejo de validar y los de arriba valen menos.
    """

    def test_bloques_que_exceden_el_archivo_revientan(self):
        datos = bytearray(self.datos)
        # Al ultimo bloque le sobreescribimos el tamano con algo enorme.
        # Queda declarado un fin de bloques mas alla del fin de archivo.
        pos = datos.find(b"RaizDePrueba")
        self.assertGreater(pos, 0, "el fixture cambio: revisar este test")
        datos_rotos = bytes(datos[:-4])          # amputa el ultimo bloque
        fd, ruta = tempfile.mkstemp(suffix=".nif", prefix="roto_")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(datos_rotos)
            with self.assertRaises(Exception):
                parser_nif.Nif(ruta)
        finally:
            os.remove(ruta)


if __name__ == "__main__":
    unittest.main()
