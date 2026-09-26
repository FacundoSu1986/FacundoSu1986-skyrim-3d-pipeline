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

import censo_nif  # noqa: E402
import esl  # noqa: E402
import nif_nodos  # noqa: E402
import nif_sintetico  # noqa: E402
import parser_esm  # noqa: E402
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


def _correr(script, *args):
    import subprocess
    import sys
    p = subprocess.run([sys.executable, script] + list(args),
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def _correr_esl(caso, datos, *flags):
    import subprocess
    import sys
    ruta = _archivo(datos, caso, ".esp")
    script = os.path.join(RAIZ, "skills", "asset-nuevo-skyrim", "scripts",
                          "esl.py")
    p = subprocess.run([sys.executable, script, ruta] + list(flags),
                       capture_output=True, text=True)
    caso.addCleanup(lambda: os.path.exists(ruta + ".bak")
                    and os.unlink(ruta + ".bak"))
    with open(ruta, "rb") as fh:
        return p.returncode, p.stdout, fh.read(), ruta


def _plugin_con_formid(form_id):
    """El fixture de plugin con el FormID del STAT cambiado.

    El offset lo da el PARSER. `datos.index(b"STAT")` encuentra la ETIQUETA
    del GRUP, no el record -- el mismo error que ya se colo una vez en
    tests/test_parser_esm.py y dejo un test verde que no probaba nada.
    """
    import tempfile as _tf
    datos, _e = plugin_sintetico.construir()
    fd, ruta = _tf.mkstemp(suffix=".esp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(datos)
        p = parser_esm.Plugin(ruta)
        i = next(o for t, o, _s, _pr in p.recorrer() if t == "STAT")
    finally:
        if os.path.exists(ruta):
            os.unlink(ruta)
    b = bytearray(datos)
    struct.pack_into("<I", b, i + 12, form_id)
    return bytes(b)


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


def _nif_con_repetidos(nombre="Dup"):
    """raiz -> dos hijos con el MISMO nombre, en lugares distintos."""
    NS = nif_sintetico
    bloques = [NS._avobject(0, [], (0.0, 0.0, 0.0), [1, 2]),
               NS._avobject(1, [], (10.0, 0.0, 0.0), []),
               NS._avobject(1, [], (0.0, 0.0, 99.0), [])]
    strings = ["Raiz", nombre]
    h = bytearray(NS.CABECERA)
    h += struct.pack("<I", NS.VERSION) + struct.pack("<B", 1)
    h += struct.pack("<I", NS.USER) + struct.pack("<I", len(bloques))
    h += struct.pack("<I", NS.BS)
    h += NS._corta("") + NS._corta("") + NS._corta("")
    h += struct.pack("<H", 1) + NS._larga("NiNode")
    for _b in bloques:
        h += struct.pack("<H", 0)
    for b in bloques:
        h += struct.pack("<I", len(b))
    h += struct.pack("<I", len(strings))
    h += struct.pack("<I", max(len(x) for x in strings))
    for x in strings:
        h += NS._larga(x)
    h += struct.pack("<I", 0)
    return bytes(h) + b"".join(bloques)


class LoCompartidoEntreSkillsTests(unittest.TestCase):
    """Cada skill se empaqueta sola, asi que lo que las dos necesitan esta
    COPIADO en las dos (docs/DECISIONS.md, issue #75 del repo). Este test
    enumera todos los nombres que estan en las dos carpetas de scripts y exige
    que sean el mismo archivo byte a byte. La lista va escrita a mano: un
    archivo nuevo con el mismo nombre en las dos rompe el test hasta que
    alguien decida si es una copia (y lo agrega aca) o un choque de nombres."""

    COMPARTIDOS = {"correr_en_blender.py", "nif_nodos.py"}

    @staticmethod
    def _carpeta(skill):
        return os.path.join(RAIZ, "skills", skill, "scripts")

    def _nombres(self, skill):
        return {f for f in os.listdir(self._carpeta(skill)) if f.endswith(".py")}

    def test_los_compartidos_son_exactamente_estos(self):
        comunes = (self._nombres("modelo-ia-a-skyrim")
                   & self._nombres("asset-nuevo-skyrim"))
        self.assertEqual(comunes, self.COMPARTIDOS)

    def test_cada_compartido_es_el_mismo_archivo(self):
        for f in sorted(self.COMPARTIDOS):
            with self.subTest(archivo=f):
                with open(os.path.join(self._carpeta("modelo-ia-a-skyrim"), f), "rb") as fh:
                    a = fh.read()
                with open(os.path.join(self._carpeta("asset-nuevo-skyrim"), f), "rb") as fh:
                    b = fh.read()
                self.assertEqual(a, b, "las dos copias de %s divergieron: copia "
                                       "la de modelo-ia-a-skyrim sobre la otra" % f)


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
        self._coinciden(nif)

    def test_y_TAMBIEN_ante_un_nombre_repetido(self):
        """El caso que el test de arriba no cubria y donde SI divergian:
        mundo() no llevaba `vistos` y se quedaba con el ULTIMO nodo de cada
        nombre, matrices() con el PRIMERO. Con dos nodos "Dup" en (10,0,0) y
        (0,0,99) una devolvia (0,0,99) y la otra (10,0,0). En el corpus no se
        veia porque el 2,49 % de archivos con nombre repetido lo repiten en
        InvMarker, con la misma transformada."""
        nif = nif_nodos.leer(_archivo(_nif_con_repetidos(), self))
        self._coinciden(nif)
        pos, _p = nif_nodos.mundo(nif)
        self.assertEqual((10.0, 0.0, 0.0, 1.0), pos["Dup"])

    def _coinciden(self, nif):
        pos, _prof = nif_nodos.mundo(nif)
        M = nif_nodos.matrices(nif)
        self.assertEqual(set(pos), set(M))
        for nombre, p in pos.items():
            for i in range(3):
                self.assertAlmostEqual(p[i], M[nombre][i][3], places=2,
                                       msg=nombre)


class LosDosLectoresDeMundoNoSePuedenSeparaTests(unittest.TestCase):
    """El repo tiene DOS lectores de jerarquia: `nif_nodos.mundo()` --que se
    empaqueta con las skills-- y `censo_nif.Nif.mundo()` --que usa el censo--.
    Tienen que dar lo mismo sobre el mismo archivo.

    Este test existe porque no lo daban, y ninguna de las dos suites lo veia:
    la divergencia estaba entre un archivo de una rama y un archivo de la
    otra, y solo aparecio al probar la combinacion en un merge local antes de
    mergear. Medido entonces: 13 de 1.200 archivos del corpus daban respuestas
    distintas segun cual se usara -- los que repiten InvMarker con
    transformadas distintas, como armor/daedric/daedricbootsf_1.nif.
    """

    def _comparar(self, datos):
        ruta = _archivo(datos, self)
        a = censo_nif.Nif(ruta).mundo()
        b, _prof = nif_nodos.mundo(nif_nodos.leer(ruta))
        self.assertEqual(a, b)

    def test_sobre_el_fixture_normal(self):
        datos, _e = nif_sintetico.construir()
        self._comparar(datos)

    def test_y_sobre_uno_con_un_NOMBRE_REPETIDO(self):
        """El caso donde divergian: uno se quedaba con el primer nodo de cada
        nombre y el otro con el ultimo."""
        self._comparar(_nif_con_repetidos())

    def test_y_con_un_subarbol_compartido(self):
        """El otro caso donde el orden del recorrido decide: un bloque al que
        llegan dos padres."""
        NS = nif_sintetico
        bloques = [NS._avobject(0, [], (0.0, 0.0, 0.0), [1, 2]),
                   NS._avobject(1, [], (1.0, 0.0, 0.0), [3]),
                   NS._avobject(2, [], (0.0, 1.0, 0.0), [3]),
                   NS._avobject(3, [], (0.0, 0.0, 1.0), [])]
        strings = ["Raiz", "A", "B", "Compartido"]
        h = bytearray(NS.CABECERA)
        h += struct.pack("<I", NS.VERSION) + struct.pack("<B", 1)
        h += struct.pack("<I", NS.USER) + struct.pack("<I", len(bloques))
        h += struct.pack("<I", NS.BS)
        h += NS._corta("") + NS._corta("") + NS._corta("")
        h += struct.pack("<H", 1) + NS._larga("NiNode")
        for _b in bloques:
            h += struct.pack("<H", 0)
        for b in bloques:
            h += struct.pack("<I", len(b))
        h += struct.pack("<I", len(strings))
        h += struct.pack("<I", max(len(x) for x in strings))
        for x in strings:
            h += NS._larga(x)
        h += struct.pack("<I", 0)
        self._comparar(bytes(h) + b"".join(bloques))

    def test_las_dos_listas_de_TIPOS_NODO_son_la_misma(self):
        """Si divergieran, los dos lectores verian juegos de nodos distintos
        y el test de arriba fallaria por otra razon que la que dice."""
        self.assertEqual(set(censo_nif.TIPOS_NODO), set(nif_nodos.TIPOS_NODO))


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


class ElRangoDeEslEstaMedidoTests(unittest.TestCase):
    """El script exigia 0x800 <= indice <= 0xFFF a TODOS los records no-TES4.
    Medido sobre los 3 `.esl` de una instalacion, eso esta mal dos veces."""

    def test_un_override_no_entra_en_la_cuenta_del_rango(self):
        """Un record cuyo indice de mod apunta a un master conserva el FormID
        del master. `ccQDRSSE001-SurvivalMode.esl` --un ESL que el juego
        carga-- trae 165, y todos se reportaban como fuera de rango."""
        nuevos, over = esl.clasificar([0x00000001, 0x01000002, 0x05000800], 5)
        self.assertEqual([0x05000800], nuevos)
        self.assertEqual([0x00000001, 0x01000002], over)

    def test_sin_masters_no_hay_overrides(self):
        """El par: si clasificar() mandara todo a overrides, el rango no se
        comprobaria nunca."""
        nuevos, over = esl.clasificar([0x00000001, 0x00000002], 0)
        self.assertEqual(2, len(nuevos))
        self.assertEqual([], over)

    def test_el_piso_del_creation_kit_no_bloquea(self):
        """`_ResourcePack.esl` trae 368 records propios por debajo de 0x800 y
        el juego lo carga: el piso es del CK, no del motor."""
        self.assertLess(esl.PISO_CREATION_KIT, esl.TECHO_ESL)
        datos = _plugin_con_formid(0x00000001)
        codigo, salida, _d, _r = _correr_esl(self, datos, "--marcar")
        self.assertEqual(0, codigo, salida)
        self.assertIn("por debajo", salida)

    def test_pero_el_techo_SI_bloquea(self):
        """El par del de arriba, y el unico limite que el motor impone."""
        datos = _plugin_con_formid(0x00001000)
        codigo, salida, despues, _r = _correr_esl(self, datos, "--marcar")
        self.assertEqual(1, codigo, salida)
        self.assertEqual(datos, despues, "escribio con un record fuera")

    def test_los_MAST_se_leen_del_TES4(self):
        """Con NOMBRES, no la lista vacia. La primera version de este test
        afirmaba `== []` sobre un fixture sin masters: pasaba con masters()
        devolviendo siempre [], que es justo el bug que tendria que atajar.
        La bateria de mutaciones lo delato."""
        datos, esperado = plugin_sintetico.construir(
            masters=("Skyrim.esm", "Update.esm", "Dawnguard.esm"))
        self.assertEqual(esperado["masters"], esl.masters(bytearray(datos)))

    def test_y_sin_masters_da_la_lista_vacia(self):
        """El par: si masters() inventara nombres, esto lo veria."""
        datos, _e = plugin_sintetico.construir()
        self.assertEqual([], esl.masters(bytearray(datos)))

    def test_con_masters_un_record_de_indice_bajo_es_override(self):
        """La cadena entera: los MAST del TES4 deciden que se clasifica como
        override, y un override no entra en la comprobacion de rango."""
        datos, _e = plugin_sintetico.construir(
            masters=("Skyrim.esm", "Update.esm"))
        ids, cerro = esl.recorrer_formids(bytearray(datos))
        self.assertTrue(cerro)
        nuevos, over = esl.clasificar(ids, len(esl.masters(bytearray(datos))))
        self.assertEqual(2, len(over), ids)
        self.assertEqual([], nuevos)


class LosCliNoRevientanTests(unittest.TestCase):
    """Un archivo que no se puede leer no es un detalle de implementacion: es
    el resultado. Los dos scripts salian por traceback."""

    def test_nif_nodos_con_un_archivo_que_no_existe(self):
        codigo, salida = _correr(os.path.join(
            RAIZ, "skills", "asset-nuevo-skyrim", "scripts", "nif_nodos.py"),
            os.path.join(tempfile.gettempdir(), "no_existe_xyz.nif"))
        self.assertEqual(1, codigo)
        self.assertIn("no se pudo leer", salida)
        self.assertNotIn("Traceback", salida)

    def test_nif_nodos_con_un_archivo_que_no_es_un_nif(self):
        ruta = _archivo(b"no soy un nif", self)
        codigo, salida = _correr(os.path.join(
            RAIZ, "skills", "asset-nuevo-skyrim", "scripts", "nif_nodos.py"),
            ruta)
        self.assertEqual(1, codigo)
        self.assertNotIn("Traceback", salida)

    def test_pero_con_un_nif_sano_sale_0(self):
        """El par: si devolviera 1 siempre, los de arriba no probarian nada."""
        datos, _e = nif_sintetico.construir()
        codigo, salida = _correr(os.path.join(
            RAIZ, "skills", "asset-nuevo-skyrim", "scripts", "nif_nodos.py"),
            _archivo(datos, self))
        self.assertEqual(0, codigo, salida)

    def test_esl_con_una_cabecera_truncada(self):
        ruta = _archivo(b"TES4", self, ".esp")
        codigo, salida = _correr(os.path.join(
            RAIZ, "skills", "asset-nuevo-skyrim", "scripts", "esl.py"), ruta)
        self.assertEqual(1, codigo)
        self.assertNotIn("Traceback", salida)


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
        for nombre, esperado in esl.AUTOTEST:
            self.assertTrue(nombre.lower().endswith((".esm", ".esp", ".esl")))
            self.assertTrue(esperado, "%s no declara nada" % nombre)
            for clave in esperado:
                self.assertIn(clave, ("records", "masters", "nuevos",
                                      "overrides", "sobre_el_techo",
                                      "bajo_el_piso_del_ck"))

    def test_y_al_menos_un_ESL_real_con_overrides(self):
        """Un ESL que el juego carga y que TIENE overrides es lo unico que
        prueba que el rango no se les aplica. Sin esa entrada, la correccion
        no esta anclada a ningun archivo."""
        con_over = [e for _n, e in esl.AUTOTEST if e.get("overrides", 0) > 0]
        self.assertTrue(con_over, "falta un ESL con overrides en la tabla")
        bajo = [e for _n, e in esl.AUTOTEST
                if e.get("bajo_el_piso_del_ck", 0) > 0]
        self.assertTrue(bajo, "falta el ESL que vive por debajo de 0x800")

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
