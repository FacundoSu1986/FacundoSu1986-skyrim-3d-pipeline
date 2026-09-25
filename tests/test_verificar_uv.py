# -*- coding: utf-8 -*-
"""La V va INVERTIDA en el NIF, y hay que comprobarlo sobre el archivo.

Un NIF guarda la V con el origen arriba de la imagen; un OBJ y Blender con el
origen abajo. Un conversor que la copie tal cual deja todo el mapeo espejado en
vertical, sin dar error: el archivo se escribe bien y el juego lo carga.

En el hacha de Tencent el sintoma se confundio con "el horneado salio mal", que
es el paso mas caro de rehacer.
"""
import os
import subprocess
import sys
import tempfile
import unittest

from _paths import preparar_path

preparar_path()

import censo_nif  # noqa: E402
import nif_sintetico  # noqa: E402
import verificar_uv  # noqa: E402

CUADRADO = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0),
            (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
UV_FUENTE = {0: {(0.0, 0.0)}, 1: {(1.0, 0.1)},
             2: {(1.0, 0.9)}, 3: {(0.0, 1.0)}}
UV_LISTA = [(0.0, 0.0), (1.0, 0.1), (1.0, 0.9), (0.0, 1.0)]

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "skills", "modelo-ia-a-skyrim", "scripts", "verificar_uv.py")


def _escalado(f=80.0):
    return [(x * f, y * f, z * f) for x, y, z in CUADRADO]


def _archivo(datos, sufijo):
    fd, ruta = tempfile.mkstemp(suffix=sufijo)
    with os.fdopen(fd, "wb") as fh:
        fh.write(datos)
    return ruta


def _obj_con_uv(pos, tris, uvs):
    """Un OBJ con una vt por v, en el mismo orden."""
    lineas = (["v %f %f %f" % p for p in pos]
              + ["vt %f %f" % uv for uv in uvs]
              + ["f %d/%d %d/%d %d/%d" % (a + 1, a + 1, b + 1, b + 1,
                                          c + 1, c + 1) for a, b, c in tris])
    return _archivo(("\n".join(lineas) + "\n").encode("ascii"), ".obj")


# Cuartos de vuelta sobre cada eje. Un conversor que rote el modelo tiene que
# dejar de aparear: tolerar la escala y la traslacion es a proposito, la
# rotacion no.
ROTACIONES = (("X", lambda p: (p[0], -p[2], p[1])),
              ("Y", lambda p: (p[2], p[1], -p[0])),
              ("Z", lambda p: (-p[1], p[0], p[2])))


class ReglaTests(unittest.TestCase):
    """REGLA: la V del NIF es el complemento de la del origen."""

    def test_el_conversor_correcto_pasa(self):
        votos, _ = verificar_uv.comparar(
            CUADRADO, UV_FUENTE, _escalado(),
            [(u, 1.0 - v) for u, v in UV_LISTA])
        self.assertGreater(votos["invertida"], 0)
        self.assertEqual(votos["igual"], 0)
        self.assertFalse(verificar_uv.juzgar(votos)[0])

    def test_copiar_la_v_tal_cual_reprueba(self):
        votos, _ = verificar_uv.comparar(CUADRADO, UV_FUENTE, _escalado(),
                                         UV_LISTA)
        self.assertGreater(votos["igual"], 0)
        fallas = verificar_uv.juzgar(votos)[0]
        self.assertTrue(fallas)
        self.assertIn("v_invertida", fallas[0])

    def test_escalar_y_trasladar_no_rompen_el_apareo(self):
        """Es la tolerancia que hace falta: el conversor escala el modelo a
        tamano de arma. Queda afirmado para que nadie la saque sin querer."""
        movido = [(x * 80.0 + 1000.0, y * 80.0 - 7.0, z * 80.0)
                  for x, y, z in CUADRADO]
        votos, _ = verificar_uv.comparar(
            CUADRADO, UV_FUENTE, movido,
            [(u, 1.0 - v) for u, v in UV_LISTA])
        self.assertGreater(votos["invertida"], 0)

    def test_los_vertices_de_v_medio_no_votan(self):
        """Cerca de v=0,5 invertir no cambia nada: contarlos seria contar
        ruido a favor de cualquiera de las dos respuestas."""
        medio = dict((i, {(float(i % 2), 0.5)}) for i in range(4))
        votos, _ = verificar_uv.comparar(
            CUADRADO, medio, _escalado(),
            [(float(i % 2), 0.5) for i in range(4)])
        self.assertEqual(votos["apareados"], 0)
        fallas = verificar_uv.juzgar(votos)[0]
        # Se afirma la RAZON, no solo que repruebe: con 0 votos de cada lado
        # la otra condicion (igual >= invertida) tambien es cierta, asi que
        # una asercion sobre la verdad a secas pasaba aunque se borrara la
        # guarda de "cero comprobaciones". Lo pesco mutar el codigo.
        self.assertTrue(fallas)
        self.assertIn("cero vertices comparables", fallas[0])

    def test_sin_uv_en_el_origen_reprueba(self):
        """Cero comprobaciones no es exito."""
        votos, _ = verificar_uv.comparar(CUADRADO, {}, _escalado(), UV_LISTA)
        self.assertEqual(votos["apareados"], 0)
        fallas = verificar_uv.juzgar(votos)[0]
        self.assertTrue(fallas)
        self.assertIn("cero vertices comparables", fallas[0])

    def test_una_u_que_no_coincide_se_informa_y_no_vota(self):
        votos, notas = verificar_uv.comparar(
            CUADRADO, UV_FUENTE, _escalado(),
            [(0.42, 1.0 - v) for _u, v in UV_LISTA])
        self.assertEqual(votos["apareados"], 0)
        self.assertTrue(any("U no coincide" in n for n in notas))


