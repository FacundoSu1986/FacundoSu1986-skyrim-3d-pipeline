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
    if formato in SIN_ALFA:
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

    print("autotest: %d comprobaciones, %d fallas" % (18, len(fallas)))
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
