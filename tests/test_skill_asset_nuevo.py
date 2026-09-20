# -*- coding: utf-8 -*-
"""La skill del asset nuevo: el marco del nodo de anclaje y el flag ESL.

Corre en CI: los NIF y los plugins se construyen byte a byte. Los `--autotest`
de los dos scripts prueban otra cosa --que reproducen valores medidos sobre el
corpus y sobre los 10 plugins-- y necesitan los archivos instalados.

Este archivo construye su propio NIF con un nodo ROTADO en vez de tocar
`nif_sintetico.py`: ese fixture lo esta modificando otra rama, y un fixture
compartido que dos ramas amplian a la vez es una colision garantizada.
"""
import math
import os
import struct
import tempfile
import unittest

from _paths import preparar_path, RAIZ

preparar_path()

import esl  # noqa: E402
import nif_nodos  # noqa: E402
import nif_sintetico  # noqa: E402
import plugin_sintetico  # noqa: E402

CANONICO = os.path.join(RAIZ, "skills", "modelo-ia-a-skyrim", "scripts",
                        "nif_nodos.py")
COPIA = os.path.join(RAIZ, "skills", "asset-nuevo-skyrim", "scripts",
                     "nif_nodos.py")


def _archivo(datos, caso, suf=".nif"):
    fd, ruta = tempfile.mkstemp(suffix=suf)
    with os.fdopen(fd, "wb") as fh:
        fh.write(datos)
    caso.addCleanup(lambda: os.path.exists(ruta) and os.unlink(ruta))
    return ruta


def _nif_con_rotacion(grados, nombre="ANCLA"):
    """Un NIF de un solo nodo cuyo marco pone el arriba del mundo a `grados`.

    `angulo_de_arriba` mide atan2 de la TERCERA FILA de la matriz, porque el
    +Z del mundo visto en local es esa fila. Asi que la respuesta se declara
    construyendo la fila: (cos, sen, 0). Las otras dos se eligen para que la
    matriz sea una rotacion de verdad --ortonormal y con determinante +1--,
    no una reflexion, que daria numeros plausibles sobre una matriz que un
    NIF nunca trae.

    Mi primera version giraba alrededor de X y esperaba `90 - grados`. Esa
    cuenta esta mal: girar en X deja el arriba con componente X nula, asi que
    el angulo sale 90 para CUALQUIER giro. El test fallo y tenia razon.
    """
    NS = nif_sintetico
    r = math.radians(grados)
    c, s = math.cos(r), math.sin(r)
    rot = (0.0, 0.0, -1.0,
           -s, c, 0.0,
           c, s, 0.0)
    p = struct.pack("<i", 0)
    p += struct.pack("<I", 0)
    p += struct.pack("<i", -1)
    p += struct.pack("<I", 14)
    p += struct.pack("<3f", 0.0, 0.0, 0.0)
    p += struct.pack("<9f", *rot)
    p += struct.pack("<f", 1.0)
    p += struct.pack("<i", -1)
    p += struct.pack("<I", 0)
    p += struct.pack("<I", 0)
    bloques = [p]

    h = bytearray(NS.CABECERA)
    h += struct.pack("<I", NS.VERSION) + struct.pack("<B", 1)
    h += struct.pack("<I", NS.USER) + struct.pack("<I", len(bloques))
    h += struct.pack("<I", NS.BS)
    h += NS._corta("") + NS._corta("") + NS._corta("")
    h += struct.pack("<H", 1) + NS._larga("NiNode")
    h += struct.pack("<H", 0)
    h += struct.pack("<I", len(bloques[0]))
    h += struct.pack("<I", 1) + struct.pack("<I", len(nombre))
    h += NS._larga(nombre)
    h += struct.pack("<I", 0)
    return bytes(h) + b"".join(bloques)


