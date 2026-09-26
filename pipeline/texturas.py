# -*- coding: utf-8 -*-
"""Fase PROCESS_TEXTURES: PBR del generador -> texturas DDS para Skyrim.

Se invoca desde el runner (`Phase.PROCESS_TEXTURES`); no tiene línea de
comandos propia a propósito: todo lo que hace pasa por un JobManifest validado
y un workspace de job, que es lo que garantiza que no escriba afuera.

QUE HACE
--------
Toma las texturas declaradas en `JobManifest.texture_inputs`, las agrupa por
nombre base, y por cada grupo escribe un DDS por mapa usando la convención de
sufijos de Skyrim:

    cartel.dds      color base
    cartel_n.dds    normal map, con la máscara especular en el alfa
    cartel_m.dds    máscara de entorno (reflejo del cubemap)
    cartel_g/_s/_p/_b.dds   glow, subsurface, parallax, backlight

Con `sombreado="cs_pbr"` en el manifest escribe para el True PBR de Community
Shaders [PROVIDER]: en vez de `cartel_m.dds`, un `cartel_rmaos.dds` (R
rugosidad, G metal, B oclusión, A 255) para la ranura 5; la altura pasa a ser
el `_p`, y `texture_set.json` lleva las ranuras y los valores del NIF. Las
convenciones salen del código fuente de CS, fijado a un commit (ver
RANURAS_CS_PBR y references/pbr-community-shaders.md de la skill).

Las conversiones de canal son las que la documentación del repo recomienda.
Lo que tiene un número atrás se dice, y lo que es heurística también:

  * el ALFA del `_n` sale de la rugosidad como `255 - roughness`. La CURVA es
    una heurística sin calibrar. Lo que tiene número es el control de después:
    el `_n` escrito se mide con `mascara_especular.py`, y el texture set pide
    revisión si pasa del 10 % de bloques en blanco (la regla de armas; las
    140 `_n` de arma del corpus están por debajo del 6,9 %) o si la media del
    alfa cae fuera del p5-p95 de los objetos portables vanilla (14 a 219). El
    hueco del atlas es rugosidad 0 y sale en 255: ese control es el que lo ve;
  * la máscara `_m` sale del canal de metalicidad, con el rango expandido. Los
    generadores entregan metalicidad muy comprimida --en el proyecto de origen,
    0 a 0,46 con media 0,06-- y sin expandir la máscara sale sin contraste. La
    expansión es una HEURÍSTICA, igual que el piso por debajo del cual el
    objeto se toma como no metálico y no se escribe `_m`; se informan el
    mínimo, el máximo y la media observados para que se pueda auditar;
  * el canal del que sale cada cosa lo decide el NOMBRE del archivo, no una
    mirada a los píxeles: `_orm`/`_metallicRoughness` es el empaquetado de
    glTF (G rugosidad, B metalicidad); `_roughness` y `_metallic` sueltos son
    grises y se comprueba que lo sean;
  * el color base se copia TAL CUAL. La luz horneada (sombras de contacto,
    oclusión, brillo pegado al color) no se saca automáticamente: la
    documentación dice que se atenúa con curvas y que no se recupera del todo,
    así que hacerlo en silencio sería inventar. Se informa como observación.

QUE NO HACE, Y POR QUE NO ES UN DESCUIDO
----------------------------------------
  * NO comprime por defecto. Con `compresion="ninguna"` (el default)
    escribe DDS sin comprimir de 32 bpp: del censo, 10.048 de 32.241 texturas
    vanilla (31,2 %) lo son y el juego las carga igual. Con `"dxt"` escribe
    el `_n` y todo mapa con alfa en DXT5 --los 12.075 `_n` del corpus son
    DXT5-- y el resto en DXT1, con `census/compresor_dxt.py` (numpy). Cada
    DXT escrito se RELEE y se informa el error por canal contra lo que se
    quiso escribir (`error_compresion`), y la máscara especular se mide
    sobre el DXT5, que es lo que llega al juego. BC7 no: el corpus no tiene
    ninguno y `mascara_especular.py` no lo lee.
  * NO escribe el NIF ni toca las rutas de la malla. Deja `texture_set.json`
    en `reports/` con la ruta declarada de cada mapa, que es lo que una fase
    EXPORT_NIF necesita para llenar el `BSShaderTextureSet`.
  * NO valida la correspondencia UV <-> textura. El censo de UV la declara no
    medida, y era el defecto real del proyecto de origen: cada pieza apuntaba
    a la región equivocada del atlas. Los mapas del generador sirven solo si
    la malla final conserva SUS UV; si PREPARE decima o re-despliega sin
    conservarlas, hay que hornear desde el modelo original. Esta fase no lo
    puede comprobar, así que lo deja escrito como `precondicion_uv` en el
    reporte y en `texture_set.json`, para que EXPORT_NIF no lo pase por alto.

VERIFICACION
------------
Cada DDS escrito se pasa por `fixtures/comparar.reglas_dds`, que son REGLAS
con número del censo atrás (`dds_parsea`, `dds_tamano`,
`dds_potencia_de_dos`, `normal_con_alfa`): si una falla, la fase falla. La
máscara especular del `_n` se mide con `mascara_especular.py`; para el alcance
de este manifest (static/clutter) eso INFORMA y no reprueba, porque la regla
de saturación está medida solo sobre armas.

Las rutas declaradas se comprueban con `comparar.resolver_textura`, que
resuelve las cuatro formas del corpus --incluida la del árbol de build de
Bethesda-- y rechaza path traversal. Una ruta que no resuelva es un error de
esta fase, no del cargador del juego.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import struct
import sys
import zlib
from pathlib import Path
from typing import Any, NamedTuple

from .errors import ArtifactValidationError, TexturaError
from .manifest import JobManifest
from .staging import JobWorkspace

# --- las herramientas existentes, invocadas --no reimplementadas------------
# Mismo mecanismo que fixtures/comparar.py: los scripts del repo viven sueltos
# en carpetas que no son paquetes, así que se agregan a sys.path con rutas
# ABSOLUTAS, para que el import no dependa del directorio de trabajo.
_RAIZ = Path(__file__).resolve().parent.parent
for _dir in (_RAIZ / "census", _RAIZ / "fixtures",
             _RAIZ / "skills" / "modelo-ia-a-skyrim" / "scripts"):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

import comparar        # noqa: E402  (needs census/ en sys.path)
import escritor_dds    # noqa: E402
import mascara_especular  # noqa: E402
import parser_dds      # noqa: E402

# --- la convención de sufijos -------------------------------------------------
# Lo que se ESCRIBE lleva siempre el sufijo de Skyrim (cartel, cartel_n,
# cartel_m...). En la ENTRADA se aceptan además los nombres de los generadores
# y de glTF: con un nombre que no reconocía, el archivo caía como color base y
# armaba su propio texture set sin avisar (revisión del PR #51).
#
# Cada sufijo de entrada dice QUÉ es el archivo:
#   slot      se escribe como textura de Skyrim; el rol es el slot;
#   fuente    no se escribe: se dobla dentro del `_n` (rugosidad -> alfa) o
#             del `_m` (metalicidad -> máscara). "empaquetada" es el ORM de
#             glTF (R oclusión o nada, G rugosidad, B metalicidad);
#             "rugosidad" y "metalico" son grises sueltos, y se COMPRUEBA que
#             sean grises;
#   ignorada  no tiene equivalente en el shader de Skyrim (oclusión, altura,
#             opacidad, especular). No se escribe, y se informa.
# El tercer campo es la convención del verde de un normal, si el nombre la da.
# Se busca el sufijo MÁS LARGO primero: `_metallicRoughness` gana sobre el
# `_roughness` que lleva adentro, y `_basecolor` sobre `_color`.
SUFIJOS_ENTRADA = {
    # Skyrim
    "_n": ("slot", "normal", None), "_m": ("slot", "entorno", None),
    "_g": ("slot", "glow", None), "_s": ("slot", "subsurface", None),
    "_p": ("slot", "parallax", None), "_b": ("slot", "backlight", None),
    # color base
    "_basecolor": ("slot", "color", None),
    "_base_color": ("slot", "color", None),
    "_albedo": ("slot", "color", None), "_diffuse": ("slot", "color", None),
    "_diff": ("slot", "color", None), "_d": ("slot", "color", None),
    "_color": ("slot", "color", None),
    # normal
    "_normal": ("slot", "normal", None), "_nor": ("slot", "normal", None),
    "_nrm": ("slot", "normal", None),
    "_normalgl": ("slot", "normal", "gl"),
    "_normaldx": ("slot", "normal", "dx"),
    # el `_g` de Skyrim es un mapa de emisión
    "_emissive": ("slot", "glow", None), "_emission": ("slot", "glow", None),
    # fuentes
    "_orm": ("fuente", "empaquetada", None),
    "_arm": ("fuente", "empaquetada", None),
    "_occlusionroughnessmetallic": ("fuente", "empaquetada", None),
    "_metallicroughness": ("fuente", "empaquetada", None),
    "_metallic_roughness": ("fuente", "empaquetada", None),
    "_metalroughness": ("fuente", "empaquetada", None),
    "_metal_roughness": ("fuente", "empaquetada", None),
    "_roughness": ("fuente", "rugosidad", None),
    "_rough": ("fuente", "rugosidad", None),
    "_metallic": ("fuente", "metalico", None),
    "_metalness": ("fuente", "metalico", None),
    "_metal": ("fuente", "metalico", None),
    # sin equivalente en el shader de Skyrim
    "_ao": ("ignorada", "oclusion", None),
    "_mixed_ao": ("ignorada", "oclusion", None),
    "_occlusion": ("ignorada", "oclusion", None),
    "_ambientocclusion": ("ignorada", "oclusion", None),
    "_height": ("ignorada", "altura", None),
    "_displacement": ("ignorada", "altura", None),
    "_disp": ("ignorada", "altura", None),
    "_bump": ("ignorada", "altura", None),
    "_opacity": ("ignorada", "opacidad", None),
    "_alpha": ("ignorada", "opacidad", None),
    "_specular": ("ignorada", "especular", None),
    "_spec": ("ignorada", "especular", None),
    "_glossiness": ("ignorada", "especular", None),
    "_gloss": ("ignorada", "especular", None),
}
_SUFIJOS_POR_LARGO = sorted(SUFIJOS_ENTRADA, key=len, reverse=True)
ALIAS_DE_COLOR = sorted(s for s, v in SUFIJOS_ENTRADA.items()
                        if v[1] == "color")

# Lo que se escribe: solo sufijos de Skyrim (y el `_rmaos` del True PBR de
# Community Shaders, que es la convencion de PBRNifPatcher).
SUFIJO_ESCRITURA = {"color": "", "normal": "_n", "entorno": "_m",
                    "glow": "_g", "subsurface": "_s",
                    "parallax": "_p", "backlight": "_b", "rmaos": "_rmaos"}

# --- True PBR de Community Shaders [PROVIDER] --------------------------------
# Sacado del codigo fuente, no de memoria: community-shaders/
# skyrim-community-shaders, commit 898b167 (src/TruePBR/
# BSLightingShaderMaterialPBR.h y src/TruePBR.cpp), y contrastado con
# PBRNifPatcher (NifPatcher2.cpp). Ver references/pbr-community-shaders.md.
#
# En que ranura del BSShaderTextureSet va cada mapa. La 4 (cubemap) no se usa,
# y la 5 --la `_m` de vanilla-- es el RMAOS.
RANURAS_CS_PBR = {"color": 0, "normal": 1, "glow": 2, "parallax": 3,
                  "rmaos": 5}
# Lo que el NIF tiene que llevar para que CS lo trate como PBR, y como
# reinterpreta los campos del BSLightingShaderProperty.
NIF_CS_PBR = {
    "shader_type": 0,
    "shader_flags_2_bit": 23,
    "glossiness": 0.04,
    "specular_strength": 1.0,
    "nota": "shader_flags_2 bit 23 (NifSkope: Unused01; CommonLib: "
            "kMenuScreen, bit 55 de 64) prende el PBR. Con PBR, Glossiness es "
            "el nivel especular de lo no metalico (0,04 por defecto en CS) y "
            "Specular Strength la escala de rugosidad: NO son los valores "
            "vanilla (glossiness 80 seria un especular 2.000 veces mayor).",
}
# El `_orm` y el `_arm` llevan la oclusion en R; el `_metallicRoughness` de
# glTF NO (Tripo lo deja en 255, medido sobre el archivo real del hacha).
_EMPAQUETADAS_CON_OCLUSION = ("_orm", "_arm", "_occlusionroughnessmetallic")

# Orden de escritura: el color primero, para que un reporte truncado deje ver
# lo más importante arriba.
ORDEN_SLOTS = ("color", "normal", "entorno", "glow", "subsurface",
               "parallax", "backlight")

# Sufijos que un generador agrega DESPUÉS del rol y que hay que quitar para que
# la base coincida entre el color, el normal y el ORM (`hacha_normal_fixed` y
# `hacha_basecolor` comparten la base `hacha`). Se quitan todos los que haya,
# no uno solo: `x_nor_gl_4k` lleva dos.
_SUFIJOS_EXTRA = (
    "_fixed", "_baked", "_processed", "_final", "_v2", "_v3",
    "_1k", "_2k", "_4k", "_8k",
)

# La convención del verde de un normal. NO es ruido: Skyrim usa OpenGL (verde
# hacia +Y; comprobado con ElvenBattleAxe_n.dds sobre su malla), así que un
# normal DirectX hay que invertirlo en el verde. Descartar el marcador dejaba
# los remaches hundidos y las incisiones salidas, sin error.
_CONVENCION = {"_opengl": "gl", "_directx": "dx", "_gl": "gl", "_dx": "dx"}

# Si la última parte de un nombre que no se reconoció trae una de estas
# palabras, el archivo tiene un rol que esta fase no conoce. Tomarlo por color
# es la falla silenciosa que la revisión del PR #51 encontró; se rechaza.
_PALABRAS_DE_ROL = ("normal", "nrm", "rough", "metal", "occlusion", "emiss",
                    "height", "displac", "opacity", "albedo", "diffuse",
                    "basecolor", "specular", "gloss", "bump")

EXTENSIONES_LEIBLES = frozenset({".png", ".tga", ".dds"})

# Un nombre base se usa para construir rutas dentro del paquete. No se sanitiza
# en silencio: un nombre con separadores sería una ruta, y una ruta que no se
# pidió es cómo un job pisa a otro.
_PATRON_BASE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._+-]{0,63}")

_PNG_FIRMA = b"\x89PNG\r\n\x1a\n"
_CANALES_PNG = {0: 1, 2: 3, 4: 2, 6: 4}


class Textura(NamedTuple):
    """Píxeles en RGBA, sin entrelazar, una fila tras otra."""

    ancho: int
    alto: int
    pixeles: bytes


# ---------------------------------------------------------------------------
# Lectura de entrada
# ---------------------------------------------------------------------------

def leer_png(ruta: Path) -> Textura:
    """PNG de 8 bits, sin entrelazar, color 0/2/4/6. Python puro (zlib).

    Se rechazan con mensaje explícito --no se adivinan-- la paleta (color 3),
    los 16 bits y el entrelazado Adam7: los tres cambian el formato de los
    datos y un lector a medias devuelve una imagen plausible y equivocada.
    """
    datos = Path(ruta).read_bytes()
    if datos[:8] != _PNG_FIRMA:
        raise TexturaError(f"{ruta}: no empieza con la firma de PNG")
    ancho = alto = profundidad = color = entrelazado = None
    idat = bytearray()
    pos = 8
    while pos + 8 <= len(datos):
        largo, tipo = struct.unpack_from(">I4s", datos, pos)
        pos += 8
        cuerpo = datos[pos:pos + largo]
        if len(cuerpo) != largo:
            raise TexturaError(f"{ruta}: chunk {tipo!r} truncado")
        pos += largo + 4                      # + CRC, que no se verifica
        if tipo == b"IHDR":
            ancho, alto, profundidad, color, _, _, entrelazado = \
                struct.unpack(">IIBBBBB", cuerpo)
        elif tipo == b"IDAT":
            idat += cuerpo
        elif tipo == b"IEND":
            break
    if ancho is None or alto is None:
        raise TexturaError(f"{ruta}: PNG sin IHDR")
    if profundidad != 8:
        raise TexturaError(
            f"{ruta}: profundidad {profundidad} bits; este lector solo hace "
            f"8 (un PNG de 16 hay que bajarlo antes, no se truncan bytes)")
    if entrelazado:
        raise TexturaError(
            f"{ruta}: PNG entrelazado (Adam7); se necesita uno no entrelazado")
    if color not in _CANALES_PNG:
        raise TexturaError(
            f"{ruta}: tipo de color {color} no soportado "
            f"(soportados: {sorted(_CANALES_PNG)}; la paleta, 3, hay que "
            f"expandirla antes)")

    try:
        crudo = zlib.decompress(bytes(idat))
    except zlib.error as e:
        raise TexturaError(f"{ruta}: IDAT no descomprime: {e}") from e

    canales = _CANALES_PNG[color]
    stride = ancho * canales
    if len(crudo) != (stride + 1) * alto:
        raise TexturaError(
            f"{ruta}: {len(crudo)} bytes de datos para {ancho}x{alto}x"
            f"{canales} (se esperaban {(stride + 1) * alto})")
    if ancho == 0 or alto == 0:
        raise TexturaError(f"{ruta}: dimensiones {ancho}x{alto}")

    salida = bytearray(ancho * alto * 4)
    previo = bytearray(stride)
    for y in range(alto):
        base = y * (stride + 1)
        filtro = crudo[base]
        if filtro > 4:
            raise TexturaError(f"{ruta}: filtro de línea {filtro} desconocido")
        linea = bytearray(crudo[base + 1: base + 1 + stride])
        if filtro == 1:                                    # Sub
            for i in range(canales, stride):
                linea[i] = (linea[i] + linea[i - canales]) & 0xFF
        elif filtro == 2:                                  # Up
            for i in range(stride):
                linea[i] = (linea[i] + previo[i]) & 0xFF
        elif filtro == 3:                                  # Average
            for i in range(stride):
                a = linea[i - canales] if i >= canales else 0
                linea[i] = (linea[i] + ((a + previo[i]) >> 1)) & 0xFF
        elif filtro == 4:                                  # Paeth
            for i in range(stride):
                a = linea[i - canales] if i >= canales else 0
                b = previo[i]
                c = previo[i - canales] if i >= canales else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                linea[i] = (linea[i] + pr) & 0xFF
        previo = linea
        for x in range(ancho):
            o = x * canales
            d = (x + y * ancho) * 4
            if canales == 1:
                salida[d:d + 4] = bytes((linea[o], linea[o], linea[o], 255))
            elif canales == 2:
                salida[d:d + 4] = bytes(
                    (linea[o], linea[o], linea[o], linea[o + 1]))
            elif canales == 3:
                salida[d:d + 4] = bytes(
                    (linea[o], linea[o + 1], linea[o + 2], 255))
            else:
                salida[d:d + 4] = linea[o:o + 4]
    return Textura(ancho, alto, bytes(salida))


def leer_tga(ruta: Path) -> Textura:
    """TGA sin comprimir: tipo 2 (truecolor) y 3 (escala de grises).

    El RLE (tipo 10) se rechaza: es otro formato de datos y leerlo a medias
    daría una imagen corrida sin ningún síntoma.
    """
    datos = Path(ruta).read_bytes()
    if len(datos) < 18:
        raise TexturaError(f"{ruta}: TGA de {len(datos)} bytes, no llega a "
                           f"la cabecera de 18")
    id_len, tipo_cmap, tipo = datos[0], datos[1], datos[2]
    if tipo_cmap:
        raise TexturaError(f"{ruta}: TGA con color map (tipo {tipo_cmap}); "
                           f"no soportado")
    if tipo not in (2, 3):
        raise TexturaError(
            f"{ruta}: tipo de imagen TGA {tipo}; solo 2 (truecolor) y 3 "
            f"(escala de grises) sin comprimir. El RLE (10) hay que "
            f"descomprimirlo antes")
    ancho, alto = struct.unpack_from("<HH", datos, 12)
    profundidad = datos[16]
    descriptor = datos[17]
    if ancho == 0 or alto == 0:
        raise TexturaError(f"{ruta}: dimensiones {ancho}x{alto}")
    # El tipo 3 (grises) es de 8 bits, un byte por texel: es como sale un mapa
    # de rugosidad. El tipo 2 es BGR o BGRA. Otra combinación se rechaza: un
    # tipo 3 de 24 bits leído como BGR daría colores inventados.
    esperadas = (8,) if tipo == 3 else (24, 32)
    if profundidad not in esperadas:
        raise TexturaError(
            f"{ruta}: TGA tipo {tipo} de {profundidad} bits por pixel; se "
            f"esperan {' o '.join(str(e) for e in esperadas)}")
    canales = profundidad // 8
    pos = 18 + id_len
    cuerpo = datos[pos:pos + ancho * alto * canales]
    if len(cuerpo) != ancho * alto * canales:
        raise TexturaError(
            f"{ruta}: {len(cuerpo)} bytes de pixel para {ancho}x{alto}x"
            f"{canales} (se esperaban {ancho * alto * canales})")
    # El bit 5 del descriptor dice si la primera fila es la de arriba. Un TGA
    # guarda BGR(A); el DDS que escribimos después quiere RGBA.
    arriba = bool(descriptor & 0x20)
    salida = bytearray(ancho * alto * 4)
    for y in range(alto):
        fila = y if arriba else (alto - 1 - y)
        for x in range(ancho):
            o = (fila * ancho + x) * canales
            d = (y * ancho + x) * 4
            if canales == 1:
                v = cuerpo[o]
                salida[d:d + 4] = bytes((v, v, v, 255))
            elif canales == 3:
                salida[d:d + 4] = bytes((cuerpo[o + 2], cuerpo[o + 1],
                                         cuerpo[o], 255))
            else:
                salida[d:d + 4] = bytes((cuerpo[o + 2], cuerpo[o + 1],
                                         cuerpo[o], cuerpo[o + 3]))
    return Textura(ancho, alto, bytes(salida))


def _offset_mascara(mask: int) -> int:
    """Desplazamiento en BYTES del byte menos significativo de la máscara.

    La máscara tiene que ser un bloque contiguo de 8 bits (un byte entero),
    que es lo que vale para todo A8R8G8B8/X8R8G8B8/B8G8R8A8 de 32 bpp. Si
    no lo es, se devuelve -1 para que el caller rechace el archivo en vez
    de inventar el orden.
    """
    if mask == 0:
        return -1
    # Quitar los bits cero de la derecha; contar BITS, luego dividir por 8.
    bits_off = 0
    m = mask
    while m and (m & 1) == 0:
        m >>= 1
        bits_off += 1
    if bits_off % 8 != 0:
        return -1
    # Tiene que ser un byte contiguo
    if (m & 0xFF) != 0xFF:
        return -1
    m >>= 8
    if m != 0:
        return -1
    return bits_off // 8


# BGRA canónico: como lo escribe census/escritor_dds.py y como están los
# 10.048 vanilla sin comprimir del censo.
_BGRA = {"r_off": 2, "g_off": 1, "b_off": 0, "a_off": 3}


def _orden_canales(d: dict) -> dict:
    """{r_off, g_off, b_off, a_off} a partir de las máscaras del header.

    Falla si las máscaras no describen canales de 8 bits contiguos en un
    DDS de 32 bpp, o si el orden no es el BGRA que esta fase escribe y que
    verifica el censo. Asumir BGRA a ciegas sobre un RGBA de otra herramienta
    devuelve colores y normales invertidos sin error; decirlo es más barato.
    """
    r, g, b, a = d["r_mask"], d["g_mask"], d["b_mask"], d["a_mask"]
    # Sin máscaras (p. ej. un DX10 B8G8R8A8 que ya habrá sido rechazado por
    # formato): no hay nada que decidir, asumir BGRA. Este camino no se
    # alcanza para un sin_comprimir_32bpp válido porque ese formato siempre
    # trae las máscaras en el pixel format.
    if r == g == b == 0:
        return dict(_BGRA)
    offs = {"r_off": _offset_mascara(r), "g_off": _offset_mascara(g),
            "b_off": _offset_mascara(b), "a_off": _offset_mascara(a) if a else 3}
    if any(v < 0 or v > 3 for v in offs.values()):
        raise TexturaError(
            "orden de canales no soportado (máscaras R=%08X G=%08X B=%08X "
            "A=%08X): los canales no son bytes contiguos de 8 bits. Esta "
            "fase escribe y lee BGRA de 8 bits por canal." % (r, g, b, a))
    if offs != _BGRA:
        # Nombrar el orden que se encontró para que el mensaje diga qué se
        # esperaba y qué se recibió, en vez de fallar con un genérico.
        nombres = {v: k for k, v in offs.items()}
        orden = "".join(nombres.get(i, "?")[0].upper() for i in range(4))
        raise TexturaError(
            "orden de canales %s no soportado; esta fase solo lee BGRA "
            "(R_mask=00FF0000 G=0000FF00 B=000000FF A=FF000000), que es el "
            "que escribe y el que usan los 10.048 vanilla sin comprimir "
            "del censo. Convertilo antes con `texconv -f BGRA8_UNORM`." % orden)
    return offs


def leer_dds(ruta: Path) -> Textura:
    """DDS SIN comprimir de 32 bpp, nivel 0, orden BGRA.

    Un DDS comprimido de ENTRADA se rechaza, con el número del censo al
    lado: leerlo sería descomprimir un DXT para volver a comprimirlo, y cada
    pasada pierde. La entrada tiene que ser el original sin pérdida (PNG,
    TGA o DDS sin comprimir); la compresión es de la salida
    (`compresion="dxt"`). Un DDS sin comprimir con otro orden
    de canales (RGBA, ARGB) también se rechaza, con las máscaras que trae
    el header en el mensaje: asumir BGRA a ciegas devolvía colores
    invertidos sin ningún error.
    """
    d = parser_dds.leer(ruta)          # lanza DdsInvalido si no parsea
    if d["comprimido"]:
        raise TexturaError(
            f"{ruta}: formato {d['formato']} comprimido; esta fase lee DDS "
            f"sin comprimir (32 bpp). Del censo, 10.048 de 32.241 texturas "
            f"vanilla son sin comprimir, así que no es un caso exótico. "
            f"Recomprimir un DXT pierde otra vez: pasá el original (PNG, TGA) "
            f"y pedí la compresión con compresion='dxt'")
    if d["formato"] != "sin_comprimir_32bpp":
        raise TexturaError(
            f"{ruta}: formato {d['formato']}; se esperaba sin_comprimir_32bpp")
    offs = _orden_canales(d)
    ancho, alto = d["ancho"], d["alto"]
    with open(ruta, "rb") as fh:
        fh.seek(128)
        crudo = fh.read(ancho * alto * 4)
    if len(crudo) != ancho * alto * 4:
        raise TexturaError(f"{ruta}: el archivo no llega a contener el nivel 0")
    salida = bytearray(len(crudo))
    r_o, g_o, b_o, a_o = offs["r_off"], offs["g_off"], offs["b_off"], offs["a_off"]
    salida[0::4] = crudo[r_o::4]
    salida[1::4] = crudo[g_o::4]
    salida[2::4] = crudo[b_o::4]
    # Sin máscara alfa (X8R8G8B8) el cuarto byte es relleno y vale lo que dejó
    # la herramienta que exportó. Leído como alfa daba 0 con algunas: una
    # máscara especular apagada que el control de saturación no ve.
    if d["a_mask"]:
        salida[3::4] = crudo[a_o::4]
    else:
        salida[3::4] = b"\xff" * (ancho * alto)
    return Textura(ancho, alto, bytes(salida))


def leer_textura(ruta: Path | str) -> Textura:
    """Despacha por extensión. Extensión desconocida = error, no una suposición."""
    ruta = Path(ruta)
    ext = ruta.suffix.lower()
    try:
        if ext == ".png":
            return leer_png(ruta)
        if ext == ".tga":
            return leer_tga(ruta)
        if ext == ".dds":
            return leer_dds(ruta)
    except TexturaError:
        raise
    except (OSError, struct.error, ValueError) as e:
        raise TexturaError(f"{ruta}: {type(e).__name__}: {e}") from e
    raise TexturaError(
        f"{ruta}: extensión {ext!r} no soportada "
        f"(soportadas: {sorted(EXTENSIONES_LEIBLES)})")


# ---------------------------------------------------------------------------
# Clasificación por nombre
# ---------------------------------------------------------------------------

class Rol(NamedTuple):
    """Lo que dice el nombre de un archivo de entrada."""

    clase: str          # "slot", "fuente" o "ignorada"
    rol: str            # el slot, el tipo de fuente o lo que se ignora
    sufijo: str         # el sufijo reconocido, en minúsculas ("" = sin sufijo)
    base: str           # el nombre del texture set
    convencion: str | None = None   # "gl"/"dx" si el nombre de un normal la da


def _quitar_extras(tallo: str) -> tuple[str, str | None]:
    """(tallo sin los sufijos del generador, convención del verde o None).

    Se quitan TODOS los sufijos extra que haya al final, y a lo sumo un
    marcador de convención, en cualquier orden: `x_nor_gl_4k` da `x_nor`, gl.
    """
    convencion = None
    cambio = True
    while cambio:
        cambio = False
        bajo = tallo.lower()
        for x in _SUFIJOS_EXTRA:
            if bajo.endswith(x) and len(tallo) > len(x):
                tallo, cambio = tallo[:-len(x)], True
                break
        if cambio or convencion is not None:
            continue
        for x, conv in _CONVENCION.items():
            if bajo.endswith(x) and len(tallo) > len(x):
                tallo, convencion, cambio = tallo[:-len(x)], conv, True
                break
    return tallo, convencion


def _clasificar_tallo(tallo: str) -> Rol:
    tallo, convencion = _quitar_extras(tallo)
    bajo = tallo.lower()
    rol = None
    for sufijo in _SUFIJOS_POR_LARGO:
        if bajo.endswith(sufijo) and len(tallo) > len(sufijo):
            clase, que, conv_sufijo = SUFIJOS_ENTRADA[sufijo]
            rol = Rol(clase, que, sufijo, tallo[:-len(sufijo)],
                      convencion or conv_sufijo)
            break
    if rol is None:
        ultima = bajo.rsplit("_", 1)[-1] if "_" in bajo else ""
        palabra = next((p for p in _PALABRAS_DE_ROL if p in ultima), None)
        if palabra is not None:
            raise TexturaError(
                f"{tallo}: el nombre termina en {ultima!r}, que parece un rol "
                f"PBR ({palabra!r}) que esta fase no reconoce. Tomarlo por "
                f"color base armaria un texture set de mas sin avisar. "
                f"Renombralo con un sufijo conocido: "
                f"{', '.join(sorted(SUFIJOS_ENTRADA))}")
        rol = Rol("slot", "color", "", tallo, convencion)
    if rol.convencion is not None and rol.rol != "normal":
        raise TexturaError(
            f"{tallo}: marca una convencion de normal ({rol.convencion}) en un "
            f"archivo que no es un normal ({rol.rol})")
    return rol


def clasificar(nombre: str) -> Rol:
    """Qué es un archivo de entrada, según su nombre.

    El sufijo se busca al FINAL del tallo, en minúsculas: `Cartel_N.PNG` es un
    normal map, `hacha_BaseColor.png` es color base. Un nombre sin sufijo es
    el color base --la forma más común del corpus: 19.108 de 32.241 texturas
    no tienen sufijo--, salvo que su última parte traiga una palabra de rol
    que no se reconoce: eso es un error, no un color.

    Los sufijos del generador (`_fixed`, `_2k`...) se quitan antes, y un
    marcador `_gl`/`_dx` se conserva como la convención del normal.

    Tripo entrega el metal y la rugosidad en UN archivo con los dos nombres
    unidos por un guion (`<base>_metallic-<base>_roughness_fixed.png`). Es el
    empaquetado de glTF: R en 255, G rugosidad, B metalicidad (medido sobre el
    archivo real del hacha de Tencent). Se reconoce como fuente empaquetada.
    """
    tallo = Path(nombre).stem
    if tallo.count("-") == 1:
        tallo_sin, _conv = _quitar_extras(tallo)
        izq, der = tallo_sin.split("-")
        a: Rol | None
        b: Rol | None
        try:
            a, b = _clasificar_tallo(izq), _clasificar_tallo(der)
        except TexturaError:
            a = b = None
        if (a is not None and b is not None and a.clase == b.clase == "fuente"
                and {a.rol, b.rol} == {"rugosidad", "metalico"}
                and a.base.lower() == b.base.lower()):
            return Rol("fuente", "empaquetada", "%s-%s" % (a.sufijo, b.sufijo),
                       a.base)
    return _clasificar_tallo(tallo)


# ---------------------------------------------------------------------------
# Geometría: potencia de dos y redimensionado
# ---------------------------------------------------------------------------

def siguiente_potencia(n: int) -> int:
    p = 1
    while p < n:
        p <<= 1
    return p


def ajustar_tamano(ancho: int, alto: int, max_lado: int
                   ) -> tuple[int, int, str]:
    """(ancho2, alto2, que_pasó) con potencia de dos en ambos lados.

    Redondear HACIA ARRIBA siempre que se pueda: achicar para llegar a la
    potencia pierde píxeles que no se recuperan. El tope `max_lado` es el
    único caso en que se reduce, y se dice.
    """
    w, h = siguiente_potencia(ancho), siguiente_potencia(alto)
    while max(w, h) > max_lado:
        w = max(1, w // 2)
        h = max(1, h // 2)
    if (w, h) == (ancho, alto):
        return w, h, "ya era potencia de dos"
    if w < ancho or h < alto:
        return w, h, "reducido al tope del manifest"
    return w, h, "redondeado hacia arriba a potencia de dos"


# Los mapas que son COLOR, y por eso vienen en sRGB. El resto son datos
# (máscara de entorno, altura) y se promedian tal cual.
SLOTS_SRGB = frozenset({"color", "glow", "subsurface", "backlight"})

# sRGB -> luz lineal, por byte. El tramo lineal va hasta 0,04045 (c <= 10).
_A_LINEAL = tuple(c / 255.0 / 12.92 if c <= 10
                  else ((c / 255.0 + 0.055) / 1.055) ** 2.4
                  for c in range(256))


def _a_srgb(v: float) -> int:
    """Luz lineal -> byte sRGB. Inversa de `_A_LINEAL` (ida y vuelta exacta
    en los 256 valores; lo fija un test)."""
    if v <= 0.0031308:
        s = v * 12.92
    else:
        s = 1.055 * v ** (1.0 / 2.4) - 0.055
    return max(0, min(255, int(s * 255.0 + 0.5)))


def redimensionar(tex: Textura, ancho2: int, alto2: int,
                  slot: str = "color") -> Textura:
    """Remuestreo por cajas (box filter), promediando 2x2 o el bloque que toque.

    Cada mapa se promedia como lo que es (trampa 35 de la skill):

      * color (`SLOTS_SRGB`): en LUZ LINEAL y de vuelta a sRGB. Promediar los
        valores sRGB oscurece los bordes con contraste;
      * normal: los vectores, y después se RENORMALIZAN. El promedio de cuatro
        normales unitarias distintas es más corto que 1 y aplana el relieve;
      * el resto, y el alfa de todos: tal cual, porque son datos lineales.

    La misma función arma los mipmaps (`escribir_dds`), así que la regla vale
    para toda la cadena y no solo para el nivel 0.
    """
    if (tex.ancho, tex.alto) == (ancho2, alto2):
        return tex
    if ancho2 <= 0 or alto2 <= 0:
        raise TexturaError(f"destino inválido: {ancho2}x{alto2}")
    salida = bytearray(ancho2 * alto2 * 4)
    es_normal = slot == "normal"
    es_srgb = slot in SLOTS_SRGB
    pix = tex.pixeles
    for y2 in range(alto2):
        y0 = y2 * tex.alto // alto2
        y1 = max(y0 + 1, (y2 + 1) * tex.alto // alto2)
        for x2 in range(ancho2):
            x0 = x2 * tex.ancho // ancho2
            x1 = max(x0 + 1, (x2 + 1) * tex.ancho // ancho2)
            acc = [0, 0, 0, 0]
            lin = [0.0, 0.0, 0.0]
            n = 0
            for y in range(y0, min(y1, tex.alto)):
                for x in range(x0, min(x1, tex.ancho)):
                    o = (y * tex.ancho + x) * 4
                    for c in range(4):
                        acc[c] += pix[o + c]
                    if es_srgb:
                        for c in range(3):
                            lin[c] += _A_LINEAL[pix[o + c]]
                    n += 1
            d = (y2 * ancho2 + x2) * 4
            salida[d + 3] = (acc[3] + n // 2) // n
            if es_normal:
                # (R,G,B) = n*0,5+0,5 por componente.
                nx = (acc[0] / n) / 255.0 * 2.0 - 1.0
                ny = (acc[1] / n) / 255.0 * 2.0 - 1.0
                nz = (acc[2] / n) / 255.0 * 2.0 - 1.0
                ln = math.sqrt(nx * nx + ny * ny + nz * nz)
                if ln > 1e-6:
                    nx, ny, nz = nx / ln, ny / ln, nz / ln
                else:
                    nx, ny, nz = 0.0, 0.0, 1.0
                for c, v in enumerate((nx, ny, nz)):
                    salida[d + c] = max(0, min(255,
                                               int((v * 0.5 + 0.5) * 255 + 0.5)))
            elif es_srgb:
                for c in range(3):
                    salida[d + c] = _a_srgb(lin[c] / n)
            else:
                for c in range(3):
                    salida[d + c] = (acc[c] + n // 2) // n
    return Textura(ancho2, alto2, bytes(salida))


# ---------------------------------------------------------------------------
# Conversión de canales
# ---------------------------------------------------------------------------

def _estadisticas(pixeles: bytes, paso: int = 4) -> dict:
    """min/max/media de un canal, muestreando. Muestrear y decirlo, no recorrer
    todo y llamarlo exacto."""
    vals = pixeles[::paso]
    if not vals:
        return {"min": None, "max": None, "media": None, "n": 0}
    return {"min": min(vals), "max": max(vals),
            "media": round(sum(vals) / len(vals), 2), "n": len(vals)}


def es_gris(tex: Textura, lado: int = 64) -> dict:
    """¿R == G == B? Mirando una grilla de `lado` x `lado` téxeles repartida
    por TODA la imagen.

    Solo se usa para COMPROBAR que un `_roughness` o un `_metallic` suelto es
    lo que dice su nombre; qué canal se lee lo decide el nombre. La versión
    anterior decidía el canal mirando los primeros 4.096 téxeles, que en una
    textura de 4096 de ancho son la primera fila --justo el borde vacío del
    atlas-- y un ORM de glTF con el rojo sin usar pasaba por gris.
    """
    xs = sorted({(2 * i + 1) * tex.ancho // (2 * lado) for i in range(lado)})
    ys = sorted({(2 * i + 1) * tex.alto // (2 * lado) for i in range(lado)})
    p = tex.pixeles
    distintos = sum(1 for y in ys for x in xs
                    if not (p[(y * tex.ancho + x) * 4]
                            == p[(y * tex.ancho + x) * 4 + 1]
                            == p[(y * tex.ancho + x) * 4 + 2]))
    return {"gris": distintos == 0, "muestra_texeles": len(xs) * len(ys),
            "no_grises": distintos}


def _canal(tex: Textura, cual: str) -> bytes:
    """Un canal de la textura, un byte por téxel.

    Con corte y paso, no con un generador: sobre un mapa de 4 millones de
    téxeles, la diferencia es entre un corte de C y varios segundos de Python.
    """
    idx = {"r": 0, "g": 1, "b": 2, "a": 3}[cual]
    return tex.pixeles[idx::4]


_INVERTIR = bytes(range(255, -1, -1))


def alfa_desde_rugosidad(tex_n: Textura, tex_rug: Textura, canal: str
                         ) -> tuple[Textura, float]:
    """El alfa del `_n` es la máscara especular: `255 - roughness`.

    Las dos texturas tienen que medir lo mismo. No es que no se pueda
    remuestrear --las dos cubren el mismo espacio UV, y `_procesar_base` las
    lleva al tamaño final ANTES de llamar acá--, es que esta función no
    remuestrea: con tamaños distintos asociaría téxeles que no se tocan.

    Devuelve (textura, % de téxeles del alfa en 255).
    """
    if (tex_n.ancho, tex_n.alto) != (tex_rug.ancho, tex_rug.alto):
        raise TexturaError(
            f"el normal mide {tex_n.ancho}x{tex_n.alto} y la rugosidad "
            f"{tex_rug.ancho}x{tex_rug.alto}: hay que llevarlas al mismo "
            f"tamaño antes de combinarlas")
    pix = bytearray(tex_n.pixeles)
    pix[3::4] = _canal(tex_rug, canal).translate(_INVERTIR)
    alfa = pix[3::4]
    saturacion = 100.0 * alfa.count(255) / max(1, len(alfa))
    return Textura(tex_n.ancho, tex_n.alto, bytes(pix)), saturacion


def invertir_verde(tex: Textura) -> Textura:
    """Normal DirectX -> OpenGL, que es lo que usa Skyrim: G' = 255 - G."""
    pix = bytearray(tex.pixeles)
    pix[1::4] = bytes(pix[1::4]).translate(_INVERTIR)
    return Textura(tex.ancho, tex.alto, bytes(pix))


