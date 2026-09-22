# -*- coding: utf-8 -*-
"""La howdah del mamut: geometria cerrada, atadura y controles.

El camino MEDIDO se prueba contra un NIF construido byte a byte por
`nif_sintetico`, con tres huesos de lomo en posiciones conocidas: ni un byte
de Bethesda, y la respuesta se sabe de antemano. Es el mismo criterio que
justifica tests/nif_sintetico.py para el parser.

Lo que NO cubre: la parte de Blender (`construir_en_blender`), que necesita
`bpy`. Lo que si cubre es todo lo que decide si la malla esta bien: la
geometria, el reparto de pesos y los once controles.
"""
import os
import tempfile
import unittest

from _paths import preparar_path

preparar_path()

import howdah_mamut  # noqa: E402
import nif_sintetico  # noqa: E402
import salud_malla  # noqa: E402

# Un lomo de prueba: tres huesos a lo largo de Y, el del medio mas alto.
LOMO = (("Lomo1", (0.0, -90.0, 180.0)),
        ("Lomo2", (0.0, 0.0, 190.0)),
        ("Lomo3", (0.0, 90.0, 182.0)))
NOMBRES_LOMO = [n for n, _p in LOMO]


def _esqueleto_sintetico(caso):
    """Escribe un NIF con los tres huesos de LOMO y devuelve la ruta."""
    datos, _esperado = nif_sintetico.construir_skinneado(
        huesos=tuple(n for n, _p in LOMO),
        traslaciones=tuple(p for _n, p in LOMO))
    fd, ruta = tempfile.mkstemp(suffix=".nif")
    with os.fdopen(fd, "wb") as fh:
        fh.write(datos)
    caso.addCleanup(lambda: os.path.exists(ruta) and os.unlink(ruta))
    return ruta


def _correr(*args):
    """Corre main() con esos argumentos y devuelve (exit, salida)."""
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            exit_code = howdah_mamut.main(list(args))
        except SystemExit as e:        # los errores de argumentos salen asi
            exit_code = e.code
    return exit_code, buf.getvalue()


class GeometriaCerradaTests(unittest.TestCase):
    """Backface culling: una malla abierta se ve invisible de atras."""

    def test_una_caja_es_cerrada(self):
        pos, tris = howdah_mamut.caja((1.0, 2.0, 3.0), (4.0, 5.0, 6.0))
        m = salud_malla.salud(pos, tris, 1)
        self.assertEqual(m["borde"], 0)
        self.assertEqual(m["winding"], 0)
        self.assertEqual(m["no_manifold"], 0)
        self.assertEqual(m["piezas"], 1)

    def test_el_toldo_es_cerrado(self):
        pos, tris = howdah_mamut.prisma([(-50.0, 100.0), (50.0, 100.0),
                                         (0.0, 140.0)], -77.0, 77.0)
        m = salud_malla.salud(pos, tris, 1)
        self.assertEqual(m["borde"], 0)
        self.assertEqual(m["winding"], 0)

    def test_toda_la_estructura_es_cerrada(self):
        lomo = {"y_centro": 0.0, "largo_tramo": 180.0, "z_lomo": 190.0,
                "x_medio": 0.0}
        e, _cotas = howdah_mamut.construir(howdah_mamut.Diseno(), lomo)
        m = salud_malla.salud(e.pos, e.tris, 1)
        self.assertEqual(m["borde"], 0)
        self.assertEqual(m["winding"], 0)

    def test_el_control_de_winding_detecta(self):
        """Una sola cara dada vuelta tiene que reprobar.

        Dar vuelta TODAS las caras no sirve para falsificar: una malla
        invertida entera esta orientada, solo que para adentro, y `winding`
        compara caras vecinas entre si. El defecto real es una cara suelta.
        """
        pos, tris = howdah_mamut.prisma([(-50.0, 100.0), (50.0, 100.0),
                                         (0.0, 140.0)], -77.0, 77.0)
        una_al_reves = list(tris)
        a, b, c = una_al_reves[0]
        una_al_reves[0] = (a, c, b)
        self.assertEqual(salud_malla.salud(pos, tris, 1)["winding"], 0)
        self.assertGreater(salud_malla.salud(pos, una_al_reves, 1)["winding"], 0)

    def test_piezas_que_apoyan_y_piezas_que_cuelgan(self):
        lomo = {"y_centro": 0.0, "largo_tramo": 180.0, "z_lomo": 190.0,
                "x_medio": 0.0}
        e, _cotas = howdah_mamut.construir(howdah_mamut.Diseno(), lomo)
        nombres = set(n for n, _m, _i0, _i1, _a in e.piezas)
        cuelgan = set(n for n, _m, _i0, _i1, apoya in e.piezas if not apoya)
        self.assertEqual(cuelgan, {"escalera_larguero", "escalera_peldano"})
        self.assertIn("tabla", nombres)
        self.assertLess(len(e.indices_que_apoyan()), len(e.pos))


