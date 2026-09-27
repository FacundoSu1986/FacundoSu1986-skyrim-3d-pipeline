# -*- coding: utf-8 -*-
"""correr_suite.py: el ancla de los tests salteados en CI.

La lista, SALTEADOS_EN_CI, se prueba donde vale: en el CI, corriendo la suite
de verdad. Aca se prueba el mecanismo, sobre una suite sintetica en un
directorio temporal: que un salteo que no esta en la lista, uno de la lista que
no se saltea y un motivo cambiado den codigo 1; que fuera de CI no se compare;
que una lista igual no tape un fallo; y que cero tests no sea verde.
"""
import io
import os
import shutil
import sys
import tempfile
import unittest

import correr_suite as cs

MODULO = "test_sintetico_de_correr_suite"
SALTEADO = MODULO + ".Sintetico.test_se_saltea"
QUE_PASA = MODULO + ".Sintetico.test_pasa"
MOTIVO = "sin el paquete"

FUENTE = (
    "import unittest\n\n\n"
    "class Sintetico(unittest.TestCase):\n\n"
    "    def test_pasa(self):\n"
    "        pass\n\n"
    "    def test_se_saltea(self):\n"
    "        self.skipTest(%r)\n" % MOTIVO
)


def _ids(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from _ids(test)
        else:
            yield test.id()


class AnclaTests(unittest.TestCase):

    def _correr(self, esperados, comparar=True, fuente=FUENTE):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        if fuente is not None:
            with open(os.path.join(d, MODULO + ".py"), "w", encoding="utf-8") as fh:
                fh.write(fuente)
        # discover deja el directorio en sys.path y el modulo en sys.modules:
        # el caso siguiente, con el mismo nombre, encontraria el viejo.
        self.addCleanup(sys.modules.pop, MODULO, None)
        self.addCleanup(lambda: sys.path.remove(d) if d in sys.path else None)
        flujo = io.StringIO()
        return cs.correr(d, esperados, comparar, flujo), flujo.getvalue()

    def test_lo_salteado_igual_a_la_lista_da_0(self):
        codigo, salida = self._correr({SALTEADO: MOTIVO})
        self.assertEqual(codigo, 0, salida)
        self.assertIn("los 1 son exactamente los de SALTEADOS_EN_CI", salida)

    def test_un_salteo_que_no_esta_en_la_lista_da_1(self):
        codigo, salida = self._correr({})
        self.assertEqual(codigo, 1, salida)
        self.assertIn("sobra   %s: %r" % (SALTEADO, MOTIVO), salida)

    def test_uno_de_la_lista_que_no_se_saltea_da_1(self):
        codigo, salida = self._correr({SALTEADO: MOTIVO, QUE_PASA: MOTIVO})
        self.assertEqual(codigo, 1, salida)
        self.assertIn("falta   %s" % QUE_PASA, salida)

    def test_otro_motivo_da_1(self):
        codigo, salida = self._correr({SALTEADO: "otro"})
        self.assertEqual(codigo, 1, salida)
        self.assertIn("motivo  %s" % SALTEADO, salida)

    def test_fuera_de_ci_no_compara(self):
        codigo, salida = self._correr({}, comparar=False)
        self.assertEqual(codigo, 0, salida)
        self.assertIn("fuera de CI no se compara (1 salteados)", salida)

    def test_una_lista_igual_no_tapa_un_fallo(self):
        fuente = FUENTE + "\n    def test_falla(self):\n        self.fail('roto')\n"
        codigo, salida = self._correr({SALTEADO: MOTIVO}, fuente=fuente)
        self.assertEqual(codigo, 1, salida)
        self.assertIn("exactamente", salida)

    def test_cero_tests_no_es_verde(self):
        codigo, salida = self._correr({}, comparar=False, fuente=None)
        self.assertEqual(codigo, 1, salida)
        self.assertIn("Cero tests", salida)


class LaListaTests(unittest.TestCase):

    def test_nombra_tests_que_existen(self):
        """Un id mal copiado, o un test renombrado, se ve aca y no recien en
        el CI (donde el ancla lo daria como uno que falta y otro que sobra)."""
        existentes = set(_ids(unittest.TestLoader().discover(cs.TESTS)))
        self.assertEqual(sorted(set(cs.SALTEADOS_EN_CI) - existentes), [])


if __name__ == "__main__":
    unittest.main()
