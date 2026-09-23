# -*- coding: utf-8 -*-
"""El alfa del normal map es la MASCARA ESPECULAR. Python puro, sin PIL.

    python scripts/mascara_especular.py <textura_n.dds> [...]
    python scripts/mascara_especular.py --arma <textura_n.dds> [...]
    python scripts/mascara_especular.py --autotest
    python scripts/mascara_especular.py --censo <carpeta textures>

Exit 0 si pasa, 1 si no pasa o si no hubo NADA que medir, 2 si los argumentos
no sirven.

POR QUE EXISTE

El shader de Skyrim usa el alfa del `_n` como mascara especular. Una mascara en
255 entera es "todo brilla igual", y el asset se ve de plastico por bien que
esten la malla y el color -- que es como se veia el hacha de Tencent: 99,7 % de
sus bloques en blanco. El sintoma se confunde con "me falta un ENB".

Y es facil de producir sin querer: `texconv -f BC7_UNORM` sobre un PNG opaco da
un DDS con alfa 255 en todos lados y no avisa de nada.

LO QUE SE PUEDE EXIGIR, Y A QUIEN

  REGLA  arma   en un `_n` de ARMA, como mucho el 10 % de los bloques con alfa
                constante 255. Medido: las 140 texturas `_n` de meshes de arma
                del corpus estan por debajo del 6,9 %, sin excepciones.

  OBS    resto  la mediana de un `_n` de objeto portable es 0,00 % de bloques
                en blanco y el p90 es 0,34 %, pero el 4,91 % (59 de 1.201) esta
                saturado del todo.

LAS EXCEPCIONES NO SON RUIDO: SON MATERIALES MATE

Los 59 saturados son ropa de granjero, ropa de chicos, quesos, manzanas,
carbon, libros, ceniza y cejas. En un material mate el brillo lo apaga la
propiedad del shader --`Specular Strength`-- y la mascara deja de importar. Por
eso la REGLA se declara SOLO para armas, donde el material es metal y la
variacion existe siempre, y para el resto esto informa.

Es la tercera vez en este repo que una regla medida sobre armas no generaliza:
antes pasaron el radio de la caja de colision (62 de 62 sobre armas, 73 % sobre
el corpus) y "la malla tiene que estar cerrada". La diferencia es que aca el
alcance se DECLARA en vez de suponerse.

CUIDADO CON EL CORPUS ENTERO

Sobre los 12.058 `_n` medibles, el 79,8 % tiene mas de la mitad de sus bloques
en blanco -- pero 9.360 de esos archivos son de `terrain`, que usa alfa plano.
Promediar sobre el corpus sin separar da justo la conclusion contraria a la
correcta.

COMO SE LEE EL ALFA SIN DECODIFICAR

En DXT5/BC3 cada bloque de 4x4 texeles empieza con 8 bytes de alfa: `alpha0`,
`alpha1` (un byte cada uno) y 6 bytes de indices de 3 bits. Si
`alpha0 == alpha1` el bloque tiene alfa CONSTANTE y vale ese byte, sin mirar
los indices. Con eso alcanza para medir cuanto de la mascara esta saturada.

Medido tambien: los 12.075 `_n` del corpus son DXT5. Cero usan DXT1 o BC5, que
es lo esperable -- sin canal alfa no hay mascara.
"""
import os
import struct
import sys

TOPE_ARMA = 10.0          # % de bloques en blanco admitido en un _n de arma
MIN_BLOQUES = 64          # menos que esto no dice nada


# Sin comprimir de 32 bpp: tiene alfa y se lee SIN decodificar nada. Antes caía
# en "formato que lleva alfa pero este lector no decodifica" y se reportaba
# como limite de la herramienta --que era falso: no hay nada que decodificar.
# El limite real sigue siendo BC7, que tiene ocho modos con particionado
# variable. Medido: 10.048 de 32.241 texturas del corpus son sin comprimir.
SIN_COMPRIMIR_32 = "SIN_COMPRIMIR_32BPP"
SIN_COMPRIMIR_24 = "SIN_COMPRIMIR_24BPP"

