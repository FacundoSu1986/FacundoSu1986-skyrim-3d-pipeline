# -*- coding: utf-8 -*-
"""enderezar_puro.py: lo del enderezado que se prueba sin Blender.

`enderezar.py` corre en Blender y NO se pudo correr al escribirlo: en este
entorno no hay Blender, asi que del lado del script lo unico verificado es la
sintaxis (compileall del CI) y que termine con `correr(main)`. Aca va la parte
que decide --ajustar la cuerda, proyectar, y negarse cuando la cadena parece
una curva de diseno--, con figuras de respuesta conocida.

El autotest del modulo ya cubre los casos; este test los vuelve a correr por
`unittest` para que el CI los vea, y agrega los dos que no son de la geometria
sino del CONTRATO: que el rechazo no devuelva puntos a medio tocar, y que el
tope se compare en las unidades que dice el docstring.
"""
import unittest

from _paths import preparar_path

preparar_path()

import enderezar_puro as ep  # noqa: E402


class AutotestTests(unittest.TestCase):

    def test_el_autotest_no_tiene_fallas(self):
        """Las comprobaciones se cuentan solas; 0 es lo unico que pasa."""
        self.assertEqual(0, ep.autotest())

    def test_hay_comprobaciones(self):
        """Cero comprobaciones no es exito: seria un autotest vacio."""
        self.assertGreater(len(_figuras()), 0)


def _figuras():
    return [p for p in dir(ep) if p.startswith("_")]


class ContratoTests(unittest.TestCase):

    def test_el_rechazo_no_devuelve_puntos_a_medio_tocar(self):
        """Un rechazo devuelve None, nunca una lista con los extremos movidos.

        Importa porque `enderezar.py` escribe lo que recibe: una lista a medio
        tocar entraria a la malla sin que nadie la mire.
        """
        arco = [(0.0, 0.0, 0.0), (1.0, -0.4, 0.0), (2.0, -0.5, 0.0),
                (3.0, -0.4, 0.0), (4.0, 0.0, 0.0)]   # flecha 0,5
        nuevos, info = ep.enderezar(arco, 0.05)
        self.assertIsNone(nuevos)
        self.assertIn("motivo", info)

    def test_aceptar_siempre_devuelve_la_misma_cantidad_de_puntos(self):
        puntos = [(0.0, 0.0, 0.0), (1.0, 0.01, 0.0), (2.0, -0.01, 0.0),
                  (3.0, 0.0, 0.0)]
        nuevos, _ = ep.enderezar(puntos, 0.05)
        self.assertEqual(len(puntos), len(nuevos))

    def test_el_tope_es_distancia_y_no_angulo(self):
        """El docstring promete una distancia perpendicular: se comprueba.

        Una cadena con los mismos 0,05 de apartamiento se acepta con tope 0,06
        y se rechaza con 0,04, sin importar cuan larga sea: si el tope fuera un
        angulo, alargar la cadena lo cambiaria.
        """
        for n in (5, 21):
            puntos = [(float(i), 0.05 if i % 2 else 0.0, 0.0)
                      for i in range(n)]
            self.assertIsNotNone(ep.enderezar(puntos, 0.06)[0], n)
            self.assertIsNone(ep.enderezar(puntos, 0.04)[0], n)

    def test_los_extremos_nunca_se_mueven(self):
        puntos = [(0.0, 0.0, 0.0), (1.0, 0.03, 0.0), (2.0, -0.03, 0.0),
                  (3.0, 0.03, 0.0), (4.0, 0.0, 0.0)]
        nuevos, _ = ep.enderezar(puntos, 0.1)
        self.assertEqual(puntos[0], nuevos[0])
        self.assertEqual(puntos[-1], nuevos[-1])


class EncadenarTests(unittest.TestCase):

    def test_un_camino_abierto_no_es_un_ciclo(self):
        """El bug que encontro el autotest, escrito como test.

        El grado maximo de un camino abierto tambien es 2. Confundirlo con un
        ciclo rechazaba la cadena, y con ella cualquier componente que la
        contuviera --o sea, no se enderezaba nada.
        """
        cadenas, motivos = ep.encadenar([(0, 1), (1, 2), (2, 3)])
        self.assertEqual([[0, 1, 2, 3]], cadenas)
        self.assertEqual([], motivos)

    def test_el_ciclo_de_verdad_si_se_rechaza(self):
        cadenas, motivos = ep.encadenar([(0, 1), (1, 2), (2, 3), (3, 0)])
        self.assertEqual([], cadenas)
        self.assertTrue(any("ciclo" in m for m in motivos))

    def test_el_orden_de_las_aristas_no_importa(self):
        esperado = [[0, 1, 2, 3]]
        for aristas in ([(0, 1), (1, 2), (2, 3)], [(2, 3), (0, 1), (1, 2)],
                        [(3, 2), (2, 1), (1, 0)]):
            with self.subTest(aristas=aristas):
                cadenas, _ = ep.encadenar(aristas)
                self.assertEqual(esperado, cadenas)

    def test_ningun_cruce_queda_dentro_de_un_camino(self):
        """LA PROPIEDAD QUE HACE SEGURO AL ENDEREZADO, sobre varias figuras.

        Un vertice de grado != 2 no puede ser interior a un camino. Si lo
        fuera, dos caminos lo pedirian en dos lugares distintos --cada uno su
        cuerda-- y el resultado dependeria del orden. Es el invariante que
        `encadenar` promete y el unico motivo por el que dos caminos pueden
        enderezarse sin coordinarse.
        """
        figuras = ([ (0,1), (1,2), (1,3) ],                      # una Y
                   [ (0,5), (5,1), (2,5), (5,3) ],                # una cruz
                   [ (0,1), (1,2), (2,3), (3,4), (2,5) ],         # cruce al medio
                   [ (0,1), (1,2), (3,4), (4,5) ],                # dos sueltos
                   [ (0,1), (1,2), (2,3), (3,0) ])                # un ciclo
        for aristas in figuras:
            grados = {}
            for a, b in aristas:
                grados[a] = grados.get(a, 0) + 1
                grados[b] = grados.get(b, 0) + 1
            caminos, _ = ep.encadenar(aristas)
            for camino in caminos:
                for v in camino[1:-1]:
                    with self.subTest(aristas=aristas, vertice=v):
                        self.assertEqual(
                            2, grados[v],
                            "el vertice %d es un cruce (grado %d) y quedo "
                            "DENTRO del camino %r" % (v, grados[v], camino))

    def test_cada_arista_pertenece_a_un_solo_camino(self):
        aristas = [(0, 1), (1, 2), (2, 3), (3, 4), (2, 5), (5, 6), (6, 7)]
        caminos, _ = ep.encadenar(aristas)
        vistas = [frozenset((c[i], c[i + 1])) for c in caminos
                  for i in range(len(c) - 1)]
        self.assertEqual(sorted(frozenset(a) for a in aristas), sorted(vistas))

    def test_las_aristas_no_se_repiten_entre_caminos(self):
        aristas = [(0, 1), (1, 2), (2, 0), (3, 4), (4, 5), (5, 3)]
        caminos, motivos = ep.encadenar(aristas)
        self.assertEqual([], caminos, "dos triangulos: los dos son ciclos")
        self.assertEqual(2, len(motivos), motivos)


if __name__ == "__main__":
    unittest.main()
