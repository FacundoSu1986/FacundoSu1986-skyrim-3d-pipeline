# -*- coding: utf-8 -*-
"""Escribe DDS con cadena de mipmaps: sin comprimir (32 bpp), DXT1, DXT5 o
BC7.

    python escritor_dds.py --autotest

SIN COMPRIMIR, DXT O BC7
------------------------
Sin comprimir no es un atajo: el 31,2 % del corpus vanilla son DDS sin
comprimir de 32 bpp (10.048 de 32.241, hallazgo 2 del censo de texturas). Es
un formato que el juego carga igual que DXT; lo que cambia es el peso.

DXT1/DXT5 los comprime `compresor_dxt.py`, que necesita numpy y se importa
solo cuando se pide un formato comprimido. La cadena de mipmaps se arma igual
que sin comprimir --en RGBA, con la reduccion que pase quien llama-- y se
comprime nivel por nivel. La cabecera es la de los DXT vanilla. Medido sobre
los 22.004 DXT1/DXT5 del corpus: los 22.001 con mipmaps tienen caps 0x401008;
21.998 tienen flags 0xA1007 (los otros 3 son cubemaps sin LINEARSIZE); pixel
format FOURCC y el tamano del nivel 0 en el campo de pitch. Los 3 sin
mipmaps, flags 0x81007 y caps 0x1000: lo mismo que se escribe sin mipmaps.

BC7 lo comprime `compresor_bc7.py`, con el mismo criterio de import perezoso.
BC7 exige el header DX10: la fourcc es "DX10" y siguen 20 bytes con el codigo
DXGI --98 = BC7_UNORM, 99 = BC7_UNORM_SRGB, el que pipeline/texturas.py pide
para los slots sRGB con `srgb=True`-- y con eso la cabecera mide 148 y el
cuerpo arranca en 148. El resto de la cabecera es el mismo de los DXT
vanilla: flags 0xA1007, caps 0x401008, y en pitch_or_linear_size el tamano
del nivel 0 a 16 bytes por bloque.

COMO SE VERIFICA
----------------
Con el lector que ya existe. `parser_dds.leer()` predice el tamano exacto del
archivo a partir del encabezado, y esa prediccion se cumple en 32.241 de 32.241
DDS de Bethesda. Si lo que escribimos no la cumple, el encabezado miente.

El autotest ademas RELEE los pixeles y los compara con los que se escribieron:
que el tamano cierre no prueba que el contenido este bien.
"""
import os
import struct
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

import parser_dds  # noqa: E402

DDSD_CAPS = 0x1
DDSD_HEIGHT = 0x2
DDSD_WIDTH = 0x4
DDSD_PITCH = 0x8
DDSD_PIXELFORMAT = 0x1000
DDSD_MIPMAPCOUNT = 0x20000
DDSD_LINEARSIZE = 0x80000

DDPF_ALPHAPIXELS = 0x1
DDPF_FOURCC = 0x4
DDPF_RGB = 0x40

FORMATOS = ("RGBA", "DXT1", "DXT5", "BC7")

DDSCAPS_COMPLEX = 0x8
DDSCAPS_TEXTURE = 0x1000
# 0x400000, no 0x400: con 0x400 las caps salian 0x1408, y los DDS vanilla con
# mipmaps tienen 0x401008 (22.001 de 22.001 DXT del corpus, y 1.999 de 1.999
# sin comprimir de 32 bpp en una muestra de un archivo de cada tres). El
# juego lee la cantidad de mipmaps de su campo, pero la cabecera tiene que
# decir lo mismo.
DDSCAPS_MIPMAP = 0x400000