def cabecera(d):
    """(ancho, alto, offset_datos, nombre) o None."""
    if len(d) < 148 or d[:4] != b"DDS ":
        return None
    alto, ancho = struct.unpack_from("<II", d, 12)
    fourcc = d[84:88]
    if fourcc == b"DXT5":
        return ancho, alto, 128, "DXT5"
    if fourcc == b"DXT1":
        return ancho, alto, 128, "DXT1"
    if fourcc == b"DX10":
        dxgi, = struct.unpack_from("<I", d, 128)
        nombre = {77: "BC3_UNORM", 78: "BC3_SRGB", 98: "BC7_UNORM",
                  99: "BC7_SRGB", 83: "BC5", 71: "BC1", 80: "BC4"}.get(
                      dxgi, "dxgi%d" % dxgi)
        return ancho, alto, 148, nombre
    if fourcc == b"\x00\x00\x00\x00":
        # Sin FourCC: el formato lo dice el pixel format. DDPF_ALPHAPIXELS
        # (0x1) mas una mascara alfa que entre en el pixel declarado.
        bits, = struct.unpack_from("<I", d, 88)
        pf, = struct.unpack_from("<I", d, 80)
        amask, = struct.unpack_from("<I", d, 104)
        if bits == 32 and (pf & 0x1) and amask:
            return ancho, alto, 128, SIN_COMPRIMIR_32
        if bits == 24:
            return ancho, alto, 128, SIN_COMPRIMIR_24
    return ancho, alto, 128, fourcc.decode("latin1", "replace").strip()


CON_ALFA_POR_BLOQUE = ("DXT5", "BC3_UNORM", "BC3_SRGB")

# Formatos que NO tienen un canal alfa utilizable: sin el no hay mascara, y eso
# es un defecto del asset.
SIN_ALFA = ("DXT1", "BC1", "BC4", "BC5")

# Formatos que SI llevan alfa pero que este lector no decodifica. BC7 tiene
# ocho modos con particionado variable; escribir ese decodificador de memoria
# es como se meten los errores que no dan error. No es un defecto del asset:
# es un limite de esta herramienta, y se dice distinto.
ALFA_NO_MEDIBLE = ("BC7_UNORM", "BC7_SRGB", "DXT2", "DXT3", "BC2")


def _medir_sin_comprimir(d, ancho, alto, paso):
    """El alfa de un DDS sin comprimir de 32 bpp, texel por texel.

    La semantica es la misma que en DXT5: un bloque de 4x4 cuenta como
    "blanco" solo si es CONSTANTE 255, y como "negro" solo si es constante 0.
    Un bloque que varia no esta saturado aunque uno de sus texeles llegue a
    255. Donde DXT5 necesita el truco `alpha0 == alpha1`, acá se miran los
    texeles.

    A diferencia de DXT5, aca la media de un bloque no constante es EXACTA:
    no hay que aproximar nada porque los valores estan ahi. El canal alfa se
    saca de una con un corte con paso (operacion de C, no un loop de Python),
    y cada bloque se decide comparando sus cuatro filas.
    """
    base = 128
    if base + ancho * alto * 4 > len(d):
        return {"error": "el archivo no llega a contener su primer mip"}
    alfa = d[base + 3: base + 3 + ancho * alto * 4: 4]
    if len(alfa) < ancho * alto:
        return {"error": "el archivo no llega a contener su primer mip"}
    bw, bh = (ancho + 3) // 4, (alto + 3) // 4
    blancos = negros = total = 0
    suma = 0
    for i in range(0, bw * bh, paso):
        bx, by = i % bw, i // bw
        x0, y0 = bx * 4, by * 4
        x1, y1 = min(x0 + 4, ancho), min(y0 + 4, alto)
        filas = [alfa[y * ancho + x0: y * ancho + x1] for y in range(y0, y1)]
        if len(set(filas)) == 1 and len(set(filas[0])) == 1:
            v = filas[0][0]
            suma += v
            if v == 255:
                blancos += 1
            elif v == 0:
                negros += 1
        else:
            n = sum(len(f) for f in filas)
            suma += sum(sum(f) for f in filas) // n
        total += 1
    if total < MIN_BLOQUES:
        return {"error": "solo %d bloques muestreados" % total}
    return {"blanco_pct": 100.0 * blancos / total,
            "negro_pct": 100.0 * negros / total, "media": suma / float(total),
            "bloques": total, "formato": SIN_COMPRIMIR_32,
            "tamano": (ancho, alto)}


