# -*- coding: utf-8 -*-
"""Las dos reglas de la caja de colision, y las tres que NO se pueden escribir.

Armar la colision copiando un donante campo por campo es lo correcto para casi
todo, pero el radio convexo y la inercia dependen de ESTA caja. Copiarlos deja
un cuerpo que no corresponde a su forma y Havok no avisa.

Lo que estos tests fijan tanto como las reglas es el LIMITE de las reglas: dos
de las tres versiones "obvias" resultaron falsas contra el corpus, y sin un
test que lo diga alguien las va a volver a escribir.
"""
import os
import subprocess
import sys
import tempfile
import unittest

from _paths import preparar_path

preparar_path()

import colision_caja  # noqa: E402
import nif_nodos  # noqa: E402
import nif_sintetico  # noqa: E402

FINA = (0.278, 0.643, 0.061)        # semieje menor por DEBAJO del tope
GRUESA = (3.558, 1.843, 2.062)      # semieje menor por ENCIMA del tope

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "skills", "asset-nuevo-skyrim", "scripts", "colision_caja.py")


def _caja(dims, **kw):
    c = {"cuerpo": "bhkRigidBodyT", "dims": list(dims), "masa": 9.0,
         "inercia": [2.5, 0.5, 2.9], "motion": 3,
         "radio": colision_caja.radio_esperado(dims)}
    c.update(kw)
    return c


def _archivo(datos):
    fd, ruta = tempfile.mkstemp(suffix=".nif")
    with os.fdopen(fd, "wb") as fh:
        fh.write(datos)
    return ruta


class RadioTests(unittest.TestCase):
    """REGLA: bhkRadius == min(semieje menor, 0,1). 2.667 de 2.684."""

    def test_el_tope_se_aplica_de_los_dos_lados(self):
        self.assertAlmostEqual(colision_caja.radio_esperado(FINA), 0.061, 6)
        self.assertAlmostEqual(colision_caja.radio_esperado(GRUESA), 0.1, 9)

    def test_las_dos_cajas_correctas_pasan(self):
        for dims in (FINA, GRUESA):
            with self.subTest(dims=dims):
                self.assertEqual(colision_caja.juzgar(_caja(dims))[0], [])

    def test_un_radio_de_otro_donante_reprueba(self):
        fallas = colision_caja.juzgar(_caja(FINA, radio=0.0297))[0]
        self.assertTrue(fallas)
        self.assertIn("REGLA radio", fallas[0])

    def test_no_vale_la_regla_sin_el_tope(self):
        """"bhkRadius es el semieje menor" a secas daba 62 de 62 SOBRE ARMAS y
        es falsa: sobre el corpus entero es 73,25 %. Una caja gruesa con el
        radio igual a su semieje menor tiene que REPROBAR."""
        fallas = colision_caja.juzgar(_caja(GRUESA, radio=min(GRUESA)))[0]
        self.assertTrue(fallas, "la version sin tope daria esto por bueno")
        self.assertIn("REGLA radio", fallas[0])


class InerciaTests(unittest.TestCase):
    """REGLA: masa > 0 <=> diagonal de inercia > 0. 1.194 de 1.194."""

    def test_el_bicondicional_en_los_cuatro_casos(self):
        casos = [
            ("masa>0 con inercia", 9.0, [2.5, 0.5, 2.9], False),
            ("masa>0 sin inercia", 9.0, [0.0, 0.0, 0.0], True),
            ("masa=0 sin inercia", 0.0, [0.0, 0.0, 0.0], False),
            ("masa=0 con inercia", 0.0, [2.5, 0.5, 2.9], True),
        ]
        for nombre, masa, inercia, debe_reprobar in casos:
            with self.subTest(caso=nombre):
                fallas = colision_caja.juzgar(
                    _caja(FINA, masa=masa, inercia=inercia))[0]
                self.assertEqual(bool(fallas), debe_reprobar,
                                 "%s: %s" % (nombre, fallas))

    def test_masa_cero_con_inercia_cero_NO_reprueba(self):
        """383 de 1.194 cuerpos vanilla son asi. Exigir "diagonal > 0" a secas
        --como decia la skill-- rechaza a Bethesda."""
        self.assertEqual(
            colision_caja.juzgar(_caja(FINA, masa=0.0,
                                       inercia=[0.0, 0.0, 0.0]))[0], [])

    def test_el_valor_de_la_inercia_no_se_exige(self):
        """Resultado negativo medido: contra m(a^2+b^2)/12 la razon va de 1,2 a
        471 y solo 1 de 2.433 ejes cae dentro del +-10 %. No hay formula, asi
        que una inercia absurda se INFORMA y no reprueba."""
        fallas, notas = colision_caja.juzgar(
            _caja(FINA, inercia=[999.0, 999.0, 999.0]))
        self.assertEqual(fallas, [])
        self.assertTrue(any("formula de caja" in n for n in notas))


