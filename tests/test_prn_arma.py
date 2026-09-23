# -*- coding: utf-8 -*-
"""El Prn: de que nodo del esqueleto cuelga el arma envainada.

Es un NiStringExtraData del NIF, y sigue al tipo de animacion del WEAP en 305
de 306 armas del jugador (census/hallazgos_plugins.md, entrada 17). El hacha
de Tencent lleva WeaponBack y cuelga en la espalda: confirmado en el juego.

Cruza dos archivos: el tipo sale del DNAM[0] del plugin y el Prn del NIF que
el MODL nombra. Por eso se prueba sobre una carpeta de mod de verdad --el
plugin al lado de meshes/--, no sobre dicts.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from _paths import preparar_path

preparar_path()

import nif_nodos  # noqa: E402
import nif_sintetico  # noqa: E402
import plugin_sintetico  # noqa: E402
import verificar_plugin as vp  # noqa: E402

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "skills", "asset-nuevo-skyrim", "scripts", "verificar_plugin.py")

# LITERAL, no vp.PRN_POR_TIPO: la tabla es un hecho del corpus. Leyendo la
# constante del script, mutarla moveria tambien la sonda.
TABLA = {1: "WeaponSword", 2: "WeaponDagger", 3: "WeaponAxe",
         4: "WeaponMace", 5: "WeaponBack", 6: "WeaponBack", 7: "WeaponBow",
         9: "WeaponBow"}
MODL = r"Weapons\Prueba\arma.nif"


def _escribir(ruta, datos):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "wb") as fh:
        fh.write(datos)


class LecturaDelPrnTests(unittest.TestCase):

    def _nif(self, datos):
        fd, ruta = tempfile.mkstemp(suffix=".nif")
        os.write(fd, datos)
        os.close(fd)
        self.addCleanup(os.unlink, ruta)
        return nif_nodos.leer(ruta)

    def test_leer_devuelve_la_tabla_de_strings(self):
        datos, esperado = nif_sintetico.construir()
        self.assertEqual(self._nif(datos)["strings"], esperado["strings"])

    def test_cadena_extra_lee_el_prn(self):
        for prn in ("WeaponBack", "WeaponSword", "SHIELD"):
            with self.subTest(prn=prn):
                datos, _ = nif_sintetico.construir_arma(prn)
                self.assertEqual(
                    nif_nodos.cadena_extra(self._nif(datos), "Prn"), prn)

    def test_sin_prn_da_none(self):
        datos, _ = nif_sintetico.construir_arma(None)
        self.assertIsNone(nif_nodos.cadena_extra(self._nif(datos), "Prn"))

    def test_otro_nombre_da_none(self):
        """El nombre se compara: un NiStringExtraData cualquiera no es el
        Prn."""
        datos, _ = nif_sintetico.construir_arma("WeaponBack")
        self.assertIsNone(
            nif_nodos.cadena_extra(self._nif(datos), "NoExiste"))


class ReglaPrnTests(unittest.TestCase):

    def _mod(self, anim, prn, con_nif=True, modl=MODL, ruta_nif=MODL,
             nif_bytes=None):
        """Una carpeta de mod: Mod.esl al lado de meshes/<ruta_nif>."""
        raiz = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, raiz)
        datos, _ = plugin_sintetico.construir_weap(anim=anim, modl=modl)
        _escribir(os.path.join(raiz, "Mod.esl"), datos)
        if con_nif:
            nif = nif_bytes
            if nif is None:
                nif, _ = nif_sintetico.construir_arma(prn)
            _escribir(os.path.join(raiz, "meshes",
                                   *ruta_nif.split("\\")), nif)
        info = vp.leer(os.path.join(raiz, "Mod.esl"))
        self.assertIsNone(info["error"])
        return vp.juzgar(info)

    def test_el_hacha_de_tencent(self):
        """Hacha de dos manos (6) con WeaponBack: cuelga en la espalda en el
        juego."""
        fallas, _ = self._mod(6, "WeaponBack")
        self.assertEqual(fallas, [])

    def test_cada_tipo_con_su_prn_pasa(self):
        for anim, prn in TABLA.items():
            with self.subTest(anim=anim, prn=prn):
                self.assertEqual(self._mod(anim, prn)[0], [])

    def test_cada_tipo_con_otro_prn_reprueba(self):
        """Enumerante: cada tipo contra TODOS los Prn que no le tocan."""
        for anim, bueno in TABLA.items():
            for prn in sorted(set(TABLA.values()) - {bueno}):
                with self.subTest(anim=anim, prn=prn):
                    fallas, _ = self._mod(anim, prn)
                    self.assertTrue(
                        any("REGLA WEAP Prn" in f and prn in f and bueno in f
                            for f in fallas),
                        "tipo %d con %s no reprobo: %r" % (anim, prn, fallas))

    def test_sin_prn_reprueba(self):
        fallas, _ = self._mod(6, None)
        self.assertTrue(any("REGLA WEAP Prn" in f and "sin Prn" in f
                            for f in fallas), fallas)

    def test_un_nif_ilegible_se_reporta_como_ilegible(self):
        """Sin esta rama igual reprobaba, pero diciendo "sin Prn", que manda a
        buscar el problema en el lugar equivocado. Lo encontro una mutacion."""
        basura = b"Gamebryo File Format, Version 20.2.0.7\n" + b"\x00" * 5
        fallas, _ = self._mod(6, None, nif_bytes=basura)
        self.assertTrue(any("REGLA WEAP Prn" in f and "no se pudo leer" in f
                            for f in fallas), fallas)

    def test_un_baston_no_tiene_regla(self):
        """Los bastones vanilla usan WeaponStaff (21) o SHIELD (18)."""
        for prn in ("WeaponStaff", "SHIELD"):
            with self.subTest(prn=prn):
                fallas, notas = self._mod(8, prn)
                self.assertEqual(fallas, [])
                self.assertTrue(any("baston" in n for n in notas), notas)

    def test_sin_nif_junto_al_plugin_lo_dice(self):
        fallas, notas = self._mod(6, "WeaponBack", con_nif=False)
        self.assertEqual(fallas, [])
        self.assertTrue(any("NIF" in n and "Prn no verificado" in n
                            for n in notas), notas)

    def test_la_ruta_no_distingue_mayusculas(self):
        """El juego corre sobre un sistema de archivos que no distingue
        mayusculas: `weapons\\PRUEBA\\Arma.nif` es el mismo archivo. Resolverlo
        distinto dejaria el Prn sin verificar en Linux sin avisar de mas."""
        fallas, notas = self._mod(6, "WeaponSword",
                                  modl=r"weapons\PRUEBA\Arma.nif")
        self.assertTrue(any("REGLA WEAP Prn" in f for f in fallas),
                        "no encontro el NIF por mayusculas: %r" % notas)


class FalsificarPrnTests(unittest.TestCase):

    def test_sin_meshes_utilizables_no_es_exito(self):
        vacia = tempfile.mkdtemp()
        try:
            p = subprocess.run([sys.executable, SCRIPT, "--falsificar-prn",
                                vacia, vacia], capture_output=True, text=True)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("no comprobar nada no es", p.stdout)
        finally:
            os.rmdir(vacia)


if __name__ == "__main__":
    unittest.main()
