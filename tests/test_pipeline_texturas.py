# -*- coding: utf-8 -*-
"""La fase PROCESS_TEXTURES: lo que convierte, lo que verifica y lo que rechaza.

Disciplina de este repo, aplicada a texturas:

  * cada conversión de canal declara de dónde sale su número, y si no tiene
    número se declara heurística y se informa en el reporte;
  * cada regla tiene que poder fallar: `test_un_dds_que_no_pasa_el_contrato`
    y `test_el_validador_detecta_un_dds_roto_de_verdad` rompen un DDS a
    propósito y exigen que la fase lo rechace. Un validador que no puede fallar
    es decoración;
  * lo que esta fase NO hace (comprimir, sacar la luz horneada, tocar el NIF)
    está escrito en el docstring de `pipeline/texturas.py`, y hay tests que lo
    fijan para que no empiece a hacerse en silencio.

Los PNG y TGA de entrada se construyen byte a byte: no hay PIL en CI y no hace
falta.
"""
import json
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

from pipeline import texturas as tx
from pipeline.errors import ArtifactValidationError, TexturaError
from pipeline.manifest import JobManifest
from pipeline.runner import PipelineRunner, State
from pipeline.staging import JobWorkspace

# Las carpetas de scripts del repo no son paquetes: se agregan a sys.path.
# tests/ va primero porque glb_sintetico vive ahí al lado (en modo discover
# unittest ya lo agrega; corriendo el módulo suelto, no).
_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _d in (os.path.dirname(os.path.abspath(__file__)),
           os.path.join(_RAIZ, "census"), os.path.join(_RAIZ, "fixtures")):
    if _d not in sys.path:
        sys.path.insert(0, _d)

from glb_sintetico import construir  # noqa: E402
import comparar      # noqa: E402
import escritor_dds  # noqa: E402
import parser_dds    # noqa: E402


# ---------------------------------------------------------------------------
# Constructores de entrada (sin PIL)
# ---------------------------------------------------------------------------

def png(ancho, alto, pixeles, color=6, profundidad=8, entrelazado=0):
    """PNG mínimo escrito a mano: filtro 0 en cada línea, un solo IDAT."""
    canales = {0: 1, 2: 3, 4: 2, 6: 4}.get(color, 1)
    stride = ancho * canales
    crudo = bytearray()
    for y in range(alto):
        crudo.append(0)                       # filtro None
        crudo += pixeles[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", ancho, alto, profundidad, color, 0, 0,
                       entrelazado)

    def chunk(tipo, datos):
        return (struct.pack(">I", len(datos)) + tipo + datos
                + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(crudo)))
            + chunk(b"IEND", b""))


def tga(ancho, alto, pixeles, bits=32, arriba=False):
    """TGA sin comprimir. `pixeles` en RGBA; se guarda BGR(A).

    Con `arriba=False` --el caso común-- el archivo guarda las filas AL REVES:
    el bit 5 del descriptor dice "la primera fila del archivo es la de arriba",
    y un TGA bottom-up guarda la última primero.
    """
    canales = bits // 8
    cab = bytearray(18)
    cab[2] = 2                                  # truecolor sin comprimir
    struct.pack_into("<HH", cab, 12, ancho, alto)
    cab[16] = bits
    cab[17] = 0x20 if arriba else 0x00
    filas = range(alto) if arriba else reversed(range(alto))
    cuerpo = bytearray()
    for y in filas:
        for x in range(ancho):
            i = (y * ancho + x) * 4
            r, g, b, a = pixeles[i:i + 4]
            if canales == 4:
                cuerpo += bytes((b, g, r, a))
            else:
                cuerpo += bytes((b, g, r))
    return bytes(cab) + bytes(cuerpo)


def rgba(ancho, alto, fn):
    """Píxeles RGBA donde fn(x, y) -> (r, g, b, a)."""
    out = bytearray()
    for y in range(alto):
        for x in range(ancho):
            out += bytes(fn(x, y))
    return bytes(out)


def dds(ancho, alto, pixeles):
    """DDS sin comprimir de 32 bpp con mipmaps, por el escritor del censo."""
    fd, ruta = tempfile.mkstemp(suffix=".dds")
    os.close(fd)
    try:
        escritor_dds.escribir(ruta, ancho, alto, pixeles)
        with open(ruta, "rb") as fh:
            return fh.read()
    finally:
        os.unlink(ruta)


