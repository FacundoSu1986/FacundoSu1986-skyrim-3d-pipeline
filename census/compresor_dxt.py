# -*- coding: utf-8 -*-
"""Comprime y descomprime bloques DXT1 (BC1) y DXT5 (BC3). Necesita numpy.

    python compresor_dxt.py --autotest
    python compresor_dxt.py --censo <carpeta textures> [--maximo N]

POR QUE HACE FALTA
------------------
El 68,8 % del corpus vanilla es DXT1 o DXT5, y los 12.075 `_n` son DXT5 sin
excepcion (census/hallazgos_texturas.md). `escritor_dds.py` escribia solo sin
comprimir: valido --el 31,2 % del corpus lo es-- pero un `_n` de 2048 pesa
22 MB sin comprimir y 5,6 MB en DXT5.

EL ALGORITMO
------------
Por bloque de 4x4, vectorizado sobre todos los bloques:

  color  eje principal de los 16 colores (iteracion de potencia sobre la
         covarianza); extremos = los dos pixeles que mas lejos caen sobre ese
         eje; despues dos pasadas de minimos cuadrados sobre los extremos,
         que se quedan solo si bajan el error REAL, medido con la paleta
         cuantizada a 565 tal como la arma el decodificador.
  alfa   extremos = maximo y minimo del bloque, modo de 8 valores. Un bloque
         de alfa constante sale con alpha0 == alpha1: es exactamente lo que
         `mascara_especular.py` lee como "bloque constante", asi que la
         mascara medida antes y despues de comprimir cuenta igual los bloques
         en blanco.

El color de DXT1 se escribe siempre con color0 > color1 (modo de 4 colores).
En el otro modo el indice 3 es NEGRO TRANSPARENTE: un DXT1 opaco que cae ahi
por accidente se agujerea. Con color0 == color1 todos los indices son 0.

EL DECODIFICADOR, Y CONTRA QUE SE MIDE
--------------------------------------
Usa la convencion de Pillow: los colores intermedios con division entera
((2a+b)//3, (a+b)//2, (6a+b)//7...). Otros decodificadores --y la GPU--
redondean distinto y difieren en 1 nivel. `--censo` compara este
decodificador con el de Pillow sobre el corpus vanilla, pixel por pixel, y el
error del compresor contra el del compresor de Pillow sobre las mismas
imagenes. Pillow no es dependencia del repo: es el oraculo de los tests.
"""
import os
import struct
import sys

import numpy as np

BYTES_POR_BLOQUE = {"DXT1": 8, "DXT5": 16}

# Bloques por tanda: el error de cada candidato es (tanda, 16, 4, 3) floats.
_TANDA = 8192


# ---------------------------------------------------------------------------
# bloques
# ---------------------------------------------------------------------------

