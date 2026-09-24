# -*- coding: utf-8 -*-
"""La malla no se puede ABRIR al decimarla (issue del hacha de Tencent).

El defecto que estos tests atajan no dio ni un error: el GLB de origen era una
malla cerrada de 1.500.000 triangulos y la que llego al juego tenia el 35 % de
sus aristas al aire. Se veia como "al arma le faltan partes".

Los tests estan escritos para enumerar la familia --toda forma de romper una
malla-- y no el caso puntual que ya encontramos, porque el mismo error entra
por cualquier paso que toque geometria: decimar, soldar, exportar, reescalar.
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
import salud_malla  # noqa: E402

CUBO_POS = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
            (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
CUBO_TRIS = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
             (0, 1, 5), (0, 5, 4), (2, 3, 7), (2, 7, 6),
             (1, 2, 6), (1, 6, 5), (0, 4, 7), (0, 7, 3)]

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "skills", "modelo-ia-a-skyrim", "scripts", "salud_malla.py")


def _archivo(datos, sufijo=".nif"):
    fd, ruta = tempfile.mkstemp(suffix=sufijo)
    with os.fdopen(fd, "wb") as fh:
        fh.write(datos)
    return ruta


def _obj(pos, tris):
    lineas = ["v %f %f %f" % p for p in pos]
    lineas += ["f %d %d %d" % (a + 1, b + 1, c + 1) for a, b, c in tris]
    return _archivo(("\n".join(lineas) + "\n").encode("ascii"), ".obj")


class MedicionTests(unittest.TestCase):
    """Los cinco numeros, sobre una figura cuya respuesta se conoce."""

    def test_cubo_cerrado(self):
        m = salud_malla.salud(CUBO_POS, CUBO_TRIS, 1)
        self.assertEqual(m["borde"], 0)
        self.assertEqual(m["aristas"], 18)
        self.assertEqual(m["piezas"], 1)
        self.assertEqual(m["no_manifold"], 0)
        self.assertEqual(m["winding"], 0)
        self.assertEqual(m["soldados"], 8)

    def test_soldar_primero_o_no_medir_nada(self):
        """Con los vertices partidos por costura, contar por INDICE dice que
        todo es borde. Soldando por posicion es el mismo cubo cerrado.

        Es la confusion que hizo leer 382 piezas donde habia 1.
        """
        pos, tris = [], []
        for a, b, c in CUBO_TRIS:
            base = len(pos)
            pos.extend([CUBO_POS[a], CUBO_POS[b], CUBO_POS[c]])
            tris.append((base, base + 1, base + 2))
        m = salud_malla.salud(pos, tris, 1)
        self.assertEqual(m["verts"], 36)
        self.assertEqual(m["soldados"], 8)
        self.assertEqual(m["borde"], 0)
        self.assertEqual(m["piezas"], 1)

    def test_cada_rotura_mueve_su_propio_numero(self):
        """Enumera la familia: cada forma de romper una malla tiene que mover
        la medida que le corresponde y NO las otras."""
        base = salud_malla.salud(CUBO_POS, CUBO_TRIS, 1)
        casos = [
            ("agujero", CUBO_POS, CUBO_TRIS[2:], "borde"),
            ("dos piezas",
             CUBO_POS + [(x + 10, y, z) for x, y, z in CUBO_POS],
             CUBO_TRIS + [(a + 8, b + 8, c + 8) for a, b, c in CUBO_TRIS],
             "piezas"),
            ("triangulo invertido", CUBO_POS,
             [tuple(reversed(CUBO_TRIS[0]))] + CUBO_TRIS[1:], "winding"),
            ("arista con tres caras", CUBO_POS + [(0.5, 0.5, 2.0)],
             CUBO_TRIS + [(0, 1, 8)], "no_manifold"),
        ]
        for nombre, pos, tris, campo in casos:
            with self.subTest(rotura=nombre):
                m = salud_malla.salud(pos, tris, 1)
                self.assertGreater(
                    m[campo], base[campo],
                    "%s no movio %s" % (nombre, campo))

    def test_el_degenerado_no_cuenta_como_triangulo(self):
        m = salud_malla.salud(CUBO_POS, CUBO_TRIS + [(0, 0, 1)], 1)
        self.assertEqual(m["degenerados"], 1)
        self.assertEqual(m["tris"], len(CUBO_TRIS))

    def test_posiciones_no_finitas_no_revientan(self):
        """El corpus tiene shapes con NaN. No puede tirar excepcion ni contar
        esos vertices como si fueran un punto."""
        pos = CUBO_POS + [(float("nan"), 0.0, 0.0)]
        m = salud_malla.salud(pos, CUBO_TRIS + [(0, 1, 8)], 1)
        self.assertIsNotNone(m)
        self.assertEqual(m["fuera_de_rango"], 1)

    def test_indice_negativo_no_indexa_desde_el_final(self):
        """`w[-2]` es un vertice VALIDO para Python: un indice negativo que
        nadie resolvio no revienta, mide OTRA malla. La guarda de salud() es
        `i < 0 or i >= len(w)` y el agujero era la segunda mitad nada mas.
        (-1,-2,-3) son los tres ultimos vertices del cubo: una cara que
        existe, y contada como si fuera un triangulo nuevo daria bordes de
        sobra. Fuera de rango es la unica lectura honesta de un indice que el
        llamador no resolvio."""
        m = salud_malla.salud(CUBO_POS, [(-1, -2, -3)] + CUBO_TRIS, 1)
        self.assertEqual(m["fuera_de_rango"], 1)
        self.assertEqual(m["tris"], len(CUBO_TRIS))
        self.assertEqual(m["borde"], 0)

    def test_el_minimo_de_triangulos_descarta_lo_que_no_dice_nada(self):
        """Un cartel de dos triangulos tiene el 100 % de borde y esta bien."""
        self.assertIsNone(salud_malla.salud(CUBO_POS, CUBO_TRIS[:2]))


class ReglaTests(unittest.TestCase):
    """REGLA: el numero de aristas de borde no puede aumentar."""

    def _t(self, pos, tris):
        return salud_malla.total([salud_malla.salud(pos, tris, 1)])

    def test_cerrada_a_rota_reprueba(self):
        cerrada = self._t(CUBO_POS, CUBO_TRIS)
        rota = self._t(CUBO_POS, CUBO_TRIS[2:])
        fallas, _ = salud_malla.comparar(cerrada, rota)
        self.assertTrue(fallas)

    def test_la_misma_malla_pasa(self):
        a = self._t(CUBO_POS, CUBO_TRIS)
        fallas, _ = salud_malla.comparar(a, self._t(CUBO_POS, CUBO_TRIS))
        self.assertFalse(fallas)

    def test_abierta_que_se_cierra_pasa(self):
        """El 85 % del corpus vanilla es abierto a proposito. Reducir el borde
        es valido; la regla es relacional, no absoluta."""
        abierta = self._t(CUBO_POS, CUBO_TRIS[2:])
        menos = self._t(CUBO_POS, CUBO_TRIS)
        fallas, _ = salud_malla.comparar(abierta, menos)
        self.assertFalse(fallas)

    def test_abierta_que_se_abre_mas_reprueba(self):
        fallas, _ = salud_malla.comparar(self._t(CUBO_POS, CUBO_TRIS[2:]),
                                         self._t(CUBO_POS, CUBO_TRIS[4:]))
        self.assertTrue(fallas)

    def test_sin_nada_que_medir_reprueba(self):
        """Cero comprobaciones no es exito."""
        fallas, _ = salud_malla.comparar(self._t(CUBO_POS, CUBO_TRIS), None)
        self.assertTrue(fallas)
        fallas, _ = salud_malla.comparar(None, None)
        self.assertTrue(fallas)

    # --- el caso que encontro el review de Codex (P1 sobre #40) --------------

    def _grid(self, n):
        pos = [(float(i), float(j), 0.0) for i in range(n) for j in range(n)]
        tris = []
        for i in range(n - 1):
            for j in range(n - 1):
                a = i * n + j
                tris.append((a, a + 1, a + n))
                tris.append((a + 1, a + n + 1, a + n))
        return pos, tris

    def _sueltos(self, k):
        pos, tris = [], []
        for q in range(k):
            b = q * 3
            pos += [(float(q * 10), 0.0, 0.0), (float(q * 10) + 1.0, 0.0, 0.0),
                    (float(q * 10), 0.0, 1.0)]
            tris.append((b, b + 1, b + 2))
        return pos, tris

    def test_borde_que_baja_con_la_malla_rasgada_reprueba_por_piezas(self):
        """Un grid abierto de 20x20 tiene 76 aristas de borde; partido en 12
        triangulos sueltos, 36: el conteo NETO BAJA y con la regla de borde
        sola ese resultado destrozado salia con exit 0. La cantidad de piezas
        (1 -> 12) es lo que el rasgado no puede fingir."""
        grid = self._t(*self._grid(20))
        sueltos = self._t(*self._sueltos(12))
        self.assertEqual(grid["borde"], 76)
        self.assertEqual(sueltos["borde"], 36)
        self.assertLess(sueltos["borde"], grid["borde"],
                        "la premisa del caso es que el borde BAJE; si eso "
                        "cambia, este test deja de probar lo que dice")
        fallas, _ = salud_malla.comparar(grid, sueltos)
        self.assertTrue(any("REGLA piezas" in f for f in fallas), fallas)

    def test_decimacion_correcta_del_grid_pasa_sin_margen(self):
        """20x20 soldado -> 10x10 soldado: menos borde, menos tri, una pieza.
        Un criterio que reprobara la decimacion buena no es un criterio, y no
        lleva margen: la regla de piezas es estructural (colapsar fusiona,
        fusionar no parte), no statistica."""
        fallas, _ = salud_malla.comparar(self._t(*self._grid(20)),
                                         self._t(*self._grid(10)))
        self.assertFalse(fallas)

    def test_reparto_por_material_no_la_corta_la_regra_de_piezas(self):
        """El exportador parte un mesh en shapes por material: las piezas
        crecen por el corte, no por rasgado. La guarda es la cantidad de
        shapes: ahi se informa y no reprueba. (El BORDE si sube en este caso,
        cada tramo pierde sus soldaduras entre shapes: esa limitacion es
        anterior a la regla de piezas y queda documentada, no tapada.)"""
        antes = self._t(CUBO_POS, CUBO_TRIS)
        despues = salud_malla.total([
            salud_malla.salud(CUBO_POS, CUBO_TRIS[:6], 1),
            salud_malla.salud(CUBO_POS, CUBO_TRIS[6:], 1)])
        self.assertGreater(despues["shapes"], antes["shapes"])
        self.assertGreater(despues["piezas"], antes["piezas"],
                           "si el cubo partido no sube piezas, el subTest "
                           "de arriba no esta discriminando nada")
        fallas, _ = salud_malla.comparar(antes, despues)
        self.assertFalse(any("REGLA piezas" in f for f in fallas), fallas)


class ReglaUvTests(unittest.TestCase):
    """REGLA del paso 4b [INVARIANT]: rehacer las UV no cambia la geometria
    soldada. Cortar costuras parte vertices; nada mas."""

    def _t(self, pos, tris):
        return salud_malla.total([salud_malla.salud(pos, tris, 1)])

    def test_cortar_costuras_pasa(self):
        partida = self._t(*salud_malla._partir_por_costura(CUBO_POS,
                                                            CUBO_TRIS))
        fallas, notas = salud_malla.comparar_uv(self._t(CUBO_POS, CUBO_TRIS),
                                                partida)
        self.assertEqual(fallas, [])
        self.assertIn("8 -> 36", notas[0])

    def test_caras_agregadas_despues_reprueban(self):
        """Caras que CIERRAN un hueco despues de desplegar (un Solidify sobre
        una cascara, trampa 32): el borde baja y las piezas no cambian, asi
        que las reglas de la decimacion lo dejan pasar. Los triangulos no."""
        antes = self._t(CUBO_POS, CUBO_TRIS[2:])
        despues = self._t(CUBO_POS, CUBO_TRIS)
        self.assertEqual(salud_malla.comparar(antes, despues)[0], [])
        fallas, _ = salud_malla.comparar_uv(antes, despues)
        self.assertTrue(any("REGLA uv tris: 12 contra 10" in f
                            for f in fallas), fallas)

    def test_una_cara_de_menos_reprueba(self):
        fallas, _ = salud_malla.comparar_uv(self._t(CUBO_POS, CUBO_TRIS),
                                            self._t(CUBO_POS, CUBO_TRIS[2:]))
        self.assertTrue(fallas)

    def test_sin_nada_que_medir_reprueba(self):
        fallas, _ = salud_malla.comparar_uv(self._t(CUBO_POS, CUBO_TRIS),
                                            None)
        self.assertTrue(fallas)


class LecturaNifTests(unittest.TestCase):
    """censo_nif.geometria(): recupera la geometria, o dice que no pudo."""

    def test_recupera_lo_que_se_escribio(self):
        datos, esperado = nif_sintetico.construir_estatico(CUBO_POS, CUBO_TRIS)
        ruta = _archivo(datos)
        try:
            g = censo_nif.Nif(ruta).geometria()
            self.assertEqual(len(g), 1)
            self.assertNotIn("error", g[0])
            self.assertEqual([tuple(t) for t in g[0]["tris"]],
                             esperado["tris"])
            self.assertEqual([tuple(round(c, 6) for c in p)
                              for p in g[0]["pos"]], esperado["pos"])
        finally:
            os.unlink(ruta)

    def test_un_data_size_mentiroso_no_devuelve_numeros(self):
        """La identidad n_ver*stride + n_tri*6 == data_size falsifica el
        layout. Si no cierra, sale 'error' -- no basura."""
        datos, _ = nif_sintetico.construir_estatico(CUBO_POS, CUBO_TRIS,
                                                    data_size=999)
        ruta = _archivo(datos)
        try:
            g = censo_nif.Nif(ruta).geometria()
            self.assertIn("error", g[0])
            self.assertIn("data_size", g[0]["error"])
        finally:
            os.unlink(ruta)

    def test_el_shape_skinneado_avisa_en_vez_de_desaparecer(self):
        """Un shape sin geometria inline no se puede omitir en silencio: el
        que llama tiene que poder negarse a dar por bueno lo que no midio."""
        datos, _ = nif_sintetico.construir_skinneado()
        ruta = _archivo(datos)
        try:
            g = censo_nif.Nif(ruta).geometria()
            self.assertTrue(g, "no devolvio ningun shape")
            self.assertTrue(all("error" in s for s in g))
            medidas, avisos = salud_malla.leer(ruta)
            self.assertEqual(medidas, [])
            self.assertTrue(avisos)
        finally:
            os.unlink(ruta)


class LecturaObjTests(unittest.TestCase):
    """La spec de Wavefront permite `f -1 -2 -3`: indices negativos relativos
    al ultimo vertice definido. La primera version del lector hacia
    `int(tok) - 1` para TODO token: el negativo quedaba barajado (y media una
    malla torcida sin avisar, el peor fallo posible) y un -len reventaba con
    IndexError. La segunda mitad del contrato del archivo (.nif o .obj) no
    puede tener un camino que mienta o truene."""

    def _escribir(self, lineas):
        return _archivo(("\n".join(lineas) + "\n").encode("ascii"), ".obj")

    def test_mismo_cubo_escrito_con_negativos(self):
        lineas = ["v %f %f %f" % p for p in CUBO_POS]
        for a, b, c in CUBO_TRIS:
            lineas.append("f %d %d %d" % (a - len(CUBO_POS),
                                          b - len(CUBO_POS),
                                          c - len(CUBO_POS)))
        ruta = self._escribir(lineas)
        try:
            medidas, _ = salud_malla.leer(ruta)
            self.assertEqual(len(medidas), 1)
            self.assertEqual(medidas[0]["borde"], 0)
            self.assertEqual(medidas[0]["tris"], len(CUBO_TRIS))
            self.assertEqual(medidas[0]["fuera_de_rango"], 0)
        finally:
            os.unlink(ruta)

    def test_indices_imposibles_se_cuentan_no_se_omiten(self):
        """v incompleto (placeholder NaN para que las caras no se corran),
        cara con el 0 que no existe, un fuera de rango, un token ilegible:
        todo tiene que salir medido y con `fuera_de_rango`, no en traceback."""
        lineas = (["v 0 0"]
                  + ["v %f %f %f" % p for p in CUBO_POS[1:]]
                  + ["f -99 1 2", "f x 2 3", "f 0 1 2",
                     "f 5 6 7", "f 6 7 8"])
        ruta = self._escribir(lineas)
        try:
            s = salud_malla._leer_obj(ruta)[0]
            self.assertEqual(len(s["pos"]), len(CUBO_POS))
            m = salud_malla.salud(s["pos"], s["tris"], 1)
            self.assertEqual(m["fuera_de_rango"], 3)
            self.assertEqual(m["tris"], 2)
        finally:
            os.unlink(ruta)


class DivergenciaConMedirParteTests(unittest.TestCase):
    """Dos lecturas de la MISMA magnitud tienen que dar el mismo numero.

    `medir_parte.aristas_de_borde()` ya contaba bordes antes que esto, pero
    corre DENTRO de Blender --sobre la escena-- y con tolerancia ABSOLUTA
    (1e-5). `salud_malla.salud()` corre sobre el ARCHIVO, sin Blender, y suelda
    con tolerancia RELATIVA al lado mayor. Las dos son defendibles y no son la
    misma: sobre una malla en unidades de Skyrim (cientos), 1e-5 absoluto es
    mucho mas fino que 2e-5 relativo.

    El test no elige cual gana: exige que coincidan donde tienen que coincidir
    y deja escrito donde no. Si manana alguien toca una, esto lo dice.

    `medir_parte` importa `bpy`, asi que no se puede importar aca. Se extrae la
    funcion REAL de su fuente con `ast` y se ejecuta: probar una copia pegada
    en el test no probaria nada.
    """

    @classmethod
    def setUpClass(cls):
        import ast
        import io
        ruta = os.path.join(os.path.dirname(SCRIPT), "medir_parte.py")
        with io.open(ruta, encoding="utf-8") as fh:
            arbol = ast.parse(fh.read())
        fn = next((n for n in arbol.body
                   if isinstance(n, ast.FunctionDef)
                   and n.name == "aristas_de_borde"), None)
        if fn is None:
            raise AssertionError(
                "medir_parte.py ya no define aristas_de_borde: este test ata "
                "las dos lecturas y hay que reapuntarlo, no borrarlo")
        entorno = {}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), ruta, "exec"),
             entorno)
        cls.aristas_de_borde = staticmethod(entorno["aristas_de_borde"])

    def _malla_falsa(self, pos, tris):
        """Lo minimo que aristas_de_borde() toca de una malla de Blender."""
        class V(object):
            def __init__(self, co):
                self.co = type("Co", (), {"x": co[0], "y": co[1],
                                          "z": co[2]})()

        class P(object):
            def __init__(self, t):
                self.vertices = list(t)

        return type("Malla", (), {"vertices": [V(p) for p in pos],
                                  "polygons": [P(t) for t in tris]})()

    def test_las_dos_cuentan_lo_mismo_en_las_mismas_figuras(self):
        casos = [("cubo cerrado", CUBO_POS, CUBO_TRIS),
                 ("cubo con un agujero", CUBO_POS, CUBO_TRIS[2:]),
                 ("dos cubos", CUBO_POS + [(x + 10, y, z)
                                           for x, y, z in CUBO_POS],
                  CUBO_TRIS + [(a + 8, b + 8, c + 8) for a, b, c in CUBO_TRIS])]
        for nombre, pos, tris in casos:
            with self.subTest(figura=nombre):
                mia = salud_malla.salud(pos, tris, 1)["borde"]
                suya = self.aristas_de_borde(self._malla_falsa(pos, tris))
                self.assertEqual(mia, suya,
                                 "%s: salud_malla %d vs medir_parte %d"
                                 % (nombre, mia, suya))

    def test_la_tolerancia_relativa_es_la_que_cierra_una_costura_real(self):
        """Donde SI divergen, y por que la relativa es la que sirve aca.

        Un vertice partido por costura y separado 1e-4 en una malla de 100
        unidades es el mismo punto: 1e-6 del tamano. La tolerancia absoluta de
        1e-5 no lo suelda y cuenta bordes falsos; la relativa si.
        """
        escala = 100.0
        pos, tris = [], []
        for a, b, c in CUBO_TRIS:
            base = len(pos)
            for i in (a, b, c):
                x, y, z = CUBO_POS[i]
                pos.append((x * escala + 1e-4 * (base % 2),
                            y * escala, z * escala))
            tris.append((base, base + 1, base + 2))
        mia = salud_malla.salud(pos, tris, 1)["borde"]
        suya = self.aristas_de_borde(self._malla_falsa(pos, tris))
        self.assertEqual(mia, 0, "la relativa tendria que cerrar el cubo")
        self.assertGreater(suya, 0,
                           "si la absoluta ya cerrara esto, el comentario de "
                           "este test esta desactualizado")


class LineaDeComandosTests(unittest.TestCase):
    """Los codigos de salida son el contrato con el pipeline."""

    def _correr(self, *args):
        p = subprocess.run([sys.executable, SCRIPT] + list(args),
                           capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    def test_autotest_pasa(self):
        codigo, salida = self._correr("--autotest")
        self.assertEqual(codigo, 0, salida)
        self.assertIn("0 fallas", salida)

    def test_par_sano_sale_cero_y_par_roto_sale_uno(self):
        # Dos cubos: 24 triangulos, por encima del minimo de la herramienta.
        # Con uno solo (12 tri) la version rota quedaba en 10 y el control
        # reprobaba por "no hay nada que medir" en vez de por la REGLA: mismo
        # codigo de salida, otra razon. Lo pesco la asercion sobre el mensaje.
        pos2 = CUBO_POS + [(x + 10, y, z) for x, y, z in CUBO_POS]
        tris2 = CUBO_TRIS + [(a + 8, b + 8, c + 8) for a, b, c in CUBO_TRIS]
        sano = _obj(pos2, tris2)
        roto = _obj(pos2, tris2[2:])
        try:
            self.assertEqual(self._correr(sano, sano)[0], 2,
                             "el mismo archivo dos veces tiene que ser 2")
            copia = _obj(pos2, tris2)
            try:
                self.assertEqual(self._correr(sano, copia)[0], 0)
            finally:
                os.unlink(copia)
            codigo, salida = self._correr(sano, roto)
            self.assertEqual(codigo, 1, salida)
            self.assertIn("REGLA borde", salida)
        finally:
            os.unlink(sano)
            os.unlink(roto)

    def test_uv_por_linea_de_comandos(self):
        pos2 = CUBO_POS + [(x + 10, y, z) for x, y, z in CUBO_POS]
        tris2 = CUBO_TRIS + [(a + 8, b + 8, c + 8) for a, b, c in CUBO_TRIS]
        antes = _obj(pos2, tris2)
        costuras = _obj(*salud_malla._partir_por_costura(pos2, tris2))
        mas_caras = _obj(pos2 + [(0.5, 0.5, 2.0)], tris2 + [(4, 5, 16),
                                                           (5, 6, 16)])
        try:
            codigo, salida = self._correr("--uv", antes, costuras)
            self.assertEqual(codigo, 0, salida)
            codigo, salida = self._correr("--uv", antes, mas_caras)
            self.assertEqual(codigo, 1, salida)
            self.assertIn("REGLA uv", salida)
            self.assertEqual(self._correr("--uv", antes, antes)[0], 2)
        finally:
            for r in (antes, costuras, mas_caras):
                os.unlink(r)

    def test_sin_argumentos_o_con_extension_rara_no_dice_que_paso(self):
        """`2` es "los argumentos no sirven" segun el contrato de arriba del
        archivo. Un .txt es exactamente eso: la primera version tiraba un
        SystemExit con mensaje y salia con 1, que es el codigo de "el control
        fallo" — un automatizador que lea el exit code sin la salida no los
        puede distinguir."""
        self.assertEqual(self._correr()[0], 2)
        self.assertEqual(self._correr("a", "b", "c")[0], 2)
        fd, txt = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        fd, otro = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            codigo, salida = self._correr(txt)
            self.assertEqual(codigo, 2, salida)
            self.assertIn(".nif o .obj", salida)
            # Dos archivos DISTINTOS: con el mismo dos veces salia 2 por "mismo
            # archivo" y el chequeo de extension no se probaba.
            for args in ((txt, otro), ("--uv", txt, otro)):
                codigo, salida = self._correr(*args)
                self.assertEqual(codigo, 2, salida)
                self.assertIn(".nif o .obj", salida)
        finally:
            os.unlink(txt)
            os.unlink(otro)

    def test_un_archivo_sin_nada_medible_no_sale_cero(self):
        """Medir nada no es pasar."""
        vacio = _obj(CUBO_POS, CUBO_TRIS[:2])
        try:
            self.assertEqual(self._correr(vacio)[0], 1)
        finally:
            os.unlink(vacio)


if __name__ == "__main__":
    unittest.main()
