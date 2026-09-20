# -*- coding: utf-8 -*-
"""El paso 8b: comparar el NIF exportado contra el vanilla.

Corre en CI: los dos NIF se construyen byte a byte, asi que no necesita el
corpus. La falsificacion sobre archivos vanilla reales --el gigante de
escarcha contra el chico, y el maniqui como par-- prueba otra cosa y vive en
`verificar_export.py --falsificar <carpeta meshes>`. Ninguna reemplaza a la
otra: esta comprueba que cada regla PUEDE fallar, aquella que falla con la
senal real y no falla sin ella.
"""
import os
import tempfile
import unittest

from _paths import preparar_path

preparar_path()

import censo_nif  # noqa: E402
import nif_sintetico  # noqa: E402
import parser_nif  # noqa: E402
import verificar_export as V  # noqa: E402


def _archivo(datos, caso):
    fd, ruta = tempfile.mkstemp(suffix=".nif")
    with os.fdopen(fd, "wb") as fh:
        fh.write(datos)
    caso.addCleanup(lambda: os.path.exists(ruta) and os.unlink(ruta))
    return ruta


# Cada entrada: (regla que tiene que aparecer, kwargs que tuercen el fixture).
# La lista NO se escribe a mano contra REGLAS: el test de abajo comprueba que
# entre todas cubran REGLAS entera, asi que agregar una regla sin su caso
# rompe la suite.
TORCEDURAS = [
    ("bloques", {"bloque_extra": True}),
    ("raiz", {"raiz_tipo": "BSFadeNode"}),
    ("nodos", {"huesos": ("HuesoA", "HuesoZ"),
               "traslaciones": ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0))}),
    ("posiciones", {"traslaciones": ((1.0, 2.0, 3.0), (99.0, 5.0, 6.0))}),
    ("piezas", {"nombre_pieza": "OtraPieza"}),
    ("huesos/pieza", {"huesos": ("HuesoA",), "traslaciones": ((1.0, 2.0, 3.0),)}),
    ("body parts", {"body_parts": (33,)}),
]


class CadaReglaPuedeFallarTests(unittest.TestCase):
    """Una regla que no reprueba ante nada no es una regla, es un adorno."""

    def setUp(self):
        base, _e = nif_sintetico.construir_skinneado()
        self.vanilla = _archivo(base, self)

    def _reglas(self, **kw):
        datos, _e = nif_sintetico.construir_skinneado(**kw)
        fallas, _n = V.comparar(_archivo(datos, self), self.vanilla)
        return {f.regla for f in fallas}, fallas

    def test_el_par_dos_archivos_iguales_no_reprueban(self):
        """Si reprobara siempre, los siete casos de abajo no probarian nada."""
        reglas, fallas = self._reglas()
        self.assertEqual(set(), reglas, [str(f) for f in fallas])

    def test_cada_torcedura_hace_fallar_su_regla(self):
        for regla, kw in TORCEDURAS:
            reglas, fallas = self._reglas(**kw)
            self.assertIn(regla, reglas,
                          "%r no hizo fallar %r; salio %r"
                          % (kw, regla, [str(f) for f in fallas]))

    def test_las_torceduras_cubren_TODAS_las_reglas(self):
        """El ancla enumerante: agregar una regla a REGLAS sin su caso
        rompe aca, en vez de quedar como garantia sin falsificar."""
        cubiertas = {r for r, _kw in TORCEDURAS}
        self.assertEqual(set(V.REGLAS), cubiertas,
                         "sin caso que las haga fallar: %s"
                         % (set(V.REGLAS) - cubiertas))

    def test_una_regla_no_declarada_no_se_puede_reportar(self):
        with self.assertRaises(ValueError):
            V.Falla("inventada", "x")


class HuesoPerdidoTests(unittest.TestCase):
    """Perder un hueso no da error en el juego: se pierde articulacion."""

    def test_dice_cual_pieza_perdio_cual_hueso(self):
        van, _e = nif_sintetico.construir_skinneado()
        nuevo, _e2 = nif_sintetico.construir_skinneado(
            huesos=("HuesoA",), traslaciones=((1.0, 2.0, 3.0),))
        fallas, _n = V.comparar(_archivo(nuevo, self), _archivo(van, self))
        textos = [f.detalle for f in fallas if f.regla == "huesos/pieza"]
        self.assertEqual(1, len(textos), textos)
        self.assertIn("PiezaDePrueba", textos[0])
        self.assertIn("HuesoB", textos[0])


class NadaQueCompararTests(unittest.TestCase):
    """Cero comparaciones no es pasar. Es el agujero que ya se colo en el
    autotest de parser_uv: con la ruta equivocada el bucle no entraba nunca y
    el resultado se imprimia como ok."""

    def test_sin_un_solo_hueso_en_comun_no_pasa(self):
        van, _e = nif_sintetico.construir_skinneado()
        nuevo, _e2 = nif_sintetico.construir_skinneado(
            huesos=("Otro1", "Otro2"))
        fallas, _n = V.comparar(_archivo(nuevo, self), _archivo(van, self))
        motivos = [f.detalle for f in fallas if f.regla == "posiciones"]
        self.assertTrue(any("NI UN" in m for m in motivos), motivos)

    def test_un_estatico_sin_huesos_no_dispara_esa_guarda(self):
        """El par de la de arriba. Un archivo sin huesos no tiene nada que
        comparar POR DISENO; exigirselo seria inventar una regla."""
        datos, _e = nif_sintetico.construir()
        r = _archivo(datos, self)
        fallas, _n = V.comparar(r, r)
        self.assertEqual([], [str(f) for f in fallas])