def a_bloques(pixeles, ancho, alto):
    """RGBA (bytes, ancho*alto*4) -> (N, 16, 4) uint8, fila por fila.

    Un lado que no es multiplo de 4 (los mipmaps de 2x2 y 1x1) se completa
    repitiendo el borde: el decodificador solo usa la parte que existe, y
    repetir no agrega colores que muevan los extremos.
    """
    img = np.frombuffer(bytes(pixeles), np.uint8).reshape(alto, ancho, 4)
    ph, pw = -(-alto // 4) * 4, -(-ancho // 4) * 4
    if (ph, pw) != (alto, ancho):
        img = np.pad(img, ((0, ph - alto), (0, pw - ancho), (0, 0)),
                     mode="edge")
    return (img.reshape(ph // 4, 4, pw // 4, 4, 4)
               .transpose(0, 2, 1, 3, 4).reshape(-1, 16, 4))


def de_bloques(bloques, ancho, alto):
    """Inverso de a_bloques: (N, 16, 4) -> RGBA bytes, recortado."""
    ph, pw = -(-alto // 4) * 4, -(-ancho // 4) * 4
    img = (bloques.reshape(ph // 4, pw // 4, 4, 4, 4)
                  .transpose(0, 2, 1, 3, 4).reshape(ph, pw, 4))
    return np.ascontiguousarray(img[:alto, :ancho]).tobytes()


# ---------------------------------------------------------------------------
# 565
# ---------------------------------------------------------------------------

def a_565(c):
    """(..., 3) en 0..255 -> uint16 565, al nivel mas cercano."""
    c = np.clip(np.asarray(c, np.float64), 0.0, 255.0)
    r = np.rint(c[..., 0] * 31.0 / 255.0).astype(np.uint16)
    g = np.rint(c[..., 1] * 63.0 / 255.0).astype(np.uint16)
    b = np.rint(c[..., 2] * 31.0 / 255.0).astype(np.uint16)
    return (r << 11) | (g << 5) | b


def de_565(v):
    """uint16 565 -> (..., 3) int32 en 0..255, como lo expande el hardware."""
    v = np.asarray(v, np.int32)
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return np.stack(((r << 3) | (r >> 2), (g << 2) | (g >> 4),
                     (b << 3) | (b >> 2)), axis=-1)


def paleta_color(c0, c1, cuatro=None):
    """(N, 4, 3) int32. `cuatro` (N,) bool: modo de 4 colores; si es None,
    se decide como DXT1: c0 > c1."""
    p0, p1 = de_565(c0), de_565(c1)
    if cuatro is None:
        cuatro = np.asarray(c0) > np.asarray(c1)
    cuatro = np.broadcast_to(np.asarray(cuatro), p0.shape[:1])[:, None]
    p2 = np.where(cuatro, (2 * p0 + p1) // 3, (p0 + p1) // 2)
    p3 = np.where(cuatro, (p0 + 2 * p1) // 3, 0)
    return np.stack((p0, p1, p2, p3), axis=1)


def _indices(px, pal):
    """(indices (N,16), error (N,)) del color mas cercano de la paleta."""
    d = ((px[:, :, None, :] - pal[:, None, :, :].astype(np.float32)) ** 2
         ).sum(-1)
    idx = d.argmin(-1)
    return idx, np.take_along_axis(d, idx[..., None], -1)[..., 0].sum(-1)


# ---------------------------------------------------------------------------
# compresion del color
# ---------------------------------------------------------------------------

def _eje(px):
    """Eje principal de cada bloque, (N, 3). Un bloque plano da (1,1,1)."""
    cen = px - px.mean(1, keepdims=True)
    cov = np.einsum("nki,nkj->nij", cen, cen)
    v = np.ones((px.shape[0], 3), np.float32)
    for _ in range(8):
        v = np.einsum("nij,nj->ni", cov, v)
        n = np.linalg.norm(v, axis=1, keepdims=True)
        v = np.where(n > 1e-6, v / np.maximum(n, 1e-6), 0.57735)
    return v, cen


def _extremos_eje(px):
    v, cen = _eje(px)
    t = np.einsum("nki,ni->nk", cen, v)
    filas = np.arange(px.shape[0])
    return px[filas, t.argmax(1)], px[filas, t.argmin(1)]


# peso de color0 para cada indice del modo de 4 colores
_PESO_C0 = np.array([1.0, 0.0, 2.0 / 3.0, 1.0 / 3.0], np.float32)


def _refinar(px, idx):
    """Extremos por minimos cuadrados, dados los indices."""
    w = _PESO_C0[idx]                                   # (N, 16)
    u = 1.0 - w
    a, b, c = (w * w).sum(1), (w * u).sum(1), (u * u).sum(1)
    r0 = np.einsum("nk,nki->ni", w, px)
    r1 = np.einsum("nk,nki->ni", u, px)
    det = a * c - b * b
    ok = np.abs(det) > 1e-6
    det = np.where(ok, det, 1.0)[:, None]
    c0 = (c[:, None] * r0 - b[:, None] * r1) / det
    c1 = (a[:, None] * r1 - b[:, None] * r0) / det
    return np.clip(c0, 0, 255), np.clip(c1, 0, 255), ok


def _color_tanda(px):
    """px (N, 16, 3) float32 -> (c0, c1, idx) con c0 >= c1 y modo 4."""
    alto_, bajo_ = _extremos_eje(px)
    c0, c1 = a_565(alto_), a_565(bajo_)
    idx, err = _indices(px, paleta_color(c0, c1, cuatro=True))
    for _ in range(2):
        f0, f1, ok = _refinar(px, idx)
        n0, n1 = a_565(f0), a_565(f1)
        nidx, nerr = _indices(px, paleta_color(n0, n1, cuatro=True))
        mejor = ok & (nerr < err)
        c0 = np.where(mejor, n0, c0)
        c1 = np.where(mejor, n1, c1)
        idx = np.where(mejor[:, None], nidx, idx)
        err = np.where(mejor, nerr, err)
    # color0 > color1 obligatorio: si no, el indice 3 es negro transparente.
    # Invertir los extremos invierte la paleta: 0<->1 y 2<->3, o sea idx ^ 1.
    invertir = c0 < c1
    c0, c1 = np.where(invertir, c1, c0), np.where(invertir, c0, c1)
    idx = np.where(invertir[:, None], idx ^ 1, idx)
    # Con c0 == c1 los cuatro colores de la paleta son iguales y argmin, ante
    # el empate, devuelve el primero: los indices ya son todos 0, y el indice
    # 3 --negro transparente en ese modo-- no aparece.
    return c0.astype(np.uint16), c1.astype(np.uint16), idx


def _empaquetar_indices(idx, bits):
    """(N, 16) -> (N,) uint64 con el indice k en los bits k*bits."""
    corr = (np.arange(16, dtype=np.uint64) * np.uint64(bits))
    return (idx.astype(np.uint64) << corr).sum(1, dtype=np.uint64)


def _bloque_color(px):
    """(N, 16, 3) -> (N, 8) uint8 de BC1."""
    c0, c1, idx = _color_tanda(px.astype(np.float32))
    out = np.empty((px.shape[0], 8), np.uint8)
    out[:, 0:2] = c0.astype("<u2").view(np.uint8).reshape(-1, 2)
    out[:, 2:4] = c1.astype("<u2").view(np.uint8).reshape(-1, 2)
    bits = _empaquetar_indices(idx, 2).astype("<u4")
    out[:, 4:8] = bits.view(np.uint8).reshape(-1, 4)
    return out


# ---------------------------------------------------------------------------
# compresion del alfa (BC3)
# ---------------------------------------------------------------------------

def paleta_alfa(a0, a1):
    """(N, 8) int32 de BC3, con la division entera de Pillow."""
    a0 = np.asarray(a0, np.int32)[:, None]
    a1 = np.asarray(a1, np.int32)[:, None]
    k = np.arange(1, 7, dtype=np.int32)[None, :]
    ocho = ((7 - k) * a0 + k * a1) // 7
    # modo de 6 valores (a0 <= a1): 4 intermedios, despues 0 y 255. El
    # compresor no lo usa; el decodificador lo necesita para el corpus.
    k5 = np.arange(1, 5, dtype=np.int32)[None, :]
    seis = np.concatenate((((5 - k5) * a0 + k5 * a1) // 5,
                           np.zeros_like(a0), np.full_like(a0, 255)), axis=1)
    intermedios = np.where(a0 > a1, ocho, seis)
    return np.concatenate((a0, a1, intermedios), axis=1)


def _bloque_alfa(a):
    """(N, 16) uint8 -> (N, 8) uint8 de BC3."""
    a = a.astype(np.int32)
    a0, a1 = a.max(1), a.min(1)
    pal = paleta_alfa(a0, a1)
    # Alfa constante: los ocho valores de la paleta son a0 y argmin devuelve
    # el indice 0. a0 > a1 en todo bloque variable: modo de 8 valores.
    idx = np.abs(a[:, :, None] - pal[:, None, :]).argmin(-1)
    out = np.empty((a.shape[0], 8), np.uint8)
    out[:, 0] = a0
    out[:, 1] = a1
    bits = _empaquetar_indices(idx, 3).astype("<u8")
    out[:, 2:8] = bits.view(np.uint8).reshape(-1, 8)[:, :6]
    return out


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def comprimir(pixeles, ancho, alto, formato):
    """RGBA bytes -> bytes del nivel en DXT1 o DXT5."""
    if formato not in BYTES_POR_BLOQUE:
        raise ValueError("formato %r: se admite DXT1 o DXT5" % (formato,))
    if len(pixeles) != ancho * alto * 4:
        raise ValueError("pixeles: %d bytes, se esperaban %d (%dx%d RGBA)"
                         % (len(pixeles), ancho * alto * 4, ancho, alto))
    bl = a_bloques(pixeles, ancho, alto)
    partes = []
    for i in range(0, bl.shape[0], _TANDA):
        t = bl[i:i + _TANDA]
        color = _bloque_color(t[:, :, :3])
        partes.append(color if formato == "DXT1" else
                      np.concatenate((_bloque_alfa(t[:, :, 3]), color), 1))
    return np.concatenate(partes).tobytes()


def _desempaquetar(bits, n_bits):
    corr = np.arange(16, dtype=np.uint64) * np.uint64(n_bits)
    return ((bits[:, None] >> corr) & np.uint64((1 << n_bits) - 1)
            ).astype(np.int64)


def descomprimir(datos, ancho, alto, formato):
    """bytes de un nivel DXT1/DXT5 -> RGBA bytes (convencion de Pillow)."""
    bpb = BYTES_POR_BLOQUE[formato]
    n = (-(-ancho // 4)) * (-(-alto // 4))
    crudo = np.frombuffer(bytes(datos[:n * bpb]), np.uint8)
    if crudo.size != n * bpb:
        raise ValueError("faltan bytes: %d de %d" % (crudo.size, n * bpb))
    crudo = crudo.reshape(n, bpb)
    color = crudo[:, bpb - 8:]
    c0 = color[:, 0:2].copy().view("<u2")[:, 0]
    c1 = color[:, 2:4].copy().view("<u2")[:, 0]
    idx = _desempaquetar(color[:, 4:8].copy().view("<u4")[:, 0]
                         .astype(np.uint64), 2)
    cuatro = (c0 > c1) if formato == "DXT1" else np.ones(n, bool)
    pal = paleta_color(c0, c1, cuatro)
    rgb = np.take_along_axis(pal, idx[:, :, None], 1)
    if formato == "DXT1":
        alfa = np.where((~cuatro)[:, None] & (idx == 3), 0, 255)
    else:
        a = crudo[:, :8]
        bits = np.zeros((n, 8), np.uint8)
        bits[:, :6] = a[:, 2:8]
        aidx = _desempaquetar(bits.view("<u8")[:, 0], 3)
        alfa = np.take_along_axis(paleta_alfa(a[:, 0], a[:, 1]), aidx, 1)
    bl = np.concatenate((rgb, alfa[:, :, None]), 2).astype(np.uint8)
    return de_bloques(bl, ancho, alto)


def error_rms(a, b):
    """RMS por canal (R, G, B, A) entre dos RGBA del mismo tamano."""
    x = np.frombuffer(bytes(a), np.uint8).reshape(-1, 4).astype(np.float64)
    y = np.frombuffer(bytes(b), np.uint8).reshape(-1, 4).astype(np.float64)
    return tuple(float(v) for v in np.sqrt(((x - y) ** 2).mean(0)))


# ---------------------------------------------------------------------------
# autotest
# ---------------------------------------------------------------------------

def _ruido(w, h, semilla):
    rng = np.random.default_rng(semilla)
    return rng.integers(0, 256, (h, w, 4), dtype=np.uint8).tobytes()


def _degradado(w, h):
    y, x = np.mgrid[0:h, 0:w]
    img = np.stack((x * 255 // max(1, w - 1), y * 255 // max(1, h - 1),
                    (x + y) * 255 // max(1, w + h - 2),
                    255 - x * 255 // max(1, w - 1)), -1).astype(np.uint8)
    return img.tobytes()


def _pillow_decodifica(datos, ancho, alto, formato):
    """El decodificador de Pillow, o None si Pillow no esta."""
    try:
        import io
        from PIL import Image
    except ImportError:
        return None
    cab = bytearray(128)
    cab[0:4] = b"DDS "
    struct.pack_into("<IIIII", cab, 4, 124, 0x81007, alto, ancho, len(datos))
    struct.pack_into("<II", cab, 76, 32, 0x4)
    cab[84:88] = formato.encode("ascii")
    struct.pack_into("<I", cab, 108, 0x1000)
    im = Image.open(io.BytesIO(bytes(cab) + bytes(datos)))
    return im.convert("RGBA").tobytes()


def autotest():
    """Cero comprobaciones NO es exito."""
    print("SUITE DE FALSIFICACION - compresor_dxt")
    print("")
    n = fallos = 0

    def ok(cond, texto):
        nonlocal n, fallos
        n += 1
        fallos += 0 if cond else 1
        print("  %-5s %s" % ("ok" if cond else "FALLA", texto))

    # a. un color que 565 representa exacto vuelve exacto, en los dos formatos
    for fmt in ("DXT1", "DXT5"):
        col = de_565(np.array([a_565([200, 120, 40])]))[0]
        pix = bytes((int(col[0]), int(col[1]), int(col[2]), 255)) * 64
        vuelta = descomprimir(comprimir(pix, 8, 8, fmt), 8, 8, fmt)
        ok(vuelta == pix, "%s: color plano representable vuelve exacto" % fmt)

    # b. dos colores representables en un bloque vuelven exactos
    c = de_565(a_565(np.array([[250, 10, 30], [8, 200, 90]])))
    pix = b"".join(bytes((int(c[k % 2][0]), int(c[k % 2][1]),
                          int(c[k % 2][2]), 255)) for k in range(16))
    vuelta = descomprimir(comprimir(pix, 4, 4, "DXT1"), 4, 4, "DXT1")
    ok(vuelta == pix, "DXT1: bloque de dos colores representables, exacto")

    # c. DXT1 opaco nunca cae en el modo de 3 colores con indice 3
    datos = comprimir(_ruido(64, 64, 1), 64, 64, "DXT1")
    bl = np.frombuffer(datos, np.uint8).reshape(-1, 8)
    c0 = bl[:, 0:2].copy().view("<u2")[:, 0]
    c1 = bl[:, 2:4].copy().view("<u2")[:, 0]
    idx = _desempaquetar(bl[:, 4:8].copy().view("<u4")[:, 0]
                         .astype(np.uint64), 2)
    malos = int(((c0 <= c1)[:, None] & (idx == 3)).any(1).sum())
    ok(malos == 0 and bool((c0 >= c1).all()),
       "DXT1: 256 bloques de ruido, %d con negro transparente" % malos)
    vuelta = descomprimir(datos, 64, 64, "DXT1")
    ok(set(vuelta[3::4]) == {255}, "DXT1: el alfa decodificado es 255 en "
       "todos los texeles")

    # d. alfa constante -> alpha0 == alpha1 (la semantica de
    #    mascara_especular), y alfa variable -> alpha0 != alpha1
    con_alfa = bytearray(_degradado(16, 16))
    for i in range(16 * 4):                 # la primera fila de bloques...
        y, x = divmod(i, 16)
        con_alfa[(y * 16 + x) * 4 + 3] = 255  # ...alfa 255 constante
    datos = comprimir(bytes(con_alfa), 16, 16, "DXT5")
    bl = np.frombuffer(datos, np.uint8).reshape(-1, 16)
    ok(bool((bl[:4, 0] == 255).all() and (bl[:4, 1] == 255).all()),
       "DXT5: los 4 bloques de alfa 255 constante salen con a0 == a1 == 255")
    ok(bool((bl[4:, 0] != bl[4:, 1]).all()),
       "DXT5: los 12 bloques de alfa variable salen con a0 != a1")

    # e. el error sobre un degradado queda chico, y el ruido no revienta
    for fmt, tope in (("DXT1", 4.0), ("DXT5", 4.0)):
        pix = _degradado(64, 64)
        e = error_rms(pix, descomprimir(comprimir(pix, 64, 64, fmt),
                                        64, 64, fmt))
        rgb = max(e[:3])
        ok(rgb < tope, "%s: degradado 64x64, RMS RGB maximo %.2f < %.1f"
           % (fmt, rgb, tope))
    pix = _degradado(64, 64)
    e = error_rms(pix, descomprimir(comprimir(pix, 64, 64, "DXT5"), 64, 64,
                                    "DXT5"))
    ok(e[3] < 2.0, "DXT5: alfa del degradado, RMS %.2f < 2" % e[3])

    # f. tamanos que no son multiplo de 4 (mipmaps de 2x2 y 1x1)
    for w, h in ((2, 2), (1, 1), (4, 1), (8, 2)):
        pix = _ruido(w, h, w * 10 + h)
        for fmt in ("DXT1", "DXT5"):
            datos = comprimir(pix, w, h, fmt)
            esperado = max(1, -(-w // 4)) * max(1, -(-h // 4)) \
                * BYTES_POR_BLOQUE[fmt]
            vuelta = descomprimir(datos, w, h, fmt)
            ok(len(datos) == esperado and len(vuelta) == w * h * 4,
               "%s %dx%d: %d bytes comprimidos, %d decodificados"
               % (fmt, w, h, len(datos), len(vuelta)))

    # g. contra Pillow: su decodificador lee lo mismo que el nuestro, y
    #    nuestro error no es peor que el de su compresor
    try:
        import io
        from PIL import Image
        hay_pillow = True
    except ImportError:
        hay_pillow = False
    if not hay_pillow:
        print("  --    Pillow no esta: se saltean las comparaciones con el "
              "oraculo (no cuentan como comprobadas)")
    else:
        for fmt in ("DXT1", "DXT5"):
            for nombre, pix in (("ruido", _ruido(64, 64, 7)),
                                ("degradado", _degradado(64, 64))):
                datos = comprimir(pix, 64, 64, fmt)
                ok(_pillow_decodifica(datos, 64, 64, fmt) ==
                   descomprimir(datos, 64, 64, fmt),
                   "%s %s: Pillow decodifica lo mismo, byte a byte"
                   % (fmt, nombre))
                im = Image.frombytes("RGBA", (64, 64), pix)
                if fmt == "DXT1":
                    im = im.convert("RGB")
                buf = io.BytesIO()
                im.save(buf, "DDS", pixel_format=fmt)
                suyo = buf.getvalue()[128:]
                canales = 4 if fmt == "DXT5" else 3
                m1 = float(np.mean(error_rms(
                    pix, descomprimir(datos, 64, 64, fmt))[:canales]))
                m2 = float(np.mean(error_rms(
                    pix, descomprimir(suyo, 64, 64, fmt))[:canales]))
                ok(m1 <= m2 * 1.02, "%s %s: RMS %.2f, Pillow %.2f"
                   % (fmt, nombre, m1, m2))

    print("")
    if n == 0:
        print("  NO se comprobo NADA.")
        return False
    if fallos:
        print("  %d FALLAS de %d." % (fallos, n))
        return False
    print("  %d comprobaciones, sin fallas." % n)
    return True


# ---------------------------------------------------------------------------
# censo: contra el corpus vanilla
# ---------------------------------------------------------------------------

def censo(raiz, maximo=400):
    """Sobre DDS DXT1/DXT5 del corpus: (1) este decodificador contra el de
    Pillow, byte a byte; (2) recomprimir lo decodificado, con este compresor y
    con el de Pillow, y comparar el error. Solo el nivel 0."""
    import io
    import parser_dds
    from PIL import Image
    rutas = []
    for base, _, archivos in os.walk(raiz):
        for f in sorted(archivos):
            if f.lower().endswith(".dds"):
                rutas.append(os.path.join(base, f))
    rutas.sort()
    paso = max(1, len(rutas) // (maximo * 4))
    n = iguales = 0
    errores = {"DXT1": [], "DXT5": []}
    for ruta in rutas[::paso]:
        try:
            d = parser_dds.leer(ruta)
        except Exception:
            continue
        fmt = d["formato"]
        if fmt not in BYTES_POR_BLOQUE or d["cubemap"] or not d["tamano_cuadra"]:
            continue
        w, h = d["ancho"], d["alto"]
        if w * h > 1024 * 1024:
            continue
        with open(ruta, "rb") as fh:
            fh.seek(128)
            datos = fh.read((-(-w // 4)) * (-(-h // 4)) * BYTES_POR_BLOQUE[fmt])
        nuestro = descomprimir(datos, w, h, fmt)
        suyo = Image.open(ruta).convert("RGBA").tobytes()
        n += 1
        iguales += nuestro == suyo
        re_n = descomprimir(comprimir(nuestro, w, h, fmt), w, h, fmt)
        im = Image.frombytes("RGBA", (w, h), nuestro)
        if fmt == "DXT1":
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "DDS", pixel_format=fmt)
        re_p = descomprimir(buf.getvalue()[128:], w, h, fmt)
        canales = 4 if fmt == "DXT5" else 3
        errores[fmt].append(
            (float(np.mean(error_rms(nuestro, re_n)[:canales])),
             float(np.mean(error_rms(nuestro, re_p)[:canales]))))
        if n >= maximo:
            break
    print("CENSO compresor_dxt sobre %s" % raiz)
    print("  %d texturas DXT1/DXT5 (nivel 0, hasta 1024x1024)" % n)
    print("  decodificador igual a Pillow byte a byte: %d de %d"
          % (iguales, n))
    for fmt, lista in errores.items():
        if not lista:
            continue
        a = np.array(lista)
        mejor = int((a[:, 0] <= a[:, 1]).sum())
        print("  %s  N=%d  RMS recomprimiendo: mediana %.2f (Pillow %.2f), "
              "p90 %.2f (Pillow %.2f); igual o mejor que Pillow en %d"
              % (fmt, len(a), np.median(a[:, 0]), np.median(a[:, 1]),
                 np.percentile(a[:, 0], 90), np.percentile(a[:, 1], 90),
                 mejor))
    if n == 0:
        print("  NO se comprobo NADA.")
        return False
    return iguales == n


def main(argv):
    if argv == ["--autotest"]:
        return 0 if autotest() else 1
    if len(argv) >= 2 and argv[0] == "--censo":
        maximo = int(argv[3]) if len(argv) == 4 and argv[2] == "--maximo" \
            else 400
        return 0 if censo(argv[1], maximo) else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