def medir(ruta, paso=3):
    """{blanco_pct, media, bloques, formato} o {'error': ...}."""
    try:
        with open(ruta, "rb") as fh:
            d = fh.read()
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, e)}
    c = cabecera(d)
    if c is None:
        return {"error": "no es un DDS legible"}
    ancho, alto, base, formato = c
    if formato == SIN_COMPRIMIR_32:
        return _medir_sin_comprimir(d, ancho, alto, paso)
    if formato in SIN_ALFA or formato == SIN_COMPRIMIR_24:
        return {"error": "formato %s: no tiene canal alfa, asi que NO HAY "
                         "mascara especular. Los 12.075 `_n` del corpus son "
                         "DXT5." % formato,
                "formato": formato, "clase": "sin_alfa"}
    if formato not in CON_ALFA_POR_BLOQUE:
        return {"error": "formato %s: lleva alfa, pero este lector solo "
                         "decodifica DXT5/BC3 y no puede medirla. No es un "
                         "defecto del archivo: es un limite de esta "
                         "herramienta. Para poder verificarla, convertila con "
                         "`texconv -f BC3_UNORM`, que es lo que usan los "
                         "12.075 `_n` del corpus." % formato,
                "formato": formato, "clase": "no_medible"}
    bw, bh = (ancho + 3) // 4, (alto + 3) // 4
    if base + bw * bh * 16 > len(d):
        return {"error": "el archivo no llega a contener su primer mip"}
    blancos = negros = total = 0
    suma = 0
    for i in range(0, bw * bh, paso):
        o = base + i * 16
        a0, a1 = d[o], d[o + 1]
        total += 1
        if a0 == a1:
            suma += a0
            if a0 == 255:
                blancos += 1
            elif a0 == 0:
                negros += 1
        else:
            suma += (a0 + a1) // 2
    if total < MIN_BLOQUES:
        return {"error": "solo %d bloques muestreados" % total}
    return {"blanco_pct": 100.0 * blancos / total,
            "negro_pct": 100.0 * negros / total,
            "media": suma / float(total), "bloques": total,
            "formato": formato, "tamano": (ancho, alto)}


def juzgar(m, es_arma):
    """(fallas, notas). Un formato que no se puede medir NO pasa --no
    comprobar nada no es exito-- pero se reporta como limite de la
    herramienta, no como defecto del asset."""
    if m.get("error"):
        if m.get("clase") == "no_medible":
            return ["NO MEDIBLE: %s" % m["error"]], []
        return ["no se pudo medir: %s" % m["error"]], []
    fallas, notas = [], []
    if es_arma and m["blanco_pct"] > TOPE_ARMA:
        fallas.append(
            "REGLA arma: %.1f %% de los bloques con alfa constante 255. La "
            "mascara especular esta saturada y el arma se ve de plastico. "
            "Medido: las 140 texturas `_n` de arma del corpus estan por debajo "
            "del 6,9 %%, sin excepciones. Suele venir de convertir un PNG "
            "opaco con texconv, que llena el alfa de 255 sin avisar."
            % m["blanco_pct"])
    elif m["blanco_pct"] > 50.0:
        notas.append(
            "OBS %.1f %% de bloques en blanco. En objetos portables la mediana "
            "es 0,00 %% y el p90 0,34 %%, pero el 4,91 %% (59 de 1.201) esta "
            "saturado del todo: son materiales MATE --ropa, comida, carbon, "
            "cejas-- donde el brillo lo apaga el shader. Si este asset no es "
            "de esa clase, la mascara esta mal." % m["blanco_pct"])
    notas.append("OBS media del alfa %.1f. En objetos portables: p5 14, "
                 "mediana 56, p95 219." % m["media"])
    return fallas, notas