def niveles(ancho, alto):
    """La cadena completa, hasta 1x1. Devuelve [(w, h), ...]."""
    fuera = []
    w, h = ancho, alto
    while True:
        fuera.append((w, h))
        if w == 1 and h == 1:
            return fuera
        w = max(1, w // 2)
        h = max(1, h // 2)


def reducir(pix, ancho, alto):
    """Un nivel de mipmap: promedio de cada bloque de 2x2.

    Se promedia en el espacio en que vienen los valores. Para una mascara o un
    mapa de datos eso es lo correcto; para color con gamma seria discutible, y
    queda dicho en vez de disimulado.
    """
    nw, nh = max(1, ancho // 2), max(1, alto // 2)
    fuera = bytearray(nw * nh * 4)
    for y in range(nh):
        y0, y1 = min(2 * y, alto - 1), min(2 * y + 1, alto - 1)
        for x in range(nw):
            x0, x1 = min(2 * x, ancho - 1), min(2 * x + 1, ancho - 1)
            base = (y * nw + x) * 4
            for c in range(4):
                s = (pix[(y0 * ancho + x0) * 4 + c] +
                     pix[(y0 * ancho + x1) * 4 + c] +
                     pix[(y1 * ancho + x0) * 4 + c] +
                     pix[(y1 * ancho + x1) * 4 + c])
                fuera[base + c] = (s + 2) // 4
    return bytes(fuera)


def cabecera(ancho, alto, n_mips, formato="RGBA", srgb=False):
    """Los primeros 128 bytes (148 con BC7, que se le anexa el DX10).

    `srgb` solo se usa con formato="BC7": 99 (SRGB) en vez de 98 (UNORM);
    en los demas formatos se ignora.
    """
    b = bytearray(128)
    b[0:4] = b"DDS "
    struct.pack_into("<I", b, 4, 124)
    comprimido = formato != "RGBA"
    flags = (DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT |
             (DDSD_LINEARSIZE if comprimido else DDSD_PITCH) |
             (DDSD_MIPMAPCOUNT if n_mips > 1 else 0))
    struct.pack_into("<III", b, 8, flags, alto, ancho)
    if comprimido:                                    # tamano del nivel 0
        bpb = 8 if formato == "DXT1" else 16
        struct.pack_into("<I", b, 20,
                         ((ancho + 3) // 4) * ((alto + 3) // 4) * bpb)
    else:
        struct.pack_into("<I", b, 20, ancho * 4)      # pitch
    struct.pack_into("<I", b, 24, 0)                  # profundidad
    struct.pack_into("<I", b, 28, n_mips)
    # --- pixel format ---
    struct.pack_into("<I", b, 76, 32)
    if comprimido:
        struct.pack_into("<I", b, 80, DDPF_FOURCC)
        # BC7 no tiene fourcc propia: la spec lo manda por "DX10" + bloque.
        b[84:88] = (b"DX10" if formato == "BC7" else formato.encode("ascii"))
    else:
        struct.pack_into("<I", b, 80, DDPF_RGB | DDPF_ALPHAPIXELS)
        struct.pack_into("<I", b, 88, 32)             # bits por pixel
        # BGRA, como lo espera D3D9 y como estan los vanilla sin comprimir
        struct.pack_into("<I", b, 92, 0x00FF0000)     # mascara R
        struct.pack_into("<I", b, 96, 0x0000FF00)     # mascara G
        struct.pack_into("<I", b, 100, 0x000000FF)    # mascara B
        struct.pack_into("<I", b, 104, 0xFF000000)    # mascara A
    caps = DDSCAPS_TEXTURE | (DDSCAPS_COMPLEX | DDSCAPS_MIPMAP
                              if n_mips > 1 else 0)
    struct.pack_into("<I", b, 108, caps)
    # El header DX10 de BC7: DXGI_FORMAT (99 sRGB / 98 UNORM), dimension 3,
    # misc 0, array size 1, misc flags 0. parser_dds exige los 148 bytes
    # exactos para BC7 y ya mapea 98/99 a sRGB.
    if formato == "BC7":
        b += struct.pack("<IIIII", 99 if srgb else 98, 3, 0, 1, 0)
    return bytes(b)


def escribir(ruta, ancho, alto, pixeles, con_mipmaps=True,
             reducir_nivel=None, formato="RGBA", srgb=False):
    """`pixeles` son ancho*alto*4 bytes en orden RGBA.

    `formato`: "RGBA" (sin comprimir; se guarda como BGRA porque es lo que
    declara la mascara del encabezado), "DXT1", "DXT5" o "BC7". `srgb` solo
    se atiende con BC7 (DXGI 99 en vez de 98) y en los demas se ignora.

    `reducir_nivel(pix, ancho, alto)` arma cada mipmap desde el anterior; por
    defecto `reducir`, que promedia en el espacio en que vienen los valores.
    Quien sabe que el mapa es color o normal pasa su propia reduccion (ver
    pipeline/texturas.py): un normal promediado sin renormalizar se aplana
    en cada nivel.
    """
    if formato not in FORMATOS:
        raise ValueError("formato %r: se admite %s" % (formato, FORMATOS))
    if formato == "BC7":
        import compresor_bc7   # necesita numpy; solo si se comprime
    elif formato != "RGBA":
        import compresor_dxt   # necesita numpy; solo si se comprime
    reducir_nivel = reducir_nivel or reducir
    esperado = ancho * alto * 4
    if len(pixeles) != esperado:
        raise ValueError("pixeles: %d bytes, se esperaban %d (%dx%d RGBA)"
                         % (len(pixeles), esperado, ancho, alto))

    cadena = niveles(ancho, alto) if con_mipmaps else [(ancho, alto)]
    cuerpo = bytearray()
    actual, aw, ah = bytes(pixeles), ancho, alto
    for i, (w, h) in enumerate(cadena):
        if i:
            actual = reducir_nivel(actual, aw, ah)
            if len(actual) != w * h * 4:
                raise ValueError("el nivel %d mide %d bytes, se esperaban %d "
                                 "(%dx%d RGBA)" % (i, len(actual), w * h * 4,
                                                   w, h))
            aw, ah = w, h
        if formato == "BC7":
            cuerpo += compresor_bc7.comprimir(actual, w, h)
            continue
        if formato != "RGBA":
            cuerpo += compresor_dxt.comprimir(actual, w, h, formato)
            continue
        for p in range(0, len(actual), 4):
            r, g, b, a = actual[p:p + 4]
            cuerpo += bytes((b, g, r, a))

    with open(ruta, "wb") as fh:
        fh.write(cabecera(ancho, alto, len(cadena), formato, srgb=srgb))
        fh.write(bytes(cuerpo))
    return ruta


def leer_pixeles(ruta):
    """Los pixeles del nivel 0, en RGBA. Para verificar lo que se escribio.
    Un DXT1/DXT5 se decodifica con `compresor_dxt` (numpy) y un BC7 con
    `compresor_bc7` (tambien numpy)."""
    d = parser_dds.leer(ruta)
    n_bl = ((d["ancho"] + 3) // 4) * ((d["alto"] + 3) // 4)
    if d["formato"] == "BC7":
        import compresor_bc7
        with open(ruta, "rb") as fh:
            fh.seek(148)              # cabecera de 128 + header DX10 de 20
            crudo = fh.read(n_bl * 16)
        return d, compresor_bc7.descomprimir(crudo, d["ancho"], d["alto"])
    if d["formato"] in ("DXT1", "DXT5"):
        import compresor_dxt
        bpb = 8 if d["formato"] == "DXT1" else 16
        with open(ruta, "rb") as fh:
            fh.seek(128)
            crudo = fh.read(n_bl * bpb)
        return d, compresor_dxt.descomprimir(crudo, d["ancho"], d["alto"],
                                             d["formato"])
    if d["comprimido"]:
        raise ValueError("se releen sin comprimir, DXT1, DXT5 y BC7; no %s"
                         % d["formato"])
    with open(ruta, "rb") as fh:
        fh.seek(128)
        crudo = fh.read(d["ancho"] * d["alto"] * 4)
    fuera = bytearray(len(crudo))
    for p in range(0, len(crudo), 4):
        b, g, r, a = crudo[p:p + 4]
        fuera[p:p + 4] = bytes((r, g, b, a))
    return d, bytes(fuera)


# --- autotest ----------------------------------------------------------------

def autotest():
    """Escribe, relee con parser_dds y compara. Cero casos NO es exito."""
    import tempfile
    print("SUITE DE FALSIFICACION - escritor_dds")
    print("")
    fallos = n = 0
    tmp = tempfile.mkdtemp()

    casos = [(4, 4), (16, 8), (64, 64), (256, 128), (512, 512)]
    print("  a. el tamano que predice parser_dds vs el tamano real")
    for w, h in casos:
        pix = bytearray()
        for y in range(h):
            for x in range(w):
                pix += bytes(((x * 7) % 256, (y * 11) % 256,
                              ((x + y) * 3) % 256, 255))
        ruta = escribir(os.path.join(tmp, "t%dx%d.dds" % (w, h)), w, h, pix)
        d = parser_dds.leer(ruta)
        real = os.path.getsize(ruta)
        ok = d["tamano_cuadra"] and d["bytes_esperados"] == real
        n += 1
        fallos += 0 if ok else 1
        print("     %4dx%-4d mips=%-2d  %7d B  predice %-7s  %s"
              % (w, h, d["mipmaps"], real, d["bytes_esperados"],
                 "ok" if ok else "FALLA"))

    print("")
    print("  b. los pixeles releidos son los que se escribieron")
    w, h = 64, 32
    pix = bytearray()
    for y in range(h):
        for x in range(w):
            pix += bytes((x * 4 % 256, y * 8 % 256, (x ^ y) % 256,
                          (x + y) % 256))
    ruta = escribir(os.path.join(tmp, "roundtrip.dds"), w, h, bytes(pix))
    d, vuelta = leer_pixeles(ruta)
    iguales = vuelta == bytes(pix)
    n += 1
    fallos += 0 if iguales else 1
    dif = sum(1 for a, b in zip(vuelta, bytes(pix)) if a != b)
    print("     %d bytes, %d distintos  %s"
          % (len(vuelta), dif, "ok" if iguales else "FALLA"))

    print("")
    print("  c. la cadena de mipmaps llega a 1x1")
    ruta = escribir(os.path.join(tmp, "mips.dds"), 256, 64,
                    bytes([200, 100, 50, 255] * (256 * 64)))
    d = parser_dds.leer(ruta)
    with open(ruta, "rb") as fh:
        caps, = struct.unpack_from("<I", fh.read(128), 108)
    ok = (d["mipmaps"] == 9 and d["mip_mas_chico"] == [1, 1]
          and caps == 0x401008)
    n += 1
    fallos += 0 if ok else 1
    print("     256x64 -> %d niveles, el mas chico %s, caps 0x%X (vanilla "
          "0x401008)  %s" % (d["mipmaps"], d["mip_mas_chico"], caps,
                             "ok" if ok else "FALLA"))

    print("")
    print("  d. potencia de dos, que el corpus cumple en 32.241 de 32.241")
    ruta = escribir(os.path.join(tmp, "p2.dds"), 128, 32,
                    bytes([1, 2, 3, 4] * (128 * 32)))
    d = parser_dds.leer(ruta)
    n += 1
    fallos += 0 if d["potencia_de_dos"] else 1
    print("     128x32 potencia_de_dos=%s  %s"
          % (d["potencia_de_dos"], "ok" if d["potencia_de_dos"] else "FALLA"))

    print("")
    print("  e. DXT1, DXT5 y BC7: tamano, cabecera vanilla y relectura")
    try:
        import numpy  # noqa: F401
        hay_numpy = True
    except ImportError:
        hay_numpy = False
        print("     numpy no esta: se saltea (no cuenta como comprobado)")
    for formato in (("DXT1", "DXT5", "BC7") if hay_numpy else ()):
        for w, h in ((4, 4), (256, 128), (64, 2)):
            plano = bytes([200, 100, 50, 255] * (w * h))  # 565: no exacto
            ruta = escribir(os.path.join(tmp, "%s_%dx%d.dds" % (formato, w, h)),
                            w, h, plano, formato=formato)
            d = parser_dds.leer(ruta)
            with open(ruta, "rb") as fh:
                cab = fh.read(148)
            flags, = struct.unpack_from("<I", cab, 8)
            lineal, = struct.unpack_from("<I", cab, 20)
            pf, = struct.unpack_from("<I", cab, 80)
            caps, = struct.unpack_from("<I", cab, 108)
            fourcc = bytes(cab[84:88])
            bpb = 8 if formato == "DXT1" else 16
            _, vuelta = leer_pixeles(ruta)
            dif = max(abs(a - b) for a, b in zip(vuelta, plano))
            ok = (d["formato"] == formato and d["tamano_cuadra"]
                  and d["mip_mas_chico"] == [1, 1]
                  and flags == 0xA1007 and pf == DDPF_FOURCC
                  and caps == 0x401008
                  and fourcc == (b"DX10" if formato == "BC7"
                                 else formato.encode("ascii"))
                  and lineal == ((w + 3) // 4) * ((h + 3) // 4) * bpb
                  and len(vuelta) == w * h * 4 and dif <= 4)
            n += 1
            fallos += 0 if ok else 1
            print("     %s %4dx%-4d %6d B  cuadra=%s flags=0x%X caps=0x%X  "
                  "error maximo %d  %s"
                  % (formato, w, h, d["bytes"], d["tamano_cuadra"], flags,
                     caps, dif, "ok" if ok else "FALLA"))

    if hay_numpy:
        # El srgb de BC7 vive en el codigo DXGI del header DX10: 99, y
        # parser_dds tiene que verlo como sRGB.
        plano = bytes([200, 100, 50, 255] * (8 * 8))
        ruta = escribir(os.path.join(tmp, "bc7srgb.dds"), 8, 8, plano,
                        formato="BC7", srgb=True)
        d = parser_dds.leer(ruta)
        with open(ruta, "rb") as fh:
            dxgi, = struct.unpack_from("<I", fh.read(148), 128)
        ok = (d["formato"] == "BC7" and d["srgb"] and dxgi == 99
              and d["tamano_cuadra"])
        n += 1
        fallos += 0 if ok else 1
        print("     BC7 srgb: DXGI=%d srgb=%s  %s"
              % (dxgi, d["srgb"], "ok" if ok else "FALLA"))

    print("")
    if n == 0:
        print("  NO se comprobo NADA.")
        return False
    if fallos:
        print("  %d FALLAS de %d. El escritor NO esta validado." % (fallos, n))
        return False
    print("  %d comprobaciones, sin fallas." % n)
    return True


def main():
    a = sys.argv[1:]
    if not a or a[0] != "--autotest":
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(0 if autotest() else 1)


if __name__ == "__main__":
    main()
