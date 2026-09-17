# -*- coding: utf-8 -*-
"""Geometria de colision y fidelidad de colocacion.

El contrato valida que un NIF este BIEN FORMADO. No mira donde queda la cosa.
Dos casos independientes mostraron lo caro que sale: 112 de 1.857 estaticos
cambiaron de lugar en un round-trip por PyNifly y el contrato dio verde, y un
escudo modelado a mano salio con la colision a 6 unidades de su malla, tambien
en verde.

Los NIF se construyen byte a byte, asi que esto corre en CI sin corpus.
"""
import contextlib
import io
import os
import struct
import sys
import tempfile
import unittest

from _paths import preparar_path

preparar_path()

import nif_sintetico  # noqa: E402
import parser_colision as pc  # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_RAIZ, "fixtures") not in sys.path:
    sys.path.insert(0, os.path.join(_RAIZ, "fixtures"))

import comparar  # noqa: E402


def nif_con_colision(vertices, traslacion=(0.0, 0.0, 0.0), con_t=False,
                     romper_tamano=False):
    """NIF minimo con un bhkConvexVerticesShape de vertices conocidos.

    `vertices` va en unidades de Skyrim; se guardan divididos por el factor de
    Havok, que es como estan en el archivo.
    """
    tipo_cuerpo = "bhkRigidBodyT" if con_t else "bhkRigidBody"
    tipos = ["BSFadeNode", "bhkConvexVerticesShape", tipo_cuerpo]

    raiz = nif_sintetico._avobject(0, [], (0.0, 0.0, 0.0), [])

    nv = len(vertices)
    forma = bytearray(36)
    struct.pack_into("<I", forma, 0, 1)                 # material
    struct.pack_into("<f", forma, 4, 0.01)              # radio
    struct.pack_into("<I", forma, 32, nv)
    for v in vertices:
        forma += struct.pack("<4f", v[0] / pc.HAVOK, v[1] / pc.HAVOK,
                             v[2] / pc.HAVOK, 0.0)
    forma += struct.pack("<I", 0)                       # numNormals = 0
    if romper_tamano:
        forma += b"\x00" * 8                            # sobra: la identidad cae

    cuerpo = bytearray(250)
    struct.pack_into("<i", cuerpo, 0, 1)                # referencia a la forma
    struct.pack_into("<3f", cuerpo, 52,
                     traslacion[0] / pc.HAVOK,
                     traslacion[1] / pc.HAVOK,
                     traslacion[2] / pc.HAVOK)
    struct.pack_into("<4f", cuerpo, 68, 0.0, 0.0, 0.0, 1.0)   # sin rotacion
    struct.pack_into("<I", cuerpo, 244, 0)              # numConstraints

    bloques = [raiz, bytes(forma), bytes(cuerpo)]

    h = bytearray(nif_sintetico.CABECERA)
    h += struct.pack("<I", nif_sintetico.VERSION) + struct.pack("<B", 1)
    h += struct.pack("<I", nif_sintetico.USER)
    h += struct.pack("<I", len(bloques))
    h += struct.pack("<I", nif_sintetico.BS)
    h += bytes(3)
    h += struct.pack("<H", len(tipos))
    for t in tipos:
        h += struct.pack("<I", len(t)) + t.encode("cp1252")
    h += struct.pack("<3H", 0, 1, 2)
    h += struct.pack("<3I", *[len(b) for b in bloques])
    nombre = nif_sintetico.RAIZ_NOMBRE
    h += struct.pack("<I", 1) + struct.pack("<I", len(nombre))
    h += struct.pack("<I", len(nombre)) + nombre.encode("cp1252")
    h += struct.pack("<I", 0)
    return bytes(h) + b"".join(bloques)


def _archivo(datos, caso):
    fd, ruta = tempfile.mkstemp(suffix=".nif")
    with os.fdopen(fd, "wb") as fh:
        fh.write(datos)
    caso.addCleanup(lambda: os.path.exists(ruta) and os.unlink(ruta))
    return ruta


CUBO = [(x, y, z) for x in (-10.0, 10.0) for y in (-20.0, 20.0)
        for z in (-5.0, 5.0)]