class EntornoTexturas(unittest.TestCase):
    """Un job temporario con texturas de entrada reales."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        (self.raiz / "workspace").mkdir()
        (self.raiz / "salida").mkdir()
        self.mesh = self.raiz / "entrada.glb"
        self.mesh.write_bytes(construir())
        self.texdir = self.raiz / "tex"
        self.texdir.mkdir()

    def escribir(self, nombre, datos):
        ruta = self.texdir / nombre
        ruta.write_bytes(datos)
        return ruta

    def job(self, job_id="job-tex", **kwargs):
        entradas = tuple(sorted(self.texdir.iterdir()))
        base = dict(
            job_id=job_id,
            source_mesh=self.mesh,
            raiz_proyecto=self.raiz,
            workspace_raiz=self.raiz / "workspace",
            raiz_salida=self.raiz / "salida",
            texture_inputs=entradas,
        )
        base.update(kwargs)
        return JobManifest(**base)

    def ws(self, job_id="job-tex"):
        espacio = JobWorkspace(self.raiz / "workspace", job_id)
        espacio.crear()
        return espacio

    def paquete(self, espacio, job_id="job-tex"):
        return espacio.raiz / job_id / "package"

    def correr_fase(self, job_id="job-tex", **kwargs):
        espacio = self.ws(job_id)
        job = self.job(job_id=job_id, **kwargs)
        return tx.fase_process_texturas(job, espacio), espacio


# ---------------------------------------------------------------------------
# Clasificación por nombre
# ---------------------------------------------------------------------------

class ClasificarTests(unittest.TestCase):

    def test_los_sufijos_de_la_convencion(self):
        esperado = {"_n": "normal", "_m": "entorno", "_g": "glow",
                    "_s": "subsurface", "_p": "parallax", "_b": "backlight"}
        for sufijo, slot in esperado.items():
            with self.subTest(sufijo=sufijo):
                self.assertEqual(tx.clasificar("cartel%s.dds" % sufijo),
                                 (slot, sufijo, "cartel"))

    def test_sin_sufijo_es_el_color_base(self):
        """19.108 de 32.241 texturas del corpus no tienen sufijo: es la forma
        más común, no un caso degenerado."""
        self.assertEqual(tx.clasificar("cartel.png"), ("color", "", "cartel"))

    def test_el_sufijo_se_busca_en_minusculas(self):
        self.assertEqual(tx.clasificar("Cartel_N.PNG")[0], "normal")
        self.assertEqual(tx.clasificar("CARTEL_M.TGA")[0], "entorno")

    def test_un_sufijo_desconocido_no_es_un_normal(self):
        """`_x` no está en la convención: tratarlo como color es honesto, y
        tratarlo como normal inventaría un mapa."""
        self.assertEqual(tx.clasificar("cartel_x.png"),
                         ("color", "", "cartel_x"))


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

class LecturaPngTests(EntornoTexturas):

    def test_rgba_vuelve_identica(self):
        pix = rgba(8, 4, lambda x, y: (x * 30, y * 60, 99, 200 - x))
        t = tx.leer_png(self.escribir("a.png", png(8, 4, pix)))
        self.assertEqual((t.ancho, t.alto), (8, 4))
        self.assertEqual(t.pixeles, pix)

    def test_rgb_sale_con_alfa_255(self):
        pix = bytes(i * 10 for i in range(18))
        t = tx.leer_png(self.escribir("rgb.png", png(6, 1, pix, color=2)))
        self.assertEqual(len(t.pixeles), 6 * 4)
        self.assertEqual([t.pixeles[i + 3] for i in range(0, 24, 4)],
                         [255] * 6)

    def test_escala_de_grises_se_expande_a_rgb(self):
        t = tx.leer_png(self.escribir("gris.png",
                                      png(4, 1, bytes((10, 200, 77, 255)),
                                          color=0)))
        self.assertEqual(t.pixeles, bytes((10, 10, 10, 255,
                                           200, 200, 200, 255,
                                           77, 77, 77, 255,
                                           255, 255, 255, 255)))

    def test_gris_con_alfa_conserva_el_alfa(self):
        t = tx.leer_png(self.escribir("ga.png",
                                      png(2, 1, bytes((10, 200, 77, 255)),
                                          color=4)))
        self.assertEqual(t.pixeles, bytes((10, 10, 10, 200, 77, 77, 77, 255)))

    def _corrompido(self, nombre, datos, mensaje):
        with self.assertRaises(TexturaError) as ctx:
            tx.leer_png(self.escribir(nombre, datos))
        self.assertIn(mensaje, str(ctx.exception))

    def test_formatos_que_no_se_leen_se_rechazan_con_motivo(self):
        self._corrompido("p16.png", png(4, 1, bytes(8), color=0,
                                        profundidad=16),
                         "profundidad 16 bits")
        self._corrompido("entrelazado.png", png(4, 1, bytes(16), entrelazado=1),
                         "entrelazado")
        self._corrompido("paleta.png", png(4, 1, bytes(4), color=3),
                         "tipo de color 3")
        self._corrompido("firma.png", b"no soy un png", "firma de PNG")

    def test_un_png_valido_no_se_rechaza(self):
        """El par de los de arriba: si rechazara todo, esos tests no probarían
        nada."""
        datos = png(2, 2, rgba(2, 2, lambda x, y: (x, y, 0, 255)))
        self.assertEqual(tx.leer_png(self.escribir("ok.png", datos)).ancho, 2)


class LecturaTgaTests(EntornoTexturas):

    def test_bgra_se_convierte_y_el_origen_se_respeta(self):
        pix = rgba(2, 2, lambda x, y: (x * 100, y * 50, 7, 255))
        # Un TGA bottom-up: las filas guardadas al revés, descriptor en 0.
        datos = tga(2, 2, pix, arriba=False)
        self.assertEqual(tx.leer_tga(self.escribir("abajo.tga", datos)).pixeles,
                         pix)
        # Los MISMOS bytes con el bit de "arriba primero" prendido se leen al
        # revés: es el descriptor el que decide, y un lector que lo ignore
        # entrega la textura espejada sin ningún error.
        volteado = bytearray(datos)
        volteado[17] = 0x20
        self.assertEqual(
            tx.leer_tga(self.escribir("arriba.tga", bytes(volteado))).pixeles,
            pix[8:] + pix[:8])

    def test_24_bits_sale_con_alfa_255(self):
        pix = rgba(2, 1, lambda x, y: (x * 100, 50, 7, 0))
        t = tx.leer_tga(self.escribir("bpp24.tga", tga(2, 1, pix, bits=24)))
        self.assertEqual(t.pixeles, bytes((0, 50, 7, 255, 100, 50, 7, 255)))

    def test_rle_y_color_map_se_rechazan(self):
        casos = (("rle.tga", 0, 10, "tipo de imagen TGA 10"),
                 ("cmap.tga", 1, 2, "color map"))
        for nombre, cmap, tipo, motivo in casos:
            with self.subTest(caso=nombre):
                cab = bytearray(18)
                cab[1] = cmap
                cab[2] = tipo
                struct.pack_into("<HH", cab, 12, 2, 2)
                cab[16] = 32
                with self.assertRaises(TexturaError) as ctx:
                    tx.leer_tga(self.escribir(nombre, bytes(cab) + bytes(64)))
                self.assertIn(motivo, str(ctx.exception))


class LecturaDdsTests(EntornoTexturas):

    def test_sin_comprimir_vuelve_identico(self):
        pix = rgba(8, 8, lambda x, y: (x * 20, y * 20, 33, x + y))
        t = tx.leer_dds(self.escribir("src.dds", dds(8, 8, pix)))
        self.assertEqual((t.ancho, t.alto), (8, 8))
        self.assertEqual(t.pixeles, pix)

    def test_un_dds_comprimido_se_rechaza_con_el_numero(self):
        """No es un detalle de implementación: esta fase no comprime, y
        pretender que sí leería un DXT5 como si fueran píxeles."""
        cab = bytearray(128)
        cab[0:4] = b"DDS "
        struct.pack_into("<I", cab, 4, 124)
        struct.pack_into("<III", cab, 8, 0x81007, 8, 8)
        struct.pack_into("<I", cab, 80, 0x4)          # DDPF_FOURCC
        cab[84:88] = b"DXT5"
        with self.assertRaises(TexturaError) as ctx:
            tx.leer_dds(self.escribir("comprimido.dds", bytes(cab) + bytes(64)))
        self.assertIn("10.048 de 32.241", str(ctx.exception))

    def test_extension_desconocida_no_se_adivina(self):
        with self.assertRaises(TexturaError) as ctx:
            tx.leer_textura(self.escribir("raro.xyz", b"lo que sea"))
        self.assertIn("no soportada", str(ctx.exception))


# ---------------------------------------------------------------------------
# Geometría
# ---------------------------------------------------------------------------

class GeometriaTests(unittest.TestCase):

    def test_siguiente_potencia(self):
        for n, esperado in ((1, 1), (2, 2), (3, 4), (100, 128), (1025, 2048)):
            self.assertEqual(tx.siguiente_potencia(n), esperado, n)

    def test_redondear_hacia_arriba_no_pierde_pixeles(self):
        self.assertEqual(tx.ajustar_tamano(100, 60, 2048),
                         (128, 64, "redondeado hacia arriba a potencia de dos"))

    def test_el_tope_es_el_unico_caso_que_reduce(self):
        w, h, que = tx.ajustar_tamano(4096, 4096, 2048)
        self.assertEqual((w, h), (2048, 2048))
        self.assertIn("reducido", que)

    def test_potencia_de_dos_dentro_del_tope_no_se_toca(self):
        self.assertEqual(tx.ajustar_tamano(1024, 512, 2048),
                         (1024, 512, "ya era potencia de dos"))

    def test_redimensionar_promedia_la_caja(self):
        # 2x2 -> 1x1: el promedio exacto de los cuatro pixeles.
        tex = tx.Textura(2, 2, bytes((0, 0, 0, 0,
                                      100, 100, 100, 100,
                                      200, 200, 200, 200,
                                      40, 40, 40, 40)))
        self.assertEqual(tx.redimensionar(tex, 1, 1).pixeles,
                         bytes((85, 85, 85, 85)))

    def test_redimensionar_al_mismo_tamano_no_toca_nada(self):
        tex = tx.Textura(2, 2, bytes(range(16)))
        self.assertIs(tx.redimensionar(tex, 2, 2), tex)

    def test_redimensionar_a_cero_es_un_error(self):
        with self.assertRaises(TexturaError):
            tx.redimensionar(tx.Textura(2, 2, bytes(16)), 0, 4)


# ---------------------------------------------------------------------------
# Conversión de canales
# ---------------------------------------------------------------------------

class ConversionTests(unittest.TestCase):

    def _tex(self, ancho, alto, fn):
        return tx.Textura(ancho, alto, rgba(ancho, alto, fn))

    def test_el_alfa_del_normal_sale_de_la_rugosidad(self):
        n = self._tex(4, 1, lambda x, y: (10, 20, 30, 255))
        # ORM: R=0 (oclusión), G=rugosidad, B=metalicidad.
        rug = self._tex(4, 1, lambda x, y: (0, (0, 64, 128, 0)[x], 255, 255))
        salida, saturacion, desc = tx.alfa_desde_rugosidad(n, rug)
        self.assertEqual([salida.pixeles[i + 3] for i in range(0, 16, 4)],
                         [255, 191, 127, 255])
        self.assertEqual(saturacion, 50.0)
        self.assertEqual(desc["canal_rugosidad"], "g")
        self.assertFalse(desc["grises"])

    def test_un_mapa_de_rugosidad_en_grises_usa_el_rojo(self):
        n = self._tex(2, 1, lambda x, y: (0, 0, 0, 255))
        rug = self._tex(2, 1, lambda x, y: (100, 100, 100, 255))
        _salida, _sat, desc = tx.alfa_desde_rugosidad(n, rug)
        self.assertTrue(desc["grises"])
        self.assertEqual(desc["canal_rugosidad"], "r")

    def test_dimensiones_distintas_no_se_asocian_en_silencio(self):
        """Asociar píxeles de mapas de distinto tamaño daría una máscara
        desplazada, que es un defecto invisible en Blender."""
        n = self._tex(4, 1, lambda x, y: (0, 0, 0, 255))
        rug = self._tex(2, 1, lambda x, y: (10, 10, 10, 255))
        with self.assertRaises(TexturaError) as ctx:
            tx.alfa_desde_rugosidad(n, rug)
        self.assertIn("no se remuestrea", str(ctx.exception))

    def test_la_expansion_de_rango_estira_e_informa(self):
        tex = self._tex(4, 1, lambda x, y: (0, 100 + x * 33, 0, 255))
        salida, obs = tx.expandir_rango(tex, "g")
        self.assertEqual([salida.pixeles[i + 1] for i in range(0, 16, 4)],
                         [0, 85, 170, 255])
        self.assertEqual((obs["min"], obs["max"]), (100, 199))
        self.assertIn("[100, 199] -> [0, 255]", obs["expansion"])

    def test_un_mapa_plano_no_se_expande(self):
        """Estirar un mapa constante no tiene sentido, y hacerlo igual
        inventaría contraste."""
        tex = self._tex(2, 1, lambda x, y: (0, 7, 0, 255))
        salida, obs = tx.expandir_rango(tex, "g")
        self.assertEqual(salida, tex)
        self.assertIn("plano", obs["expansion"])

    def test_la_mascara_de_entorno_sale_en_grises(self):
        tex = self._tex(2, 1, lambda x, y: (0, 0, 50, 255))
        salida, info = tx.entorno_desde_metalico(tex)
        self.assertEqual(salida.pixeles,
                         bytes((50, 50, 50, 255, 50, 50, 50, 255)))
        self.assertIn("cubemap", info["nota"])


# ---------------------------------------------------------------------------
# La fase
# ---------------------------------------------------------------------------

class FaseTests(EntornoTexturas):

    # 64x64: es el lado mínimo que valida el manifest, y da 256 bloques de 4x4,
    # que es lo que mascara_especular.py necesita para poder medir (MIN_BLOQUES
    # = 64). Con menos, la medición diría "no dice nada" y con razón.
    COLOR = rgba(64, 64, lambda x, y: (x * 4 % 256, y * 4 % 256, 128, 255))
    # Alfa en 255: es lo que entrega un PNG opaco, y es el defecto del hacha
    # cuando no hay rugosidad que lo corrija.
    NORMAL = rgba(64, 64, lambda x, y: (128, 128, 255, 255))
    ORM = rgba(64, 64, lambda x, y: (0, 200, 40, 255))

    def _texdir(self, espacio, job_id="job-tex"):
        return (espacio.raiz / job_id / "package" / "textures"
                / "static" / job_id)

    def test_color_normal_y_orm_producen_tres_dds(self):
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        self.escribir("cartel_n.png", png(64, 64, self.NORMAL))
        self.escribir("cartel_orm.png", png(64, 64, self.ORM))
        rep, espacio = self.correr_fase()

        self.assertTrue(rep["ejecutada"])
        self.assertNotIn("stub", rep)
        ts = rep["texture_sets"][0]
        self.assertEqual([t["slot"] for t in ts["texturas"]],
                         ["color", "normal", "entorno"])
        self.assertEqual(sorted(p.name for p in self._texdir(espacio).iterdir()),
                         ["cartel.dds", "cartel_m.dds", "cartel_n.dds"])

        # El alfa del _n salió de la rugosidad: 255 - 200 = 55.
        tex = tx.leer_dds(self._texdir(espacio) / "cartel_n.dds")
        self.assertEqual({tex.pixeles[i + 3]
                          for i in range(0, len(tex.pixeles), 4)}, {55})
        # El _m salió de la metalicidad (40), plana: no se estira, queda 40.
        mascara = tx.leer_dds(self._texdir(espacio) / "cartel_m.dds")
        self.assertEqual({mascara.pixeles[i]
                          for i in range(0, len(mascara.pixeles), 4)}, {40})

        # Y el tamaño que predice el parser es el real: el contrato del DDS.
        for nombre in ("cartel.dds", "cartel_n.dds", "cartel_m.dds"):
            d = parser_dds.leer(str(self._texdir(espacio) / nombre))
            self.assertTrue(d["tamano_cuadra"], nombre)
            self.assertTrue(d["potencia_de_dos"], nombre)

    def test_las_rutas_declaradas_resuelven_contra_el_paquete(self):
        """El contrato del otro lado: una ruta que no resuelva es un error de
        esta fase, no del cargador del juego."""
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        rep, espacio = self.correr_fase()
        for t in rep["texture_sets"][0]["texturas"]:
            self.assertIsNotNone(
                comparar.resolver_textura(t["declarada"], self.paquete(espacio)),
                t["declarada"])

    def test_la_ruta_declarada_usa_la_convencion_del_corpus(self):
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        rep, _espacio = self.correr_fase()
        self.assertEqual(rep["texture_sets"][0]["texturas"][0]["declarada"],
                         "textures\\static\\job-tex\\cartel.dds")

    def test_sin_texture_inputs_la_fase_corrio_y_no_hizo_nada(self):
        """Distinto de ser stub: `ejecutada` True, sin `stub`, y lo dice."""
        espacio = self.ws("job-vacio")
        job = self.job(job_id="job-vacio", texture_inputs=())
        rep = tx.fase_process_texturas(job, espacio)
        self.assertTrue(rep["ejecutada"])
        self.assertNotIn("stub", rep)
        self.assertEqual(rep["texture_sets"], [])
        self.assertIn("no tuvo nada que hacer", rep["nota"])

    def test_una_entrada_que_no_produce_nada_es_un_error(self):
        """Un ORM suelto no es un texture set: sin difuso no hay nada que
        declarar en el BSShaderTextureSet, y decirlo acá es más barato que
        descubrirlo en el juego con el asset invisible."""
        self.escribir("cartel_orm.png", png(64, 64, self.ORM))
        with self.assertRaises(TexturaError) as ctx:
            self.correr_fase()
        self.assertIn("no tiene color base", str(ctx.exception))

    def test_dos_entradas_al_mismo_lugar_no_se_resuelven_en_silencio(self):
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        self.escribir("cartel.tga", tga(8, 8, self.COLOR))
        with self.assertRaises(TexturaError) as ctx:
            self.correr_fase()
        self.assertIn("no se elige", str(ctx.exception))

    def test_potencia_de_dos_dentro_del_tope_no_se_toca(self):
        self.escribir("c.png", png(64, 64, rgba(64, 64,
                                                lambda x, y: (x, y, 0, 255))))
        rep, _espacio = self.correr_fase(max_lado_textura=64)
        t = rep["texture_sets"][0]["texturas"][0]
        self.assertEqual(t["dimensiones"], [64, 64])
        self.assertEqual(t["dimensiones_origen"], [64, 64])
        self.assertEqual(t["ajuste"], "ya era potencia de dos")

    def test_el_tope_por_debajo_del_original_reduce_de_verdad(self):
        self.escribir("c.png", png(128, 64, rgba(128, 64,
                                                 lambda x, y: (x, y, 0, 255))))
        rep, _espacio = self.correr_fase(max_lado_textura=64)
        t = rep["texture_sets"][0]["texturas"][0]
        self.assertEqual(t["dimensiones"], [64, 32])
        self.assertIn("reducido", t["ajuste"])

    def test_el_color_se_copia_tal_cual(self):
        """La luz horneada NO se saca automáticamente: la documentación dice
        que se atenúa con curvas y no se recupera. Hacerlo en silencio sería
        inventar una conversión que nadie midió."""
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        _rep, espacio = self.correr_fase()
        tex = tx.leer_dds(self._texdir(espacio) / "cartel.dds")
        self.assertEqual(tex.pixeles[:16], self.COLOR[:16])

    def test_normal_sin_fuente_de_rugosidad_queda_marcado(self):
        """El alfa en 255 es 'todo brilla al máximo', el defecto del hacha. No
        reprueba --la regla está medida solo para armas-- pero no pasa
        inadvertido."""
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        self.escribir("cartel_n.png", png(64, 64, self.NORMAL))
        rep, _espacio = self.correr_fase()
        self.assertEqual(rep["requiere_revision"], ["cartel"])
        self.assertIn("99,7", rep["nota"])

    def test_un_dds_que_no_pasa_el_contrato_falla_la_fase(self):
        """Falsificación en el lugar: si el validador no puede fallar, los
        tests de arriba no probarían nada."""
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        with mock.patch.object(tx, "validar_salida",
                               return_value=["dds_potencia_de_dos"]):
            with self.assertRaises(ArtifactValidationError) as ctx:
                self.correr_fase()
        self.assertIn("dds_potencia_de_dos", str(ctx.exception))

    def test_el_validador_detecta_un_dds_roto_de_verdad(self):
        """El par del de arriba, sin mock."""
        roto = self.escribir("roto.dds", b"DDS " + bytes(200))
        self.assertEqual(tx.validar_salida(roto, "textures\\x\\roto.dds"),
                         ["dds_parsea"])

    def test_el_reporte_es_json_serializable(self):
        """El runner lo escribe a reports/final.json con json.dumps: un Path o
        un set en el reporte rompería la fase en el peor momento."""
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        self.escribir("cartel_n.png", png(64, 64, self.NORMAL))
        self.escribir("cartel_orm.png", png(64, 64, self.ORM))
        rep, _espacio = self.correr_fase()
        json.dumps(rep)

    def test_deja_el_texture_set_para_la_fase_de_export(self):
        """El BSShaderTextureSet se llena con rutas, no con archivos: esto es lo
        que una EXPORT_NIF va a leer, y si no resolviera contra el paquete el
        NIF apuntaría a texturas que no existen."""
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        self.escribir("cartel_n.png", png(64, 64, self.NORMAL))
        rep, espacio = self.correr_fase()
        sets = json.loads((espacio.raiz / "job-tex" / "reports"
                           / "texture_set.json").read_text(encoding="utf-8"))
        self.assertEqual(sets["categoria"], "static")
        self.assertEqual(sets["texture_sets"][0]["texturas"], {
            "color": "textures\\static\\job-tex\\cartel.dds",
            "normal": "textures\\static\\job-tex\\cartel_n.dds",
        })
        for declarada in sets["texture_sets"][0]["texturas"].values():
            self.assertIsNotNone(
                comparar.resolver_textura(declarada, self.paquete(espacio)))


# ---------------------------------------------------------------------------
# El runner, con la fase conectada de verdad
# ---------------------------------------------------------------------------

class RunnerConTexturasTests(EntornoTexturas):

    def _cartel(self):
        self.escribir("cartel.png",
                      png(8, 8, rgba(8, 8, lambda x, y: (x, y, 0, 255))))
        return self.job()

    def test_la_fase_no_es_stub_y_el_gate_sigue_frenando(self):
        """Con PROCESS_TEXTURES cableada, publicar sigue siendo imposible: lo
        que frena ahora es PREPARE/EXPORT_NIF/READ_BACK/VALIDATE/PACKAGE."""
        r = PipelineRunner(self._cartel()).run()
        self.assertIs(State.FAILED, r.estado)
        self.assertNotIn("process_textures", r.fases_sin_conectar)
        for fase in ("prepare", "export_nif", "read_back", "validate",
                     "package"):
            self.assertIn(fase, r.fases_sin_conectar)
        self.assertFalse((self.raiz / "salida" / "job-tex").exists())
        # Y la evidencia quedó escrita.
        final = json.loads((self.raiz / "workspace" / "job-tex" / "reports"
                            / "final.json").read_text(encoding="utf-8"))
        self.assertEqual("FAILED", final["estado"])
        self.assertTrue(final["fases"]["process_textures"]["ejecutada"])

    def test_una_textura_invalida_fracasa_la_corrida_entera(self):
        self.escribir("cartel.png", b"esto no es un png")
        r = PipelineRunner(self.job()).run()
        self.assertIs(State.FAILED, r.estado)
        final = json.loads((self.raiz / "workspace" / "job-tex" / "reports"
                            / "final.json").read_text(encoding="utf-8"))
        self.assertIn("TexturaError",
                      final["fases"]["process_textures"]["error"])
        self.assertFalse((self.raiz / "salida" / "job-tex").exists())


if __name__ == "__main__":
    unittest.main()
