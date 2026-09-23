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

Las conversiones de canal son las que la documentación del repo recomienda, y
cada una está acotada a lo que se puede defender con un número:

  * el ALFA del `_n` sale de la rugosidad como `255 - roughness`. El hacha del
    proyecto de origen llegó al juego con el 99,7 % de su máscara en blanco y
    se veía de plástico; en el corpus, las 140 texturas `_n` de malla de arma
    están todas por debajo del 6,9 % de bloques en blanco;
  * la máscara `_m` sale del canal de metalicidad del ORM, con el rango
    expandido. Los generadores entregan metalicidad muy comprimida --en el
    proyecto de origen, 0 a 0,46 con media 0,06-- y sin expandir la máscara
    sale sin contraste. La expansión es una HEURÍSTICA: se informan el mínimo,
    el máximo y la media observados para que se pueda auditar;
  * el color base se copia TAL CUAL. La luz horneada (sombras de contacto,
    oclusión, brillo pegado al color) no se saca automáticamente: la
    documentación dice que se atenúa con curvas y que no se recupera del todo,
    así que hacerlo en silencio sería inventar. Se informa como observación.

QUE NO HACE, Y POR QUE NO ES UN DESCUIDO
----------------------------------------
  * NO comprime a DXT1/DXT5/BC7. Escribe DDS sin comprimir de 32 bpp con la
    cadena completa de mipmaps, que es lo que ya hace y ya verifica
    `census/escritor_dds.py`. Del censo: 10.048 de 32.241 texturas vanilla
    (31,2 %) son sin comprimir y el juego las carga igual. Un compresor de
    bloques es otra pieza con su propia falsificación --el docstring de
    escritor_dds.py lo dice-- y va aparte. Lo que sí se informa es que los
    12.075 `_n` del corpus son DXT5, o sea que el `_n` es el primer mapa que
    va a pedir el compresor.
  * NO escribe el NIF ni toca las rutas de la malla. Deja `texture_set.json`
    en `reports/` con la ruta declarada de cada mapa, que es lo que una fase
    EXPORT_NIF necesita para llenar el `BSShaderTextureSet`.
  * NO valida la correspondencia UV <-> textura. El censo de UV la declara no
    medida, y era el defecto real del proyecto de origen: cada pieza apuntaba
    a la región equivocada del atlas.

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
import re
import struct
import sys
import zlib
from pathlib import Path
from typing import NamedTuple

from .errors import ArtifactValidationError, TexturaError
from .manifest import JobManifest
from .staging import JobWorkspace

# --- las herramientas existentes, invocadas --no reimplementadas------------
# Mismo mecanismo que fixtures/comparar.py: los scripts del repo viven sueltos
# en carpetas que no son paquetes, así que se agregan a sys.path con rutas
# ABSOLUTAS. (comparar.py inserta una relativa; si el CWD no es la raíz del
# repo, su import de parser_dds se cae. Acá va absoluta a propósito.)
_RAIZ = Path(__file__).resolve().parent.parent
for _dir in (_RAIZ / "census", _RAIZ / "fixtures",
             _RAIZ / "skills" / "modelo-ia-a-skyrim" / "scripts"):
    if str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

import comparar        # noqa: E402  (needs census/ en sys.path)
import escritor_dds    # noqa: E402
import mascara_especular  # noqa: E402
import parser_dds      # noqa: E402

# --- la convención de sufijos, tal cual está documentada --------------------
# Sufijos de SKYRIM (lo que se ESCRIBE) y sus equivalentes que entregan los
# generadores / el estándar glTF. Se aceptan varios alias en la entrada pero
# se escribe SIEMPRE con el sufijo canónico de Skyrim (cartel, cartel_n,
# cartel_m...). El orden de la lista importa: los sufijos más LARGOS se buscan
# primero, así `hacha_metallicRoughness` se clasifica como fuente ORM y no
# como rugosidad por el sufijo `_roughness` que lleva adentro.
SUFIJO_A_SLOT = {
    # Skyrim canónico
    "_n": "normal",
    "_m": "entorno",
    "_g": "glow",
    "_s": "subsurface",
    "_p": "parallax",
    "_b": "backlight",
    # Alias de color/base que usan los generadores y glTF. Un nombre con uno
    # de estos sufijos es el color base: no queremos que `hacha_basecolor`
    # quede como base `hacha_basecolor` sin que produzca un cartel.dds.
    "_basecolor": "color",
    "_base_color": "color",
    "_albedo": "color",
    "_diffuse": "color",
    "_d": "color",
    "_color": "color",
    # Alias de normal
    "_normal": "normal",
    "_normalgl": "normal",
    "_nor": "normal",
    "_nrm": "normal",
}
SLOT_A_SUFIJO = {v: k for k, v in SUFIJO_A_SLOT.items()}
# Solo los sufijos de SKYRIM se usan al escribir; los alias no aparecen en el
# paquete.
SUFIJO_ESCRITURA = {"color": "", "normal": "_n", "entorno": "_m",
                    "glow": "_g", "subsurface": "_s",
                    "parallax": "_p", "backlight": "_b"}