class DecodificarColisionTests(unittest.TestCase):
    """El layout se falsifico sobre 3.553 formas convexas del corpus; aca se
    fija con vertices que conocemos de antemano."""

    def _formas(self, datos):
        import parser_nif
        return pc.formas_de_colision(parser_nif.Nif(_archivo(datos, self)))

    def test_recupera_los_vertices_que_se_escribieron(self):
        fc = self._formas(nif_con_colision(CUBO))[0]
        self.assertNotIn("error", fc)
        self.assertEqual(8, len(fc["vertices"]))
        self.assertEqual([[-10.0, 10.0], [-20.0, 20.0], [-5.0, 5.0]],
                         [[round(v, 3) for v in e] for e in fc["caja"]])

    def test_la_identidad_de_tamano_rechaza_un_bloque_inconsistente(self):
        """36 + 16*nv + 4 + 16*nn == tamano. Si no cierra, no se inventan
        numeros: sale con error."""
        fc = self._formas(nif_con_colision(CUBO, romper_tamano=True))[0]
        self.assertIn("error", fc)
        self.assertNotIn("caja", fc)

    def test_bhkRigidBody_sin_T_no_desplaza(self):
        fc = self._formas(nif_con_colision(CUBO, traslacion=(100.0, 0, 0),
                                           con_t=False))[0]
        self.assertAlmostEqual(0.0, pc.centro(fc["caja"])[0], places=3)

    def test_bhkRigidBodyT_si_desplaza(self):
        """El par del de arriba: si la transformada nunca se aplicara, el test
        anterior pasaria sin probar nada."""
        fc = self._formas(nif_con_colision(CUBO, traslacion=(100.0, 0, 0),
                                           con_t=True))[0]
        self.assertAlmostEqual(100.0, pc.centro(fc["caja"])[0], places=2)


class FidelidadTests(unittest.TestCase):
    """--fiel compara COLOCACION entre dos NIF del mismo asset."""

    def fiel(self, a, b):
        """Calla el informe: lo que se evalua es el exit code, no el texto."""
        with contextlib.redirect_stdout(io.StringIO()):
            return comparar.modo_fiel(a, b)

    def test_un_archivo_contra_si_mismo_es_fiel(self):
        r = _archivo(nif_con_colision(CUBO), self)
        self.assertEqual(0, self.fiel(r, r))

    def test_una_colision_movida_reprueba(self):
        a = _archivo(nif_con_colision(CUBO, traslacion=(0, 0, 0), con_t=True),
                     self)
        b = _archivo(nif_con_colision(CUBO, traslacion=(40.0, 0, 0), con_t=True),
                     self)
        self.assertEqual(1, self.fiel(a, b))

    def test_un_desvio_menor_a_la_tolerancia_pasa(self):
        """La tolerancia existe porque el half-float y la ida y vuelta por
        Havok no son exactos. Si fuera cero, cualquier round-trip reprobaria."""
        a = _archivo(nif_con_colision(CUBO, con_t=True), self)
        b = _archivo(nif_con_colision(CUBO, traslacion=(0.01, 0, 0),
                                      con_t=True), self)
        self.assertEqual(0, self.fiel(a, b))

    def test_perder_la_colision_reprueba(self):
        """El modo de falla que vimos de verdad: PyNifly escribe el
        bhkCollisionObject y se come el cuerpo y la forma."""
        con = _archivo(nif_con_colision(CUBO), self)
        sin, _ = nif_sintetico.construir()
        self.assertEqual(1, self.fiel(con, _archivo(sin, self)))


class AutotestHonestoTests(unittest.TestCase):

    def test_carpeta_sin_nif_no_cuenta_como_validacion(self):
        with tempfile.TemporaryDirectory() as d:
            with contextlib.redirect_stdout(io.StringIO()) as salida:
                ok = pc.autotest(d)
        self.assertFalse(
            ok, "autotest devolvio True sin leer un solo archivo. Salida: "
                + salida.getvalue())


if __name__ == "__main__":
    unittest.main()
