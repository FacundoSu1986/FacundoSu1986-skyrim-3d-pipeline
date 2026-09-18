# -*- coding: utf-8 -*-
"""El contrato del lado de las texturas (#3).

Un NIF que apunta a texturas que no existen pasa TODAS sus reglas de NIF. Por
eso el contrato tiene dos mitades y esta es la segunda.

Las DDS se construyen byte a byte reutilizando el fixture de
tests/test_parser_dds.py, asi que esto corre en CI sin corpus.
"""
import io
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from _paths import preparar_path

preparar_path()

import nif_sintetico  # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_RAIZ, "fixtures") not in sys.path:
    sys.path.insert(0, os.path.join(_RAIZ, "fixtures"))

import comparar  # noqa: E402
from test_parser_dds import dds  # noqa: E402

DXT1 = b"DXT1"
DXT5 = b"DXT5"


def _tam_bloques(ancho, alto, mips, bpb):
    """Bytes de la cadena, contados a mano. Si la cuenta se hace con la formula
    del parser, el test no prueba nada."""
    total = 0
    w, h = ancho, alto
    for _ in range(mips):
        total += ((w + 3) // 4) * ((h + 3) // 4) * bpb
        w = max(1, w // 2)
        h = max(1, h // 2)
    return total


class ResolverRutasTests(unittest.TestCase):
    """Las cuatro formas salieron de medir el corpus, no de suponer."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = self.tmp.name
        destino = os.path.join(self.raiz, "clutter", "signage")
        os.makedirs(destino)
        with open(os.path.join(destino, "cartel.dds"), "wb") as fh:
            fh.write(b"no importa el contenido")

    def _resuelve(self, declarada):
        return comparar.resolver_textura(declarada, self.raiz) is not None

    def test_con_prefijo_textures(self):
        self.assertTrue(self._resuelve(r"textures\clutter\signage\cartel.dds"))

    def test_relativa_sin_prefijo(self):
        """El 12,2 % del corpus. Es la forma que casi convierto en defecto."""
        self.assertTrue(self._resuelve(r"clutter\signage\cartel.dds"))

    def test_con_prefijo_data(self):
        self.assertTrue(
            self._resuelve(r"data\textures\clutter\signage\cartel.dds"))

    def test_ruta_del_arbol_de_build_de_bethesda(self):
        """La cuarta forma. Rescata 133 de las 393 que no resolvian, y no la
        habria escrito sin mirar que eran esas rutas."""
        self.assertTrue(self._resuelve(
            r"skyrimhd\build\pc\data\textures\clutter\signage\cartel.dds"))

    def test_mayusculas_no_importan(self):
        self.assertTrue(self._resuelve(r"TEXTURES\CLUTTER\SIGNAGE\CARTEL.DDS"))

    def test_mayusculas_en_disco_resuelven(self):
        """En sistemas case-sensitive (Linux), si el archivo en disco tiene
        mayusculas (como los extraidos de Bethesda: RoadSignsCities01.dds),
        la busqueda insensible debe encontrarlo aunque la ruta declarada
        use minusculas o mayusculas distintas."""
        destino = os.path.join(self.raiz, "ClutterDir", "SignageSub")
        os.makedirs(destino)
        with open(os.path.join(destino, "RoadSign.DDS"), "wb") as fh:
            fh.write(b"contenido")

        # Declarada en minusculas contra disco con mayusculas
        self.assertTrue(self._resuelve(r"textures\clutterdir\signagesub\roadsign.dds"))
        # Declarada con mayusculas exactas
        self.assertTrue(self._resuelve(r"textures\ClutterDir\SignageSub\RoadSign.DDS"))
        # Declarada con caso invertido
        self.assertTrue(self._resuelve(r"TEXTURES\CLUTTERDIR\SIGNAGESUB\ROADSIGN.DDS"))

    def test_path_traversal_rechazado(self):
        # Crear un archivo secreto fuera de self.raiz para asegurar que
        # NO se resuelva incluso existiendo fisicamente en disco.
        padre = os.path.dirname(self.raiz)
        secreto = os.path.join(padre, "secreto.dds")
        with open(secreto, "wb") as fh:
            fh.write(b"contenido secreto")
        self.addCleanup(lambda: os.path.exists(secreto) and os.unlink(secreto))

        self.assertFalse(self._resuelve(r"..\secreto.dds"))
        self.assertFalse(self._resuelve(r"textures\..\..\secreto.dds"))
        self.assertFalse(self._resuelve(r"/etc/passwd"))
        self.assertFalse(self._resuelve(r"C:\Windows\System32\drivers\etc\hosts"))

    def test_lo_que_no_existe_no_resuelve(self):
        """El par de los de arriba: si resolviera cualquier cosa, los otros
        cinco pasarian sin probar nada."""
        self.assertFalse(self._resuelve(r"textures\clutter\signage\otro.dds"))
        self.assertFalse(self._resuelve("NOR"))
        self.assertFalse(self._resuelve(""))


class ReglasDdsTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name

    def _claves_malas(self, ruta, declarada=None):
        return {c for ok, c, _d, _e in comparar.reglas_dds(ruta, declarada)
                if not ok}

    def _dxt(self, nombre, ancho, alto, mips, fourcc, bpb, sobra=0):
        cuerpo = _tam_bloques(ancho, alto, mips, bpb) + sobra
        return dds(self.dir, nombre, cuerpo, ancho=ancho, alto=alto,
                   mips=mips, fourcc=fourcc)

    def test_una_dds_sana_pasa_todo(self):
        ruta = self._dxt("difusa.dds", 64, 64, 7, DXT5, 16)
        self.assertEqual(set(), self._claves_malas(ruta))

    def test_tamano_que_no_cuadra_reprueba(self):
        ruta = self._dxt("difusa.dds", 64, 64, 7, DXT5, 16, sobra=32)
        self.assertIn("dds_tamano", self._claves_malas(ruta))

    def test_lado_que_no_es_potencia_de_dos_reprueba(self):
        """0 de 32.241 texturas vanilla lo violan. Es el invariante mas limpio
        del corpus, y el unico que se puede exigir sin matices."""
        ruta = self._dxt("difusa.dds", 100, 64, 1, DXT5, 16)
        self.assertIn("dds_potencia_de_dos", self._claves_malas(ruta))

    def test_dimension_cero_reprueba(self):
        """Una dimension 0 no es potencia de dos ni tiene tamano predecible valido."""
        ruta_w0 = self._dxt("cero_ancho.dds", 0, 64, 1, DXT5, 16)
        self.assertIn("dds_potencia_de_dos", self._claves_malas(ruta_w0))
        self.assertIn("dds_tamano", self._claves_malas(ruta_w0))

        ruta_h0 = self._dxt("cero_alto.dds", 64, 0, 1, DXT5, 16)
        self.assertIn("dds_potencia_de_dos", self._claves_malas(ruta_h0))
        self.assertIn("dds_tamano", self._claves_malas(ruta_h0))

        ruta_ambas0 = self._dxt("cero_ambas.dds", 0, 0, 1, DXT5, 16)
        self.assertIn("dds_potencia_de_dos", self._claves_malas(ruta_ambas0))
        self.assertIn("dds_tamano", self._claves_malas(ruta_ambas0))

    def test_parser_dds_cero_dimensiones_tamano_cuadra_false(self):
        """Un DDS con dimensiones 0x0 o ancho 0 no debe predecir tamano ni tener tamano_cuadra True."""
        import parser_dds
        ruta = self._dxt("cero.dds", 0, 64, 1, DXT5, 16)
        d = parser_dds.leer(ruta)
        self.assertIsNone(d["bytes_esperados"])
        self.assertFalse(d["tamano_cuadra"])
        self.assertFalse(d["potencia_de_dos"])
        self.assertEqual([0, 64], d["mip_mas_chico"])

    def test_formato_no_predecible_reprueba_dds_tamano(self):
        """Si el formato no tiene formula de tamano (FourCC desconocido),
        bytes_esperados es None y dds_tamano no puede aprobar."""
        ruta_desconocida = self._dxt("formato_raro.dds", 64, 64, 1, b"JUNK", 16)
        self.assertIn("dds_tamano", self._claves_malas(ruta_desconocida))

    def test_normal_en_dxt1_reprueba(self):
        """DXT1 no tiene canal alfa, y el alfa de un _n lleva el especular.
        0 de 12.075 normales del corpus usan un formato sin alfa."""
        ruta = self._dxt("piedra_n.dds", 64, 64, 7, DXT1, 8)
        self.assertIn("normal_con_alfa", self._claves_malas(ruta))

    def test_normal_en_dxt5_pasa(self):
        ruta = self._dxt("piedra_n.dds", 64, 64, 7, DXT5, 16)
        self.assertNotIn("normal_con_alfa", self._claves_malas(ruta))

    def test_normal_sin_comprimir_con_alfa_pasa(self):
        """El caso que obligo a reescribir la regla. Estaba como
        "formato == DXT5" y reprobaba un normal sin comprimir de 32 bpp, que
        tiene los cuatro canales a precision completa.

        El error era de criterio: para BC7 ya habiamos dicho que 0 de 32.241 es
        lo que Bethesda USO, no lo que el motor EXIGE, y lo dejamos como
        observacion. Con el _n se habia usado la otra vara."""
        cuerpo = 64 * 64 * 4
        ruta = dds(self.dir, "piedra_n.dds", cuerpo, ancho=64, alto=64,
                   mips=1, bits=32, alfa_mask=0xFF000000)
        self.assertNotIn("normal_con_alfa", self._claves_malas(ruta))

    def test_normal_sin_comprimir_sin_canal_alfa_reprueba(self):
        """El par del de arriba: un DDS de 24 bpp no tiene bytes para el alfa.
        Con la mascara alfa declarada (inconsistente) el parser lo daba por
        bueno y la regla pasaba. Tiene que reprobar: el especular de un _n
        vive en ese canal."""
        cuerpo = 64 * 64 * 3
        ruta = dds(self.dir, "piedra_n.dds", cuerpo, ancho=64, alto=64,
                   mips=1, bits=24, alfa_mask=0xFF000000)
        self.assertIn("normal_con_alfa", self._claves_malas(ruta))

    def test_la_regla_del_normal_mira_el_nombre_declarado(self):
        """La ruta en disco puede ser un temporal con cualquier nombre; lo que
        decide es como la declara el NIF."""
        ruta = self._dxt("cualquiera.dds", 64, 64, 7, DXT1, 8)
        self.assertNotIn("normal_con_alfa", self._claves_malas(ruta))
        self.assertIn("normal_con_alfa",
                      self._claves_malas(ruta, r"textures\x\piedra_n.dds"))

    def test_archivo_que_no_es_dds_reprueba_por_parseo(self):
        ruta = os.path.join(self.dir, "mentira.dds")
        with open(ruta, "wb") as fh:
            fh.write(b"esto no es un DDS")
        self.assertEqual({"dds_parsea"}, self._claves_malas(ruta))

    def test_cada_regla_de_dds_reprueba_en_algun_caso(self):
        """Enumera: una regla de textura que nada reprueba es decoracion.
        Es el mismo test que atrapo nodo_raiz_conocido en el lado del NIF."""
        casos = (
            (self._dxt("a.dds", 64, 64, 7, DXT5, 16, sobra=32), None),
            (self._dxt("b.dds", 100, 64, 1, DXT5, 16), None),
            (self._dxt("c_n.dds", 64, 64, 7, DXT1, 8), None),
        )
        vistas = set()
        for ruta, decl in casos:
            vistas |= self._claves_malas(ruta, decl)

        sana = self._dxt("sana_n.dds", 64, 64, 7, DXT5, 16)
        todas = {c for _ok, c, _d, _e in comparar.reglas_dds(sana)}
        nunca = todas - vistas
        self.assertEqual(
            set(), nunca,
            "reglas de DDS que no reprueban en ningun caso: %s" % nunca)


class EvidenciaDeLasReglasDeTexturaTests(unittest.TestCase):
    """Misma disciplina que el lado del NIF: sin numero atras, no es regla."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ruta = dds(self.tmp.name, "x_n.dds",
                        _tam_bloques(64, 64, 7, 16),
                        ancho=64, alto=64, mips=7, fourcc=DXT5)

    def test_ninguna_regla_de_dds_va_sin_su_medicion(self):
        flojas = [c for _ok, c, _d, ev in comparar.reglas_dds(self.ruta)
                  if not ev or not any(ch.isdigit() for ch in ev)]
        self.assertEqual([], flojas,
                         "reglas de DDS sin evidencia numerica: %s" % flojas)

    def test_las_observaciones_de_dds_dicen_por_que_no_son_reglas(self):
        for clave, _det, por_que in comparar.observaciones_dds(self.ruta):
            self.assertTrue(
                por_que and any(ch.isdigit() for ch in por_que),
                "la observacion %s no trae numeros" % clave)

    def test_bc7_no_es_una_regla(self):
        """SE admite BC7 aunque Bethesda no lo haya usado en un solo archivo.
        Convertir '0 de 32.241' en prohibicion seria confundir lo que el juego
        acepta con lo que Bethesda eligio."""
        claves = {c for _ok, c, _d, _e in comparar.reglas_dds(self.ruta)}
        self.assertNotIn("dds_formato", claves)
        observadas = {c for c, _d, _p in comparar.observaciones_dds(self.ruta)}
        self.assertIn("dds_formato", observadas)


class ReglasTexturasDelNifTests(unittest.TestCase):
    """Comprueba reglas_texturas_del_nif y modo_contrato con texturas."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz_texturas = os.path.join(self.tmp.name, "textures")
        os.makedirs(self.raiz_texturas)

    def _crear_nif(self, tex_paths):
        datos, _ = nif_sintetico.construir()
        for t in tex_paths:
            datos += b"\x00" + t.encode("cp1252") + b"\x00"
        ruta = os.path.join(self.tmp.name, "prueba.nif")
        with open(ruta, "wb") as fh:
            fh.write(datos)
        return ruta

    def test_nif_invalido_no_rompe_reglas_texturas(self):
        ruta_roto = os.path.join(self.tmp.name, "roto.nif")
        with open(ruta_roto, "wb") as fh:
            fh.write(b"not a valid nif")
        res = comparar.reglas_texturas_del_nif(ruta_roto, self.raiz_texturas)
        self.assertEqual([], res)

    def test_modo_contrato_con_nif_invalido_y_raiz_no_crashea(self):
        ruta_roto = os.path.join(self.tmp.name, "roto.nif")
        with open(ruta_roto, "wb") as fh:
            fh.write(b"not a valid nif")
        with patch("sys.stdout", new=io.StringIO()):
            ret = comparar.modo_contrato(ruta_roto, self.raiz_texturas)
        self.assertEqual(1, ret)

    def test_textura_inexistente_reporta_textura_existe(self):
        nif_ruta = self._crear_nif([r"textures\clutter\inexistente.dds"])
        res = comparar.reglas_texturas_del_nif(nif_ruta, self.raiz_texturas)
        claves = [c for ok, c, _d, _ev in res if not ok]
        self.assertIn("textura_existe", claves)
        evidencias = [ev for ok, c, _d, ev in res if c == "textura_existe"]
        self.assertTrue(evidencias and any(ch.isdigit() for ch in evidencias[0]))

    def test_textura_existente_y_valida_pasa(self):
        dir_dds = os.path.join(self.raiz_texturas, "clutter")
        os.makedirs(dir_dds)
        dds(dir_dds, "sign.dds", _tam_bloques(64, 64, 7, 16),
            ancho=64, alto=64, mips=7, fourcc=DXT5)
        nif_ruta = self._crear_nif([r"textures\clutter\sign.dds"])
        res = comparar.reglas_texturas_del_nif(nif_ruta, self.raiz_texturas)
        fallos = [c for ok, c, _d, _ev in res if not ok]
        self.assertEqual([], fallos)

    def test_parsers_coinciden_en_dds_mayusculas(self):
        """Los dos parsers (census/parser_nif y skill/censo_nif) deben coincidir
        en detectar extensiones .DDS en mayusculas."""
        import censo_nif
        import parser_nif
        nif_ruta = self._crear_nif([r"textures\clutter\Sign01.DDS"])
        p_nif = parser_nif.Nif(nif_ruta)
        c_nif = censo_nif.Nif(nif_ruta)
        self.assertIn(r"textures\clutter\Sign01.DDS", p_nif.texturas())
        self.assertIn(r"textures\clutter\Sign01.DDS", c_nif.texturas())

    def test_limpiar_cache_dir_vacia_cache(self):
        comparar._listar_dir_lower(self.raiz_texturas)
        self.assertTrue(len(comparar._DIR_CACHE) > 0)
        comparar.limpiar_cache_dir()
        self.assertEqual(0, len(comparar._DIR_CACHE))


if __name__ == "__main__":
    unittest.main()
