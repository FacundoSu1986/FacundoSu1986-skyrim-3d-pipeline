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

def _grupos(nombres):
    """{base: (slots, fuentes, ignoradas)} de `_agrupar` sobre archivos vacíos:
    la agrupación decide por el NOMBRE, no por el contenido."""
    with tempfile.TemporaryDirectory() as d:
        rutas = []
        for n in nombres:
            p = Path(d) / n
            p.write_bytes(b"x")
            rutas.append(p)
        g = tx._agrupar(sorted(rutas))
        return {b: (sorted(v["slots"]), sorted(v["fuentes"]),
                    sorted(x["rol"] for x in v["ignoradas"]))
                for b, v in g.items()}


class ClasificarTests(unittest.TestCase):

    def test_los_sufijos_de_la_convencion(self):
        esperado = {"_n": "normal", "_m": "entorno", "_g": "glow",
                    "_s": "subsurface", "_p": "parallax", "_b": "backlight"}
        for sufijo, slot in esperado.items():
            with self.subTest(sufijo=sufijo):
                self.assertEqual(tx.clasificar("cartel%s.dds" % sufijo),
                                 ("slot", slot, sufijo, "cartel", None))

    def test_sin_sufijo_es_el_color_base(self):
        """19.108 de 32.241 texturas del corpus no tienen sufijo: es la forma
        más común, no un caso degenerado."""
        self.assertEqual(tx.clasificar("cartel.png"),
                         ("slot", "color", "", "cartel", None))

    def test_el_sufijo_se_busca_en_minusculas(self):
        self.assertEqual(tx.clasificar("Cartel_N.PNG").rol, "normal")
        self.assertEqual(tx.clasificar("CARTEL_M.TGA").rol, "entorno")

    def test_un_sufijo_desconocido_no_es_un_normal(self):
        """`_x` no está en la convención: tratarlo como color es honesto, y
        tratarlo como normal inventaría un mapa."""
        self.assertEqual(tx.clasificar("cartel_x.png"),
                         ("slot", "color", "", "cartel_x", None))

    def test_los_sufijos_de_gltf_se_reconocen(self):
        """Nombres estándar de glTF y de los generadores. Sin esto,
        `hacha_normal.png` y `hacha_metallicRoughness.png` quedaban como
        tres texture sets independientes y la fase escribía tres "color"
        silenciosamente."""
        casos = {
            "hacha_basecolor.png": ("slot", "color", "_basecolor"),
            "hacha_BaseColor.png": ("slot", "color", "_basecolor"),
            "hacha_base_color.png": ("slot", "color", "_base_color"),
            "hacha_albedo.png": ("slot", "color", "_albedo"),
            "hacha_diffuse.png": ("slot", "color", "_diffuse"),
            "hacha_D.png": ("slot", "color", "_d"),
            "hacha_color.png": ("slot", "color", "_color"),
            "hacha_normal.png": ("slot", "normal", "_normal"),
            "hacha_Normal.png": ("slot", "normal", "_normal"),
            "hacha_nor.png": ("slot", "normal", "_nor"),
            "hacha_nrm.png": ("slot", "normal", "_nrm"),
            "hacha_metallicRoughness.png": ("fuente", "empaquetada",
                                            "_metallicroughness"),
            "hacha_occlusionRoughnessMetallic.png": (
                "fuente", "empaquetada", "_occlusionroughnessmetallic"),
            "hacha_orm.png": ("fuente", "empaquetada", "_orm"),
            "hacha_roughness.png": ("fuente", "rugosidad", "_roughness"),
        }
        for nombre, (clase, rol, sufijo) in casos.items():
            with self.subTest(nombre=nombre):
                r = tx.clasificar(nombre)
                self.assertEqual((r.clase, r.rol, r.sufijo, r.base),
                                 (clase, rol, sufijo, "hacha"))

    def test_los_nombres_de_substance(self):
        """Hallazgo de la revisión: `_Metallic`, `_Emissive` y `_Height`
        caían como color y armaban un texture set cada uno, sin aviso. El
        metal suelto es una fuente, la emisión es el `_g` de Skyrim, y la
        altura no tiene equivalente y se informa."""
        self.assertEqual(
            _grupos(["hacha_BaseColor.png", "hacha_Normal.png",
                     "hacha_Roughness.png", "hacha_Metallic.png",
                     "hacha_Emissive.png", "hacha_Height.png",
                     "hacha_Mixed_AO.png"]),
            {"hacha": (["color", "glow", "normal"],
                       ["metalico", "rugosidad"], ["altura", "oclusion"])})

    def test_los_nombres_de_poly_haven(self):
        """`x_nor_gl_4k` lleva DOS marcas detrás del rol; con una sola
        quitada caía como color. `_diff` es su color y `_rough` su rugosidad."""
        self.assertEqual(
            _grupos(["x_diff_4k.png", "x_nor_gl_4k.png", "x_rough_4k.png"]),
            {"x": (["color", "normal"], ["rugosidad"], [])})
        self.assertEqual(tx.clasificar("x_nor_gl_4k.png").convencion, "gl")
        self.assertEqual(tx.clasificar("x_arm_4k.png").rol, "empaquetada")

    def test_los_nombres_reales_de_tripo(self):
        """Los tres archivos que entregó Tripo para el hacha de Tencent. El de
        metal y rugosidad junta dos nombres con un guion; recortado a mano
        quedaba en un grupo propio y la fase fallaba. Su contenido es el
        empaquetado de glTF (R 255, G rugosidad, B metalicidad), medido sobre
        el archivo real."""
        nombres = ["texture_pbr_20250901_fixed.png",
                   "texture_pbr_20250901_normal_fixed.png",
                   "texture_pbr_20250901_metallic-texture_pbr_20250901"
                   "_roughness_fixed.png"]
        self.assertEqual(_grupos(nombres),
                         {"texture_pbr_20250901": (["color", "normal"],
                                                   ["empaquetada"], [])})

    def test_la_base_de_una_fuente_descuenta_los_sufijos_extra(self):
        """Hallazgo de la revisión: `_es_fuente` recortaba `_fixed` para
        reconocer la fuente, pero la base salía del nombre entero
        (`hacha_metal`, `hacha_or`)."""
        for nombre in ("hacha_metallicRoughness_fixed.png",
                       "hacha_orm_2k.png", "hacha_rough_4k.png"):
            with self.subTest(nombre=nombre):
                self.assertEqual(tx.clasificar(nombre).base, "hacha")

    def test_sufijos_extra_del_generador_se_quitan(self):
        """`hacha_normal_fixed.png` (Tripo), `hacha_basecolor_baked.png`
        tienen un sufijo que el generador agrega DESPUÉS del rol."""
        self.assertEqual(tx.clasificar("hacha_normal_fixed.png")[:4],
                         ("slot", "normal", "_normal", "hacha"))
        self.assertEqual(tx.clasificar("hacha_basecolor_baked.png")[:4],
                         ("slot", "color", "_basecolor", "hacha"))
        self.assertEqual(tx.clasificar("hacha_normal_2k.png")[:4],
                         ("slot", "normal", "_normal", "hacha"))

    def test_la_convencion_del_normal_no_se_tira(self):
        """Hallazgo de la revisión: `_dx` se descartaba como ruido y el normal
        DirectX se escribía sin invertir el verde."""
        casos = {"hacha_normal_dx.png": "dx", "hacha_Normal_DirectX.png": "dx",
                 "hacha_normaldx.png": "dx", "hacha_normal_gl.png": "gl",
                 "hacha_normalgl.png": "gl", "hacha_normal.png": None}
        for nombre, conv in casos.items():
            with self.subTest(nombre=nombre):
                r = tx.clasificar(nombre)
                self.assertEqual((r.rol, r.base, r.convencion),
                                 ("normal", "hacha", conv))

    def test_una_convencion_de_normal_en_otro_mapa_es_un_error(self):
        with self.assertRaises(TexturaError) as ctx:
            tx.clasificar("hacha_basecolor_dx.png")
        self.assertIn("no es un normal", str(ctx.exception))

    def test_un_rol_que_no_se_reconoce_no_es_color(self):
        """La causa de fondo del hallazgo: lo que no se reconocía era color.
        Una palabra de rol al final del nombre ahora es un error."""
        for nombre in ("hacha_normalmap.png", "hacha_roughnessmap.png",
                       "hacha_metalmask.png"):
            with self.subTest(nombre=nombre):
                with self.assertRaises(TexturaError) as ctx:
                    tx.clasificar(nombre)
                self.assertIn("no reconoce", str(ctx.exception))

    def test_un_empaquetado_y_una_suelta_no_se_mezclan(self):
        with self.assertRaises(TexturaError) as ctx:
            _grupos(["x.png", "x_orm.png", "x_roughness.png"])
        self.assertIn("cual manda", str(ctx.exception))

    def test_el_mensaje_sin_color_lista_solo_alias_de_color(self):
        """Antes listaba TODOS los sufijos, `_n` y `_nrm` incluidos, como si
        fueran de color."""
        self.assertIn("_basecolor", tx.ALIAS_DE_COLOR)
        self.assertNotIn("_n", tx.ALIAS_DE_COLOR)
        self.assertNotIn("_nrm", tx.ALIAS_DE_COLOR)
        self.assertFalse(hasattr(tx, "SLOT_A_SUFIJO"),
                         "SLOT_A_SUFIJO quedaba muerto y daba '_nrm'")


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

    def _tga_gris(self, bits=8, tipo=3):
        cab = bytearray(18)
        cab[2] = tipo
        struct.pack_into("<HH", cab, 12, 3, 1)
        cab[16] = bits
        cab[17] = 0x20                                 # primera fila arriba
        return bytes(cab) + bytes((10, 128, 250) * (bits // 8))

    def test_un_tga_gris_de_8_bits_se_lee(self):
        """Hallazgo de la revisión: el docstring anunciaba el tipo 3 (grises)
        y el lector exigía 24 o 32 bits, así que un mapa de rugosidad en TGA
        gris se rechazaba."""
        t = tx.leer_tga(self.escribir("rug.tga", self._tga_gris()))
        self.assertEqual(t.pixeles, bytes((10, 10, 10, 255, 128, 128, 128, 255,
                                           250, 250, 250, 255)))

    def test_tipo_y_profundidad_que_no_van_juntos_se_rechazan(self):
        for nombre, bits, tipo in (("gris24.tga", 24, 3), ("color8.tga", 8, 2)):
            with self.subTest(nombre=nombre):
                with self.assertRaises(TexturaError) as ctx:
                    tx.leer_tga(self.escribir(nombre,
                                              self._tga_gris(bits, tipo)))
                self.assertIn("TGA tipo %d de %d bits" % (tipo, bits),
                              str(ctx.exception))

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

    def test_sin_mascara_alfa_el_alfa_es_255(self):
        """Hallazgo de la revisión: en un X8R8G8B8 el cuarto byte es relleno,
        y se leía como alfa. Con relleno 0 el `_n` quedaba con la máscara
        especular apagada y el control de saturación no lo veía."""
        pix = rgba(8, 8, lambda x, y: (10, 20, 30, 0))
        datos = bytearray(dds(8, 8, pix))
        flags, = struct.unpack_from("<I", datos, 80)
        struct.pack_into("<I", datos, 80, flags & ~0x1)   # sin ALPHAPIXELS
        struct.pack_into("<I", datos, 104, 0)             # sin mascara alfa
        t = tx.leer_dds(self.escribir("x8.dds", bytes(datos)))
        self.assertEqual(t.pixeles[:8], bytes((10, 20, 30, 255) * 2))

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
        # 2x2 -> 1x1, un mapa de DATOS: el promedio exacto de los cuatro.
        tex = tx.Textura(2, 2, bytes((0, 0, 0, 0,
                                      100, 100, 100, 100,
                                      200, 200, 200, 200,
                                      40, 40, 40, 40)))
        self.assertEqual(tx.redimensionar(tex, 1, 1, slot="entorno").pixeles,
                         bytes((85, 85, 85, 85)))

    def test_redimensionar_al_mismo_tamano_no_toca_nada(self):
        tex = tx.Textura(2, 2, bytes(range(16)))
        self.assertIs(tx.redimensionar(tex, 2, 2), tex)

    def test_redimensionar_a_cero_es_un_error(self):
        with self.assertRaises(TexturaError):
            tx.redimensionar(tx.Textura(2, 2, bytes(16)), 0, 4)

    def test_redimensionar_normal_renormaliza(self):
        """El promedio de dos normales unitarias que apuntan en direcciones
        opuestas da un vector más corto que 1; si no se renormaliza el
        relieve se aplana en los mipmaps y en el resize principal. Es
        el mismo defecto que se describe en la trampa 35 (aliasing) pero
        para las normales."""
        # Un píxel apuntando a +X (255,128,255) y otro a -X (0,128,255):
        # promedio (127,128,255) = apunta a +Z, largo 0,5 → hay que
        # renormalizar a (128,128,255).
        crudo = bytearray()
        crudo += bytes((255, 128, 255, 200))
        crudo += bytes((0,   128, 255, 100))
        crudo += bytes((0,   128, 255, 100))
        crudo += bytes((255, 128, 255, 200))
        tex = tx.Textura(2, 2, bytes(crudo))
        chico = tx.redimensionar(tex, 1, 1, slot="normal")
        r, g, b, a = chico.pixeles
        # El alfa es el promedio de los cuatro: (200+100+100+200)/4 = 150.
        self.assertEqual(a, 150)
        # El vector normalizado tiene que ser unitario.
        nx = r/255*2-1; ny = g/255*2-1; nz = b/255*2-1
        ln = (nx*nx+ny*ny+nz*nz)**0.5
        self.assertAlmostEqual(ln, 1.0, delta=0.02,
                               msg="la normal redimensionada no se "
                                   "renormalizó: largo %.3f" % ln)

    def test_el_color_se_promedia_en_luz_lineal(self):
        """Hallazgo de la revisión: el color se promediaba en valores sRGB,
        que oscurece los bordes. En luz lineal los mismos cuatro píxeles dan
        118, no 85. El alfa es un dato y sigue dando 85."""
        tex = tx.Textura(2, 2, bytes((0, 0, 0, 0,
                                      100, 100, 100, 100,
                                      200, 200, 200, 200,
                                      40, 40, 40, 40)))
        self.assertEqual(tx.redimensionar(tex, 1, 1, slot="color").pixeles,
                         bytes((118, 118, 118, 85)))

    def test_srgb_ida_y_vuelta_es_exacta(self):
        """Un bloque de un solo valor no puede cambiar al promediarse: la
        conversión a lineal y de vuelta tiene que devolver el mismo byte."""
        self.assertEqual([tx._a_srgb(tx._A_LINEAL[c]) for c in range(256)],
                         list(range(256)))

    def test_los_mipmaps_del_normal_tambien_se_renormalizan(self):
        """Hallazgo de la revisión: se renormalizaba el nivel 0 y los mipmaps
        los armaba `escritor_dds.reducir`, que promedia sin renormalizar. Un
        damero de normales unitarias (0,8, 0, 0,6) y (-0,8, 0, 0,6) da, en el
        nivel 1, vectores de largo 0,6 si no se renormaliza."""
        pix = rgba(4, 4, lambda x, y: ((230, 128, 204, 255) if (x + y) % 2
                                       else (25, 128, 204, 255)))
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "damero_n.dds"
            tx.escribir_dds(tx.Textura(4, 4, pix), ruta, slot="normal")
            datos = ruta.read_bytes()
        nivel1 = datos[128 + 4 * 4 * 4: 128 + 4 * 4 * 4 + 2 * 2 * 4]
        for i in range(0, len(nivel1), 4):
            b, g, r = nivel1[i], nivel1[i + 1], nivel1[i + 2]   # BGRA
            v = [c / 255 * 2 - 1 for c in (r, g, b)]
            largo = sum(c * c for c in v) ** 0.5
            self.assertAlmostEqual(largo, 1.0, delta=0.02,
                                   msg="mip 1, texel %d: largo %.3f"
                                   % (i // 4, largo))

    def test_orden_de_canales_rgba_se_rechaza_con_mensaje(self):
        """Un DDS escrito con orden RGBA (raro, pero posible exportando de
        GIMP/Photoshop) se rechaza con las máscaras que trae en el header,
        en vez de asumir BGRA y devolver colores invertidos sin error."""
        import tempfile, os
        cab = bytearray(128)
        cab[0:4] = b"DDS "
        import struct as st
        st.pack_into("<I", cab, 4, 124)
        st.pack_into("<III", cab, 8, 0x1007, 4, 4)
        st.pack_into("<I", cab, 20, 16)
        st.pack_into("<I", cab, 28, 1)
        st.pack_into("<I", cab, 76, 32)
        st.pack_into("<I", cab, 80, 0x1 | 0x40)    # ALPHAPIXELS|RGB
        st.pack_into("<I", cab, 88, 32)
        # RGBA: R en el byte bajo (0x000000FF)
        st.pack_into("<IIII", cab, 92,
                     0x000000FF, 0x0000FF00, 0x00FF0000, 0xFF000000)
        st.pack_into("<I", cab, 108, 0x1000)
        fd, ruta = tempfile.mkstemp(suffix=".dds")
        os.close(fd)
        with open(ruta, "wb") as fh:
            fh.write(bytes(cab))
            fh.write(bytes(64))   # 4x4x4
        try:
            with self.assertRaises(TexturaError) as ctx:
                tx.leer_dds(ruta)
            self.assertIn("RGBA", str(ctx.exception))
        finally:
            os.unlink(ruta)


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
        salida, saturacion = tx.alfa_desde_rugosidad(n, rug, "g")
        self.assertEqual([salida.pixeles[i + 3] for i in range(0, 16, 4)],
                         [255, 191, 127, 255])
        self.assertEqual(saturacion, 50.0)

    def test_el_canal_lo_decide_quien_llama(self):
        n = self._tex(2, 1, lambda x, y: (0, 0, 0, 255))
        rug = self._tex(2, 1, lambda x, y: (100, 7, 7, 255))
        salida, _sat = tx.alfa_desde_rugosidad(n, rug, "r")
        self.assertEqual(salida.pixeles[3::4], bytes((155, 155)))

    def test_es_gris_mira_toda_la_imagen_y_no_la_primera_fila(self):
        """Hallazgo de la revisión: se decidía "gris" con los primeros 4.096
        téxeles, que en una textura de 4096 de ancho son la primera fila --el
        borde vacío del atlas--. Un ORM de glTF con el rojo sin usar (0) y esa
        fila en negro pasaba por gris, se leía el rojo como rugosidad y el
        alfa del `_n` quedaba en 255 entero."""
        tex = self._tex(4096, 4, lambda x, y: ((0, 0, 0, 255) if y == 0
                                               else (0, 150, 220, 255)))
        self.assertFalse(tx.es_gris(tex)["gris"])
        self.assertTrue(tx.es_gris(self._tex(
            64, 64, lambda x, y: (x, x, x, 255)))["gris"])

    def test_dimensiones_distintas_no_se_asocian_en_silencio(self):
        """La función no remuestrea: con tamaños distintos asociaría téxeles
        que no se tocan. Quien llama las lleva antes al mismo tamaño (y eso
        lo prueba FaseTests)."""
        n = self._tex(4, 1, lambda x, y: (0, 0, 0, 255))
        rug = self._tex(2, 1, lambda x, y: (10, 10, 10, 255))
        with self.assertRaises(TexturaError) as ctx:
            tx.alfa_desde_rugosidad(n, rug, "r")
        self.assertIn("mismo tamaño", str(ctx.exception))

    def test_una_metalicidad_de_ruido_no_da_mascara(self):
        """Hallazgo de la revisión: un máximo de 2 se estiraba a 255 y la `_m`
        salía salpicada de reflejo total en un objeto de madera."""
        ruido = self._tex(8, 8, lambda x, y: (255, 180, (x + y) % 3, 255))
        tex, info = tx.entorno_desde_metalico(ruido, "b")
        self.assertIsNone(tex)
        self.assertIn("no es metalico", info["nota"])
        # y justo en el piso, sí
        piso = self._tex(8, 8, lambda x, y: (0, 0, (0, tx.PISO_METAL)[x % 2],
                                             255))
        tex, _info = tx.entorno_desde_metalico(piso, "b")
        self.assertIsNotNone(tex)

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
        salida, info = tx.entorno_desde_metalico(tex, "b")
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


class FaseRevisionPr51Tests(EntornoTexturas):
    """Un test por hallazgo de la segunda revisión del PR #51, sobre la fase
    entera: los de nombre o de lectura se prueban arriba."""

    COLOR = FaseTests.COLOR
    NORMAL = FaseTests.NORMAL

    def _texdir(self, espacio, job_id="job-tex"):
        return (espacio.raiz / job_id / "package" / "textures"
                / "static" / job_id)

    def _gris(self, fn, lado=64):
        return png(lado, lado, rgba(lado, lado,
                                    lambda x, y: (fn(x, y),) * 3 + (255,)))

    def test_un_normal_directx_sale_con_el_verde_invertido(self):
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        self.escribir("cartel_normal_dx.png",
                      png(64, 64, rgba(64, 64, lambda x, y: (128, 200, 230, 90))))
        rep, espacio = self.correr_fase()
        n = tx.leer_dds(self._texdir(espacio) / "cartel_n.dds")
        self.assertEqual(set(n.pixeles[1::4]), {55})
        self.assertIn("DirectX", rep["texture_sets"][0]["texturas"][1]["origen"])

    def test_una_rugosidad_suelta_no_genera_mascara_de_entorno(self):
        """Hallazgo de la revisión: con un `_roughness` gris, la `_m` salía de
        la rugosidad, y el cubemap se reflejaba justo donde el material es
        mate."""
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        self.escribir("cartel_n.png", png(64, 64, self.NORMAL))
        self.escribir("cartel_roughness.png",
                      self._gris(lambda x, y: 20 if x < 32 else 230))
        rep, espacio = self.correr_fase()
        self.assertEqual(sorted(p.name for p in self._texdir(espacio).iterdir()),
                         ["cartel.dds", "cartel_n.dds"])
        n = tx.leer_dds(self._texdir(espacio) / "cartel_n.dds")
        self.assertEqual((n.pixeles[3], n.pixeles[63 * 4 + 3]), (235, 25))

    def test_metal_y_rugosidad_sueltos_como_los_exporta_substance(self):
        self.escribir("cartel_BaseColor.png", png(64, 64, self.COLOR))
        self.escribir("cartel_Normal.png", png(64, 64, self.NORMAL))
        self.escribir("cartel_Roughness.png", self._gris(lambda x, y: 100))
        self.escribir("cartel_Metallic.png",
                      self._gris(lambda x, y: 0 if x < 32 else 200))
        rep, espacio = self.correr_fase()
        m = tx.leer_dds(self._texdir(espacio) / "cartel_m.dds")
        self.assertEqual((m.pixeles[0], m.pixeles[63 * 4]), (0, 255))
        n = tx.leer_dds(self._texdir(espacio) / "cartel_n.dds")
        self.assertEqual(set(n.pixeles[3::4]), {155})

    def test_un_roughness_que_no_es_gris_se_rechaza(self):
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        self.escribir("cartel_roughness.png",
                      png(64, 64, rgba(64, 64, lambda x, y: (0, 150, 220, 255))))
        with self.assertRaises(TexturaError) as ctx:
            self.correr_fase()
        self.assertIn("nombralo con _orm", str(ctx.exception))

    def test_una_mascara_saturada_desde_la_fuente_pide_revision(self):
        """Hallazgo de la revisión: `requiere_revision` solo se prendía sin
        fuente de rugosidad. Rugosidad 0 --el hueco negro del atlas-- da alfa
        255 y pasaba callado."""
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        self.escribir("cartel_n.png", png(64, 64, self.NORMAL))
        self.escribir("cartel_orm.png",
                      png(64, 64, rgba(64, 64, lambda x, y: (255, 0, 0, 255))))
        rep, _espacio = self.correr_fase()
        self.assertEqual(rep["requiere_revision"], ["cartel"])
        motivos = rep["texture_sets"][0]["motivos_revision"]
        self.assertTrue(any("en 255" in m for m in motivos), motivos)

    def test_una_mascara_casi_apagada_tambien_pide_revision(self):
        """Media del alfa 5: por debajo del p5 de los portables vanilla (14)."""
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        self.escribir("cartel_n.png", png(64, 64, self.NORMAL))
        self.escribir("cartel_orm.png",
                      png(64, 64, rgba(64, 64, lambda x, y: (255, 250, 0, 255))))
        rep, _espacio = self.correr_fase()
        motivos = rep["texture_sets"][0]["motivos_revision"]
        self.assertTrue(any("fuera del p5-p95" in m for m in motivos), motivos)

    def test_una_mascara_como_las_vanilla_no_pide_revision(self):
        """El par de los dos de arriba: si todo pidiera revisión, no dirían
        nada. Rugosidad 200 -> alfa 55, cerca de la mediana (56)."""
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        self.escribir("cartel_n.png", png(64, 64, self.NORMAL))
        self.escribir("cartel_orm.png",
                      png(64, 64, rgba(64, 64, lambda x, y: (255, 200, 0, 255))))
        rep, _espacio = self.correr_fase()
        self.assertNotIn("requiere_revision", rep)
        self.assertEqual(rep["texture_sets"][0]["motivos_revision"], [])

    def test_normal_y_rugosidad_de_tamanos_distintos_se_combinan(self):
        """Hallazgo de la revisión: se exigía el mismo tamaño ANTES de llevar
        los mapas al tamaño final, y un normal de 128 con un ORM de 64
        hacía fallar la fase."""
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        self.escribir("cartel_n.png",
                      png(128, 128, rgba(128, 128, lambda x, y: (128, 128, 255, 255))))
        self.escribir("cartel_orm.png",
                      png(64, 64, rgba(64, 64, lambda x, y: (255, 200, 40, 255))))
        rep, espacio = self.correr_fase()
        n = tx.leer_dds(self._texdir(espacio) / "cartel_n.dds")
        self.assertEqual((n.ancho, set(n.pixeles[3::4])), (128, {55}))
        obs = [o for o in rep["texture_sets"][0]["observaciones"]
               if o.get("clase") == "mascara_especular"][0]
        self.assertIn("64x64 llevada a 128x128", obs["remuestreo"])

    def test_se_convierten_las_copias_y_no_los_originales(self):
        """Hallazgo de la revisión: la fase hasheaba los originales y los
        volvía a leer después. Si otro proceso los reescribía en el medio,
        el reporte hablaba de bytes que no se convirtieron."""
        original = self.escribir("cartel.png", png(64, 64, self.COLOR))
        espacio = self.ws()
        job = self.job()
        tx.copiar_entradas(job.texture_inputs, espacio)     # lo que hace INGEST
        original.write_bytes(png(64, 64, rgba(64, 64,
                                              lambda x, y: (9, 9, 9, 255))))
        rep = tx.fase_process_texturas(job, espacio)
        tex = tx.leer_dds(self._texdir(espacio) / "cartel.dds")
        self.assertEqual(tex.pixeles[:16], self.COLOR[:16])
        copia = espacio.raiz / "job-tex" / "input" / "texturas" / "cartel.png"
        self.assertEqual(rep["entradas"][0]["sha256"], tx._sha256(copia))
        self.assertEqual(rep["entradas"][0]["copia"], "input/texturas/cartel.png")

    def test_dos_entradas_con_el_mismo_nombre_no_se_pisan(self):
        otra = self.raiz / "otra"
        otra.mkdir()
        (otra / "cartel.png").write_bytes(png(64, 64, self.COLOR))
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        entradas = (self.texdir / "cartel.png", otra / "cartel.png")
        with self.assertRaises(TexturaError) as ctx:
            self.correr_fase(texture_inputs=entradas)
        self.assertIn("mismo nombre", str(ctx.exception))

    def test_la_precondicion_de_uv_queda_escrita(self):
        """La fase no puede comprobar que la malla conserve las UV del
        generador; EXPORT_NIF no puede no enterarse."""
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        rep, espacio = self.correr_fase()
        sets = json.loads((espacio.raiz / "job-tex" / "reports"
                           / "texture_set.json").read_text(encoding="utf-8"))
        self.assertIn("conserva SUS UV", sets["precondicion_uv"])
        self.assertEqual(rep["precondicion_uv"], sets["precondicion_uv"])

    def test_una_oclusion_suelta_se_informa_y_no_arma_un_texture_set(self):
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        self.escribir("cartel_ao.png", self._gris(lambda x, y: 200))
        self.escribir("otra_ao.png", self._gris(lambda x, y: 200))
        rep, _espacio = self.correr_fase()
        self.assertEqual([t["base"] for t in rep["texture_sets"]], ["cartel"])
        self.assertEqual(rep["ignoradas"],
                         [{"archivo": "otra_ao.png", "rol": "oclusion"}])
        self.assertTrue(any(o.get("clase") == "ignorada"
                            for o in rep["texture_sets"][0]["observaciones"]))


class FaseCsPbrTests(EntornoTexturas):
    """sombreado="cs_pbr": el True PBR de Community Shaders.

    Las convenciones salen de su código fuente (commit 898b167,
    BSLightingShaderMaterialPBR.h): ranura 5 = RMAOS con rugosidad en R,
    metalicidad en G, oclusión en B y reflectancia no metálica en A. Van
    LITERALES acá y no leídas de pipeline.texturas: si alguien cambia la
    constante, el test tiene que enterarse."""

    COLOR = FaseTests.COLOR
    NORMAL = FaseTests.NORMAL

    def _texdir(self, espacio, job_id="job-tex"):
        return (espacio.raiz / job_id / "package" / "textures"
                / "static" / job_id)

    def _gris(self, v):
        return png(64, 64, rgba(64, 64, lambda x, y: (v, v, v, 255)))

    def _texel(self, espacio, nombre):
        t = tx.leer_dds(self._texdir(espacio) / nombre)
        return tuple(t.pixeles[:4])

    def _base(self):
        self.escribir("cartel.png", png(64, 64, self.COLOR))
        self.escribir("cartel_n.png", png(64, 64, self.NORMAL))

    def test_el_metallicroughness_de_gltf_da_el_rmaos_sin_oclusion(self):
        """El rojo del metallicRoughness de glTF no es oclusión (Tripo lo deja
        en 255): B sale en 255, "nada ocluido"."""
        self._base()
        self.escribir("cartel_metallicRoughness.png",
                      png(64, 64, rgba(64, 64, lambda x, y: (7, 200, 40, 255))))
        rep, espacio = self.correr_fase(sombreado="cs_pbr")
        self.assertEqual(sorted(p.name for p in self._texdir(espacio).iterdir()),
                         ["cartel.dds", "cartel_n.dds", "cartel_rmaos.dds"])
        self.assertEqual(self._texel(espacio, "cartel_rmaos.dds"),
                         (200, 40, 255, 255))
        self.assertEqual(rep["texture_sets"][0]["sombreado"], "cs_pbr")

    def test_el_orm_lleva_la_oclusion_al_azul(self):
        self._base()
        self.escribir("cartel_orm.png",
                      png(64, 64, rgba(64, 64, lambda x, y: (100, 200, 40, 255))))
        _rep, espacio = self.correr_fase(sombreado="cs_pbr")
        self.assertEqual(self._texel(espacio, "cartel_rmaos.dds"),
                         (200, 40, 100, 255))

    def test_un_ao_suelto_manda_sobre_el_rojo_del_orm(self):
        """Es la salida de hornear.py: `_roughness`, `_metallic` y `_ao`
        sueltos. En vanilla el AO se ignora; acá es el azul."""
        self.escribir("cartel_albedo.png", png(64, 64, self.COLOR))
        self.escribir("cartel_normalgl.png", png(64, 64, self.NORMAL))
        self.escribir("cartel_roughness.png", self._gris(180))
        self.escribir("cartel_metallic.png", self._gris(20))
        self.escribir("cartel_ao.png", self._gris(90))
        rep, espacio = self.correr_fase(sombreado="cs_pbr")
        self.assertEqual(self._texel(espacio, "cartel_rmaos.dds"),
                         (180, 20, 90, 255))
        self.assertFalse(any(o.get("clase") == "ignorada"
                             for o in rep["texture_sets"][0]["observaciones"]),
                         "en cs_pbr el AO se usa, no se ignora")

    def test_sin_metal_el_verde_es_cero(self):
        self._base()
        self.escribir("cartel_roughness.png", self._gris(120))
        _rep, espacio = self.correr_fase(sombreado="cs_pbr")
        self.assertEqual(self._texel(espacio, "cartel_rmaos.dds"),
                         (120, 0, 255, 255))

    def test_sin_rugosidad_no_hay_rmaos_y_es_un_error(self):
        """Una ranura 5 vacía no es neutra: CS pone blanco, rugosidad 1 y
        metal 1 en toda la pieza."""
        self._base()
        with self.assertRaises(TexturaError) as ctx:
            self.correr_fase(sombreado="cs_pbr")
        self.assertIn("sin fuente de rugosidad", str(ctx.exception))

    def test_la_altura_es_el_p_y_la_m_no_se_escribe(self):
        self._base()
        self.escribir("cartel_orm.png",
                      png(64, 64, rgba(64, 64, lambda x, y: (255, 200, 40, 255))))
        self.escribir("cartel_height.png", self._gris(128))
        self.escribir("cartel_m.png", self._gris(200))
        rep, espacio = self.correr_fase(sombreado="cs_pbr")
        nombres = sorted(p.name for p in self._texdir(espacio).iterdir())
        self.assertIn("cartel_p.dds", nombres)
        self.assertNotIn("cartel_m.dds", nombres)
        detalles = [o.get("detalle", "") for o in
                    rep["texture_sets"][0]["observaciones"]]
        self.assertTrue(any("ranura 5 es el `_rmaos`" in d for d in detalles),
                        detalles)

    def test_en_vanilla_la_misma_entrada_da_la_m_y_no_el_rmaos(self):
        """El par de los de arriba: el modo por defecto no cambió."""
        self._base()
        self.escribir("cartel_orm.png",
                      png(64, 64, rgba(64, 64, lambda x, y: (100, 200, 40, 255))))
        self.escribir("cartel_height.png", self._gris(128))
        _rep, espacio = self.correr_fase()
        self.assertEqual(sorted(p.name for p in self._texdir(espacio).iterdir()),
                         ["cartel.dds", "cartel_m.dds", "cartel_n.dds"])

    def test_la_mascara_vanilla_no_pide_revision_en_pbr(self):
        """Rugosidad 0 da alfa 255 en el `_n`: en vanilla pide revisión; en
        PBR el especular sale del `_rmaos` y ese alfa es solo el glossiness
        del SSR."""
        self._base()
        self.escribir("cartel_roughness.png", self._gris(0))
        rep, _espacio = self.correr_fase(sombreado="cs_pbr")
        self.assertNotIn("requiere_revision", rep)

    def test_el_texture_set_dice_ranuras_y_flag_para_el_nif(self):
        self._base()
        self.escribir("cartel_roughness.png", self._gris(120))
        _rep, espacio = self.correr_fase(sombreado="cs_pbr")
        sets = json.loads((espacio.raiz / "job-tex" / "reports"
                           / "texture_set.json").read_text(encoding="utf-8"))
        self.assertEqual(sets["sombreado"], "cs_pbr")
        self.assertEqual(sets["ranuras"], {"color": 0, "normal": 1, "glow": 2,
                                           "parallax": 3, "rmaos": 5})
        self.assertEqual(sets["nif"]["shader_flags_2_bit"], 23)
        self.assertEqual(sets["nif"]["shader_type"], 0)
        self.assertEqual(sets["nif"]["glossiness"], 0.04)
        self.assertEqual(sets["texture_sets"][0]["texturas"]["rmaos"],
                         "textures\\static\\job-tex\\cartel_rmaos.dds")


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

    def test_ingest_copia_las_texturas_e_inspect_sigue_viendo_la_malla(self):
        """INGEST copia las texturas a input/texturas/. INSPECT tomaba "el
        primer archivo de input/", y con una malla que ordena después de
        `texturas` (zeta.glb) habría inspeccionado la carpeta."""
        zeta = self.raiz / "zeta.glb"
        zeta.write_bytes(construir())
        self.escribir("cartel.png",
                      png(8, 8, rgba(8, 8, lambda x, y: (x, y, 0, 255))))
        PipelineRunner(self.job(source_mesh=zeta)).run()
        final = json.loads((self.raiz / "workspace" / "job-tex" / "reports"
                            / "final.json").read_text(encoding="utf-8"))
        ingest = final["fases"]["ingest"]
        self.assertEqual([t["salida"] for t in ingest["texturas"]],
                         ["texturas/cartel.png"])
        copia = (self.raiz / "workspace" / "job-tex" / "input" / "texturas"
                 / "cartel.png")
        self.assertEqual(ingest["texturas"][0]["sha256"], tx._sha256(copia))
        self.assertNotIn("error", final["fases"]["inspect"])
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