class LecturaDelBloqueTests(unittest.TestCase):
    """Los offsets, contra un NIF escrito byte a byte."""

    def test_recupera_lo_que_se_escribio(self):
        datos, esperado = nif_sintetico.construir_con_colision(
            dims=FINA, radio=0.061, masa=9.0, inercia=(2.5, 0.5, 2.9),
            motion=3)
        ruta = _archivo(datos)
        try:
            cs = colision_caja.cajas(nif_nodos.leer(ruta))
            self.assertEqual(len(cs), 1)
            c = cs[0]
            self.assertNotIn("error", c)
            self.assertEqual([round(x, 5) for x in c["dims"]],
                             [round(x, 5) for x in esperado["dims"]])
            self.assertAlmostEqual(c["radio"], esperado["radio"], 5)
            self.assertAlmostEqual(c["masa"], esperado["masa"], 5)
            self.assertEqual([round(x, 5) for x in c["inercia"]],
                             [round(x, 5) for x in esperado["inercia"]])
            self.assertEqual(c["motion"], esperado["motion"])
            self.assertEqual(c["cuerpo"], esperado["cuerpo"])
        finally:
            os.unlink(ruta)

    def test_un_cuerpo_corto_avisa_en_vez_de_leer_lo_que_sigue(self):
        """Si el bloque no llega a motionSystem, leer ahi devolveria un byte
        del bloque siguiente. Tiene que salir 'error'."""
        datos, _ = nif_sintetico.construir_con_colision(
            dims=FINA, radio=0.061, masa=9.0, inercia=(2.5, 0.5, 2.9),
            tam_cuerpo=120)
        ruta = _archivo(datos)
        try:
            cs = colision_caja.cajas(nif_nodos.leer(ruta))
            self.assertEqual(len(cs), 1)
            self.assertIn("error", cs[0])
            self.assertTrue(colision_caja.juzgar(cs[0])[0])
        finally:
            os.unlink(ruta)


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

    def test_caja_sana_sale_cero_y_caja_rota_sale_uno(self):
        sana, _ = nif_sintetico.construir_con_colision(
            dims=FINA, radio=0.061, masa=9.0, inercia=(2.5, 0.5, 2.9))
        rota, _ = nif_sintetico.construir_con_colision(
            dims=FINA, radio=0.0297, masa=9.0, inercia=(2.5, 0.5, 2.9))
        r_sana, r_rota = _archivo(sana), _archivo(rota)
        try:
            self.assertEqual(self._correr(r_sana)[0], 0)
            codigo, salida = self._correr(r_rota)
            self.assertEqual(codigo, 1, salida)
            self.assertIn("REGLA radio", salida)
        finally:
            os.unlink(r_sana)
            os.unlink(r_rota)

    def test_un_nif_sin_cajas_no_sale_cero(self):
        """Cero comprobaciones no es exito."""
        datos, _ = nif_sintetico.construir()
        ruta = _archivo(datos)
        try:
            codigo, salida = self._correr(ruta)
            self.assertEqual(codigo, 1, salida)
            self.assertIn("cero cajas comprobadas", salida)
        finally:
            os.unlink(ruta)


if __name__ == "__main__":
    unittest.main()