class LasDosCopiasSonLaMismaTests(unittest.TestCase):
    """`nif_nodos.py` vive en las dos skills porque cada una se empaqueta
    sola. La copia que estaba fuera del repo ya habia divergido: usaba
    `tipo.endswith("Node")` --la trampa de BSFurnitureMarkerNode-- y se habia
    quedado sin el arreglo de BSMasterParticleSystem. Medido: de 40 archivos
    MPS del corpus, 39 daban un juego de nodos distinto al del lector
    validado."""

    def test_byte_a_byte(self):
        with open(CANONICO, "rb") as fh:
            a = fh.read()
        with open(COPIA, "rb") as fh:
            b = fh.read()
        self.assertEqual(a, b,
                         "las dos copias de nif_nodos.py divergieron; "
                         "copiá la de modelo-ia-a-skyrim sobre la otra")

    def test_y_la_trampa_del_sufijo_no_volvio(self):
        """`endswith("Node")` mete BSFurnitureMarkerNode, que hereda de
        NiExtraData: 123 archivos de muebles. El fixture trae uno."""
        with open(CANONICO, "rb") as fh:
            fuente = fh.read().decode("utf-8")
        self.assertNotIn('endswith("Node")', fuente)
        datos, esperado = nif_sintetico.construir()
        nif = nif_nodos.leer(_archivo(datos, self))
        nombres = {n["nombre"] for n in nif["nodos"].values()}
        self.assertEqual(esperado["nombres_nodo"], nombres)
        self.assertNotIn(esperado["nombre_marcador"], nombres)


class ElMarcoDelNodoDeAnclajeTests(unittest.TestCase):
    """Ningún nodo de anclaje del juego mira al +Y: de los 116 marcos de los
    64 esqueletos del corpus, CERO caen a menos de 5 grados de 90. Modelar con
    el arriba en +Y saca el asset girado esa diferencia."""

    def _marco(self, grados):
        nif = nif_nodos.leer(_archivo(_nif_con_rotacion(grados), self))
        return nif_nodos.angulo_de_arriba(nif_nodos.matrices(nif)["ANCLA"])

    def test_un_marco_conocido_da_el_angulo_conocido(self):
        for grados in (0.0, 30.0, 90.0, 155.7, 249.1, 306.8):
            ang, _arr, norma = self._marco(grados)
            self.assertAlmostEqual(grados, ang, places=3,
                                   msg="marco a %s grados" % grados)
            self.assertAlmostEqual(1.0, norma, places=6)

    def test_el_caso_degenerado_se_reconoce(self):
        """Cuatro nodos REALES del juego tienen el arriba del mundo sobre su
        eje Z local: atan2(0,0) da 0,0 y se imprimia como si fuera una
        medida. La identidad es ese caso."""
        datos, _e = nif_sintetico.construir()
        nif = nif_nodos.leer(_archivo(datos, self))
        M = nif_nodos.matrices(nif)
        raiz = nif_sintetico.RAIZ_NOMBRE
        _ang, _arr, norma = nif_nodos.angulo_de_arriba(M[raiz])
        self.assertLess(norma, nif_nodos.MINIMO_PROYECCION)

    def test_pero_un_marco_sano_no_se_marca_como_degenerado(self):
        """El par del de arriba."""
        for grados in (0.0, 155.7):
            _a, _r, norma = self._marco(grados)
            self.assertGreater(norma, nif_nodos.MINIMO_PROYECCION)

    def test_la_inversa_se_niega_ante_una_matriz_degenerada(self):
        with self.assertRaises(ValueError):
            nif_nodos._invertir([[0.0] * 4, [0.0] * 4, [0.0] * 4])

    def test_matrices_y_mundo_coinciden_en_la_posicion(self):
        """matrices() es nueva; mundo() la usa medio corpus. Si divergieran,
        el marco seria plausible y la posicion otra."""
        datos, _e = nif_sintetico.construir()
        nif = nif_nodos.leer(_archivo(datos, self))
        pos, _prof = nif_nodos.mundo(nif)
        M = nif_nodos.matrices(nif)
        for nombre, p in pos.items():
            self.assertAlmostEqual(p[0], M[nombre][0][3], places=2, msg=nombre)
            self.assertAlmostEqual(p[1], M[nombre][1][3], places=2, msg=nombre)
            self.assertAlmostEqual(p[2], M[nombre][2][3], places=2, msg=nombre)


