# -*- coding: utf-8 -*-
"""Tres desacuerdos entre dos lecturas del mismo formato (issues #18, #19, #20).

El repo tiene tres parsers de NIF: el completo (`census/parser_nif.py`), la
semilla de la skill (`censo_nif.py`) y el lector de nodos (`nif_nodos.py`).
Cuando dos leen el mismo campo distinto, uno de los dos esta mal y el corpus no
siempre lo delata -- por eso hay tests, y por eso estan escritos para enumerar
la familia en vez de fijar el caso que ya encontramos.
"""
import os
import struct
import tempfile
import unittest

from _paths import preparar_path

preparar_path()

import censo_nif  # noqa: E402
import verificar  # noqa: E402
import nif_nodos  # noqa: E402
import parser_nif  # noqa: E402
import nif_sintetico  # noqa: E402


def _con_bs(datos, bs):
    """Los mismos bytes con otra BS version. El campo esta despues de la linea
    magica: version(4) + endian(1) + user(4) + n_bloques(4)."""
    i = datos.index(bytes([10])) + 1 + 4 + 1 + 4 + 4
    b = bytearray(datos)
    struct.pack_into("<I", b, i, bs)
    return bytes(b)


def _archivo(datos):
    fd, ruta = tempfile.mkstemp(suffix=".nif")
    with os.fdopen(fd, "wb") as fh:
        fh.write(datos)
    return ruta


class TiposDeShapeTests(unittest.TestCase):
    """#19: la semilla iteraba solo BSTriShape."""

    def test_las_dos_listas_de_tipos_de_shape_son_la_misma(self):
        """No compara contra una lista escrita a mano: compara los dos parsers
        entre si. Si manana aparece un cuarto tipo y se agrega a uno solo, cae
        aca, que es el modo en que se rompio la primera vez."""
        self.assertEqual(
            tuple(censo_nif.TIPOS_SHAPE), tuple(parser_nif.TIPOS_SHAPE),
            "censo_nif y parser_nif no coinciden en que bloques son shapes: "
            "el que se quede corto reporta n_shapes=0 sin avisar")

    def test_bsdynamictrishape_cuenta_como_shape(self):
        """3.803 archivos del corpus (17 %) traen BSDynamicTriShape y ningun
        BSTriShape. La semilla los reportaba con n_shapes = 0."""
        self.assertIn("BSDynamicTriShape", censo_nif.TIPOS_SHAPE)


class TiposDeNodoTests(unittest.TestCase):
    """Las tres listas de TIPOS_NODO, y el tipo que faltaba en las tres."""

    def _listas(self):
        return {"census/parser_nif.py": parser_nif.TIPOS_NODO,
                "skills/.../censo_nif.py": censo_nif.TIPOS_NODO,
                "skills/.../nif_nodos.py": nif_nodos.TIPOS_NODO}

    def test_las_tres_listas_de_tipos_de_nodo_son_la_misma(self):
        """Ya estaban separadas: parser_nif tenia BSRangeNode y los otros dos
        no. Compara las tres ENTRE SI, no contra una lista escrita a mano: si
        manana se agrega un tipo a una sola, cae aca."""
        listas = self._listas()
        base = set(next(iter(listas.values())))
        for nombre, lista in listas.items():
            self.assertEqual(
                base, set(lista),
                "%s no coincide con las otras: %s"
                % (nombre, base ^ set(lista)))

    def test_bsmasterparticlesystem_es_un_nodo(self):
        """93 archivos del corpus lo traen como raiz. El layout de NiNode
        parsea coherente en 93 de 93 bloques, y agregarlo recupera 93 nodos y
        94 hijos que se salteaban, sin una sola evidencia nueva en
        verificar.py. BSFurnitureMarkerNode, el caso contrario, rompia 123."""
        for nombre, lista in self._listas().items():
            self.assertIn("BSMasterParticleSystem", lista, nombre)

    def test_una_raiz_de_ese_tipo_se_recorre_como_nodo(self):
        """No alcanza con que este en la lista: el arbol tiene que recorrerse.
        Enumera los tres parsers, como el test de la cabecera BS>=130, porque
        censo_nif y nif_nodos NO comparten el recorrido con parser_nif: un
        arreglo en uno no tapa a los otros dos. Y confronta la verdad
        declarada del fixture con los bytes en las dos raices: si `esperado`
        miente, esto falla contra el archivo, no contra otra lista a mano."""
        entradas = (
            ("census/parser_nif.py", lambda r: parser_nif.Nif(r).nodos()),
            ("skills/.../censo_nif.py", lambda r: censo_nif.Nif(r).nodos()),
            ("skills/.../nif_nodos.py", lambda r: nif_nodos.leer(r)["nodos"]),
        )
        conteos = {}
        for tipo in ("BSFadeNode", "BSMasterParticleSystem"):
            datos, esperado = nif_sintetico.construir(tipo)
            self.assertEqual(tipo, esperado["raiz"],
                             "el fixture no declara la verdad que construyo")
            ruta = _archivo(datos)
            try:
                for nombre, abrir in entradas:
                    nodos = abrir(ruta)
                    self.assertEqual(
                        tipo, nodos[0]["tipo"],
                        "%s no lee la raiz %s como nodo" % (nombre, tipo))
                    conteos[(tipo, nombre)] = (
                        len(nodos),
                        sum(len(x["hijos"]) for x in nodos.values()))
                for nombre, nif in (
                        ("census/parser_nif.py", parser_nif.Nif(ruta)),
                        ("skills/.../censo_nif.py", censo_nif.Nif(ruta))):
                    self.assertEqual(
                        esperado["cuenta_tipos"], nif.cuenta_tipos(),
                        "%s: la verdad declarada del fixture no coincide con "
                        "el archivo con raiz %s" % (nombre, tipo))
            finally:
                os.unlink(ruta)
        self.assertEqual(
            1, len(set(conteos.values())),
            "los tres recorridos no coinciden: %s" % conteos)
        self.assertNotEqual((0, 0), next(iter(conteos.values())))

    def test_bsfurnituremarkernode_sigue_afuera(self):
        """El par del test de arriba. Si 'agregar tipos' fuera siempre bueno,
        este repo no habria tenido que sacar uno que rompia 123 archivos."""
        for nombre, lista in self._listas().items():
            self.assertNotIn("BSFurnitureMarkerNode", lista, nombre)