class AtaduraTests(unittest.TestCase):
    """El reparto de pesos: nunca mas de 4 huesos por vertice."""

    def setUp(self):
        self.linea = howdah_mamut.polilinea(dict(LOMO), NOMBRES_LOMO)
        # El lomo de prueba tiene los huesos a distinta altura, asi que un
        # punto a la altura de uno no cae exactamente sobre el segmento del
        # otro. Para las cuentas exactas hace falta una linea RECTA: misma
        # forma, respuesta cerrada.
        self.recta = [("A", (0.0, -90.0, 190.0)),
                      ("B", (0.0, 0.0, 190.0)),
                      ("C", (0.0, 90.0, 190.0))]

    def test_ordena_por_y(self):
        self.assertEqual([n for n, _p in self.linea], NOMBRES_LOMO)

    def test_suma_uno_y_dos_huesos_como_maximo(self):
        for y in range(-200, 201, 7):
            w, _fuera, _exceso = howdah_mamut.pesos_en((0.0, float(y), 190.0),
                                                       self.linea)
            self.assertAlmostEqual(sum(w.values()), 1.0, places=9)
            self.assertLessEqual(len(w), howdah_mamut.MAX_HUESOS_POR_VERTICE)

    def test_el_peso_camina_con_el_punto(self):
        """A medida que el punto avanza, el peso pasa al hueso siguiente."""
        anterior = -1.0
        for y in range(-90, 91, 10):
            w, _fuera, _exceso = howdah_mamut.pesos_en((0.0, float(y), 190.0),
                                                       self.recta)
            peso_ultimo = w.get("C", 0.0)
            self.assertGreaterEqual(peso_ultimo, anterior)
            anterior = peso_ultimo
        self.assertAlmostEqual(anterior, 1.0, places=6)

    def test_el_peso_del_medio_es_uno_en_el_medio(self):
        w, _fuera, _exceso = howdah_mamut.pesos_en((0.0, 0.0, 190.0), self.recta)
        self.assertEqual(w, {"B": 1.0})

    def test_el_reparto_sobre_el_lomo_real_tambien_suma_uno(self):
        """Con la linea torcida del lomo, lo que importa es que sume 1."""
        for y in range(-120, 121, 5):
            w, _fuera, _exceso = howdah_mamut.pesos_en((0.0, float(y), 190.0),
                                                       self.linea)
            self.assertAlmostEqual(sum(w.values()), 1.0, places=9)

    def test_al_costado_no_es_fuera(self):
        """Un vertice a 75 cm del eje esta lejos, pero su proyeccion cae
        dentro del tramo: no esta colgado."""
        w, fuera, _exceso = howdah_mamut.pesos_en((52.0, 0.0, 190.0), self.linea)
        self.assertFalse(fuera)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=9)

    def test_pasado_el_extremo_es_fuera(self):
        _w, fuera, exceso = howdah_mamut.pesos_en((0.0, 140.0, 190.0), self.recta)
        self.assertTrue(fuera)
        self.assertAlmostEqual(exceso, 50.0, places=6)

    def test_antes_del_primer_hueso_tambien_es_fuera(self):
        _w, fuera, exceso = howdah_mamut.pesos_en((0.0, -130.0, 190.0),
                                                  self.recta)
        self.assertTrue(fuera)
        self.assertAlmostEqual(exceso, 40.0, places=6)

    def test_un_solo_hueso_es_rigido(self):
        linea = howdah_mamut.polilinea(dict(LOMO), ["Lomo2"])
        w, fuera, _exceso = howdah_mamut.pesos_en((0.0, 0.0, 190.0), linea)
        self.assertEqual(w, {"Lomo2": 1.0})
        self.assertFalse(fuera)

    def test_sin_huesos_no_hay_pesos(self):
        w, fuera, _exceso = howdah_mamut.pesos_en((0.0, 0.0, 0.0), [])
        self.assertEqual(w, {})
        self.assertTrue(fuera)