# Orden de escritura: el color primero, para que un reporte truncado deje ver
# lo más importante arriba.
ORDEN_SLOTS = ("color", "normal", "entorno", "glow", "subsurface",
               "parallax", "backlight")

# Sufijos que un generador agrega DESPUÉS del rol (_fixed, _baked, _processed,
# _1k, _2k, _4k) y que hay que quitar para que el nombre base coincida entre
# el color, el normal y el ORM. Por ejemplo:
#   hacha_normal_fixed.png     -> base hacha,  slot normal
#   hacha_basecolor.png        -> base hacha,  slot color
# Si no se quita `_fixed`, los dos archivos quedan en grupos distintos y el
# normal nunca se combina con el color: falla silenciosa (ver hallazgo del
# PR #51).
_SUFIJOS_EXTRA = (
    "_fixed", "_baked", "_processed", "_final", "_v2", "_v3",
    "_1k", "_2k", "_4k", "_8k",
    "_dx", "_gl", "_opengl",
)

# Fuentes PBR que no se emiten como textura propia: se doblan dentro del `_n`
# (rugosidad -> alfa) y del `_m` (metalicidad -> máscara). Ordenados por
# longitud decreciente para que `_metallicRoughness` matchee antes que
# `_roughness`.
FUENTES_RUGOSIDAD = (
    "_metallicroughness", "_metalroughness", "_metallic_roughness",
    "_metal_roughness", "_occlusionroughnessmetallic", "_orm",
    "_roughness", "_rough",
)

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
    if ancho is None:
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
    if profundidad not in (24, 32):
        raise TexturaError(f"{ruta}: {profundidad} bits por pixel; se esperan "
                           f"24 o 32")
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
            if canales == 3:
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

    Un DDS comprimido se rechaza con el número del censo al lado: no es un
    detalle de implementación, es que esta fase todavía no comprime y por lo
    tanto no debería pretender que sí. Un DDS sin comprimir con otro orden
    de canales (RGBA, ARGB) también se rechaza, con las máscaras que trae
    el header en el mensaje: asumir BGRA a ciegas devolvía colores
    invertidos sin ningún error.
    """
    d = parser_dds.leer(ruta)          # lanza DdsInvalido si no parsea
    if d["comprimido"]:
        raise TexturaError(
            f"{ruta}: formato {d['formato']} comprimido; esta fase lee DDS "
            f"sin comprimir (32 bpp). Del censo, 10.048 de 32.241 texturas "
            f"vanilla son sin comprimir, así que no es un caso exótico")
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
    for p in range(0, len(crudo), 4):
        salida[p]     = crudo[p + r_o]
        salida[p + 1] = crudo[p + g_o]
        salida[p + 2] = crudo[p + b_o]
        salida[p + 3] = crudo[p + a_o]
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

def clasificar(nombre: str) -> tuple[str, str, str]:
    """(slot, sufijo, base) a partir del nombre de archivo.

    El sufijo se busca al FINAL del tallo, en minúsculas: `Cartel_N.PNG` es un
    normal map, `hacha_BaseColor.png` es color base, `hacha_Normal.png` es
    normal. Un nombre sin sufijo reconocido es el color base --es la forma
    más común del corpus: 19.108 de 32.241 texturas no tienen sufijo--.

    Los sufijos "extra" del generador (_fixed, _baked, _1k, _2k...) se quitan
    antes de decidir la base, así `hacha_normal_fixed` y `hacha_basecolor`
    comparten la base `hacha` y van al mismo texture set.
    """
    tallo = Path(nombre).stem
    tallo_b = tallo.lower()
    # Quitar sufijos extra del final (uno solo; más de uno es raro y se deja).
    for x in _SUFIJOS_EXTRA:
        if tallo_b.endswith(x):
            tallo = tallo[:-len(x)]
            tallo_b = tallo.lower()
            break
    # Buscar sufijo de slot, más largo primero para que `_basecolor` gane
    # sobre `_color` y no matcheen prefijos parciales.
    for sufijo in sorted(SUFIJO_A_SLOT, key=len, reverse=True):
        if tallo_b.endswith(sufijo):
            return SUFIJO_A_SLOT[sufijo], sufijo, tallo[:-len(sufijo)]
    return "color", "", tallo


def _es_fuente(tallo: str) -> str | None:
    """'_orm'/'_roughness'/... -> esa fuente, o None si no es una fuente.

    Quita los sufijos extra igual que `clasificar` y busca el sufijo de
    fuente más largo que matchee, así `_metallicRoughness` gana sobre
    `_roughness`.
    """
    bajo = tallo.lower()
    for x in _SUFIJOS_EXTRA:
        if bajo.endswith(x):
            tallo = tallo[:-len(x)]
            bajo = tallo.lower()
            break
    for fuente in sorted(FUENTES_RUGOSIDAD, key=len, reverse=True):
        if bajo.endswith(fuente):
            return fuente
    return None


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


def redimensionar(tex: Textura, ancho2: int, alto2: int,
                  slot: str = "color") -> Textura:
    """Remuestreo por cajas (box filter), promediando 2x2 o el bloque que toque.

    Es el mismo criterio que `census/escritor_dds.reducir`, que es el que
    genera los mipmaps. Los mapas de DATOS (máscaras, metalicidad, rugosidad,
    glow) se promedian lineal y queda bien. El color en sRGB es discutible por
    la gamma, igual que en escritor_dds. Los NORMALES son el caso especial:
    después de promediar hay que RENORMALIZAR cada vector, porque el promedio
    de cuatro normales unitarias apuntando en direcciones distintas es más
    corto que 1 y queda el relieve más suave de lo debido.
    """
    if (tex.ancho, tex.alto) == (ancho2, alto2):
        return tex
    if ancho2 <= 0 or alto2 <= 0:
        raise TexturaError(f"destino inválido: {ancho2}x{alto2}")
    salida = bytearray(ancho2 * alto2 * 4)
    es_normal = slot == "normal"
    for y2 in range(alto2):
        y0 = y2 * tex.alto // alto2
        y1 = max(y0 + 1, (y2 + 1) * tex.alto // alto2)
        for x2 in range(ancho2):
            x0 = x2 * tex.ancho // ancho2
            x1 = max(x0 + 1, (x2 + 1) * tex.ancho // ancho2)
            acc = [0, 0, 0, 0]
            n = 0
            for y in range(y0, min(y1, tex.alto)):
                for x in range(x0, min(x1, tex.ancho)):
                    o = (y * tex.ancho + x) * 4
                    for c in range(4):
                        acc[c] += tex.pixeles[o + c]
                    n += 1
            d = (y2 * ancho2 + x2) * 4
            if es_normal:
                # Normal guardada como (R,G,B) = (nx*0.5+0.5, ny*0.5+0.5,
                # nz*0.5+0.5), A especular. Se promedia en espacio de
                # vector unitario y se renormaliza para no aplanar el
                # relieve. El alfa es lineal y se promedia aparte.
                import math
                nx = (acc[0] / n) / 255.0 * 2.0 - 1.0
                ny = (acc[1] / n) / 255.0 * 2.0 - 1.0
                nz = (acc[2] / n) / 255.0 * 2.0 - 1.0
                ln = math.sqrt(nx*nx + ny*ny + nz*nz)
                if ln > 1e-6:
                    nx, ny, nz = nx/ln, ny/ln, nz/ln
                else:
                    nx, ny, nz = 0.0, 0.0, 1.0
                salida[d]     = max(0, min(255, int((nx * 0.5 + 0.5) * 255 + 0.5)))
                salida[d + 1] = max(0, min(255, int((ny * 0.5 + 0.5) * 255 + 0.5)))
                salida[d + 2] = max(0, min(255, int((nz * 0.5 + 0.5) * 255 + 0.5)))
                salida[d + 3] = (acc[3] + n // 2) // n
            else:
                for c in range(4):
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


def describir_fuente(tex: Textura) -> dict:
    """Qué canal es la rugosidad y cuál la metalicidad en una fuente PBR.

    Regla documentada y reportada, no una heurística oculta:
      - si el mapa es escala de grises (R == G == B en la muestra), es un mapa
        de rugosidad dedicado y se usa R;
      - si no, se asume ORM (R = oclusión, G = rugosidad, B = metalicidad),
        que es lo que entregan la mayoría de los generadores.
    """
    muestra = tex.pixeles[: 4096 * 4]
    grises = all(muestra[i] == muestra[i + 1] == muestra[i + 2]
                 for i in range(0, len(muestra), 4))
    canal_r, canal_m = ("r", "r") if grises else ("g", "b")
    return {
        "grises": grises,
        "canal_rugosidad": canal_r,
        "canal_metalico": canal_m,
        # La muestra se declara: decidir "es escala de grises" mirando 4096
        # téxeles de un mapa de 4 millones es un muestreo, y un muestreo que no
        # se dice es una conclusión que no se puede auditar.
        "muestra_texeles": len(muestra) // 4,
        "rugosidad": _estadisticas(_canal(tex, canal_r)),
        "metalicidad": _estadisticas(_canal(tex, canal_m)),
    }


def _canal(tex: Textura, cual: str) -> bytes:
    """Un canal de la textura, un byte por téxel.

    Con corte y paso, no con un generador: sobre un mapa de 4 millones de
    téxeles, la diferencia es entre un corte de C y varios segundos de Python.
    """
    idx = {"r": 0, "g": 1, "b": 2, "a": 3}[cual]
    return tex.pixeles[idx::4]


def alfa_desde_rugosidad(tex_n: Textura, tex_rug: Textura
                         ) -> tuple[Textura, float, dict]:
    """El alfa del `_n` es la máscara especular: `255 - roughness`.

    Requiere que ambas texturas tengan las mismas dimensiones --si no, el
    remuestreo silencioso asociaría píxeles de mapas distintos-- y avisa si el
    resultado queda saturado, que es el defecto que esta conversión existe para
    no producir.

    Devuelve (textura, % de téxeles en 255, descripción de la fuente).
    """
    if (tex_n.ancho, tex_n.alto) != (tex_rug.ancho, tex_rug.alto):
        raise TexturaError(
            f"el normal mide {tex_n.ancho}x{tex_n.alto} y la rugosidad "
            f"{tex_rug.ancho}x{tex_rug.alto}: no se remuestrea para asociar "
            f"píxeles de mapas distintos")
    desc = describir_fuente(tex_rug)
    rug = _canal(tex_rug, desc["canal_rugosidad"])
    pix = bytearray(tex_n.pixeles)
    for i in range(0, len(pix), 4):
        pix[i + 3] = 255 - rug[i // 4]
    salida = Textura(tex_n.ancho, tex_n.alto, bytes(pix))
    alfa = _canal(salida, "a")
    saturacion = 100.0 * alfa.count(255) / max(1, len(alfa))
    return salida, saturacion, desc


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


def entorno_desde_metalico(tex_fuente: Textura) -> tuple[Textura, dict]:
    """La máscara `_m` desde la metalicidad del ORM, con rango expandido.

    `_m` NO es la metalicidad de PBR: controla cuánto refleja el cubemap del
    shader Environment_Map. El canal de metalicidad es la mejor fuente
    disponible, y por eso se usa, pero la máscara sale en escala de grises.
    """
    desc = describir_fuente(tex_fuente)
    tex, obs = expandir_rango(tex_fuente, desc["canal_metalico"])
    canal = _canal(tex, desc["canal_metalico"])
    pix = bytearray(len(canal) * 4)
    for i, v in enumerate(canal):
        d = i * 4
        pix[d:d + 4] = bytes((v, v, v, 255))
    return Textura(tex.ancho, tex.alto, bytes(pix)), {
        "fuente": desc, "expansion": obs,
        "nota": "mascara en escala de grises: _m es reflejo de cubemap, no "
                "metalicidad de PBR",
    }


# ---------------------------------------------------------------------------
# Escritura y verificación
# ---------------------------------------------------------------------------

def escribir_dds(tex: Textura, ruta: Path) -> Path:
    """DDS sin comprimir de 32 bpp con la cadena completa de mipmaps.

    Delega en `census/escritor_dds.py`, que ya está verificado: su autotest
    compara el tamaño que predice `parser_dds` contra el real y RELEE los
    píxeles escritos. La cadena baja hasta 1x1; el corpus corta en 2x2 en el
    96,4 % de los casos, así que tener el nivel de más no es un defecto --y
    medir "cadena completa" contra 1x1 marcaba 31.940 texturas correctas como
    rotas.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    return escritor_dds.escribir(str(ruta), tex.ancho, tex.alto,
                                 tex.pixeles, con_mipmaps=True)


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