class VersionBsNoValidadaTests(unittest.TestCase):
    """#18: dos lecturas distintas de la cabecera para BS>=130, ninguna
    validada -- el corpus tiene 22.393 con BS=100, uno con BS=83 y cero con
    BS>=130. Adivinar el largo de un campo de cabecera corre TODOS los offsets
    de bloque, que es la familia del bug de 'pesos por vertice = 1035'."""

    def setUp(self):
        self.datos, _ = nif_sintetico.construir()
        self.rutas = []

    def tearDown(self):
        for r in self.rutas:
            try:
                os.unlink(r)
            except OSError:
                pass

    def _ruta(self, datos):
        r = _archivo(datos)
        self.rutas.append(r)
        return r

    def test_bs_100_se_lee_en_los_tres(self):
        """El par del test de abajo: si los tres rechazaran todo, el otro test
        pasaria sin probar nada."""
        ruta = self._ruta(self.datos)
        self.assertTrue(parser_nif.Nif(ruta).bloques)
        self.assertTrue(censo_nif.Nif(ruta).bloques)
        self.assertTrue(nif_nodos.leer(ruta))

    def test_ningun_parser_adivina_la_cabecera_de_bs_130(self):
        """Enumera los tres puntos de entrada. Un cuarto parser que copie el
        patron y no ponga la guarda cae aca en cuanto se agregue a la lista."""
        entradas = (
            ("census/parser_nif.py", lambda r: parser_nif.Nif(r)),
            ("skills/.../censo_nif.py", lambda r: censo_nif.Nif(r)),
            ("skills/.../nif_nodos.py", lambda r: nif_nodos.leer(r)),
        )
        for bs in (130, 155):
            ruta = self._ruta(_con_bs(self.datos, bs))
            for nombre, abrir in entradas:
                with self.assertRaises(Exception, msg=nombre) as cm:
                    abrir(ruta)
                self.assertIn(
                    "130", str(cm.exception),
                    "%s con BS=%d no explica por que no lee: %s"
                    % (nombre, bs, cm.exception))