class VariasPiezasTests(unittest.TestCase):
    """Un NIF exportado casi nunca es UNA malla: el exportador la reparte en
    un shape por material, todos en el mismo marco. El conversor escala el
    modelo ENTERO, no cada pieza, asi que las piezas se normalizan por la caja
    de su UNION. Normalizada cada una por la suya, en el hacha de Filo Celeste
    (dos piezas) no apareaba ni un vertice y reprobaba por "cero vertices
    comparables"; con la caja de la union, 12.898 invertidas y 0 iguales.

    El fixture es una barra cerrada de 36 triangulos partida en dos tubos de
    18 (nif_sintetico.barra_en_piezas), con coordenadas irregulares para que
    ni el metodo viejo ni una rotacion apareen de casualidad.
    """

    def setUp(self):
        self.pos, self.tris, self.uvs = nif_sintetico.barra_cerrada()
        self.uv_obj = dict((i, {uv}) for i, uv in enumerate(self.uvs))

    def _piezas(self, invertir_v=True):
        """Las dos piezas como las devuelve censo_nif.geometria(con_uv=True):
        escaladas x80 y trasladadas, como las deja el conversor."""
        return [{"nombre": p["nombre"], "pos": p["pos"], "uv": p["uvs"]}
                for p in nif_sintetico.barra_en_piezas(
                    80.0, (1000.0, -7.0, 0.0), invertir_v=invertir_v)]

    def test_la_premisa_cada_pieza_por_su_caja_no_aparea(self):
        """El metodo viejo sobre este fixture. Si apareara algo, pasar el
        test de abajo no probaria el arreglo."""
        for p in self._piezas():
            votos, _ = verificar_uv.comparar(self.pos, self.uv_obj,
                                             p["pos"], p["uv"])
            self.assertEqual(votos["apareados"], 0, p["nombre"])

    def test_las_dos_piezas_invertidas_votan_todas(self):
        votos, _ = verificar_uv.comparar_piezas(self.pos, self.uv_obj,
                                                self._piezas())
        # 12 vertices por pieza: el anillo del corte esta escrito en las dos,
        # y vota en las dos.
        self.assertEqual(votos["invertida"], 24)
        self.assertEqual(votos["igual"], 0)
        self.assertEqual(verificar_uv.juzgar(votos)[0], [])

    def test_las_dos_piezas_sin_invertir_reprueban(self):
        """La caja de la union no puede volver el control un sello: el
        conversor que copia la V tal cual sigue reprobando."""
        votos, _ = verificar_uv.comparar_piezas(self.pos, self.uv_obj,
                                                self._piezas(False))
        self.assertEqual(votos["igual"], 24)
        self.assertEqual(votos["invertida"], 0)
        fallas = verificar_uv.juzgar(votos)[0]
        self.assertTrue(fallas and "REGLA v_invertida" in fallas[0], fallas)

    def test_una_rotacion_sigue_sin_aparear(self):
        for eje, rotar in ROTACIONES:
            with self.subTest(eje=eje):
                piezas = [dict(p, pos=[rotar(q) for q in p["pos"]])
                          for p in self._piezas()]
                votos, _ = verificar_uv.comparar_piezas(
                    self.pos, self.uv_obj, piezas)
                self.assertEqual(votos["apareados"], 0)
                fallas = verificar_uv.juzgar(votos)[0]
                self.assertTrue(fallas and
                                "cero vertices comparables" in fallas[0],
                                fallas)

    def test_una_pieza_sin_uv_cuenta_igual_para_la_caja(self):
        """La pieza sin UV tambien es parte del modelo que el conversor
        escalo. Sacarla de la caja achica la caja, y la otra pieza deja de
        aparear."""
        piezas = self._piezas()
        piezas[1]["uv"] = None
        votos, notas = verificar_uv.comparar_piezas(self.pos, self.uv_obj,
                                                    piezas)
        self.assertEqual(votos["invertida"], 12)
        self.assertTrue(any("no declara UV" in n for n in notas), notas)

    def test_nif_de_dos_piezas_por_linea_de_comandos(self):
        ruta_obj = _obj_con_uv(self.pos, self.tris, self.uvs)
        bien, _ = nif_sintetico.construir_estatico_piezas(
            nif_sintetico.barra_en_piezas(80.0, (1000.0, -7.0, 0.0),
                                          invertir_v=True))
        mal, _ = nif_sintetico.construir_estatico_piezas(
            nif_sintetico.barra_en_piezas(80.0, (1000.0, -7.0, 0.0)))
        r_bien = _archivo(bien, ".nif")
        r_mal = _archivo(mal, ".nif")
        try:
            p = subprocess.run([sys.executable, SCRIPT, ruta_obj, r_bien],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("invertida 24, igual 0", p.stdout)
            p = subprocess.run([sys.executable, SCRIPT, ruta_obj, r_mal],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("REGLA v_invertida", p.stdout)
        finally:
            for r in (ruta_obj, r_bien, r_mal):
                os.unlink(r)


class LecturaUvTests(unittest.TestCase):
    """censo_nif.geometria(con_uv=True) contra lo que se escribio."""

    def test_recupera_las_uv(self):
        uvs = [(0.0, 0.0), (0.25, 0.5), (0.5, 0.75), (0.75, 1.0)]
        datos, esperado = nif_sintetico.construir_estatico(
            CUADRADO, [(0, 1, 2), (0, 2, 3)], uvs=uvs)
        ruta = _archivo(datos, ".nif")
        try:
            g = censo_nif.Nif(ruta).geometria(con_uv=True)[0]
            self.assertNotIn("error", g)
            self.assertEqual([(round(u, 3), round(v, 3)) for u, v in g["uv"]],
                             [(round(u, 3), round(v, 3))
                              for u, v in esperado["uvs"]])
        finally:
            os.unlink(ruta)

    def test_sin_el_bit_de_uv_devuelve_none_y_no_basura(self):
        """El bit de presencia es (vdesc >> 44) & 0x2. Sin el, leer en
        UV_OFFSET devolveria dos half-floats de lo que haya ahi."""
        datos, _ = nif_sintetico.construir_estatico(CUADRADO,
                                                    [(0, 1, 2), (0, 2, 3)])
        ruta = _archivo(datos, ".nif")
        try:
            self.assertIsNone(censo_nif.Nif(ruta).geometria(con_uv=True)[0]["uv"])
        finally:
            os.unlink(ruta)

    def test_las_dos_lecturas_de_uv_del_repo_coinciden(self):
        """censo_nif (la semilla de la skill) y census/parser_uv leen el mismo
        campo. Si una se mueve, esto lo dice."""
        import parser_uv
        from parser_nif import Nif as NifCenso
        uvs = [(0.1, 0.2), (0.3, 0.4), (0.5, 0.6), (0.7, 0.8)]
        datos, _ = nif_sintetico.construir_estatico(
            CUADRADO, [(0, 1, 2), (0, 2, 3)], uvs=uvs)
        ruta = _archivo(datos, ".nif")
        try:
            a = censo_nif.Nif(ruta).geometria(con_uv=True)[0]
            b = parser_uv.geometria(NifCenso(ruta))[0]
            self.assertEqual(a["uv"], b["uv"])
            self.assertEqual(a["pos"], b["pos"])
            self.assertEqual(a["tris"], b["tris"])
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
        self.assertEqual(self._correr("a.nif", "b.obj")[0], 2)
        self.assertEqual(self._correr("a.obj", "b.nif", "c")[0], 2)

    def test_par_correcto_sale_cero_y_par_sin_invertir_sale_uno(self):
        tris = [(0, 1, 2), (0, 2, 3)]
        obj = "\n".join(
            ["v %f %f %f" % p for p in CUADRADO]
            + ["vt %f %f" % uv for uv in UV_LISTA]
            + ["f %d/%d %d/%d %d/%d" % (a + 1, a + 1, b + 1, b + 1,
                                        c + 1, c + 1) for a, b, c in tris])
        ruta_obj = _archivo((obj + "\n").encode("ascii"), ".obj")
        bien, _ = nif_sintetico.construir_estatico(
            _escalado(), tris, uvs=[(u, 1.0 - v) for u, v in UV_LISTA])
        mal, _ = nif_sintetico.construir_estatico(_escalado(), tris,
                                                  uvs=UV_LISTA)
        r_bien = _archivo(bien, ".nif")
        r_mal = _archivo(mal, ".nif")
        try:
            codigo, salida = self._correr(ruta_obj, r_bien)
            self.assertEqual(codigo, 0, salida)
            codigo, salida = self._correr(ruta_obj, r_mal)
            self.assertEqual(codigo, 1, salida)
            self.assertIn("REGLA v_invertida", salida)
        finally:
            for r in (ruta_obj, r_bien, r_mal):
                os.unlink(r)


if __name__ == "__main__":
    unittest.main()