def _agrupar(rutas) -> dict:
    """{base: {'slots': {slot: Path}, 'fuentes': {fuente: Path}}}.

    Dos entradas que escriban en el mismo lugar son un error: si no, cuál gana
    lo decide el orden del directorio y el resultado no es reproducible.
    """
    grupos: dict[str, dict] = {}
    for ruta in rutas:
        ruta = Path(ruta)
        tallo = ruta.stem
        fuente = _es_fuente(tallo)
        if fuente is not None:
            base = tallo[: -len(fuente)]
            clave, bolsillo = "fuentes", fuente
        else:
            slot, _sufijo, base = clasificar(ruta.name)
            clave, bolsillo = "slots", slot
        if not _PATRON_BASE.fullmatch(base):
            raise TexturaError(
                f"{ruta.name}: nombre base {base!r} no usable para construir "
                f"rutas (se admite [A-Za-z0-9 ._+-], 1-64 chars, sin "
                f"separadores de directorio)")
        grupo = grupos.setdefault(base, {"slots": {}, "fuentes": {}})
        if bolsillo in grupo[clave]:
            raise TexturaError(
                f"{ruta.name}: dos entradas escriben en {base}/{bolsillo} "
                f"({grupo[clave][bolsillo].name} y {ruta.name}); no se elige "
                f"una en silencio")
        grupo[clave][bolsillo] = ruta
    return grupos