class LaRaizLlevaElNombreDelArchivoTests(unittest.TestCase):
    """Medido: en 2.786 de 3.000 archivos del corpus (92,9 %) el nodo raiz se
    llama igual que el .nif. Comparar ese nombre es comparar nombres de
    archivo -- reprobaba 1.198 de los 1.216 pares `_0`/`_1` del MISMO asset."""

    def test_la_raiz_con_otro_nombre_es_observacion_no_falla(self):
        van, _e = nif_sintetico.construir_skinneado()
        original = nif_sintetico.RAIZ_NOMBRE
        try:
            nif_sintetico.RAIZ_NOMBRE = "OtroNombreDeArchivo"
            nuevo, _e2 = nif_sintetico.construir_skinneado()
        finally:
            nif_sintetico.RAIZ_NOMBRE = original
        fallas, notas = V.comparar(_archivo(nuevo, self), _archivo(van, self))
        self.assertEqual([], [str(f) for f in fallas])
        self.assertTrue(any(n.tema == "raiz" for n in notas),
                        [str(n) for n in notas])

    def test_pero_el_TIPO_de_la_raiz_si_reprueba(self):
        van, _e = nif_sintetico.construir_skinneado(raiz_tipo="NiNode")
        nuevo, _e2 = nif_sintetico.construir_skinneado(raiz_tipo="BSFadeNode")
        fallas, _n = V.comparar(_archivo(nuevo, self), _archivo(van, self))
        self.assertIn("raiz", {f.regla for f in fallas})


class ElLectorDeLaSkillNoSePuedeSepararDelCensoTests(unittest.TestCase):
    """censo_nif.py duplica a proposito lo que census/parser_nif.py ya lee:
    la skill se empaqueta sola y no puede importar census/. La duplicacion ya
    produjo dos bugs en este repo, asi que lo que la hace segura no es una
    promesa, es este test."""

    def _nif(self, **kw):
        datos, esperado = nif_sintetico.construir_skinneado(**kw)
        return _archivo(datos, self), esperado

    def test_los_dos_parsers_leen_los_mismos_huesos_y_particiones(self):
        casos = [{}, {"huesos": ("H1", "H2", "H3"),
                      "traslaciones": ((0.0, 0.0, 1.0), (0.0, 0.0, 2.0),
                                       (0.0, 0.0, 3.0))},
                 {"body_parts": (32, 33)}]
        for kw in casos:
            ruta, esperado = self._nif(**kw)
            skill = censo_nif.Nif(ruta).skin_por_shape()
            censo = parser_nif.Nif(ruta)
            partes, huesos = censo._parse_dismember_instances()
            self.assertEqual(esperado["huesos"],
                             skill[esperado["pieza"]]["huesos"], kw)
            self.assertEqual(huesos["nombres"],
                             skill[esperado["pieza"]]["huesos"], kw)
            self.assertEqual([p["body_part_id"] for p in partes],
                             skill[esperado["pieza"]]["body_parts"], kw)

    def test_las_dos_listas_de_tipos_de_skin_son_la_misma(self):
        self.assertEqual(set(parser_nif.TIPOS_SKIN), set(censo_nif.TIPOS_SKIN))


class FalsificacionTests(unittest.TestCase):

    def test_sin_corpus_no_es_exito(self):
        import contextlib
        import io as _io
        with tempfile.TemporaryDirectory() as d:
            with contextlib.redirect_stdout(_io.StringIO()) as salida:
                ok = V.falsificar(d)
        self.assertFalse(ok, salida.getvalue())

    def test_la_tabla_declara_lo_que_compara(self):
        """Una entrada sin nada que comprobar pasaria sin mirar el archivo."""
        self.assertTrue(V.FALSIFICACION)
        for rel_n, rel_v, esperado in V.FALSIFICACION:
            self.assertTrue(rel_n.lower().endswith(".nif"))
            self.assertTrue(rel_v.lower().endswith(".nif"))
            self.assertTrue(esperado, "%s no declara nada" % rel_n)
            for clave in esperado:
                self.assertIn(clave, ("fallas", "posiciones", "fallas_min"))

    def test_hay_al_menos_un_caso_que_pasa_y_uno_que_revienta(self):
        """Una tabla de solo-revienta no distingue el control de uno roto."""
        pasan = [e for _a, _b, e in V.FALSIFICACION if e.get("fallas") == 0]
        revientan = [e for _a, _b, e in V.FALSIFICACION
                     if e.get("posiciones", 0) > 0]
        self.assertTrue(pasan)
        self.assertTrue(revientan)


if __name__ == "__main__":
    unittest.main()