def revisar(rutas, es_arma):
    medidos = 0
    con_falla = 0
    for ruta in rutas:
        m = medir(ruta)
        fallas, notas = juzgar(m, es_arma)
        print("== %s" % os.path.basename(ruta))
        if not m.get("error"):
            medidos += 1
            print("   %s %dx%d  blanco %.2f %%  negro %.2f %%  media %.1f"
                  % (m["formato"], m["tamano"][0], m["tamano"][1],
                     m["blanco_pct"], m["negro_pct"], m["media"]))
        for n in notas:
            print("   %s" % n)
        for f in fallas:
            print("   FALLA %s" % f)
        if fallas:
            con_falla += 1
    if medidos == 0:
        print("\nFALLA: cero texturas medidas -- no comprobar nada no es exito")
        return 1
    print("\n%d texturas medidas, %d con falla" % (medidos, con_falla))
    return 1 if con_falla else 0


# --------------------------------------------------------------------------
def _dds(ancho, alto, alfas):
    """Un DXT5 minimo con un alfa constante por bloque. Solo para el
    autotest: el resto de los bytes no se leen."""
    cab = bytearray(128)
    cab[0:4] = b"DDS "
    struct.pack_into("<I", cab, 4, 124)
    struct.pack_into("<II", cab, 12, alto, ancho)
    cab[84:88] = b"DXT5"
    bw, bh = (ancho + 3) // 4, (alto + 3) // 4
    cuerpo = bytearray(bw * bh * 16)
    for i in range(bw * bh):
        a = alfas[i % len(alfas)]
        cuerpo[i * 16] = a
        cuerpo[i * 16 + 1] = a
    return bytes(cab) + bytes(cuerpo)