def _procesar_base(base: str, grupo: dict, mani: JobManifest,
                   ws: JobWorkspace) -> dict:
    """Convierte un grupo de mapas en los DDS de su texture set."""
    categoria = mani.asset_category
    fuentes = grupo["fuentes"]
    tex_fuente = None
    if fuentes:
        # Una sola fuente de rugosidad por grupo: con dos, cuál manda sería
        # otra vez una decisión silenciosa.
        if len(fuentes) > 1:
            raise TexturaError(
                f"{base}: varias fuentes de rugosidad "
                f"({sorted(f.name for f in fuentes.values())}); dejar una")
        ruta_fuente = next(iter(fuentes.values()))
        nombre_fuente = ruta_fuente.name
        tex_fuente = leer_textura(ruta_fuente)
        desc_fuente = describir_fuente(tex_fuente)
    else:
        desc_fuente = None

    salidas = []
    observaciones = []
    requiere_revision = False

    # Sin color base no hay texture set: el shader de Skyrim siempre apunta a
    # una textura difusa. Si el grupo no la tiene, el nombre de archivo está
    # mal puesto --un ORM no es un albedo-- y decirlo acá es más barato que
    # descubrirlo en el juego con el asset invisible.
    if "color" not in grupo["slots"]:
        raise TexturaError(
            f"{base}: el grupo no tiene color base (un archivo sin sufijo, o "
            f"con uno de {sorted(SUFIJO_A_SLOT)}). Sin difuso no hay "
            f"BSShaderTextureSet posible; si el archivo es el color, sacale "
            f"el sufijo")

    for slot in ORDEN_SLOTS:
        sufijo = SUFIJO_ESCRITURA.get(slot, "")
        nombre_salida = base + sufijo
        ruta_entrada = grupo["slots"].get(slot)
        origen = None

        if slot == "entorno" and ruta_entrada is None and tex_fuente is not None:
            tex, info = entorno_desde_metalico(tex_fuente)
            origen = "generada desde la metalicidad de %s" % nombre_fuente
            observaciones.append({
                "textura": nombre_salida,
                "clase": "conversion",
                "detalle": info,
            })
        elif ruta_entrada is None:
            continue
        else:
            tex = leer_textura(ruta_entrada)
            origen = ruta_entrada.name
            if slot == "normal" and tex_fuente is not None:
                tex_n, saturacion, desc = alfa_desde_rugosidad(tex, tex_fuente)
                tex = tex_n
                origen = "%s + alfa desde %s" % (ruta_entrada.name,
                                                 nombre_fuente)
                observaciones.append({
                    "textura": nombre_salida,
                    "clase": "mascara_especular",
                    "saturacion_pct": round(saturacion, 2),
                    "canal_rugosidad": desc["canal_rugosidad"],
                    "fuente_grises": desc["grises"],
                })
            elif slot == "normal":
                saturada = set(tex.pixeles[3::4]) == {255}
                observaciones.append({
                    "textura": nombre_salida,
                    "clase": "mascara_especular",
                    "saturacion_pct": 100.0 if saturada else None,
                    "nota": "sin fuente de rugosidad: el alfa se conserva "
                            "tal cual vino",
                })
                if saturada:
                    requiere_revision = True

        dims_origen = [tex.ancho, tex.alto]
        ancho2, alto2, que = ajustar_tamano(tex.ancho, tex.alto,
                                            mani.max_lado_textura)
        tex = redimensionar(tex, ancho2, alto2, slot=slot)

        declarada = ruta_declarada(categoria, mani.job_id, nombre_salida)
        destino = ws.ruta_segura(
            Path("textures") / categoria / mani.job_id / (nombre_salida + ".dds"),
            subdir="package")
        escribir_dds(tex, destino)

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
            "dimensiones": [ancho2, alto2],
            "dimensiones_origen": dims_origen,
            "ajuste": que,
            "formato": "sin_comprimir_32bpp",
            "sha256": _sha256(destino),
        }
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
        salidas.append(entrada)

    if not salidas:
        raise TexturaError(
            f"{base}: ninguna de las entradas produce una textura de salida. "
            f"Una entrada que se ignora en silencio es el modo de fallo que "
            f"esta fase existe para no tener")
    return {
        "base": base,
        "fuente_pbr": desc_fuente,
        "texturas": salidas,
        "observaciones": observaciones,
        "requiere_revision": requiere_revision,
    }