def expandir_rango(tex: Textura, canal: str = "g") -> tuple[Textura, dict]:
    """Estira [min, max] del canal a [0, 255] y devuelve lo observado.

    HEURÍSTICA, y se declara: no hay medición del corpus que fije cuánto hay
    que expandir. Lo que sí hay es la medición de que los generadores entregan
    metalicidad comprimida (0 a 0,46 con media 0,06 en el proyecto de origen)
    y de que sin expandir la máscara sale sin contraste. Los números observados
    viajan en el reporte para que se puedan auditar.
    """
    vals = _canal(tex, canal)
    lo, hi = min(vals), max(vals)
    obs = {"canal": canal, "min": lo, "max": hi,
           "media": round(sum(vals) / len(vals), 2)}
    if hi <= lo:
        obs["expansion"] = "ninguna: el mapa es plano"
        return tex, obs
    pix = bytearray(tex.pixeles)
    idx = {"r": 0, "g": 1, "b": 2, "a": 3}[canal]
    span = hi - lo
    for i in range(idx, len(pix), 4):
        pix[i] = ((pix[i] - lo) * 255 + span // 2) // span
    obs["expansion"] = f"[{lo}, {hi}] -> [0, 255]"
    return Textura(tex.ancho, tex.alto, bytes(pix)), obs


# Por debajo de este máximo la metalicidad es ruido de compresión sobre un
# objeto que no es de metal, y no se escribe `_m`. HEURÍSTICA: 16 es el 6 % del
# rango; una región metálica real de un generador llega mucho más arriba (en el
# proyecto de origen, a 117). Sin este piso, `expandir_rango` estiraba un
# máximo de 2 a 255 y la máscara salía salpicada de reflejo total.
PISO_METAL = 16


def entorno_desde_metalico(tex_fuente: Textura, canal: str = "b"
                           ) -> tuple[Textura | None, dict]:
    """La máscara `_m` desde la metalicidad, con rango expandido.

    `_m` NO es la metalicidad de PBR: controla cuánto refleja el cubemap del
    shader Environment_Map. El canal de metalicidad es la mejor fuente
    disponible, y por eso se usa, pero la máscara sale en escala de grises.

    Devuelve (None, info) si el máximo no llega a `PISO_METAL`: el objeto no
    es metálico y una `_m` inventada sería peor que ninguna.
    """
    vals = _canal(tex_fuente, canal)
    if max(vals) < PISO_METAL:
        return None, {
            "canal": canal, "max": max(vals),
            "nota": "metalicidad maxima %d < %d (heuristica): el objeto no es "
                    "metalico y no se escribe _m" % (max(vals), PISO_METAL)}
    tex, obs = expandir_rango(tex_fuente, canal)
    v = _canal(tex, canal)
    pix = bytearray(len(v) * 4)
    for c in range(3):
        pix[c::4] = v
    pix[3::4] = b"\xff" * len(v)
    return Textura(tex.ancho, tex.alto, bytes(pix)), {
        "canal": canal, "expansion": obs,
        "nota": "mascara en escala de grises: _m es reflejo de cubemap, no "
                "metalicidad de PBR",
    }


# ---------------------------------------------------------------------------
# Escritura y verificación
# ---------------------------------------------------------------------------

def formato_dds(slot: str, tex: Textura, compresion: str) -> str:
    """El formato de cada mapa: "RGBA" (sin comprimir), "DXT1" o "DXT5".

    Con "dxt": el `_n` siempre DXT5, porque su alfa es la máscara especular
    aunque venga en 255 (12.075 de 12.075 `_n` vanilla son DXT5; DXT1 no
    tiene alfa y la máscara desaparece). Cualquier otro mapa con algún téxel
    de alfa < 255 va en DXT5; el resto en DXT1, que pesa la mitad. En el
    corpus, `_d` es DXT1 en el 57 % y `_m` en el 36 %
    (census/hallazgos_texturas.md, hallazgo 7).
    """
    if compresion == "ninguna":
        return "RGBA"
    if slot == "normal":
        return "DXT5"
    opaco = tex.pixeles[3::4].count(255) == tex.ancho * tex.alto
    return "DXT1" if opaco else "DXT5"


def escribir_dds(tex: Textura, ruta: Path, slot: str = "color",
                 formato: str = "RGBA") -> Path:
    """DDS con la cadena completa de mipmaps, sin comprimir o DXT1/DXT5.

    Delega en `census/escritor_dds.py`, que ya está verificado: su autotest
    compara el tamaño que predice `parser_dds` contra el real y RELEE los
    píxeles escritos. La cadena baja hasta 1x1; el corpus corta en 2x2 en el
    96,4 % de los casos, así que tener el nivel de más no es un defecto --y
    medir "cadena completa" contra 1x1 marcaba 31.940 texturas correctas como
    rotas.

    Cada mipmap se arma con `redimensionar(..., slot)`: el color en luz lineal
    y el normal renormalizado en TODOS los niveles, no solo en el primero.
    """
    def reducir_nivel(pix: bytes, ancho: int, alto: int) -> bytes:
        return redimensionar(Textura(ancho, alto, pix), max(1, ancho // 2),
                             max(1, alto // 2), slot).pixeles

    ruta.parent.mkdir(parents=True, exist_ok=True)
    return escritor_dds.escribir(str(ruta), tex.ancho, tex.alto,
                                 tex.pixeles, con_mipmaps=True,
                                 reducir_nivel=reducir_nivel,
                                 formato=formato)


def error_compresion(tex: Textura, ruta: Path) -> dict:
    """Relee el nivel 0 de un DXT escrito y mide el error contra `tex`.

    RMS y máximo por canal, en niveles de 0 a 255. No reprueba: no hay un
    número del corpus que diga cuánto error es mucho. Informa, para que un
    mapa que el compresor destrozó se vea en el reporte y no en el juego.
    """
    import numpy as np
    _d, vuelta = escritor_dds.leer_pixeles(str(ruta))
    a = np.frombuffer(tex.pixeles, np.uint8).reshape(-1, 4).astype(np.int32)
    b = np.frombuffer(vuelta, np.uint8).reshape(-1, 4).astype(np.int32)
    dif = np.abs(a - b)
    return {"rms": [round(float(v), 2)
                    for v in np.sqrt((dif.astype(np.float64) ** 2).mean(0))],
            "maximo": [int(v) for v in dif.max(0)],
            "canales": "RGBA"}


def validar_salida(ruta: Path, declarada: str) -> list[str]:
    """Pasa el DDS por las REGLAS del contrato. Devuelve las claves que fallan.

    `reglas_dds` no decora: cada regla lleva el número del censo que la
    sostiene, y hay un test que exige que cada una repruebe en algún caso.
    """
    malas = [clave for ok, clave, _det, _ev in comparar.reglas_dds(str(ruta),
                                                                  declarada)
             if not ok]
    return malas


def medir_mascara(ruta: Path) -> dict:
    """Mide el alfa del `_n` sin decodificar. Para static/clutter INFORMA.

    La regla de saturación (<= 10 % de bloques en blanco) está medida sobre
    las 140 texturas `_n` de malla de ARMA y declarada solo para armas; para
    el resto, `juzgar(es_arma=False)` devuelve notas, porque 59 de 1.201
    objetos portables vanilla están saturados y son materiales mate. Acá se
    respeta ese alcance en vez de convertirlo en regla universal.
    """
    m = mascara_especular.medir(str(ruta))
    fallas, notas = mascara_especular.juzgar(m, es_arma=False)
    return {"medicion": m, "fallas": fallas, "notas": notas}


def ruta_declarada(categoria: str, job_id: str, nombre: str) -> str:
    """La ruta como la declara el NIF: con `textures\\` y separadores Windows.

    La mayoría del corpus usa ese prefijo (87,8 %) y el juego también carga la
    forma relativa (12,2 %). Se usa la forma con prefijo porque es la que
    resuelve cualquier herramienta, y `comparar.resolver_textura` la acepta.
    """
    return "textures\\%s\\%s\\%s.dds" % (categoria, job_id, nombre)


# ---------------------------------------------------------------------------
# La fase
# ---------------------------------------------------------------------------

def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def copiar_entradas(rutas, ws: JobWorkspace) -> list[tuple[Path, Path]]:
    """[(original, copia en input/texturas/)] de cada textura de entrada.

    El contrato de INGEST es copiar con hash y no volver a leer el original:
    si otra herramienta reescribe una textura durante la corrida, el reporte
    tiene que hablar de los bytes que se convirtieron. Lo llama INGEST; esta
    fase lo vuelve a llamar por si se la invoca sola, y entonces copia lo que
    falte (el workspace de un job es siempre nuevo: `JobWorkspace.crear`
    rechaza uno existente).

    Dos entradas con el mismo nombre en carpetas distintas se pisarían en la
    copia: es un error, no una elección.
    """
    base = ws.ruta_segura(Path("texturas"), subdir="input")
    base.mkdir(exist_ok=True)
    vistos: dict[str, Path] = {}
    pares = []
    for ruta in sorted(Path(p) for p in rutas):
        clave = ruta.name.lower()
        if clave in vistos:
            raise TexturaError(
                f"{ruta.name}: dos entradas con el mismo nombre ({vistos[clave]} "
                f"y {ruta}); en el staging se pisarian")
        vistos[clave] = ruta
        copia = ws.ruta_segura(Path("texturas") / ruta.name, subdir="input")
        if not copia.exists():
            shutil.copyfile(ruta, copia)
        pares.append((ruta, copia))
    return pares


def _agrupar(rutas) -> dict:
    """{base: {'slots', 'fuentes', 'ignoradas', 'convencion_normal'}}.

    Dos entradas que escriban en el mismo lugar son un error: si no, cuál gana
    lo decide el orden del directorio y el resultado no es reproducible. Lo
    mismo dos fuentes de la misma cosa (un ORM y un `_roughness` sueltos).
    """
    grupos: dict[str, dict] = {}
    for ruta in rutas:
        ruta = Path(ruta)
        r = clasificar(ruta.name)
        if not _PATRON_BASE.fullmatch(r.base):
            raise TexturaError(
                f"{ruta.name}: nombre base {r.base!r} no usable para construir "
                f"rutas (se admite [A-Za-z0-9 ._+-], 1-64 chars, sin "
                f"separadores de directorio)")
        grupo = grupos.setdefault(r.base, {"slots": {}, "fuentes": {},
                                           "ignoradas": [],
                                           "rutas_ignoradas": {},
                                           "sufijo_fuente": {},
                                           "convencion_normal": None})
        if r.clase == "ignorada":
            # Para el shader vanilla no tienen uso. El True PBR de Community
            # Shaders SI usa la oclusion (azul del `_rmaos`) y la altura
            # (`_p`): la ruta se guarda aparte, fuera de lo que va al reporte.
            grupo["ignoradas"].append({"archivo": ruta.name, "rol": r.rol})
            if r.rol in grupo["rutas_ignoradas"]:
                raise TexturaError(
                    f"{ruta.name}: dos entradas de {r.rol} para {r.base} "
                    f"({grupo['rutas_ignoradas'][r.rol].name} y {ruta.name})")
            grupo["rutas_ignoradas"][r.rol] = ruta
            continue
        clave = "slots" if r.clase == "slot" else "fuentes"
        if r.rol in grupo[clave]:
            raise TexturaError(
                f"{ruta.name}: dos entradas escriben en {r.base}/{r.rol} "
                f"({grupo[clave][r.rol].name} y {ruta.name}); no se elige "
                f"una en silencio")
        grupo[clave][r.rol] = ruta
        if r.clase == "fuente":
            grupo["sufijo_fuente"][r.rol] = r.sufijo
        if r.clase == "slot" and r.rol == "normal":
            grupo["convencion_normal"] = r.convencion
    for base, grupo in grupos.items():
        f = grupo["fuentes"]
        if "empaquetada" in f and ("rugosidad" in f or "metalico" in f):
            raise TexturaError(
                f"{base}: hay un mapa empaquetado ({f['empaquetada'].name}) y "
                f"ademas uno suelto "
                f"({', '.join(sorted(x.name for k, x in f.items() if k != 'empaquetada'))}); "
                f"cual manda seria una decision silenciosa. Dejar uno")
    return grupos


def _fuentes(grupo: dict) -> tuple[tuple | None, tuple | None, dict]:
    """(rugosidad, metalicidad, descripcion). Cada una es (Textura, canal,
    nombre de archivo) o None.

    El canal lo dice el nombre: el empaquetado de glTF lleva la rugosidad en
    G y la metalicidad en B. Un mapa suelto es gris y se lee su R, y se
    COMPRUEBA que sea gris: un ORM llamado `_roughness` daria el rojo --la
    oclusion-- como rugosidad.
    """
    f = grupo["fuentes"]
    rug = met = None
    desc = {}
    if "empaquetada" in f:
        t = leer_textura(f["empaquetada"])
        nombre = f["empaquetada"].name
        rug, met = (t, "g", nombre), (t, "b", nombre)
        desc["empaquetada"] = {
            "archivo": nombre, "dimensiones": [t.ancho, t.alto],
            "canales": "G rugosidad, B metalicidad (empaquetado de glTF)",
            "rugosidad": _estadisticas(_canal(t, "g")),
            "metalicidad": _estadisticas(_canal(t, "b"))}
    for rol, que in (("rugosidad", "rugosidad"), ("metalico", "metalicidad")):
        if rol not in f:
            continue
        t = leer_textura(f[rol])
        nombre = f[rol].name
        gris = es_gris(t)
        if not gris["gris"]:
            raise TexturaError(
                f"{nombre}: el nombre dice {que} suelta, que es un mapa gris, "
                f"y {gris['no_grises']} de {gris['muestra_texeles']} texeles "
                f"de la muestra no lo son. Si es un mapa empaquetado (ORM), "
                f"nombralo con _orm o _metallicRoughness")
        if rol == "rugosidad":
            rug = (t, "r", nombre)
        else:
            met = (t, "r", nombre)
        desc[rol] = {"archivo": nombre, "dimensiones": [t.ancho, t.alto],
                     "canales": "gris, se lee R", "gris": gris,
                     que: _estadisticas(_canal(t, "r"))}
    return rug, met, desc


def _motivos_mascara(m: dict) -> list[str]:
    """Por qué el `_n` escrito pide revisión, con el número al lado.

    No reprueba: la regla de saturación está medida solo sobre armas, y esta
    fase es de static/clutter. Pero una máscara fuera de lo que usa el
    vanilla no puede pasar callada: es el defecto del hacha (99,7 % en
    blanco) y es lo que produce el hueco negro del atlas, que es rugosidad 0
    y sale en 255.
    """
    motivos = []
    blanco = m.get("blanco_pct")
    media = m.get("media")
    if blanco is not None and blanco > mascara_especular.TOPE_ARMA:
        motivos.append(
            "%.1f %% de los bloques del alfa en 255: mas del %g %% que la "
            "regla de armas admite (las 140 _n de arma del corpus estan por "
            "debajo del 6,9 %%)" % (blanco, mascara_especular.TOPE_ARMA))
    p5, _p50, p95 = mascara_especular.MEDIA_PORTABLES
    if media is not None and not (p5 <= media <= p95):
        motivos.append(
            "media del alfa %.1f, fuera del p5-p95 de los objetos portables "
            "vanilla (%d a %d)" % (media, p5, p95))
    return motivos


def _al_tamano(tex: Textura, ancho: int, alto: int) -> Textura:
    """Un mapa de DATOS llevado a otro tamaño. Las texturas de un mismo
    texture set cubren el mismo espacio UV, así que remuestrear una para
    combinarla con otra asocia el mismo punto de la superficie."""
    return redimensionar(tex, ancho, alto, slot="datos")


def rmaos_desde(rug: tuple, met: tuple | None, ao: tuple | None,
                ancho: int, alto: int) -> Textura:
    """El `_rmaos` del True PBR de Community Shaders.

    R rugosidad, G metalicidad, B oclusion, A reflectancia de lo no metalico
    (src/TruePBR/BSLightingShaderMaterialPBR.h: "Roughness in r, metallic in
    g, AO in b, nonmetal reflectance in a"). El shader multiplica R por la
    escala de rugosidad y A por el nivel especular del NIF
    (Lighting.hlsl: `rawRMAOS *= float4(PBRParams1.x, 1, 1, PBRParams1.z)`),
    asi que A en 255 deja el nivel especular del NIF tal cual.

    Sin metalicidad, G = 0 (no metalico). Sin oclusion, B = 255 (nada
    ocluido). Cada fuente es (Textura, canal, nombre) y se lleva a
    `ancho` x `alto` como dato.
    """
    n = ancho * alto
    pix = bytearray(n * 4)
    pix[0::4] = _canal(_al_tamano(rug[0], ancho, alto), rug[1])
    pix[1::4] = (_canal(_al_tamano(met[0], ancho, alto), met[1])
                 if met is not None else bytes(n))
    pix[2::4] = (_canal(_al_tamano(ao[0], ancho, alto), ao[1])
                 if ao is not None else b"\xff" * n)
    pix[3::4] = b"\xff" * n
    return Textura(ancho, alto, bytes(pix))


def _oclusion(grupo: dict, rug: tuple) -> tuple | None:
    """(Textura, canal, nombre) de la oclusion, o None.

    Un `_ao` suelto (gris, se comprueba) manda; si no, el rojo de un `_orm` o
    `_arm`. El `_metallicRoughness` de glTF no lleva oclusion en R.
    """
    ruta = grupo["rutas_ignoradas"].get("oclusion")
    if ruta is not None:
        t = leer_textura(ruta)
        gris = es_gris(t)
        if not gris["gris"]:
            raise TexturaError(
                f"{ruta.name}: el nombre dice oclusion suelta, que es un mapa "
                f"gris, y {gris['no_grises']} de {gris['muestra_texeles']} "
                f"texeles de la muestra no lo son")
        return (t, "r", ruta.name)
    if grupo["sufijo_fuente"].get("empaquetada") in _EMPAQUETADAS_CON_OCLUSION:
        return (rug[0], "r", rug[2])
    return None


def _procesar_base(base: str, grupo: dict, mani: JobManifest,
                   ws: JobWorkspace) -> dict:
    """Convierte un grupo de mapas en los DDS de su texture set."""
    categoria = mani.asset_category

    # Sin color base no hay texture set: el shader de Skyrim siempre apunta a
    # una textura difusa. Si el grupo no la tiene, el nombre de archivo está
    # mal puesto --un ORM no es un albedo-- y decirlo acá es más barato que
    # descubrirlo en el juego con el asset invisible.
    if "color" not in grupo["slots"]:
        raise TexturaError(
            f"{base}: el grupo no tiene color base (un archivo sin sufijo, o "
            f"con uno de {ALIAS_DE_COLOR}). Sin difuso no hay "
            f"BSShaderTextureSet posible; si el archivo es el color, sacale "
            f"el sufijo")

    rug, met, desc_fuentes = _fuentes(grupo)
    cs = mani.sombreado == "cs_pbr"
    slots = dict(grupo["slots"])
    ignoradas = list(grupo["ignoradas"])
    observaciones = []
    oclusion = None
    if cs:
        # True PBR de Community Shaders: el especular sale del `_rmaos`, y sin
        # rugosidad no hay de donde armarlo. Una ranura 5 vacia no es neutra:
        # CS pone una textura BLANCA, o sea rugosidad 1 y metal 1 en toda la
        # pieza (BSLightingShaderMaterialPBR.cpp, defaultTextureWhite).
        if rug is None:
            raise TexturaError(
                f"{base}: sombreado cs_pbr sin fuente de rugosidad. El `_rmaos` "
                f"sale de ella, y sin `_rmaos` Community Shaders usa blanco: "
                f"rugosidad 1 y metal 1 en toda la pieza. Dale un `_orm`, "
                f"`_metallicRoughness` o `_roughness`")
        if "entorno" in slots:
            observaciones.append({
                "textura": slots.pop("entorno").name, "clase": "ignorada",
                "detalle": "en True PBR la ranura 5 es el `_rmaos`, no la `_m` "
                           "de reflejo: no se escribe"})
        # La altura, que el shader vanilla no usa, es el `_p` de CS.
        altura = grupo["rutas_ignoradas"].get("altura")
        if altura is not None and "parallax" not in slots:
            slots["parallax"] = altura
            ignoradas = [x for x in ignoradas if x["rol"] != "altura"]
        oclusion = _oclusion(grupo, rug)
        if grupo["rutas_ignoradas"].get("oclusion") is not None:
            ignoradas = [x for x in ignoradas if x["rol"] != "oclusion"]
    salidas = []
    observaciones = [{"textura": x["archivo"], "clase": "ignorada",
                      "detalle": "rol %s: sin equivalente en el shader %s; "
                                 "no se escribe"
                                 % (x["rol"], "de Community Shaders" if cs
                                    else "de Skyrim")}
                     for x in ignoradas] + observaciones
    motivos: list[str] = []

    def escribir(slot, nombre_salida, tex, origen, dims_origen, ajuste):
        declarada = ruta_declarada(categoria, mani.job_id, nombre_salida)
        destino = ws.ruta_segura(
            Path("textures") / categoria / mani.job_id
            / (nombre_salida + ".dds"), subdir="package")
        formato = formato_dds(slot, tex, mani.compresion)
        escribir_dds(tex, destino, slot, formato)
        malas = validar_salida(destino, declarada)
        if malas:
            raise ArtifactValidationError(
                f"{destino.name}: no pasa las reglas de DDS del contrato "
                f"({', '.join(malas)}). Un DDS escrito por esta fase que no "
                f"pasa el contrato es un error del pipeline, no del insumo")
        entrada = {
            "slot": slot,
            "declarada": declarada,
            "archivo": str(destino),
            "origen": origen,
            "dimensiones": [tex.ancho, tex.alto],
            "dimensiones_origen": dims_origen,
            "ajuste": ajuste,
            "formato": ("sin_comprimir_32bpp" if formato == "RGBA"
                        else formato),
            "sha256": _sha256(destino),
        }
        if formato != "RGBA":
            entrada["error_compresion"] = error_compresion(tex, destino)
        return destino, entrada

    for slot in ORDEN_SLOTS:
        nombre_salida = base + SUFIJO_ESCRITURA[slot]
        ruta_entrada = slots.get(slot)

        if slot == "entorno" and ruta_entrada is None:
            if cs or met is None:
                continue
            tex, info = entorno_desde_metalico(met[0], met[1])
            observaciones.append({"textura": nombre_salida,
                                  "clase": "conversion", "detalle": info})
            if tex is None:
                continue
            origen = "generada desde la metalicidad de %s" % met[2]
        elif ruta_entrada is None:
            continue
        else:
            tex = leer_textura(ruta_entrada)
            origen = ruta_entrada.name
            if slot == "normal" and grupo["convencion_normal"] == "dx":
                tex = invertir_verde(tex)
                origen += " (verde invertido: DirectX -> OpenGL)"
                observaciones.append({
                    "textura": nombre_salida, "clase": "conversion",
                    "detalle": "normal DirectX: Skyrim usa OpenGL (verde "
                               "hacia +Y), se invirtio el verde"})

        dims_origen = [tex.ancho, tex.alto]
        ancho2, alto2, que = ajustar_tamano(tex.ancho, tex.alto,
                                            mani.max_lado_textura)
        tex = redimensionar(tex, ancho2, alto2, slot=slot)

        if slot == "normal":
            if rug is not None:
                t_rug = _al_tamano(rug[0], ancho2, alto2)
                tex, saturacion = alfa_desde_rugosidad(tex, t_rug, rug[1])
                origen += " + alfa desde %s" % rug[2]
                obs = {"textura": nombre_salida,
                       "clase": "mascara_especular",
                       "saturacion_pct": round(saturacion, 2),
                       "fuente": rug[2], "canal_rugosidad": rug[1]}
                if (rug[0].ancho, rug[0].alto) != (ancho2, alto2):
                    obs["remuestreo"] = "rugosidad de %dx%d llevada a %dx%d" % (
                        rug[0].ancho, rug[0].alto, ancho2, alto2)
                observaciones.append(obs)
            else:
                observaciones.append({
                    "textura": nombre_salida, "clase": "mascara_especular",
                    "nota": "sin fuente de rugosidad: el alfa se conserva "
                            "tal cual vino"})

        destino, entrada = escribir(slot, nombre_salida, tex, origen,
                                    dims_origen, que)
        if slot == "normal":
            medicion = medir_mascara(destino)
            entrada["mascara"] = {
                "blanco_pct": medicion["medicion"].get("blanco_pct"),
                "media": medicion["medicion"].get("media"),
                "notas": medicion["notas"],
            }
            if medicion["fallas"]:
                raise ArtifactValidationError(
                    f"{destino.name}: no se pudo verificar la máscara "
                    f"especular ({medicion['fallas'][0]})")
            # Los topes de revision son de la mascara especular VANILLA. En
            # True PBR el especular sale del `_rmaos`; el alfa del `_n` solo lo
            # lee la ruta no diferida para el SSR, como glossiness
            # (Lighting.hlsl), y 255 - rugosidad es justo eso.
            if not cs:
                motivos.extend("%s: %s" % (nombre_salida, x)
                               for x in _motivos_mascara(medicion["medicion"]))
        salidas.append(entrada)

    if cs:
        if rug is None:
            # No pasa: cs_pbr sin rugosidad reprueba al principio. Esta aca
            # para que no dependa de que ese chequeo siga en su lugar.
            raise TexturaError(f"{base}: sombreado cs_pbr sin fuente de rugosidad")
        ancho2, alto2, que = ajustar_tamano(rug[0].ancho, rug[0].alto,
                                            mani.max_lado_textura)
        tex = rmaos_desde(rug, met, oclusion, ancho2, alto2)
        origen = "R rugosidad (%s), G metal (%s), B oclusion (%s), A 255" % (
            rug[2], met[2] if met is not None else "sin fuente: 0",
            oclusion[2] if oclusion is not None else "sin fuente: 255")
        _destino, entrada = escribir("rmaos", base + SUFIJO_ESCRITURA["rmaos"],
                                     tex, origen,
                                     [rug[0].ancho, rug[0].alto], que)
        salidas.append(entrada)

    return {
        "base": base,
        "sombreado": mani.sombreado,
        "fuente_pbr": desc_fuentes or None,
        "texturas": salidas,
        "observaciones": observaciones,
        "requiere_revision": bool(motivos),
        "motivos_revision": motivos,
    }


# Lo que esta fase no puede comprobar y la siguiente no puede olvidar.
PRECONDICION_UV = (
    "los mapas se convirtieron tal como los entrego el generador: sirven solo "
    "si la malla final conserva SUS UV. Si PREPARE decima o re-despliega sin "
    "conservarlas, hay que hornear desde el modelo original (trampas 31, 32 y "
    "35 de la skill modelo-ia-a-skyrim)")


def fase_process_texturas(mani: JobManifest, ws: JobWorkspace) -> dict:
    """Adaptador de la fase PROCESS_TEXTURES.

    Declara `ejecutada: True` y NUNCA `stub`. Si el manifest no declara
    `texture_inputs`, la fase corrió y no tuvo nada que hacer --que es distinto
    de no estar conectada, y el reporte tiene que distinguirlo (ver
    `_fase_noop` en runner.py).

    Lee las COPIAS de input/texturas/, no los originales: el hash del reporte
    y los bytes convertidos son los mismos.
    """
    reporte: dict[str, Any] = {
        "ejecutada": True,
        "herramienta": "pipeline.texturas + census/escritor_dds.py + "
                       "census/compresor_dxt.py + fixtures/comparar.py + "
                       "scripts/mascara_especular.py",
        "formato_salida": ("DDS sin comprimir 32bpp con cadena de mipmaps"
                           if mani.compresion == "ninguna" else
                           "DDS DXT5 (_n y mapas con alfa) y DXT1 (el resto) "
                           "con cadena de mipmaps"),
        "compresion": mani.compresion,
        "max_lado_textura": mani.max_lado_textura,
        "entradas": [],
        "texture_sets": [],
    }
    if not mani.texture_inputs:
        reporte["nota"] = ("el manifest no declara texture_inputs: la fase "
                           "corrió y no tuvo nada que hacer. Un asset sin "
                           "texturas lo tiene que rechazar VALIDATE leyendo "
                           "las rutas del NIF, no esta fase adivinando")
        return reporte

    pares = copiar_entradas(mani.texture_inputs, ws)
    reporte["entradas"] = [
        {"archivo": str(original), "copia": "input/texturas/" + copia.name,
         "sha256": _sha256(copia)} for original, copia in pares]
    grupos = _agrupar(copia for _original, copia in pares)
    for base in sorted(grupos):
        g = grupos[base]
        if not g["slots"] and not g["fuentes"]:
            # Solo mapas sin equivalente (una oclusión suelta): no son un
            # texture set, y tampoco se pierden en silencio.
            reporte.setdefault("ignoradas", []).extend(g["ignoradas"])
            continue
        reporte["texture_sets"].append(_procesar_base(base, g, mani, ws))
    reporte["precondicion_uv"] = PRECONDICION_UV

    # El texture set que una futura EXPORT_NIF necesita para llenar el
    # BSShaderTextureSet. Se deja en reports/ --no en package/-- porque es
    # metadata de la corrida, no un archivo que el juego cargue.
    ruta_sets = ws.subdir("reports") / "texture_set.json"
    contenido = {
        "job_id": mani.job_id,
        "categoria": mani.asset_category,
        "formato": reporte["formato_salida"],
        "sombreado": mani.sombreado,
        "precondicion_uv": PRECONDICION_UV,
        "texture_sets": [
            {"base": t["base"],
             "texturas": {x["slot"]: x["declarada"] for x in t["texturas"]}}
            for t in reporte["texture_sets"]
        ],
    }
    if mani.sombreado == "cs_pbr":
        # Lo que EXPORT_NIF tiene que poner en el NIF: sin esto, el `_rmaos`
        # termina en la ranura de la `_m` vanilla y el flag PBR queda apagado.
        contenido["ranuras"] = RANURAS_CS_PBR
        contenido["nif"] = NIF_CS_PBR
    ruta_sets.write_text(json.dumps(contenido, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    reporte["texture_set_json"] = ruta_sets.name

    sets_con_revision = [t["base"] for t in reporte["texture_sets"]
                         if t["requiere_revision"]]
    if sets_con_revision:
        reporte["requiere_revision"] = sets_con_revision
        reporte["nota"] = (
            "estos texture sets tienen la mascara especular (alfa del _n) "
            "fuera de lo que usa el vanilla; los motivos, con su numero, van "
            "en `motivos_revision` de cada uno. Alfa en 255 es 'todo brilla "
            "al maximo', el defecto del hacha (99,7 % en blanco). No reprueba "
            "porque la regla de saturacion esta medida solo para armas.")
    return reporte