class EslFallaCerradoTests(unittest.TestCase):
    """`--marcar` escribia el flag sobre un plugin roto. Un truncado de 30
    bytes hacia que el recorrido viera 1 record en vez de 2; con un record
    menos no habia ninguno fuera de rango, y la comprobacion que existe para
    que no corrompas tu mod pasaba JUSTO por no haber mirado."""

    def setUp(self):
        self.datos, _e = plugin_sintetico.construir()

    def test_el_fixture_sano_cierra(self):
        """El par de todos los de abajo."""
        ids, cerro = esl.recorrer_formids(bytearray(self.datos))
        self.assertTrue(cerro)
        self.assertEqual(2, len(ids))

    def test_un_truncado_no_cierra(self):
        ids, cerro = esl.recorrer_formids(bytearray(self.datos[:-30]))
        self.assertFalse(cerro)
        self.assertLess(len(ids), 2)

    def test_un_grup_mas_chico_que_su_cabecera_no_cierra(self):
        b = bytearray(self.datos)
        i = self.datos.index(b"GRUP")
        struct.pack_into("<I", b, i + 4, 4)
        _ids, cerro = esl.recorrer_formids(b)
        self.assertFalse(cerro)

    def _correr(self, payload, *flags):
        import subprocess
        import sys
        ruta = _archivo(payload, self, ".esp")
        script = os.path.join(RAIZ, "skills", "asset-nuevo-skyrim", "scripts",
                              "esl.py")
        p = subprocess.run([sys.executable, script, ruta] + list(flags),
                           capture_output=True, text=True)
        with open(ruta, "rb") as fh:
            despues = fh.read()
        return p.returncode, p.stdout, despues, ruta

    def test_marcar_sobre_un_truncado_no_escribe_nada(self):
        antes = self.datos[:-30]
        codigo, salida, despues, ruta = self._correr(antes, "--marcar")
        self.assertEqual(1, codigo, salida)
        self.assertEqual(antes, despues, "escribio sobre un plugin roto")
        self.assertFalse(os.path.exists(ruta + ".bak"))

    def test_pero_sobre_uno_sano_si_marca(self):
        """El par: si se negara siempre, el fail-closed no probaria nada."""
        codigo, salida, despues, _r = self._correr(self.datos, "--marcar")
        self.assertEqual(0, codigo, salida)
        flags, = struct.unpack_from("<I", despues, 8)
        self.assertTrue(flags & esl.BANDERA_ESL, "no puso el flag")

    def test_sin_records_no_se_marca(self):
        """Cero records propios es no haber leido nada, no un plugin listo."""
        solo_tes4 = self.datos[:self.datos.index(b"GRUP")]
        codigo, salida, _d, _r = self._correr(solo_tes4, "--marcar")
        self.assertEqual(1, codigo, salida)
        self.assertIn("cero records", salida.lower())


class LasTablasDeAutotestDeclaranAlgoTests(unittest.TestCase):

    def test_esl_sin_carpeta_no_es_exito(self):
        import contextlib
        import io as _io
        with tempfile.TemporaryDirectory() as d:
            with contextlib.redirect_stdout(_io.StringIO()) as s:
                self.assertFalse(esl.autotest(d), s.getvalue())

    def test_nif_nodos_sin_corpus_no_es_exito(self):
        import contextlib
        import io as _io
        with tempfile.TemporaryDirectory() as d:
            with contextlib.redirect_stdout(_io.StringIO()) as s:
                self.assertFalse(nif_nodos.autotest(d), s.getvalue())

    def test_esl_declara_conteos(self):
        self.assertTrue(esl.AUTOTEST)
        for nombre, n in esl.AUTOTEST:
            self.assertTrue(nombre.lower().endswith((".esm", ".esp", ".esl")))
            self.assertGreater(n, 0, nombre)

    def test_nif_nodos_declara_valores_y_un_contraejemplo(self):
        """La tabla tiene que traer al menos un esqueleto donde el SHIELD NO
        este a 155,7: el angulo no es una constante del juego."""
        self.assertTrue(nif_nodos.AUTOTEST)
        angulos = set()
        for rel, esperado in nif_nodos.AUTOTEST:
            self.assertTrue(rel.lower().endswith(".nif"))
            self.assertTrue(esperado, "%s no declara nada" % rel)
            for clave in esperado:
                self.assertIn(clave, ("n_nodos", "angulos", "locales",
                                      "degenerados"))
            if "SHIELD" in esperado.get("angulos", {}):
                angulos.add(esperado["angulos"]["SHIELD"])
        self.assertGreater(len(angulos), 1,
                           "todas las entradas dan el mismo angulo de SHIELD: "
                           "falta el contraejemplo")
        self.assertTrue(any(e.get("degenerados")
                            for _r, e in nif_nodos.AUTOTEST),
                        "falta el caso donde el angulo no significa nada")


if __name__ == "__main__":
    unittest.main()
