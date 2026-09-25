# -*- coding: utf-8 -*-
"""montaje_puro.py: lo de los pasos 5 y 6 que se prueba sin Blender.

`montar.py` corre en Blender y se falsifica con el centurion vanilla
(`montar.py -- --falsificar`): las 15 piezas corridas, giradas y escaladas
vuelven a su lugar con un error maximo de 0,0002 unidades. Aca va la matematica y los
controles, con valores escritos a mano.
"""
import math
import unittest

from _paths import preparar_path

preparar_path()

import montaje_puro as mp  # noqa: E402


def _cerca(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


class SegmentoTests(unittest.TestCase):

    def test_los_extremos_caen_en_los_huesos(self):
        for escala in ("eje", "uniforme"):
            m, _n = mp.ajuste_segmento((0, 0, 0), (0, 0, 2), (10, 5, 3),
                                       (10, 9, 3), escala)
            a, b = mp.aplicar(m, [(0, 0, 0), (0, 0, 2)])
            self.assertTrue(_cerca(a, (10, 5, 3)) and _cerca(b, (10, 9, 3)),
                            escala)

    def test_eje_conserva_el_grosor_y_uniforme_lo_escala(self):
        """El largo lo ponen las animaciones; el grosor es diseno."""
        lado = (1.0, 0.0, 1.0)
        centro = (10.0, 7.0, 3.0)
        m, _n = mp.ajuste_segmento((0, 0, 0), (0, 0, 2), (10, 5, 3),
                                   (10, 9, 3), "eje")
        self.assertAlmostEqual(
            1.0, math.dist(mp.aplicar(m, [lado])[0], centro))
        m, _n = mp.ajuste_segmento((0, 0, 0), (0, 0, 2), (10, 5, 3),
                                   (10, 9, 3), "uniforme")
        self.assertAlmostEqual(
            2.0, math.dist(mp.aplicar(m, [lado])[0], centro))

    def test_frente_deshace_el_giro_alrededor_del_eje(self):
        girado = mp._mat3_vec(mp.rotacion_eje((0, 0, 1), 1.1), (0, 1, 0))
        m, _n = mp.ajuste_segmento((0, 0, 0), (0, 0, 1), (0, 0, 0),
                                   (0, 0, 1), "uniforme", frente=girado)
        self.assertTrue(_cerca(mp.aplicar(m, [girado])[0], (0, 1, 0)))

    def test_una_direccion_paralela_al_eje_es_error(self):
        """Medido en --falsificar: el pie (largo en Y) volvio corrido 26
        unidades cuando esto era una nota."""
        with self.assertRaises(mp.MontajeError) as ctx:
            mp.ajuste_segmento((0, 0, 0), (0, 1, 0), (0, 0, 0), (0, 2, 0),
                               "uniforme", frente=(0, 1, 0))
        self.assertIn("arriba", str(ctx.exception))
        m, _n = mp.ajuste_segmento((0, 0, 0), (0, 1, 0), (0, 0, 0), (0, 2, 0),
                                   "uniforme", frente=(0, 0, 1),
                                   frente_destino=(0, 0, 1))
        self.assertTrue(_cerca(mp.aplicar(m, [(0, 1, 0)])[0], (0, 2, 0)))

    def test_segmento_de_largo_cero_es_error(self):
        with self.assertRaises(mp.MontajeError):
            mp.ajuste_segmento((1, 1, 1), (1, 1, 1), (0, 0, 0), (0, 0, 1))

    def test_segmentos_opuestos(self):
        m, _n = mp.ajuste_segmento((0, 0, 0), (0, 0, 1), (0, 0, 0),
                                   (0, 0, -1), "uniforme")
        self.assertTrue(_cerca(mp.aplicar(m, [(0, 0, 1)])[0], (0, 0, -1)))


class CajaTests(unittest.TestCase):

    PARTE = ((0.0, 0.0, 0.0), (1.0, 2.0, 4.0))
    VANILLA = ((10.0, 10.0, 10.0), (12.0, 16.0, 14.0))

    def _dims(self, m):
        c = mp.caja(mp.aplicar(m, list(self.PARTE)))
        return tuple(round(c[1][i] - c[0][i], 9) for i in range(3))

    def test_contener_llenar_y_ejes(self):
        """Razones 2, 3 y 1: contener toma 1, llenar 3, ejes una por eje."""
        m, _n = mp.ajuste_caja(self.PARTE, self.VANILLA, "contener")
        self.assertEqual((1.0, 2.0, 4.0), self._dims(m))
        m, _n = mp.ajuste_caja(self.PARTE, self.VANILLA, "llenar")
        self.assertEqual((3.0, 6.0, 12.0), self._dims(m))
        m, notas = mp.ajuste_caja(self.PARTE, self.VANILLA, "ejes")
        self.assertEqual((2.0, 6.0, 4.0), self._dims(m))
        self.assertTrue(any("deforma" in n for n in notas))

    def test_los_centros_coinciden(self):
        m, _n = mp.ajuste_caja(self.PARTE, self.VANILLA, "llenar")
        self.assertTrue(_cerca(mp.aplicar(m, [(0.5, 1.0, 2.0)])[0],
                               (11.0, 13.0, 12.0)))


class EspejoTests(unittest.TestCase):

    def test_el_espejo_invierte_y_el_montaje_no_lo_esconde(self):
        """Mesh.transform de Blender NO invierte las caras con un espejo
        (medido con 4.4.1): montar.py lo hace si el determinante es negativo."""
        self.assertLess(mp.determinante(mp.espejo_x()), 0)
        self.assertEqual([(-1.0, 2.0, 3.0)],
                         mp.aplicar(mp.espejo_x(), [(1.0, 2.0, 3.0)]))
        m, _n = mp.ajuste_segmento((0, 0, 0), (0, 0, 2), (1, 1, 1), (1, 1, 5))
        self.assertLess(mp.determinante(mp.componer(m, mp.espejo_x())), 0)
        self.assertGreater(mp.determinante(m), 0)


class PesosTests(unittest.TestCase):

    DONANTE = [(0.0, 0.0, 0.0), (0.0, 0.0, 10.0)]
    PESOS = [{"Muslo": 1.0, "SBP_32_BODY": 1.0},
             {"Pantorrilla": 0.6, "Pie": 0.4, "SBP_32_BODY": 1.0}]

    def test_copia_del_mas_cercano(self):
        p, d = mp.pesos_por_vecino([(0.1, 0, 1), (0, 0.2, 9)], self.DONANTE,
                                   self.PESOS)
        self.assertEqual({"Muslo": 1.0, "SBP_32_BODY": 1.0}, p[0])
        self.assertEqual({"Pantorrilla": 0.6, "Pie": 0.4, "SBP_32_BODY": 1.0},
                         p[1])
        self.assertAlmostEqual(math.hypot(0.1, 1.0), d[0])

    def test_con_y_sin_numpy_dan_lo_mismo(self):
        pts = [(x * 0.37, (x * 7) % 5 * 0.9, (x * 3) % 11 * 1.1)
               for x in range(60)]
        donante = [(x * 0.5, (x * 3) % 7 * 1.0, (x * 5) % 9 * 1.2)
                   for x in range(40)]
        con = mp.vecinos(pts, donante)
        guardado, mp.np = mp.np, None
        try:
            sin = mp.vecinos(pts, donante)
        finally:
            mp.np = guardado
        self.assertEqual(con[0], sin[0])
        for a, b in zip(con[1], sin[1]):
            self.assertAlmostEqual(a, b)

    def test_la_copia_no_pisa_al_donante(self):
        p, _d = mp.pesos_por_vecino([(0, 0, 0)], self.DONANTE, self.PESOS)
        p[0]["Muslo"] = 0.1
        self.assertEqual(1.0, self.PESOS[0]["Muslo"])


class ControlesTests(unittest.TestCase):

    def test_pieza_sana(self):
        f, _n = mp.controles_pesos([{"Muslo": 1.0, "SBP_32_BODY": 1.0}] * 4,
                                   ["Muslo"])
        self.assertEqual([], f)

    def test_cada_regla_reprueba_algo(self):
        casos = [
            ("REGLA huesos", [{"Pie": 1.0, "SBP_32_BODY": 1.0}], ["Pie",
                                                                  "Dedo"]),
            ("REGLA suma", [{"Pie": 0.7, "SBP_32_BODY": 1.0}], ["Pie"]),
            ("REGLA max4", [dict([("H%d" % i, 0.2) for i in range(5)] +
                                 [("SBP_32_BODY", 1.0)])],
             ["H%d" % i for i in range(5)]),
            ("REGLA particion", [{"Pie": 1.0}], ["Pie"]),
            ("REGLA particion", [{"Pie": 1.0, "SBP_32_BODY": 1.0,
                                  "SBP_30_HEAD": 1.0}], ["Pie"]),
        ]
        for regla, pesos, huesos in casos:
            f, _n = mp.controles_pesos(pesos, huesos)
            self.assertTrue(any(regla in x for x in f), (regla, f))

    def test_sin_vertices_no_pasa(self):
        f, _n = mp.controles_pesos([], ["Pie"])
        self.assertTrue(f)


class PlanTests(unittest.TestCase):

    def test_un_plan_bueno(self):
        plan = {"donante": "v.nif", "salida": "n.nif", "piezas": {
            "A": {"parte": "a.glb", "modo": "segmento", "desde": [0, 0, 0],
                  "hasta": [0, 0, 1], "huesos": ["NPC A", [0, 0, 9]],
                  "arriba": [0, 0, 1], "espejar": True},
            "B": {"parte": "b.blend", "objeto": "Cabeza", "modo": "caja"}}}
        self.assertEqual([], mp.validar_plan(plan))

    def test_junta_todos_los_problemas(self):
        plan = {"donante": "v.nif", "salida": "v.nif", "piezas": {
            "A": {"parte": "a.obj", "modo": "segmento", "desde": [0, 0, 0],
                  "hasta": [0, 0, 1], "huesos": ["x", "y"],
                  "frente": [0, 1, 0], "arriba": [0, 0, 1]},
            "B": {"parte": "b.obj", "modo": "caja", "escla": "llenar"}}}
        p = mp.validar_plan(plan)
        self.assertEqual(3, len(p), p)
        self.assertTrue(any("mismo archivo" in x for x in p))
        self.assertTrue(any("una sola" in x for x in p))
        self.assertTrue(any("'escla'" in x for x in p))

    def test_el_autotest_pasa(self):
        self.assertEqual(0, mp.autotest())


if __name__ == "__main__":
    unittest.main()