def _sin_comprimir(ancho, alto, alfas, bits=32):
    """Un DDS sin comprimir, un solo nivel, alfa por texel. Solo autotest.

    Con bits=24 no hay canal alfa: es el caso que tiene que reprobar por
    "sin_alfa" y no por "no medible" -- un DDS de 24 bpp no tiene bytes para
    la mascara, aunque la cabecera la mencione.
    """
    cab = bytearray(128)
    cab[0:4] = b"DDS "
    struct.pack_into("<I", cab, 4, 124)
    struct.pack_into("<III", cab, 8, 0x1007, alto, ancho)
    canales = bits // 8
    struct.pack_into("<I", cab, 20, ancho * canales)        # pitch
    struct.pack_into("<I", cab, 28, 1)                      # un nivel
    struct.pack_into("<I", cab, 76, 32)                     # ddspf.size
    struct.pack_into("<I", cab, 80, 0x1 | 0x40)             # ALPHAPIXELS|RGB
    struct.pack_into("<I", cab, 88, bits)
    if bits == 32:
        struct.pack_into("<IIII", cab, 92,
                         0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    else:
        struct.pack_into("<III", cab, 92,
                         0x00FF0000, 0x0000FF00, 0x000000FF)
    struct.pack_into("<I", cab, 108, 0x1000)                # DDSCAPS_TEXTURE
    cuerpo = bytearray()
    for i in range(ancho * alto):
        a = alfas[i % len(alfas)]
        cuerpo += bytes((0, 0, 0, a)) if canales == 4 else bytes((0, 0, 0))
    return bytes(cab) + bytes(cuerpo)


def autotest():
    import tempfile
    fallas = []

    def exigir(cond, texto):
        if not cond:
            fallas.append(texto)

    def con(alfas, ancho=64, alto=64):
        fd, ruta = tempfile.mkstemp(suffix="_n.dds")
        with os.fdopen(fd, "wb") as fh:
            fh.write(_dds(ancho, alto, alfas))
        try:
            return medir(ruta, paso=1), ruta
        finally:
            os.unlink(ruta)

    m, _ = con([255])
    exigir(abs(m["blanco_pct"] - 100.0) < 1e-6,
           "una mascara toda en 255 no dio 100 %%: %s" % m.get("blanco_pct"))
    exigir(bool(juzgar(m, True)[0]), "la mascara saturada no reprobo como arma")
    exigir(not juzgar(m, False)[0],
           "la mascara saturada reprobo sin declararla arma: 59 texturas "
           "vanilla son asi")
    exigir(any("4,91" in n for n in juzgar(m, False)[1]),
           "no informo la excepcion de los materiales mate")

    m, _ = con([0])
    exigir(abs(m["blanco_pct"]) < 1e-6, "una mascara en 0 conto blancos")
    exigir(not juzgar(m, True)[0], "una mascara oscura reprobo como arma")

    m, _ = con([40, 80, 120, 200])
    exigir(abs(m["blanco_pct"]) < 1e-6, "conto blancos donde no los hay")
    exigir(abs(m["media"] - 110.0) < 1.0,
           "la media salio %.1f, se esperaba 110" % m["media"])
    exigir(not juzgar(m, True)[0], "una mascara variada reprobo como arma")

    # justo encima y justo debajo del tope
    bajo = [255] + [0] * 19          # 5 % en blanco
    alto_ = [255] * 3 + [0] * 17     # 15 % en blanco
    m, _ = con(bajo)
    exigir(not juzgar(m, True)[0],
           "5 %% en blanco reprobo y el tope es 10 %%")
    m, _ = con(alto_)
    exigir(bool(juzgar(m, True)[0]),
           "15 %% en blanco no reprobo y el tope es 10 %%")

    # un formato sin alfa por bloque no se deja pasar en silencio
    fd, ruta = tempfile.mkstemp(suffix="_n.dds")
    with os.fdopen(fd, "wb") as fh:
        d = bytearray(_dds(64, 64, [128]))
        d[84:88] = b"DXT1"
        fh.write(bytes(d))
    try:
        m = medir(ruta)
        exigir(m.get("clase") == "sin_alfa", "un DXT1 no se clasifico como "
               "sin alfa: %s" % m.get("clase"))
        f = juzgar(m, False)[0]
        exigir(bool(f), "un DXT1 no reprobo")
        exigir("NO MEDIBLE" not in f[0],
               "un DXT1 se reporto como limite de la herramienta, y es un "
               "defecto del asset: no tiene alfa")
    finally:
        os.unlink(ruta)

    # BC7 SI lleva alfa: es un limite de esta herramienta, no un defecto.
    fd, ruta = tempfile.mkstemp(suffix="_n.dds")
    with os.fdopen(fd, "wb") as fh:
        d = bytearray(_dds(64, 64, [128]))
        d[84:88] = b"DX10"
        d += bytes(20)
        struct.pack_into("<I", d, 128, 98)          # DXGI_FORMAT_BC7_UNORM
        fh.write(bytes(d))
    try:
        m = medir(ruta)
        exigir(m.get("clase") == "no_medible",
               "un BC7 no se clasifico como no medible: %s" % m.get("clase"))
        f = juzgar(m, True)[0]
        exigir(bool(f), "un BC7 paso sin medirse")
        exigir("NO MEDIBLE" in f[0],
               "un BC7 se reporto como defecto del asset, y lleva alfa")
    finally:
        os.unlink(ruta)

    # --- sin comprimir de 32 bpp: el formato que escribe pipeline/texturas.py
    def con_sc(alfas, **kw):
        fd, ruta = tempfile.mkstemp(suffix="_n.dds")
        with os.fdopen(fd, "wb") as fh:
            fh.write(_sin_comprimir(64, 64, alfas, **kw))
        try:
            return medir(ruta, paso=1), ruta
        finally:
            os.unlink(ruta)

    m, _ = con_sc([255])
    exigir(m.get("formato") == SIN_COMPRIMIR_32,
           "un sin comprimir de 32 bpp no se clasifico como tal: %s"
           % m.get("formato"))
    exigir(abs(m.get("blanco_pct", -1) - 100.0) < 1e-6,
           "sin comprimir: una mascara toda en 255 no dio 100 %%: %s"
           % m.get("blanco_pct"))
    exigir(abs(m.get("media", -1) - 255.0) < 1e-6,
           "sin comprimir: la media de una mascara en 255 no es 255")
    exigir(bool(juzgar(m, True)[0]),
           "sin comprimir: la mascara saturada no reprobo como arma")
    exigir(not juzgar(m, False)[0],
           "sin comprimir: la mascara saturada reprobo sin declararla arma, "
           "y 59 texturas vanilla de objeto portable son asi")

    m, _ = con_sc([0])
    exigir(abs(m.get("blanco_pct", -1)) < 1e-6,
           "sin comprimir: una mascara en 0 conto blancos")

    m, _ = con_sc([40, 80, 120, 200])
    exigir(abs(m.get("blanco_pct", -1)) < 1e-6,
           "sin comprimir: conto blancos donde no los hay")
    exigir(abs(m.get("media", -1) - 110.0) < 1.0,
           "sin comprimir: la media salio %.1f, se esperaba 110"
           % m.get("media", -1))

    # saturacion PARCIAL: la que distingue "medir" de "contar si hay un 255".
    # 16 texeles en 255 y 16 en 0 por bloque -> la mitad de los bloques.
    m, _ = con_sc([255] * 16 + [0] * 16)
    exigir(abs(m.get("blanco_pct", -1) - 50.0) < 1e-6,
           "sin comprimir: la saturacion parcial salio %.2f %%, se esperaba "
           "50.00" % m.get("blanco_pct", -1))

    # un 24 bpp no tiene alfa: defecto del asset, no limite de la herramienta
    fd, ruta = tempfile.mkstemp(suffix="_n.dds")
    with os.fdopen(fd, "wb") as fh:
        fh.write(_sin_comprimir(64, 64, [128], bits=24))
    try:
        m = medir(ruta)
        exigir(m.get("clase") == "sin_alfa",
               "un sin comprimir de 24 bpp no se clasifico como sin alfa: %s"
               % m.get("clase"))
        f = juzgar(m, False)[0]
        exigir(bool(f), "un 24 bpp no reprobo")
        exigir("NO MEDIBLE" not in f[0],
               "un 24 bpp se reporto como limite de la herramienta, y es un "
               "defecto: no tiene bytes para el alfa")
    finally:
        os.unlink(ruta)

    print("autotest: %d comprobaciones, %d fallas" % (25, len(fallas)))
    for x in fallas:
        print("  FALLA %s" % x)
    return 1 if fallas else 0


def censo(raiz):
    """Reproduce la medicion del corpus. Imprime, no reprueba."""
    from collections import defaultdict
    por_cat = defaultdict(list)
    n = 0
    for base, _, nombres in os.walk(raiz):
        for nom in nombres:
            if not nom.lower().endswith("_n.dds"):
                continue
            ruta = os.path.join(base, nom)
            rel = os.path.relpath(ruta, raiz).lower().replace("\\", "/")
            m = medir(ruta, paso=7)
            if m.get("error"):
                continue
            n += 1
            por_cat[rel.split("/")[0]].append(m["blanco_pct"])
    print("texturas _n medidas: %d" % n)
    print("%-16s %6s %10s %10s %8s" % ("categoria", "n", "mediana", "p90", "max"))
    for cat, v in sorted(por_cat.items(), key=lambda kv: -len(kv[1])):
        v = sorted(v)
        k = len(v)
        print("%-16s %6d %9.2f%% %9.2f%% %7.1f%%"
              % (cat, k, v[k // 2], v[min(k - 1, (9 * k) // 10)], v[-1]))
    return 0 if n else 1


def main(argv):
    if len(argv) == 1 and argv[0] == "--autotest":
        return autotest()
    if len(argv) == 2 and argv[0] == "--censo":
        return censo(argv[1])
    es_arma = bool(argv) and argv[0] == "--arma"
    if es_arma:
        argv = argv[1:]
    if argv and all(a.lower().endswith(".dds") for a in argv):
        return revisar(argv, es_arma)
    print("uso: mascara_especular.py [--arma] <textura_n.dds> [...] | "
          "--autotest | --censo <carpeta>")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