class MedidoTests(unittest.TestCase):
    """Contra el NIF sintetico: lo que se mide, se comprueba."""

    def test_lee_los_huesos_del_binario(self):
        huesos = howdah_mamut.leer_huesos(_esqueleto_sintetico(self))
        for nombre, (x, y, z) in LOMO:
            self.assertIn(nombre, huesos)
            self.assertAlmostEqual(huesos[nombre][0], x, places=2)
            self.assertAlmostEqual(huesos[nombre][1], y, places=2)
            self.assertAlmostEqual(huesos[nombre][2], z, places=2)

    def test_la_sugerencia_pone_la_columna_primero(self):
        """Rankea, no ordena: el orden a lo largo del lomo lo pone
        `polilinea`, que es quien lo necesita."""
        huesos = howdah_mamut.leer_huesos(_esqueleto_sintetico(self))
        sugeridos = [n for n, _p in howdah_mamut.sugerir_huesos_lomo(huesos)]
        self.assertEqual(set(sugeridos[:3]), set(NOMBRES_LOMO))

    def test_la_sugerencia_ordena_de_uno_solo_al_lomo(self):
        huesos = howdah_mamut.leer_huesos(_esqueleto_sintetico(self))
        sugeridos = [n for n, _p in howdah_mamut.sugerir_huesos_lomo(huesos)]
        self.assertEqual(howdah_mamut.polilinea(huesos, sugeridos[:3]),
                         howdah_mamut.polilinea(huesos, NOMBRES_LOMO))

    def test_medidas_del_lomo(self):
        huesos = howdah_mamut.leer_huesos(_esqueleto_sintetico(self))
        lomo, falta = howdah_mamut.medidas_del_lomo(huesos, NOMBRES_LOMO)
        self.assertEqual(falta, [])
        self.assertAlmostEqual(lomo["y_centro"], 0.0, places=6)
        self.assertAlmostEqual(lomo["largo_tramo"], 180.0, places=6)
        self.assertAlmostEqual(lomo["z_lomo"], 190.0, places=6)

    def test_un_hueso_que_no_existe_no_se_repone(self):
        huesos = howdah_mamut.leer_huesos(_esqueleto_sintetico(self))
        lomo, falta = howdah_mamut.medidas_del_lomo(huesos, ["Lomo1", "NoEsta"])
        self.assertIsNone(lomo)
        self.assertEqual(falta, ["NoEsta"])

    def test_corrida_medida_pasa(self):
        ruta = _esqueleto_sintetico(self)
        exit_code, salida = _correr("--esqueleto", ruta, "--huesos", *NOMBRES_LOMO)
        self.assertEqual(exit_code, 0, salida)
        self.assertIn("fallas: 0", salida)
        self.assertIn("[MEDIDO]", salida)

    def test_la_cubierta_apoya_sobre_el_lomo_medido(self):
        huesos = howdah_mamut.leer_huesos(_esqueleto_sintetico(self))
        lomo, _ = howdah_mamut.medidas_del_lomo(huesos, NOMBRES_LOMO)
        d = howdah_mamut.Diseno()
        e, cotas = howdah_mamut.construir(d, lomo)
        # la cara de abajo de la cubierta queda `despeje` por encima del lomo
        self.assertAlmostEqual(cotas["z_base"] - cotas["z_lomo"],
                               d.despeje * howdah_mamut.CM_A_U, places=6)
        # La cubierta y todo lo que se para sobre ella queda por encima del
        # lomo: nada lo atraviesa. Dos excepciones, y las dos por diseño: las
        # correas bajan por el flanco para abrazar el torso, y la escalera
        # cuelga hacia atras y hacia abajo.
        bajan = {"correa", "escalera_larguero", "escalera_peldano"}
        for nombre, _m, i0, i1, _a in e.piezas:
            if nombre not in bajan:
                self.assertGreater(min(p[2] for p in e.pos[i0:i1]),
                                   cotas["z_lomo"] - 1e-9, nombre)
        # y la escalera llega mas abajo que el lomo: si no, no sirve para
        # subir. Es lo que la delata como pieza que cuelga.
        escalera = [i for n, _m, i0, i1, a in e.piezas
                    if n == "escalera_peldano" for i in range(i0, i1)]
        self.assertLess(min(e.pos[i][2] for i in escalera), cotas["z_lomo"])

    def test_cubierta_mas_larga_que_el_tramo_falla(self):
        """El detector detecta: 300 cm de cubierta sobre 257 cm de columna."""
        ruta = _esqueleto_sintetico(self)
        exit_code, salida = _correr("--esqueleto", ruta, "--huesos",
                                    *NOMBRES_LOMO, "--largo-cm", "300")
        self.assertEqual(exit_code, 1)
        self.assertIn("largo_vs_tramo", salida)

    def test_hueso_inexistente_no_arranca(self):
        ruta = _esqueleto_sintetico(self)
        exit_code, salida = _correr("--esqueleto", ruta, "--huesos", "NoEsta")
        self.assertEqual(exit_code, 2)
        self.assertIn("no estan en el esqueleto", salida)

    def test_listar_huesos_muestra_los_nombres_reales(self):
        ruta = _esqueleto_sintetico(self)
        exit_code, salida = _correr("--esqueleto", ruta, "--listar-huesos")
        self.assertEqual(exit_code, 0)
        for nombre, _p in LOMO:
            self.assertIn(nombre, salida)


