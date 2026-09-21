# -*- coding: utf-8 -*-
"""Proporciones de arma contra el rango de su CLASE.

Una daga y un martillo a dos manos no comparten una sola proporción, así que
una tabla única para "armas" no dice nada de ninguna.

Estos tests fijan dos cosas que costaron aparecer:

* **La tabla y el clasificador tienen que ser el mismo.** La primera versión
  generó la tabla con un clasificador y envió otro, con un comodín `axe` que
  metía `axeofysgramor` (99 unidades), `executioneraxe` (145) y seis piezas de
  `brokenaxe*` en la clase de las hachas de una mano. La REGLA rechazaba el
  **6,36 %** del corpus del que había salido.

* **El límite de la regla.** El rango vanilla es ancho: el mango del hacha de
  Tencent medía 0,1124 del largo y el rango de su clase es [0,0369, 0,1854].
  La regla **no lo marca**, aunque a ojo se veía grueso. Lo que sí lo dice es
  el percentil, y eso es una OBSERVACIÓN.
"""
import os
import subprocess
import sys
import tempfile
import unittest

from _paths import preparar_path

preparar_path()

import proporciones_arma as pa  # noqa: E402

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "skills", "modelo-ia-a-skyrim", "scripts", "proporciones_arma.py")


def _barra(largo=100.0, fino=1.0, grueso=5.0, corte=0.25):
    """Una barra con un extremo fino: el mango es el extremo fino."""
    pts = []
    for i in range(int(largo) + 1):
        y = float(i)
        r = fino if y < largo * corte else grueso
        for sx in (-r, r):
            for sz in (-r, r):
                pts.append((sx, y, sz))
    return pts


def _medidas(clase, campo=None, valor=None):
    """La mediana de una clase, con un campo torcido si se pide."""
    ref = pa.CLASES[clase]
    m = dict((c, ref[c][1]) for c, _ in pa.CAMPOS)
    if campo is not None:
        m[campo] = valor
    return m


class MedicionTests(unittest.TestCase):

    def test_la_barra_da_los_numeros_conocidos(self):
        m = pa.medir(_barra())
        self.assertAlmostEqual(m["largo"], 100.0, 6)
        self.assertAlmostEqual(m["mango"], 2.0, 6)
        self.assertAlmostEqual(m["mango_largo"], 0.02, 9)
        self.assertEqual(m["eje"], "Y")

    def test_el_mango_es_el_extremo_fino_de_cualquier_lado(self):
        derecha = pa.medir(_barra())
        izquierda = pa.medir([(x, 100.0 - y, z) for x, y, z in _barra()])
        self.assertAlmostEqual(derecha["mango"], izquierda["mango"], 6)

    def test_una_malla_sin_extremos_medibles_no_inventa(self):
        self.assertIsNone(pa.medir([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]))


class TablaTests(unittest.TestCase):
    """La tabla tiene que aceptar lo que la genero."""

    def test_la_mediana_de_cada_clase_pasa_su_propia_regla(self):
        for clase in pa.CLASES:
            with self.subTest(clase=clase):
                self.assertEqual(pa.juzgar(_medidas(clase), clase)[0], [])

    def test_los_dos_bordes_de_cada_clase_pasan(self):
        """El archivo que DEFINE un límite no puede reprobarlo. La tabla está
        redondeada a 4 decimales, así que hace falta una unidad de tolerancia:
        `elvenbattleaxe` tiene grosor/largo 0,043099 y el mínimo guardado es
        0,0431, y sin tolerancia reprobaba."""
        for clase in pa.CLASES:
            for campo, _ in pa.CAMPOS:
                for extremo in (0, 2):
                    with self.subTest(clase=clase, campo=campo,
                                      extremo=extremo):
                        v = pa.CLASES[clase][campo][extremo]
                        self.assertEqual(
                            pa.juzgar(_medidas(clase, campo, v), clase)[0], [])

    def test_una_unidad_de_redondeo_por_fuera_todavia_pasa(self):
        """Es el caso REAL, y el anterior no lo cubría: probar con el valor
        exacto del borde pasa aunque la tolerancia sea cero. `elvenbattleaxe`
        tiene grosor/largo 0,043099 y la tabla guarda 0,0431 — está una unidad
        de redondeo por debajo del mínimo que él mismo define."""
        for clase in pa.CLASES:
            for campo, _ in pa.CAMPOS:
                lo, _med, hi = pa.CLASES[clase][campo]
                # El 9e-5 va LITERAL y no `pa.TOLERANCIA`: la tabla está
                # redondeada a 4 decimales y eso es un hecho de la tabla, no
                # de la constante. Leyendo la constante, mutarla a 0 movía
                # también la sonda y el test seguía en verde.
                for v, lado in ((lo - 9e-5, "bajo el mínimo"),
                                (hi + 9e-5, "sobre el máximo")):
                    with self.subTest(clase=clase, campo=campo, lado=lado):
                        self.assertEqual(
                            pa.juzgar(_medidas(clase, campo, v), clase)[0], [],
                            "%s %s %s reprobó dentro del redondeo"
                            % (clase, campo, lado))

    def test_cada_clase_tiene_al_menos_diez_ejemplares(self):
        """Con menos de diez, un rango no es un rango."""
        for clase, ref in pa.CLASES.items():
            with self.subTest(clase=clase):
                self.assertGreaterEqual(ref["n"], 10)

    def test_los_rangos_estan_ordenados(self):
        for clase, ref in pa.CLASES.items():
            for campo, _ in pa.CAMPOS:
                with self.subTest(clase=clase, campo=campo):
                    lo, med, hi = ref[campo]
                    self.assertLessEqual(lo, med)
                    self.assertLessEqual(med, hi)