def fase_process_texturas(mani: JobManifest, ws: JobWorkspace) -> dict:
    """Adaptador de la fase PROCESS_TEXTURES.

    Declara `ejecutada: True` y NUNCA `stub`. Si el manifest no declara
    `texture_inputs`, la fase corrió y no tuvo nada que hacer --que es distinto
    de no estar conectada, y el reporte tiene que distinguirlo (ver
    `_fase_noop` en runner.py).
    """
    entradas = sorted(Path(p) for p in mani.texture_inputs)
    reporte = {
        "ejecutada": True,
        "herramienta": "pipeline.texturas + census/escritor_dds.py + "
                       "fixtures/comparar.py + scripts/mascara_especular.py",
        "formato_salida": "DDS sin comprimir 32bpp con cadena de mipmaps",
        "max_lado_textura": mani.max_lado_textura,
        "entradas": [{"archivo": str(p), "sha256": _sha256(p)}
                     for p in entradas],
        "texture_sets": [],
    }
    if not entradas:
        reporte["nota"] = ("el manifest no declara texture_inputs: la fase "
                           "corrió y no tuvo nada que hacer. Un asset sin "
                           "texturas lo tiene que rechazar VALIDATE leyendo "
                           "las rutas del NIF, no esta fase adivinando")
        return reporte

    grupos = _agrupar(entradas)
    for base in sorted(grupos):
        reporte["texture_sets"].append(
            _procesar_base(base, grupos[base], mani, ws))

    # El texture set que una futura EXPORT_NIF necesita para llenar el
    # BSShaderTextureSet. Se deja en reports/ --no en package/-- porque es
    # metadata de la corrida, no un archivo que el juego cargue.
    ruta_sets = ws.subdir("reports") / "texture_set.json"
    ruta_sets.write_text(json.dumps({
        "job_id": mani.job_id,
        "categoria": mani.asset_category,
        "formato": reporte["formato_salida"],
        "texture_sets": [
            {"base": t["base"],
             "texturas": {x["slot"]: x["declarada"] for x in t["texturas"]}}
            for t in reporte["texture_sets"]
        ],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    reporte["texture_set_json"] = ruta_sets.name

    sets_con_revision = [t["base"] for t in reporte["texture_sets"]
                         if t["requiere_revision"]]
    if sets_con_revision:
        reporte["requiere_revision"] = sets_con_revision
        reporte["nota"] = (
            "estos texture sets quedaron con el alfa del _n saturado en 255 "
            "porque no hubo fuente de rugosidad: 'todo brilla al máximo', que "
            "es el defecto del hacha (99,7 % en blanco). No reprueba porque "
            "la regla de saturación está medida solo para armas; se informa. "
            "Arreglo: dar una fuente de rugosidad o escribir el alfa a mano.")
    return reporte
