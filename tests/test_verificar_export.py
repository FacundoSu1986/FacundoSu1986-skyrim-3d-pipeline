# -*- coding: utf-8 -*-
"""El paso 8b: comparar el NIF exportado contra el vanilla.

Corre en CI: los dos NIF se construyen byte a byte, asi que no necesita el
corpus. La falsificacion sobre archivos vanilla reales --el gigante de escarcha
contra el chico, y el maniqui como par-- prueba otra cosa y vive en
`verificar_export.py --falsificar <carpeta meshes>`. Ninguna reemplaza a la
otra: esta comprueba que cada regla PUEDE fallar, aquella que falla con la
senal real y no falla sin ella.

POR QUE LAS TORCEDURAS SE REPARTEN EN EJES

La primera version de este archivo movia SOLO X, y siempre 95 unidades. Con
eso, la suite quedaba verde con `TOLERANCIA` puesta en 0,5 o en 0,0001, con la
comparacion de escala borrada, y con `_desvio` mirando un solo eje. Enumerar
las reglas no alcanza: hay que enumerar las DIMENSIONES de cada regla, y una de
ellas es el umbral mismo, que se prueba a los dos lados del filo.
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
    # Un export LE (trampa 33): BS 83. Reprueba por la version y no sigue.
    ("version", {"bs": 83}),
    ("bloques", {"bloque_extra": True}),
    ("raiz", {"raiz_tipo": "BSFadeNode"}),
    ("nodos", {"huesos": ("HuesoA", "HuesoZ")}),
    ("posiciones", {"traslaciones": ((1.0, 2.0, 3.0), (99.0, 5.0, 6.0))}),
    # Y y Z aparte de X: con solo X, `_desvio` mirando un unico eje pasaba.
    ("posiciones", {"traslaciones": ((1.0, 2.0, 3.0), (4.0, 99.0, 6.0))}),
    ("posiciones", {"traslaciones": ((1.0, 2.0, 3.0), (4.0, 5.0, 99.0))}),
    ("posiciones", {"escalas": (1.0, 0.33)}),     # la escala, no la posicion
    # Un hueso HOJA girado: MISMA posicion, otros ejes. Sin este caso, dos
    # huesos girados 90 grados daban "pasa: 0 fallas sobre 8 comprobaciones".
    ("orientacion", {"rot_huesos": (nif_sintetico.IDENTIDAD,
                                    nif_sintetico.CUARTO_DE_VUELTA)}),
    ("orientacion", {"rot_pieza": nif_sintetico.CUARTO_DE_VUELTA}),
    ("piezas", {"nombre_pieza": "OtraPieza"}),
    ("colocacion", {"tr_pieza": (0.0, 140.0, 0.0)}),
    ("colocacion", {"esc_pieza": 0.72}),
    ("huesos/pieza", {"huesos": ("HuesoA",),
                      "traslaciones": ((1.0, 2.0, 3.0),)}),
    ("body parts", {"body_parts": (33,)}),
    ("body parts", {"body_parts": (33, 32)}),     # mismo conjunto, otro orden
    ("skin", {"skin_tipo": "NiSkinInstance"}),
    ("comparables", {"huesos": ("HuesoA", "HuesoA")}),
]


class CadaReglaPuedeFallarTests(unittest.TestCase):
    """Una regla que no reprueba ante nada no es una regla, es un adorno."""

    def setUp(self):
        base, _e = nif_sintetico.construir_skinneado(body_parts=(32, 33))
        self.vanilla = _archivo(base, self)

    def _reglas(self, **kw):
        kw.setdefault("body_parts", (32, 33))
        kw.setdefault("traslaciones",
                      nif_sintetico.HUESOS_TRASLACION[:len(
                          kw.get("huesos", nif_sintetico.HUESOS_NOMBRE))])
        datos, _e = nif_sintetico.construir_skinneado(**kw)
        fallas, _n, _c = V.comparar(_archivo(datos, self), self.vanilla)
        return {f.regla for f in fallas}, fallas

    def test_el_par_dos_archivos_iguales_no_reprueban(self):
        """Si reprobara siempre, los casos de abajo no probarian nada."""
        reglas, fallas = self._reglas()
        self.assertEqual(set(), reglas, [str(f) for f in fallas])

    def test_cada_torcedura_hace_fallar_su_regla(self):
        for regla, kw in TORCEDURAS:
            reglas, fallas = self._reglas(**kw)
            self.assertIn(regla, reglas,
                          "%r no hizo fallar %r; salio %r"
                          % (kw, regla, [str(f) for f in fallas]))

    def test_las_torceduras_cubren_TODAS_las_reglas(self):
        """El ancla enumerante: agregar una regla a REGLAS sin su caso rompe
        aca, en vez de quedar como garantia sin falsificar."""
        cubiertas = {r for r, _kw in TORCEDURAS}
        self.assertEqual(set(V.REGLAS), cubiertas,
                         "sin caso que las haga fallar: %s"
                         % (set(V.REGLAS) - cubiertas))

    def test_un_export_LE_reprueba_por_la_version_y_nada_mas(self):
        """Sin la regla, el mismo archivo reprobaba por `bloques`, que no dice
        la causa. Con ella, una sola falla, que nombra la trampa."""
        # Con un bloque de mas: si siguiera comparando, `bloques` tambien
        # reprobaria y taparia la causa.
        reglas, fallas = self._reglas(bs=83, bloque_extra=True)
        self.assertEqual({"version"}, reglas)
        self.assertEqual(1, len(fallas))
        self.assertIn("BS 83", str(fallas[0]))
        self.assertIn("intuit_defaults=False", str(fallas[0]))

    def test_una_regla_no_declarada_no_se_puede_reportar(self):
        with self.assertRaises(ValueError):
            V.Falla("inventada", "x")


class LaToleranciaEsElRedondeoDelLectorTests(unittest.TestCase):
    """El numero que el PR puso de estrella no estaba protegido por nada que
    corra en CI: TOLERANCIA vivia en un archivo y el round() en otro."""

    def test_la_tolerancia_se_deriva_del_redondeo(self):
        self.assertEqual(10.0 ** -censo_nif.DECIMALES_MUNDO, V.TOLERANCIA)
        self.assertEqual(10.0 ** -censo_nif.DECIMALES_ESCALA,
                         V.TOLERANCIA_ESCALA)

    def _desvio_de(self, delta):
        base, _e = nif_sintetico.construir_skinneado()
        movido, _e2 = nif_sintetico.construir_skinneado(
            traslaciones=((1.0, 2.0, 3.0), (4.0, 5.0 + delta, 6.0)))
        fallas, _n, _c = V.comparar(_archivo(movido, self),
                                    _archivo(base, self))
        return [f for f in fallas if f.regla == "posiciones"]

    def test_por_debajo_del_redondeo_no_reprueba(self):
        """Medido en el corpus: 4 de 2.112 comparaciones de character assets
        difieren en exactamente 0,010, que es el redondeo. Reprobarlas seria
        un falso positivo sobre el propio vanilla."""
        self.assertEqual([], [str(f) for f in self._desvio_de(0.004)])

    def test_al_doble_del_redondeo_si_reprueba(self):
        """El par del de arriba. Sin este, TOLERANCIA = 0,5 pasaba la suite."""
        self.assertEqual(1, len(self._desvio_de(0.02)),
                         [str(f) for f in self._desvio_de(0.02)])


class CeroComparacionesNoEsPasarTests(unittest.TestCase):
    """0 fallas sobre 0 comparaciones no es un ok. Un NIF de 73 bytes --solo
    cabecera-- parseaba sin excepcion y salia 'pasa', exit 0."""

    def _solo_cabecera(self):
        import struct
        NS = nif_sintetico
        h = bytearray(NS.CABECERA)
        h += struct.pack("<I", NS.VERSION) + struct.pack("<B", 1)
        h += struct.pack("<I", NS.USER) + struct.pack("<I", 0)
        h += struct.pack("<I", NS.BS)
        h += NS._corta("") + NS._corta("") + NS._corta("")
        h += struct.pack("<H", 0) + struct.pack("<I", 0)
        h += struct.pack("<I", 0) + struct.pack("<I", 0)
        return bytes(h)

    def test_un_nif_sin_bloques_no_produce_ninguna_comparacion(self):
        a = _archivo(self._solo_cabecera(), self)
        b = _archivo(self._solo_cabecera(), self)
        fallas, _n, n_comp = V.comparar(a, b)
        self.assertEqual([], [str(f) for f in fallas])
        self.assertEqual(0, n_comp)

    def test_y_main_lo_rechaza_con_exit_1(self):
        import contextlib
        import io as _io
        import sys
        a = _archivo(self._solo_cabecera(), self)
        b = _archivo(self._solo_cabecera(), self)
        argv = sys.argv
        try:
            sys.argv = ["verificar_export.py", a, b]
            with contextlib.redirect_stdout(_io.StringIO()) as salida:
                codigo = V.main()
        finally:
            sys.argv = argv
        self.assertEqual(1, codigo, salida.getvalue())
        self.assertIn("NO se comparo NADA", salida.getvalue())

    def test_un_nif_normal_cuenta_CADA_comparacion(self):
        """El par: si n_comp fuera siempre 0, el rechazo de arriba tambien
        reprobaria a los archivos sanos.

        El numero es exacto y no un `> 0`: con `> 0` bastaba con que contara
        los tipos de bloque, y dejar de contar las posiciones pasaba la suite.
        Para este fixture: 3 tipos de bloque + 3 nodos (raiz y dos huesos)
        + 3 orientaciones de nodo + 1 orientacion de pieza + 1 pieza colocada
        + 1 pieza con sus huesos = 12."""
        datos, _e = nif_sintetico.construir_skinneado()
        r = _archivo(datos, self)
        _f, _n, n_comp = V.comparar(r, _archivo(datos, self))
        self.assertEqual(3 + 3 + 3 + 1 + 1 + 1, n_comp)

    def test_y_crece_con_lo_que_hay_para_comparar(self):
        """Un hueso mas es una comparacion mas: el conteo sigue a los datos,
        no es una constante que quedo escrita."""
        datos, _e = nif_sintetico.construir_skinneado(
            huesos=("A", "B", "C"),
            traslaciones=((1.0, 0.0, 0.0), (2.0, 0.0, 0.0), (3.0, 0.0, 0.0)))
        r = _archivo(datos, self)
        _f, _n, n_comp = V.comparar(r, _archivo(datos, self))
        self.assertEqual(3 + 4 + 4 + 1 + 1 + 1, n_comp)

    def test_un_nif_ilegible_no_sale_por_un_traceback(self):
        """falsificar() ya tenia esta guarda y main() no. Un archivo que el
        lector no puede abrir NO es un detalle de implementacion: es el
        resultado, y sale por exit 1 con una linea que se entiende."""
        import contextlib
        import io as _io
        import sys
        datos, _e = nif_sintetico.construir_skinneado()
        sano = _archivo(datos, self)
        roto = _archivo(b"no soy un nif", self)
        argv = sys.argv
        try:
            sys.argv = ["verificar_export.py", sano, roto]
            with contextlib.redirect_stdout(_io.StringIO()) as salida:
                codigo = V.main()
        finally:
            sys.argv = argv
        self.assertEqual(1, codigo, salida.getvalue())
        self.assertIn("no se pudo leer", salida.getvalue())

    def test_pero_dos_NIF_legibles_no_disparan_esa_guarda(self):
        """El par: si main() devolviera 1 ante cualquier cosa, el de arriba
        pasaria con el codigo roto."""
        import contextlib
        import io as _io
        import sys
        datos, _e = nif_sintetico.construir_skinneado()
        a = _archivo(datos, self)
        b = _archivo(datos, self)
        argv = sys.argv
        try:
            sys.argv = ["verificar_export.py", a, b]
            with contextlib.redirect_stdout(_io.StringIO()) as salida:
                codigo = V.main()
        finally:
            sys.argv = argv
        self.assertEqual(0, codigo, salida.getvalue())

    def test_el_mismo_archivo_dos_veces_no_es_una_verificacion(self):
        import contextlib
        import io as _io
        import sys
        datos, _e = nif_sintetico.construir_skinneado()
        r = _archivo(datos, self)
        argv = sys.argv
        try:
            sys.argv = ["verificar_export.py", r, r]
            with contextlib.redirect_stdout(_io.StringIO()) as salida:
                codigo = V.main()
        finally:
            sys.argv = argv
        self.assertEqual(2, codigo, salida.getvalue())


class UnEstaticoTambienSeVerificaTests(unittest.TestCase):
    """Un BSTriShape no es un nodo, asi que mundo() no lo miraba. Sobre un
    estatico --el caso mas comun del pipeline-- eso dejaba CERO posiciones que
    comparar: la pieza corrida 140 unidades daba 0 fallas y exit 0."""

    def test_la_pieza_corrida_reprueba(self):
        base, _e = nif_sintetico.construir_skinneado()
        movida, _e2 = nif_sintetico.construir_skinneado(
            tr_pieza=(0.0, 140.0, 0.0))
        fallas, _n, _c = V.comparar(_archivo(movida, self),
                                    _archivo(base, self))
        textos = [f.detalle for f in fallas if f.regla == "colocacion"]
        self.assertEqual(1, len(textos), textos)
        self.assertIn("140", textos[0])

    def test_la_raiz_con_otro_NOMBRE_no_reprueba(self):
        """La raiz sale de la comparacion de NOMBRES: en el 92,9 % del corpus
        lleva el nombre del archivo."""
        base, _e = nif_sintetico.construir_skinneado()
        otra, _e2 = nif_sintetico.construir_skinneado(
            nombre_raiz="OtroArchivo.nif")
        fallas, notas, _c = V.comparar(_archivo(otra, self),
                                       _archivo(base, self))
        self.assertEqual([], [str(f) for f in fallas])
        self.assertTrue(any(n.tema == "raiz" for n in notas))

    def test_pero_la_raiz_con_otra_TRANSFORMADA_si_reprueba(self):
        """Sacarla de la comparacion por nombre no es sacarla de la de
        posicion: su transformada mueve todo lo que cuelga. La mutacion que
        la volvia a excluir sobrevivia la suite entera."""
        base, _e = nif_sintetico.construir_skinneado()
        movida, _e2 = nif_sintetico.construir_skinneado(
            tr_raiz=(30.0, 30.0, 30.0))
        fallas, _n, _c = V.comparar(_archivo(movida, self),
                                    _archivo(base, self))
        de_raiz = [f for f in fallas if f.regla == "posiciones"
                   and nif_sintetico.RAIZ_NOMBRE in f.detalle]
        self.assertEqual(1, len(de_raiz), [str(f) for f in fallas])

    def test_y_la_raiz_con_otra_ESCALA_tambien(self):
        base, _e = nif_sintetico.construir_skinneado()
        escalada, _e2 = nif_sintetico.construir_skinneado(esc_raiz=0.4)
        fallas, _n, _c = V.comparar(_archivo(escalada, self),
                                    _archivo(base, self))
        de_raiz = [f for f in fallas if f.regla == "posiciones"
                   and nif_sintetico.RAIZ_NOMBRE in f.detalle]
        self.assertEqual(1, len(de_raiz), [str(f) for f in fallas])


class HuesoPerdidoTests(unittest.TestCase):
    """Perder un hueso no da error en el juego: se pierde articulacion."""

    def test_dice_cual_pieza_perdio_cual_hueso(self):
        van, _e = nif_sintetico.construir_skinneado()
        nuevo, _e2 = nif_sintetico.construir_skinneado(
            huesos=("HuesoA",), traslaciones=((1.0, 2.0, 3.0),))
        fallas, _n, _c = V.comparar(_archivo(nuevo, self),
                                    _archivo(van, self))
        textos = [f.detalle for f in fallas if f.regla == "huesos/pieza"]
        self.assertEqual(1, len(textos), textos)
        self.assertIn("PiezaDePrueba", textos[0])
        self.assertIn("HuesoB", textos[0])


class NombresRepetidosNoSePuedenCompararTests(unittest.TestCase):
    """Indexar por nombre no decide nada sobre un nombre repetido: el ultimo
    tapa al primero. Medido: 557 de 22.394 archivos (2,49 %) repiten un nombre
    de nodo y 222 (0,99 %) uno de shape."""

    def test_un_nombre_de_nodo_repetido_reprueba(self):
        van, _e = nif_sintetico.construir_skinneado()
        dup, _e2 = nif_sintetico.construir_skinneado(
            huesos=("HuesoA", "HuesoA"))
        fallas, _n, _c = V.comparar(_archivo(dup, self), _archivo(van, self))
        self.assertIn("comparables", {f.regla for f in fallas})

    def test_el_lector_los_reporta_en_vez_de_taparlos(self):
        dup, _e = nif_sintetico.construir_skinneado(
            huesos=("HuesoA", "HuesoA"),
            traslaciones=((1.0, 2.0, 3.0), (99.0, 99.0, 99.0)))
        n = censo_nif.Nif(_archivo(dup, self))
        self.assertEqual(["HuesoA"], n.nombres_repetidos())
        self.assertEqual(1, sum(1 for k in n.mundo() if k == "HuesoA"))

    def test_ante_un_repetido_gana_el_PRIMERO(self):
        """No es un detalle: nif_nodos.mundo() y nif_nodos.matrices() se
        quedan con el primero, y este lector se quedaba con el ultimo. Sobre
        los 13 de 1.200 archivos del corpus que repiten InvMarker con
        transformadas distintas, los dos lectores del repo daban respuestas
        distintas del mismo archivo. Que gane uno u otro importa menos que
        que sea EL MISMO."""
        dup, _e = nif_sintetico.construir_skinneado(
            huesos=("HuesoA", "HuesoA"),
            traslaciones=((1.0, 2.0, 3.0), (99.0, 99.0, 99.0)))
        n = censo_nif.Nif(_archivo(dup, self))
        self.assertEqual((1.0, 2.0, 3.0, 1.0), n.mundo()["HuesoA"])

    def test_sin_repetidos_no_hay_falla(self):
        """El par: si `comparables` reprobara siempre, no distinguiria."""
        datos, _e = nif_sintetico.construir_skinneado()
        self.assertEqual([], censo_nif.Nif(_archivo(datos, self))
                         .nombres_repetidos())


class LaJerarquiaPuedeVenirRotaTests(unittest.TestCase):
    """mundo() no llevaba `vistos`: un ciclo la colgaba y un subarbol
    compartido se recorria en tiempo exponencial."""

    def test_un_subarbol_compartido_no_se_recorre_dos_veces(self):
        import struct
        NS = nif_sintetico
        # raiz -> [1, 2]; 1 -> [3]; 2 -> [3]  (3 con dos padres)
        tipos = ["NiNode"]
        strings = ["Raiz", "A", "B", "Compartido"]
        bloques = [NS._avobject(0, [], (0.0, 0.0, 0.0), [1, 2]),
                   NS._avobject(1, [], (1.0, 0.0, 0.0), [3]),
                   NS._avobject(2, [], (0.0, 1.0, 0.0), [3]),
                   NS._avobject(3, [], (0.0, 0.0, 1.0), [])]
        h = bytearray(NS.CABECERA)
        h += struct.pack("<I", NS.VERSION) + struct.pack("<B", 1)
        h += struct.pack("<I", NS.USER) + struct.pack("<I", len(bloques))
        h += struct.pack("<I", NS.BS)
        h += NS._corta("") + NS._corta("") + NS._corta("")
        h += struct.pack("<H", len(tipos))
        for t in tipos:
            h += NS._larga(t)
        for _k in bloques:
            h += struct.pack("<H", 0)
        for b in bloques:
            h += struct.pack("<I", len(b))
        h += struct.pack("<I", len(strings))
        h += struct.pack("<I", max(len(s) for s in strings))
        for s in strings:
            h += NS._larga(s)
        h += struct.pack("<I", 0)
        n = censo_nif.Nif(_archivo(bytes(h) + b"".join(bloques), self))
        pos = n.mundo()
        self.assertEqual({"Raiz", "A", "B", "Compartido"}, set(pos))
        # Visitado una sola vez: por el primer padre, no por el ultimo.
        self.assertEqual((1.0, 0.0, 1.0, 1.0), pos["Compartido"])
        self.assertEqual([], n.nombres_repetidos())


class LosRecorridosCarosSeHacenUnaVezTests(unittest.TestCase):
    """Un comparar() hacia SEIS recorridos de jerarquia --mundo(),
    mundo_shapes() y nombres_repetidos(), por archivo-- y 38 lecturas de
    nodos() sobre steamcenturion, una por skin instance. Con cache los mismos
    dos numeros son 2 y 2, uno por archivo. Medido sobre un NIF sintetico de
    240 piezas: 0,1299 s sin cache contra 0,0151 s con ella."""

    def test_nodos_y_el_recorrido_de_mundo_se_cachean(self):
        datos, _e = nif_sintetico.construir_skinneado()
        n = censo_nif.Nif(_archivo(datos, self))
        self.assertIs(n.nodos(), n.nodos())
        self.assertIs(n._recorrer_mundo(), n._recorrer_mundo())

    def test_pero_dos_archivos_distintos_no_comparten_cache(self):
        """El par: una cache a nivel de modulo daria lo mismo para los dos y
        haria pasar cualquier comparacion."""
        a, _e = nif_sintetico.construir_skinneado()
        b, _e2 = nif_sintetico.construir_skinneado(
            traslaciones=((9.0, 9.0, 9.0), (4.0, 5.0, 6.0)))
        na = censo_nif.Nif(_archivo(a, self))
        nb = censo_nif.Nif(_archivo(b, self))
        self.assertNotEqual(na.mundo(), nb.mundo())


class ElLectorDeLaSkillNoSePuedeSepararDelCensoTests(unittest.TestCase):
    """censo_nif.py duplica a proposito lo que census/parser_nif.py ya lee: la
    skill se empaqueta sola y no puede importar census/. La duplicacion ya
    produjo dos bugs en este repo, asi que lo que la hace segura no es una
    promesa, es este test."""

    def _nif(self, **kw):
        datos, esperado = nif_sintetico.construir_skinneado(**kw)
        return _archivo(datos, self), esperado

    def test_los_dos_parsers_leen_los_mismos_huesos_y_particiones(self):
        casos = [{}, {"huesos": ("H1", "H2", "H3"),
                      "traslaciones": ((0.0, 0.0, 1.0), (0.0, 0.0, 2.0),
                                       (0.0, 0.0, 3.0))},
                 {"body_parts": (32, 33)},
                 {"skin_tipo": "NiSkinInstance"}]
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

    def test_donde_DIVERGEN_a_proposito_y_por_que_no_importa_todavia(self):
        """Un ref de hueso que no cae en un nodo: censo_nif devuelve "?N" y
        parser_nif lo descarta. NO es una divergencia inocente --convierte un
        relleno en un hueso ganado-- pero tampoco es un bug vivo: medido sobre
        el corpus entero, 0 de 115.766 refs de hueso dejan de resolver. Queda
        declarada aca para que el test de arriba no diga "leen lo mismo" sin
        aclarar donde no."""
        orig = nif_sintetico._dismember
        try:
            nif_sintetico._dismember = (
                lambda br, bp, cp=True: orig(list(br) + [-1], bp, cp))
            ruta, esperado = self._nif()
        finally:
            nif_sintetico._dismember = orig
        skill = censo_nif.Nif(ruta).skin_por_shape()[esperado["pieza"]]
        censo = parser_nif.Nif(ruta)._parse_dismember_instances()[1]
        self.assertEqual(esperado["huesos"] + ["?-1"], skill["huesos"])
        self.assertEqual(esperado["huesos"], censo["nombres"])

    def test_las_dos_listas_de_tipos_de_skin_son_la_misma(self):
        self.assertEqual(set(parser_nif.TIPOS_SKIN), set(censo_nif.TIPOS_SKIN))

    def test_la_busqueda_de_archivos_no_se_reimplementa(self):
        """La copia que habia perdia la guarda de ambiguedad de censo_nif."""
        self.assertIs(censo_nif._buscar, V.censo_nif._buscar)
        d = self.enterContext(tempfile.TemporaryDirectory())
        for sub in ("a", "b"):
            os.makedirs(os.path.join(d, sub, "x"))
            open(os.path.join(d, sub, "x", "y.nif"), "wb").close()
        with self.assertRaises(SystemExit):
            V._buscar(d, "x/y.nif")


class FalsificacionTests(unittest.TestCase):

    def test_sin_corpus_no_es_exito(self):
        import contextlib
        import io as _io
        with tempfile.TemporaryDirectory() as d:
            with contextlib.redirect_stdout(_io.StringIO()) as salida:
                ok = V.falsificar(d)
        self.assertFalse(ok, salida.getvalue())

    def test_un_archivo_ilegible_no_aborta_el_bucle(self):
        """Antes reventaba con traceback: sin resumen, sin exit code, y sin
        llegar a la guarda de 'cero comprobaciones no es exito'."""
        import contextlib
        import io as _io
        # TemporaryDirectory y no mkdtemp: los .nif que este test escribe
        # quedaban en el tmp del sistema, y en un sandbox llegaron a hacer que
        # `--falsificar /tmp` reportara [ilegible] en vez de [falta].
        d = self.enterContext(tempfile.TemporaryDirectory())
        for rel_n, rel_v, _e in V.FALSIFICACION:
            for rel in (rel_n, rel_v):
                ruta = os.path.join(d, rel.replace("/", os.sep))
                if not os.path.exists(ruta):
                    os.makedirs(os.path.dirname(ruta), exist_ok=True)
                    with open(ruta, "wb") as fh:
                        fh.write(b"no soy un nif")
        with contextlib.redirect_stdout(_io.StringIO()) as salida:
            ok = V.falsificar(d)
        self.assertFalse(ok)
        self.assertIn("ilegible", salida.getvalue())
        self.assertIn("comprobaciones ok", salida.getvalue())

    def test_la_tabla_declara_lo_que_compara(self):
        """Una entrada sin nada que comprobar pasaria sin mirar el archivo."""
        self.assertTrue(V.FALSIFICACION)
        for rel_n, rel_v, esperado in V.FALSIFICACION:
            self.assertTrue(rel_n.lower().endswith(".nif"))
            self.assertTrue(rel_v.lower().endswith(".nif"))
            self.assertTrue(esperado, "%s no declara nada" % rel_n)
            for clave in esperado:
                self.assertIn(clave, ("fallas", "posiciones", "orientacion",
                                      "comparaciones_min"))

    def test_hay_al_menos_un_caso_que_pasa_y_uno_que_revienta(self):
        """Una tabla de solo-revienta no distingue el control de uno roto."""
        pasan = [e for _a, _b, e in V.FALSIFICACION if e.get("fallas") == 0]
        revientan = [e for _a, _b, e in V.FALSIFICACION
                     if e.get("posiciones", 0) > 0]
        self.assertTrue(pasan)
        self.assertTrue(revientan)

    def test_el_caso_identidad_afirma_cuanto_comparo(self):
        """Sin eso solo podia fallar si el lector REVIENTA, no si el lector
        NO VE NADA: con un childbody corrupto reportaba 'ok'."""
        for _a, _b, esperado in V.FALSIFICACION:
            if esperado.get("fallas") == 0:
                self.assertIn("comparaciones_min", esperado)


if __name__ == "__main__":
    unittest.main()