class ClasificadorTests(unittest.TestCase):

    def test_las_pistas_especificas_ganan_a_las_generales(self):
        casos = [("elvenbattleaxe.nif", "hacha2m"),
                 ("steelwaraxe.nif", "hacha1m"),
                 ("daedricgreatsword.nif", "mandoble"),
                 ("ironsword.nif", "espada"),
                 ("orcishwarhammer.nif", "martillo2m"),
                 ("ebonydagger.nif", "daga")]
        for nombre, esperada in casos:
            with self.subTest(archivo=nombre):
                self.assertEqual(pa.clase_por_nombre(nombre), esperada)

    def test_sin_comodin_axe(self):
        """El comodín `axe` hacía que la REGLA rechazara el 6,36 % del corpus.
        Estos archivos son hachas vanilla y NO son hachas de una mano."""
        for nombre in ("axeofysgramor.nif", "1stpersonexecutioneraxe.nif",
                       "brokenaxespike.nif", "brokenaxecenter.nif",
                       "boundaxeencheffects.nif"):
            with self.subTest(archivo=nombre):
                self.assertIsNone(
                    pa.clase_por_nombre(nombre),
                    "%s se clasificó solo; con un comodín vuelve el 6,36 %%"
                    % nombre)


class ReglaTests(unittest.TestCase):

    def test_fuera_del_rango_reprueba_en_los_dos_sentidos(self):
        ref = pa.CLASES["hacha2m"]
        for campo, _ in pa.CAMPOS:
            for factor, lado in ((1.5, "por encima"), (0.5, "por debajo")):
                with self.subTest(campo=campo, lado=lado):
                    v = ref[campo][2 if factor > 1 else 0] * factor
                    fallas = pa.juzgar(_medidas("hacha2m", campo, v),
                                       "hacha2m")[0]
                    self.assertTrue(fallas, "%s %s no reprobó" % (campo, lado))

    def test_una_clase_desconocida_reprueba(self):
        self.assertTrue(pa.juzgar(_medidas("daga"), "no-existe")[0])

    def test_el_mango_del_hacha_de_tencent_NO_lo_marca_la_regla(self):
        """El límite de esta herramienta, afirmado. 0,1124 está dentro de
        [0,0369, 0,1854]: la regla no lo marca. Lo que sí dice algo es el
        percentil, y sale como OBSERVACIÓN."""
        fallas, notas = pa.juzgar(
            _medidas("hacha2m", "mango_largo", 0.1124), "hacha2m")
        self.assertEqual(fallas, [])
        self.assertTrue(any("mango / largo" in n and "por encima" in n
                            for n in notas))


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
        self.assertEqual(self._correr("x.obj")[0], 2)

    def test_sin_clase_adivinable_no_sale_cero(self):
        fd, ruta = tempfile.mkstemp(suffix=".nif")
        os.close(fd)
        try:
            codigo, salida = self._correr(ruta)
            self.assertEqual(codigo, 1, salida)
            self.assertIn("no se pudo adivinar la clase", salida)
        finally:
            os.unlink(ruta)


if __name__ == "__main__":
    unittest.main()