class DeclaradoTests(unittest.TestCase):
    """Sin vanilla: se puede bocetar, pero el informe dice que no midio."""

    def test_declarado_pasa_y_lo_dice(self):
        exit_code, salida = _correr("--declarar", "--alto-lomo-cm", "260")
        self.assertEqual(exit_code, 0, salida)
        self.assertIn("[DECLARADO]", salida)
        self.assertIn("NO MEDIDO", salida)

    def test_declarado_sin_alto_no_arranca(self):
        exit_code, salida = _correr("--declarar")
        self.assertEqual(exit_code, 2)
        self.assertIn("--alto-lomo-cm", salida)

    def test_sin_esqueleto_ni_declarar_no_arranca(self):
        exit_code, _salida = _correr("--ancho-cm", "150")
        self.assertEqual(exit_code, 2)

    def test_el_alto_declarado_mueve_la_cubierta(self):
        lomo = {"y_centro": 0.0, "largo_tramo": 180.0,
                "z_lomo": 260.0 * howdah_mamut.CM_A_U, "x_medio": 0.0}
        _e, cotas = howdah_mamut.construir(howdah_mamut.Diseno(), lomo)
        self.assertAlmostEqual(cotas["z_lomo"], 182.0, places=6)


class UnidadesTests(unittest.TestCase):
    """1 metro son 70 unidades de Skyrim [OBSERVED]."""

    def test_cien_cm_son_setenta_unidades(self):
        self.assertAlmostEqual(100.0 * howdah_mamut.CM_A_U, 70.0, places=9)

    def test_un_diseno_de_220_cm_ocupa_154_unidades(self):
        lomo = {"y_centro": 0.0, "largo_tramo": 180.0, "z_lomo": 190.0,
                "x_medio": 0.0}
        _e, cotas = howdah_mamut.construir(howdah_mamut.Diseno(), lomo)
        self.assertAlmostEqual(cotas["y"][1] - cotas["y"][0], 154.0, places=6)


class PresupuestoTests(unittest.TestCase):
    """El techo de triangulos es una medicion, no un numero redondo."""

    def test_la_howdah_entra_en_el_presupuesto_de_una_criatura(self):
        lomo = {"y_centro": 0.0, "largo_tramo": 180.0, "z_lomo": 190.0,
                "x_medio": 0.0}
        e, _cotas = howdah_mamut.construir(howdah_mamut.Diseno(), lomo)
        self.assertLess(len(e.tris), howdah_mamut.PRESUPUESTO_GRUPO)
        self.assertLess(len(e.pos), howdah_mamut.MAX_VERTICES_SHAPE)

    def test_un_presupuesto_chico_reprueba(self):
        ruta = _esqueleto_sintetico(self)
        exit_code, salida = _correr("--esqueleto", ruta, "--huesos",
                                    *NOMBRES_LOMO, "--presupuesto", "100")
        self.assertEqual(exit_code, 1)
        self.assertIn("triangulos", salida)


if __name__ == "__main__":
    unittest.main()