def _nif_con_rigidbody(tam, n_constraints):
    """NIF minimo con un solo bhkRigidBody del tamano pedido.

    Bytes construidos a mano, cero material con copyright: la misma tecnica de
    tests/nif_sintetico.py y tests/test_parser_dds.py.
    """
    tipos = ["BSFadeNode", "bhkRigidBody"]
    raiz = nif_sintetico._avobject(0, [], (0.0, 0.0, 0.0), [])
    rb = bytearray(tam)
    struct.pack_into("<i", rb, 0, -1)             # sin shape asociado
    rb[4] = 1                                     # layer
    struct.pack_into("<f", rb, 180, 5.0)          # masa
    rb[224] = 1                                   # motion system
    if tam >= 248:
        struct.pack_into("<I", rb, 244, n_constraints)
    bloques = [raiz, bytes(rb)]

    h = bytearray(nif_sintetico.CABECERA)
    h += struct.pack("<I", nif_sintetico.VERSION) + struct.pack("<B", 1)
    h += struct.pack("<I", nif_sintetico.USER)
    h += struct.pack("<I", len(bloques))
    h += struct.pack("<I", nif_sintetico.BS)
    h += bytes(3)                                 # author/process/export vacios
    h += struct.pack("<H", len(tipos))
    for t in tipos:
        h += struct.pack("<I", len(t)) + t.encode("cp1252")
    h += struct.pack("<2H", 0, 1)
    h += struct.pack("<2I", len(bloques[0]), len(bloques[1]))
    nombre = nif_sintetico.RAIZ_NOMBRE
    h += struct.pack("<I", 1) + struct.pack("<I", len(nombre))
    h += struct.pack("<I", len(nombre)) + nombre.encode("cp1252")
    h += struct.pack("<I", 0)                     # sin grupos
    return bytes(h) + bloques[0] + bloques[1]


class UmbralDeRigidBodyTests(unittest.TestCase):
    """#20: dos lecturas del tamano de bhkRigidBody que no coincidian.

    El parser leia campos con s >= 246 y el verificador exige la identidad
    s == 250 + 4*numConstraints. Subir el piso a 250 cerro la franja 246..249
    pero NO el desacuerdo: con s=251 y c=0 el parser seguia publicando
    layer/masa/motion de un bloque que el verificador marcaba como roto.

    Una version anterior de este test leia el codigo fuente buscando la cadena
    "if s >= 250:". Pasaba en verde con el desacuerdo adentro, porque comprobaba
    que el arreglo estuviera ESCRITO y no que funcionara. Este ejecuta los dos
    lados sobre los mismos bytes.
    """

    def _rutas(self, datos):
        fd, ruta = tempfile.mkstemp(suffix=".nif")
        with os.fdopen(fd, "wb") as fh:
            fh.write(datos)
        self.addCleanup(lambda: os.path.exists(ruta) and os.unlink(ruta))
        return ruta

    def _lee_y_acepta(self, tam, c):
        ruta = self._rutas(_nif_con_rigidbody(tam, c))
        lee = parser_nif.Nif(ruta).colision_info()["layer"] is not None
        _, ev = verificar._chequear(ruta)
        acepta = not any(cat == "rigidbody_size" for cat, _ in ev)
        return lee, acepta

    def test_parser_y_verificador_coinciden_en_todo_el_rango(self):
        """Enumera la familia entera en vez del caso que encontro Codex.
        Un arreglo que tape s=251 y deje s=255 cae aca igual."""
        desacuerdos = []
        for c in range(0, 6):
            for tam in range(246, 278):
                lee, acepta = self._lee_y_acepta(tam, c)
                if lee != acepta:
                    desacuerdos.append((tam, c, lee, acepta))
        self.assertEqual(
            [], desacuerdos,
            "parser y verificador discrepan en %d de 192 combinaciones: %s"
            % (len(desacuerdos), desacuerdos[:6]))

    def test_el_tamano_valido_si_se_lee(self):
        """El par del test de arriba: si el parser rechazara todo, coincidirian
        los dos en 'no' y el test pasaria sin probar nada."""
        for tam, c in ((250, 0), (254, 1), (262, 3), (266, 4)):
            lee, acepta = self._lee_y_acepta(tam, c)
            self.assertTrue(lee, "tam=%d c=%d deberia leerse" % (tam, c))
            self.assertTrue(acepta, "tam=%d c=%d deberia aceptarse" % (tam, c))

    def test_el_caso_exacto_del_review(self):
        """s=251 con c=0: declarado >= 250 pero fuera de la identidad."""
        lee, acepta = self._lee_y_acepta(251, 0)
        self.assertFalse(acepta)
        self.assertFalse(
            lee, "el parser publica colision de un bloque que el verificador "
                 "rechaza: el tamano no garantiza el layout de los offsets")


if __name__ == "__main__":
    unittest.main()
