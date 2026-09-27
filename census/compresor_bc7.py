# -*- coding: utf-8 -*-
"""Comprime y descomprime bloques BC7 (modos 5 y 6). Necesita numpy.

    python compresor_bc7.py --autotest

POR QUE HACE FALTA
------------------
SE admite BC7 aunque Bethesda no lo haya usado: de las 32.241 texturas del
corpus vanilla, BC7 es 0 (census/hallazgos_texturas.md), y
references/limites-skyrim.md recomienda BC7 para contenido nuevo --sRGB para
difuso, lineal para normales y mascara-- contra los DXT1/DXT5 que Bethesda
eligio. `pipeline/manifest.py` lo expone como `compresion="bc7"`: sin pedirlo,
nada cambio.

BC7 mide 16 bytes por bloque de 4x4 = 8 bpp, lo mismo que DXT5 y el doble que
DXT1. La ganancia no es de peso: es precision (endpoints de 7-8 bits contra
los 16 bits de un 565, y paletas de hasta 16 colores contra 4).

QUE CODIFICA ESTE ARCHIVO: LOS MODOS 5 Y 6
-------------------------------------------
BC7 tiene ocho modos; los modos 0-3 y 7 necesitan la tabla de particiones del
espec (64 entradas por subconjunto), y el modo 4 agrega un selector de indice
por bloque. Los modos 5 y 6 son los dos que no necesitan nada de eso --un
subconjunto, sin rotacion obligatoria, sin particiones-- y entre los dos
cubren los dos casos que interesan (layout de los modos segun
learn.microsoft.com, "BC7 Format Mode Reference", verificado bloque a bloque
contra el decodificador de Pillow):

  modo 6  RGBAP 7.7.7.7.1: un p-bit por endpoint compartido por sus cuatro
          componentes, 16 indices de 4 bits; color y alfa comparten el indice.
  modo 5  RGB 7.7.7 (expansion a 8 bits replicando el MSB: (v<<1)|(v>>6)) y
          alfa 8 bits EXACTO, en dos planos de indices de 2 bits (4 colores y
          4 alfas), con rotacion 0 (el alfa va donde va el alfa).

Se codifica cada bloque en los DOS modos y se queda el de menor error cuadratico
(empate: modo 6). Los otros modos quedan fuera por una decision, no por un
olvido: agregarlos es agregar la tabla de particiones y con ella una pieza que
tendria que falsificarse aparte.

LA MASCARA ESPECULAR MANDA
---------------------------
El alfa de un `_n` ES la mascara especular (`mascara_especular.py`). Un bloque
cuyo alfa es constante tiene que volver con ESE alfa, no uno cerca: si no, un
bloque en blanco deja de contar como blanco despues de comprimir. Se garantiza
igual que en DXT5 (`compresor_dxt.py`, el alfa de BC3): en el modo 6, si las
16 alfas del bloque valen A, los dos p-bits se fuerzan a A & 1, lo que
representa A exacto en los 16 indices; en el modo 5 el alfa es 8 bits sin
p-bit, y a0 == a1 == A cae solo. Costo: los componentes de color del endpoint
quedan en la reticula de esa paridad (error a lo sumo 1 nivel por componente,
la misma reticula que el p-bit ya impone).

EL DECODIFICADOR, Y CONTRA QUE SE MIDE
--------------------------------------
Este decodificador NO esta escrito de memoria: cada layout (orden de campos,
pesos de interpolacion, anclas, rotacion, expansion 7->8) se determino
bloque a bloque decodificando con Pillow 12.3 y con texture2ddecoder, y los
tests lo fijan con literales. `tests/test_compresor_bc7.py` exige que la
salida del compresor decodificada por Pillow salga BYTE A BYTE igual que la
del decodificador de aca, que los errores de las imagenes de prueba bajen
frente a DXT5, y que el autotest de este archivo pase. Pillow no es
dependencia del repo: es el oraculo de los tests.
"""
import os
import sys

import numpy as np

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

from compresor_dxt import a_bloques, de_bloques, error_rms  # noqa: E402

BYTES_POR_BLOQUE = 16

# Pesos de interpolacion, en 64os, del spec de BC7: 16 para indices de 4 bits
# (modo 6), 4 para indices de 2 bits (modo 5). Son la paleta que arma el
# decodificador: pal[k] = ((64 - w) * e0 + w * e1 + 32) >> 6, que es tambien
# la cuenta que hace el hardware.
_PESOS4 = np.array([0, 4, 9, 13, 17, 21, 26, 30,
                    34, 38, 43, 47, 51, 55, 60, 64], np.int32)
_PESOS2 = np.array([0, 21, 43, 64], np.int32)

# Bloques por tanda: el error de cada candidato es (tanda, 16, 16, 4) floats.
_TANDA = 8192


# ---------------------------------------------------------------------------
# cuantizacion
# ---------------------------------------------------------------------------
def _exp8_m5(v7):
    """7 bits -> 8 replicando el MSB, como el decodificador del modo 5:
    (v << 1) | (v >> 6). Verificado con Pillow: 63 -> 126, 100 -> 201."""
    v7 = np.asarray(v7, np.int32)
    return (v7 << 1) | (v7 >> 6)


def _a_7bits(x):
    """(..., 3) float 0..255 -> (..., 3) int 0..127 con _exp8_m5 lo mas
    cerca posible de x."""
    x = np.clip(np.asarray(x, np.float64), 0.0, 255.0)
    j = np.clip(np.rint(x / 2.0), 0, 127).astype(np.int32)
    mejor, err = j, np.abs(_exp8_m5(j) - x)
    for delta in (-1, 1):
        c = np.clip(j + delta, 0, 127)
        e = np.abs(_exp8_m5(c) - x)
        tomar = e < err
        mejor, err = np.where(tomar, c, mejor), np.where(tomar, e, err)
    return mejor


def _a_7bits_con_p(x, p):
    """(..., 4) float, (...) int 0/1 -> j tal que (j << 1) | p queda lo mas
    cerca de x. El p-bit es por endpoint: los cuatro componentes comparten
    la paridad."""
    x = np.clip(np.asarray(x, np.float64), 0.0, 255.0)
    return np.clip(np.rint((x - p[..., None]) / 2.0), 0, 127).astype(np.int32)


def _elegir_p(x):
    """(..., 4) float -> (j, p): el p-bit por endpoint que minimiza el error
    de sus cuatro componentes. Empate: p = 0 (determinista)."""
    x = np.asarray(x, np.float64)
    j0 = np.clip(np.rint(x / 2.0), 0, 127)
    j1 = np.clip(np.rint((x - 1.0) / 2.0), 0, 127)
    e0 = ((2 * j0 - x) ** 2).sum(-1)
    e1 = ((2 * j1 + 1.0 - x) ** 2).sum(-1)
    p = (e1 < e0).astype(np.int32)
    j = np.where((p == 1)[..., None], j1, j0).astype(np.int32)
    return j, p


# ---------------------------------------------------------------------------
# paletas e indices
# ---------------------------------------------------------------------------
def _paleta(e0, e1, pesos):
    """(N, K) endpoints int -> (N, len(pesos), K) con la interpolacion exacta
    del decodificador (redondeo +32 y division por 64)."""
    w = np.asarray(pesos, np.int32)
    return (((64 - w)[None, :, None] * e0[:, None, :]
             + w[None, :, None] * e1[:, None, :] + 32) >> 6)


def _indices(px, pal):
    """(indices (N, 16), error (N,)) del elemento de paleta mas cercano.
    Mismo calculo que compresor_dxt._indices, aca para no acoplar los dos."""
    d = ((px[:, :, None, :] - pal[:, None, :, :].astype(np.float32)) ** 2
         ).sum(-1)
    idx = d.argmin(-1)
    return idx, np.take_along_axis(d, idx[..., None], -1)[..., 0].sum(-1)


def _eje(px):
    """Eje principal de cada bloque, (N, C). Iteracion de potencia sobre la
    covarianza, como compresor_dxt._eje pero para C canales (3 o 4)."""
    cen = px - px.mean(1, keepdims=True)
    cov = np.einsum("nki,nkj->nij", cen, cen)
    v = np.ones((px.shape[0], px.shape[2]), np.float32)
    for _ in range(8):
        v = np.einsum("nij,nj->ni", cov, v)
        n = np.linalg.norm(v, axis=1, keepdims=True)
        v = np.where(n > 1e-6, v / np.maximum(n, 1e-6),
                     1.0 / np.sqrt(px.shape[2]))
    return v, cen


def _extremos(px):
    """Los dos pixeles que mas lejos caen sobre el eje principal."""
    v, cen = _eje(px)
    t = np.einsum("nki,ni->nk", cen, v)
    filas = np.arange(px.shape[0])
    return px[filas, t.argmax(1)], px[filas, t.argmin(1)]


def _refinar(px, w0, w1):
    """(e0, e1, valido) por minimos cuadrados, dados los pesos de cada
    texel para cada endpoint. w0 + w1 = 1 por construccion."""
    a = (w0 * w0).sum(1)
    b = (w0 * w1).sum(1)
    c = (w1 * w1).sum(1)
    r0 = np.einsum("nk,nki->ni", w0, px)
    r1 = np.einsum("nk,nki->ni", w1, px)
    det = a * c - b * b
    ok = np.abs(det) > 1e-6
    det = np.where(ok, det, 1.0)[:, None]
    e0 = (c[:, None] * r0 - b[:, None] * r1) / det
    e1 = (a[:, None] * r1 - b[:, None] * r0) / det
    return np.clip(e0, 0, 255), np.clip(e1, 0, 255), ok


# ---------------------------------------------------------------------------
# modo 6: RGBAP 7.7.7.7.1, 16 indices de 4 bits
# ---------------------------------------------------------------------------
def _m6_cuantiza(e0f, e1f, constante, alfa):
    """Endpoints float -> (j0, p0, j1, p1). Si el alfa del bloque es
    constante A, los dos p-bits se fuerzan a A & 1: (j << 1) | (A & 1)
    representa A exacto, y el alfa de la mascara no se mueve."""
    j0, p0 = _elegir_p(e0f)
    j1, p1 = _elegir_p(e1f)
    if constante is not None:
        fuerzo = (alfa.astype(np.int32) & 1).astype(np.int32)
        p0 = np.where(constante, fuerzo, p0)
        p1 = np.where(constante, fuerzo, p1)
        j0 = _a_7bits_con_p(e0f, p0)
        j1 = _a_7bits_con_p(e1f, p1)
    return j0, p0, j1, p1


def _m6_paleta(j0, p0, j1, p1):
    e0 = (j0 << 1) | p0[:, None]
    e1 = (j1 << 1) | p1[:, None]
    return _paleta(e0, e1, _PESOS4)


def _bloque_m6(px, alfa, constante):
    """(N, 16, 4) float32 -> (j0, p0, j1, p1, indices, error)."""
    e0f, e1f = _extremos(px)
    j0, p0, j1, p1 = _m6_cuantiza(e0f, e1f, constante, alfa)
    idx, err = _indices(px, _m6_paleta(j0, p0, j1, p1))
    for _ in range(2):
        w = _PESOS4[idx].astype(np.float32) / 64.0
        f0, f1, ok = _refinar(px, 1.0 - w, w)
        nj0, np0, nj1, np1 = _m6_cuantiza(f0, f1, constante, alfa)
        nidx, nerr = _indices(px, _m6_paleta(nj0, np0, nj1, np1))
        mejor = ok & (nerr < err)
        j0 = np.where(mejor[:, None], nj0, j0)
        j1 = np.where(mejor[:, None], nj1, j1)
        p0 = np.where(mejor, np0, p0)
        p1 = np.where(mejor, np1, p1)
        idx = np.where(mejor[:, None], nidx, idx)
        err = np.where(mejor, nerr, err)
    # La ancla (texel 0) se guarda con UN bit menos: si su indice tiene el
    # bit alto en 1, se invierten los endpoints y todos los indices (k ->
    # 15 - k). Los pesos son simetricos (w[k] + w[15 - k] = 64), asi que la
    # paleta invertida es la misma paleta y el error no cambia.
    voltereo = idx[:, 0] >= 8
    j0, j1 = np.where(voltereo[:, None], j1, j0), np.where(voltereo[:, None],
                                                           j0, j1)
    p0, p1 = np.where(voltereo, p1, p0), np.where(voltereo, p0, p1)
    idx = np.where(voltereo[:, None], 15 - idx, idx)
    return j0, p0, j1, p1, idx, err


def _empaqueta_m6(j0, p0, j1, p1, idx):
    """Campos -> (bajos, altos) uint64 del bloque. Layout, en bits desde el
    menos significativo: modo 7 (0b1000000), R0 R1 G0 G1 B0 B1 A0 A1 de 7
    bits, p0, p1, indice del texel 0 de 3 bits, los otros 15 de 4."""
    n = j0.shape[0]
    campos = np.stack((j0[:, 0], j1[:, 0], j0[:, 1], j1[:, 1],
                       j0[:, 2], j1[:, 2], j0[:, 3], j1[:, 3]), 1)
    bajos = (np.full(n, 64, np.uint64)
             + (campos.astype(np.uint64)
                << (np.arange(8, dtype=np.uint64) * 7 + 7)).sum(1)
             + (p0.astype(np.uint64) << np.uint64(63)))
    despl = np.arange(16, dtype=np.uint64) * 4
    despl[0] = 1
    altos = (p1.astype(np.uint64)
             + (idx.astype(np.uint64) << despl).sum(1))
    return bajos, altos


# ---------------------------------------------------------------------------
# modo 5: RGB 7.7.7 + alfa 8 bits, dos planos de indices de 2 bits
# ---------------------------------------------------------------------------
def _bloque_m5(px):
    """(N, 16, 4) float32 -> (j0, j1, a0, a1, ci, ai, error)."""
    rgb, al = px[:, :, :3], px[:, :, 3:]
    c0f, c1f = _extremos(rgb)
    a0f, a1f = _extremos(al)
    j0, j1 = _a_7bits(c0f), _a_7bits(c1f)
    b0 = np.clip(np.rint(a0f), 0, 255).astype(np.int32)
    b1 = np.clip(np.rint(a1f), 0, 255).astype(np.int32)
    ci, ec = _indices(rgb, _paleta(_exp8_m5(j0), _exp8_m5(j1), _PESOS2))
    ai, ea = _indices(al, _paleta(b0, b1, _PESOS2))
    err = ec + ea
    for _ in range(2):
        w = _PESOS2[ci].astype(np.float32) / 64.0
        f0, f1, okc = _refinar(rgb, 1.0 - w, w)
        w = _PESOS2[ai].astype(np.float32) / 64.0
        g0, g1, oka = _refinar(al, 1.0 - w, w)
        nj0, nj1 = _a_7bits(f0), _a_7bits(f1)
        nb0 = np.clip(np.rint(g0), 0, 255).astype(np.int32)
        nb1 = np.clip(np.rint(g1), 0, 255).astype(np.int32)
        nci, ecm = _indices(
            rgb, _paleta(_exp8_m5(nj0), _exp8_m5(nj1), _PESOS2))
        nai, eam = _indices(al, _paleta(nb0, nb1, _PESOS2))
        nerr = ecm + eam
        mejor = (okc & oka) & (nerr < err)
        j0 = np.where(mejor[:, None], nj0, j0)
        j1 = np.where(mejor[:, None], nj1, j1)
        b0 = np.where(mejor[:, None], nb0, b0)
        b1 = np.where(mejor[:, None], nb1, b1)
        ci = np.where(mejor[:, None], nci, ci)
        ai = np.where(mejor[:, None], nai, ai)
        err = np.where(mejor, nerr, err)
    # Ancla de cada plano (mismo truco que el modo 6, con pesos w[k] +
    # w[3 - k] = 64).
    vc, va = ci[:, 0] >= 2, ai[:, 0] >= 2
    j0, j1 = np.where(vc[:, None], j1, j0), np.where(vc[:, None], j0, j1)
    b0, b1 = np.where(va[:, None], b1, b0), np.where(va[:, None], b0, b1)
    ci = np.where(vc[:, None], 3 - ci, ci)
    ai = np.where(va[:, None], 3 - ai, ai)
    return j0, j1, b0, b1, ci, ai, err


def _empaqueta_m5(j0, j1, b0, b1, ci, ai):
    """Campos -> (bajos, altos) uint64 del bloque. Layout: modo 5 (6 bits),
    rotacion 0 (2 bits), R0 R1 G0 G1 B0 B1 de 7 bits, A0 A1 de 8, indice de
    color (ancla 1 bit + 15 de 2), indice de alfa (igual)."""
    n = j0.shape[0]
    campos = np.stack((j0[:, 0], j1[:, 0], j0[:, 1], j1[:, 1],
                       j0[:, 2], j1[:, 2]), 1)
    bajos = (np.full(n, 32, np.uint64)
             + (campos.astype(np.uint64)
                << (np.arange(6, dtype=np.uint64) * 7 + 8)).sum(1)
             + (b0[:, 0].astype(np.uint64) << np.uint64(50))
             + ((b1[:, 0].astype(np.uint64) & 63) << np.uint64(58)))
    d_ci = np.arange(16, dtype=np.uint64) * 2 + 1
    d_ci[0] = 2
    d_ai = np.arange(16, dtype=np.uint64) * 2 + 32
    d_ai[0] = 33
    altos = ((b1[:, 0].astype(np.uint64) >> 6)
             + (ci.astype(np.uint64) << d_ci).sum(1)
             + (ai.astype(np.uint64) << d_ai).sum(1))
    return bajos, altos


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def comprimir(pixeles, ancho, alto):
    """RGBA bytes -> bytes BC7: cada bloque en el mejor de los modos 5 y 6."""
    if len(pixeles) != ancho * alto * 4:
        raise ValueError("pixeles: %d bytes, se esperaban %d (%dx%d RGBA)"
                         % (len(pixeles), ancho * alto * 4, ancho, alto))
    bl = a_bloques(pixeles, ancho, alto).astype(np.float32)
    alfa = bl[:, :, 3]
    constante = alfa.max(1) == alfa.min(1)
    a_plana = alfa[:, 0]
    partes: list[bytes] = []
    for i in range(0, bl.shape[0], _TANDA):
        t = bl[i:i + _TANDA]
        c = constante[i:i + _TANDA]
        a = a_plana[i:i + _TANDA]
        j0, p0, j1, p1, idx6, err6 = _bloque_m6(t, a, c)
        j0b, j1b, b0, b1, ci, ai, err5 = _bloque_m5(t)
        usar5 = err5 < err6            # empate: modo 6
        b6_0, b6_1 = _empaqueta_m6(j0, p0, j1, p1, idx6)
        b5_0, b5_1 = _empaqueta_m5(j0b, j1b, b0, b1, ci, ai)
        bajos = np.where(usar5, b5_0, b6_0)
        altos = np.where(usar5, b5_1, b6_1)
        out = np.empty((len(bajos), 16), np.uint8)
        out[:, :8] = bajos.astype("<u8").view(np.uint8).reshape(-1, 8)
        out[:, 8:] = altos.astype("<u8").view(np.uint8).reshape(-1, 8)
        partes.append(out.tobytes())
    return b"".join(partes)


def _dec_m6(bajos, altos):
    corr = np.arange(8, dtype=np.uint64) * 7 + 7
    campos = ((bajos[:, None] >> corr) & 127).astype(np.int32)
    p0 = ((bajos >> np.uint64(63)) & 1).astype(np.int32)
    p1 = (altos & 1).astype(np.int32)
    e0 = (campos[:, 0::2] << 1) | p0[:, None]
    e1 = (campos[:, 1::2] << 1) | p1[:, None]
    idx = np.empty((bajos.shape[0], 16), np.int32)
    idx[:, 0] = ((altos >> np.uint64(1)) & 7).astype(np.int32)
    idx[:, 1:] = ((altos[:, None] >> (np.arange(1, 16, dtype=np.uint64)
                                      * 4)) & 15).astype(np.int32)
    pal = _paleta(e0, e1, _PESOS4)
    filas = np.arange(pal.shape[0])[:, None]
    return pal[filas, idx].astype(np.uint8)


def _dec_m5(bajos, altos):
    c7 = ((bajos[:, None] >> (np.arange(6, dtype=np.uint64) * 7 + 8))
          & 127).astype(np.int32)
    a0 = ((bajos >> np.uint64(50)) & 255).astype(np.int32)
    a1 = ((((bajos >> np.uint64(58)) & 63) | ((altos & 3) << 6))
          ).astype(np.int32)
    ci = np.empty((bajos.shape[0], 16), np.int32)
    ci[:, 0] = ((altos >> np.uint64(2)) & 1).astype(np.int32)
    ci[:, 1:] = ((altos[:, None] >> (np.arange(1, 16, dtype=np.uint64) * 2 + 1))
                 & 3).astype(np.int32)
    ai = np.empty((bajos.shape[0], 16), np.int32)
    ai[:, 0] = ((altos >> np.uint64(33)) & 1).astype(np.int32)
    ai[:, 1:] = ((altos[:, None]
                  >> (np.arange(1, 16, dtype=np.uint64) * 2 + 32)) & 3
                 ).astype(np.int32)
    palc = _paleta(_exp8_m5(c7[:, 0::2]), _exp8_m5(c7[:, 1::2]), _PESOS2)
    pala = _paleta(a0[:, None], a1[:, None], _PESOS2)
    filas = np.arange(palc.shape[0])[:, None]
    rgb = palc[filas, ci]
    al = pala[filas, ai][:, :, 0]
    # Rotacion: r = 1 cambia R con A, r = 2 la G, r = 3 la B (verificado con
    # Pillow). El compresor escribe siempre r = 0; el decodificador lee las
    # cuatro por si el archivo vino de otro encoder.
    rot = ((bajos >> np.uint64(6)) & 3).astype(np.int32)
    for r in (1, 2, 3):
        m = rot == r
        if not m.any():
            continue
        tmp = rgb[m, :, r - 1].copy()
        rgb[m, :, r - 1] = al[m]
        al[m] = tmp
    return np.concatenate((rgb, al[:, :, None]), -1).astype(np.uint8)


def descomprimir(datos, ancho, alto):
    """bytes de un nivel BC7 -> RGBA bytes (convencion de Pillow).

    Lee los modos 5 y 6 --los que escribe `comprimir`-- y rechaza cualquier
    otro con el numero de modo, en vez de devolver basura.
    """
    n = (-(-ancho // 4)) * (-(-alto // 4))
    crudo = np.frombuffer(bytes(datos[:n * BYTES_POR_BLOQUE]), np.uint8)
    if crudo.size != n * BYTES_POR_BLOQUE:
        raise ValueError("faltan bytes: %d de %d"
                         % (crudo.size, n * BYTES_POR_BLOQUE))
    bloques = crudo.reshape(n, BYTES_POR_BLOQUE)
    bajos = bloques[:, :8].copy().view("<u8")[:, 0]
    altos = bloques[:, 8:].copy().view("<u8")[:, 0]
    m6 = (bajos & 0x7F) == 64
    m5 = (bajos & 0x3F) == 32
    if not bool((m6 | m5).all()):
        v = int(bajos[~(m6 | m5)][0] & 0xFF)
        modo = (v & -v).bit_length() - 1 if v else 8
        raise ValueError("BC7 modo %d: compresor_bc7 escribe y lee solo los "
                         "modos 5 y 6" % modo)
    salida = np.empty((n, 16, 4), np.uint8)
    if bool(m6.any()):
        salida[m6] = _dec_m6(bajos[m6], altos[m6])
    if bool(m5.any()):
        salida[m5] = _dec_m5(bajos[m5], altos[m5])
    return de_bloques(salida, ancho, alto)


# ---------------------------------------------------------------------------
# autotest
# ---------------------------------------------------------------------------
def _bloque_m6_a_mano(f7, p0, p1, idx):
    """Un bloque modo 6 armado bit a bit, para comparar con literales que
    salieron de Pillow. `f7` = (R0, R1, G0, G1, B0, B1, A0, A1) de 7 bits;
    `idx` = 16 indices de 4 (el 0 se guarda con 3)."""
    bits = [0] * 6 + [1]
    for f in f7:
        bits += [(f >> i) & 1 for i in range(7)]
    bits += [p0, p1]
    bits += [(idx[0] >> i) & 1 for i in range(3)]
    for k in range(1, 16):
        bits += [(idx[k] >> i) & 1 for i in range(4)]
    assert len(bits) == 128
    data = bytearray(16)
    for i, b in enumerate(bits):
        if b:
            data[i // 8] |= 1 << (i % 8)
    return bytes(data)


def _bloque_m5_a_mano(rot, f7, a8, cidx, aidx):
    """Un bloque modo 5 armado bit a bit. `f7` = (R0, R1, G0, G1, B0, B1);
    `a8` = (A0, A1); indices de 2 bits (el texel 0 se guarda con 1)."""
    bits = [0] * 5 + [1]
    bits += [(rot >> i) & 1 for i in range(2)]
    for f in f7:
        bits += [(f >> i) & 1 for i in range(7)]
    for f in a8:
        bits += [(f >> i) & 1 for i in range(8)]
    bits += [cidx[0] & 1]
    for k in range(1, 16):
        bits += [(cidx[k] >> i) & 1 for i in range(2)]
    bits += [aidx[0] & 1]
    for k in range(1, 16):
        bits += [(aidx[k] >> i) & 1 for i in range(2)]
    assert len(bits) == 128
    data = bytearray(16)
    for i, b in enumerate(bits):
        if b:
            data[i // 8] |= 1 << (i % 8)
    return bytes(data)


def _ruido(w, h, semilla):
    rng = np.random.default_rng(semilla)
    return rng.integers(0, 256, (h, w, 4), dtype=np.uint8).tobytes()


def _degradado(w, h):
    y, x = np.mgrid[0:h, 0:w]
    img = np.stack((x * 255 // max(1, w - 1), y * 255 // max(1, h - 1),
                    (x + y) * 255 // max(1, w + h - 2),
                    128 + (x * 127 // max(1, w - 1))), -1).astype(np.uint8)
    return img.tobytes()


def _normal_con_mascara(w, h):
    """Un `_n` sintetico: RGB de normal suave y alfa (la mascara) con otro
    patron, los dos independientes -- el caso en que los planos separados del
    modo 5 le ganan al indice compartido del modo 6."""
    y, x = np.mgrid[0:h, 0:w]
    r = 128 + (x - w // 2) * 60 // max(1, w // 2)
    g = 128 + (y - h // 2) * 60 // max(1, h // 2)
    b = np.full((h, w), 230)
    a = (x * 255 // max(1, w - 1))
    img = np.stack((r, g, b, a), -1).astype(np.uint8)
    return img.tobytes()


def _pillow_decodifica(datos, ancho, alto):
    """El decodificador de Pillow sobre un DDS DX10 minimo, o None si no
    esta Pillow."""
    import io
    import struct
    try:
        from PIL import Image
    except ImportError:
        return None
    cab = bytearray(148)
    cab[0:4] = b"DDS "
    n_bl = max(1, -(-ancho // 4)) * max(1, -(-alto // 4))
    # size, flags (caps|alto|ancho|pixelformat|tamaño lineal), alto, ancho,
    # tamaño lineal: los cinco enteros que siguen al "DDS ".
    struct.pack_into("<IIIII", cab, 4, 124, 0x8100F, alto, ancho, n_bl * 16)
    struct.pack_into("<I", cab, 28, 1)          # mips
    struct.pack_into("<I", cab, 76, 32)         # tamano del pixelformat
    struct.pack_into("<I", cab, 80, 0x4)        # DDPF_FOURCC
    cab[84:88] = b"DX10"
    struct.pack_into("<I", cab, 108, 0x1000)    # DDSCAPS_TEXTURE
    struct.pack_into("<IIIII", cab, 128, 98, 3, 0, 1, 0)
    im = Image.open(io.BytesIO(bytes(cab) + bytes(datos)))
    return im.convert("RGBA").tobytes()


def autotest():
    """Cero comprobaciones NO es exito."""
    print("SUITE DE FALSIFICACION - compresor_bc7")
    print("")
    n = fallos = 0

    def ok(cond, texto):
        nonlocal n, fallos
        n += 1
        fallos += 0 if cond else 1
        print("  %-5s %s" % ("ok" if cond else "FALLA", texto))

    # a. decodificador del modo 6 contra literales que salieron de Pillow
    blk = _bloque_m6_a_mano((10, 20, 30, 40, 50, 60, 70, 80), 1, 0,
                            [0] * 16)
    vuelta = descomprimir(blk, 4, 4)
    ok(set(tuple(vuelta[i:i + 4]) for i in range(0, 64, 4))
       == {(21, 61, 101, 141)},
       "m6 bloque a mano, p0=1: e0 = (21, 61, 101, 141) en los 16 texeles")
    rampa = _bloque_m6_a_mano((0, 100, 0, 100, 0, 100, 0, 100), 0, 0,
                              list(range(16)))
    vuelta = descomprimir(rampa, 4, 4)
    esperado = [(0, 0, 0, 0), (13, 13, 13, 13), (28, 28, 28, 28),
                (41, 41, 41, 41), (53, 53, 53, 53), (66, 66, 66, 66),
                (81, 81, 81, 81), (94, 94, 94, 94), (106, 106, 106, 106),
                (119, 119, 119, 119), (134, 134, 134, 134),
                (147, 147, 147, 147), (159, 159, 159, 159),
                (172, 172, 172, 172), (188, 188, 188, 188),
                (200, 200, 200, 200)]
    got = [tuple(vuelta[i:i + 4]) for i in range(0, 64, 4)]
    ok(got == esperado,
       "m6 rampa de indices: los 16 pesos de 4 bits, literales de Pillow")

    # b. decodificador del modo 5 contra literales de Pillow
    blk = _bloque_m5_a_mano(0, (10, 20, 30, 40, 50, 60), (70, 80),
                            [0] * 16, [0] * 16)
    vuelta = descomprimir(blk, 4, 4)
    ok(set(tuple(vuelta[i:i + 4]) for i in range(0, 64, 4))
       == {(20, 60, 100, 70)},
       "m5 e0: (20, 60, 100, 70) con A0 = 8 bits exacto")
    blk = _bloque_m5_a_mano(0, (63, 64, 100, 127, 0, 32), (0, 255),
                            [1] * 16, [0] * 16)
    vuelta = descomprimir(blk, 4, 4)
    ok(tuple(vuelta[0:4]) == (127, 219, 21, 0),
       "m5 expansion 7->8 y peso 21/64: (127, 219, 21, 0)")
    blk = _bloque_m5_a_mano(1, (10, 20, 30, 40, 50, 60), (70, 80),
                            [0] * 16, [0] * 16)
    vuelta = descomprimir(blk, 4, 4)
    ok(tuple(vuelta[0:4]) == (70, 60, 100, 20),
       "m5 rotacion 1: R y A se permutan como Pillow")

    # c. un bloque de modo no soportado se rechaza en vez de devolver basura
    otro = bytearray(16)
    otro[0] = 0x01                      # modo 0: 1 en el bit 0
    try:
        descomprimir(bytes(otro), 4, 4)
        ok(False, "modo 0 del spec: tenia que rechazarse")
    except ValueError as e:
        ok("modo 0" in str(e), "modo 0 del spec rechazado: %s" % e)

    # d. alfa constante sobrevive exacto: la mascara especular no se mueve
    for alfa in (255, 55, 0):
        pix = bytearray()
        for y in range(16):
            for x in range(16):
                pix += bytes(((x * 13) % 256, (y * 7) % 256,
                              ((x + y) * 5) % 256, alfa))
        vuelta = descomprimir(comprimir(bytes(pix), 16, 16), 16, 16)
        ok(set(vuelta[3::4]) == {alfa},
           "alfa constante %d: los 256 texeles vuelven con %d exacto"
           % (alfa, alfa))

    # e. un bloque de dos colores representables vuelve exacto, con el
    #    texel 0 en el color "caro" (fuerza la inversion de la ancla)
    a, b = (11, 21, 31, 255), (201, 211, 221, 255)   # paridad impar = p 1
    caso = bytes(a) * 15 + bytes(b)
    vuelta = descomprimir(comprimir(caso, 4, 4), 4, 4)
    ok(vuelta == caso, "dos colores impares con alfa 255: exacto con ancla "
       "en el segundo color")
    caso = bytes(b) + bytes(a) * 15
    vuelta = descomprimir(comprimir(caso, 4, 4), 4, 4)
    ok(vuelta == caso, "los mismos dos colores con el texel 0 en el primero")

    # f. el error bajito en un degradado, y BC7 le gana a DXT5 en el mismo
    #    pixmap (los dos con numpy, los dos releidos con su decodificador)
    import compresor_dxt as cd
    resultados = {}
    for nombre, pix in (("degradado", _degradado(64, 64)),
                        ("normal+mascara", _normal_con_mascara(64, 64)),
                        ("ruido", _ruido(64, 64, 7))):
        e7 = error_rms(pix, descomprimir(comprimir(pix, 64, 64), 64, 64))
        e5 = error_rms(pix, cd.descomprimir(
            cd.comprimir(pix, 64, 64, "DXT5"), 64, 64, "DXT5"))
        resultados[nombre] = (e7, e5)
        m7, m5 = float(np.mean(e7)), float(np.mean(e5))
        ok(m7 <= m5 + 4.0,
           "%s 64x64: RMS medio BC7 %.2f vs DXT5 %.2f (por canal BC7 %s "
           "vs DXT5 %s)" % (nombre, m7, m5, e7, e5))
    e7, e5 = resultados["degradado"]
    ok(sum(e7[:3]) / 3 < sum(e5[:3]) / 3,
       "degradado: el RGB de BC7 (%.2f) le gana al de DXT5 (%.2f)"
       % (sum(e7[:3]) / 3, sum(e5[:3]) / 3))
    ok(e7[3] < 4.0,
       "degradado: alfa BC7 %.2f < 4.0 (DXT5 deja EXACTO este alfa "
       "sintetico: 8 paradas de 8 bits sobre un rango corto)" % e7[3])
    e7, e5 = resultados["normal+mascara"]
    ok(float(np.mean(e7)) < float(np.mean(e5)),
       "normal+mascara: BC7 (%.2f) le gana a DXT5 (%.2f), alfa incluido "
       "(%.2f vs %.2f)" % (float(np.mean(e7)), float(np.mean(e5)),
                           e7[3], e5[3]))
    ok(e7[3] < 1.0, "normal+mascara: alfa de BC7 %.2f < 1.0" % e7[3])
    e7, e5 = resultados["ruido"]
    ok(float(np.mean(e7[:3])) <= float(np.mean(e5[:3])) + 1.0,
       "ruido: el RGB de BC7 (%.2f) no queda atras del de DXT5 (%.2f)"
       % (float(np.mean(e7[:3])), float(np.mean(e5[:3]))))
    ok(e7[3] < 20.0,
       "ruido: alfa BC7 %.2f < 20.0 -- el alfa ALEATORIO es el peor caso "
       "del modo 5 (4 paradas contra las 8 de DXT5, que acá da %.2f); un "
       "alfa de verdad no es ruido" % (e7[3], e5[3]))

    # g. tamanos que no son multiplo de 4 (mipmaps de 2x2 y 1x1)
    for w, h in ((2, 2), (1, 1), (4, 1), (8, 2)):
        pix = _ruido(w, h, w * 10 + h)
        datos = comprimir(pix, w, h)
        bytes_esperados = max(1, -(-w // 4)) * max(1, -(-h // 4)) * 16
        vuelta = descomprimir(datos, w, h)
        ok(len(datos) == bytes_esperados and len(vuelta) == w * h * 4,
           "%dx%d: %d bytes comprimidos, %d decodificados" % (w, h, len(datos),
                                                              len(vuelta)))

    # h. contra Pillow: su decodificador lee lo mismo que el nuestro, byte a
    #    byte, sobre lo que escribimos
    try:
        import PIL  # noqa: F401
        hay_pillow = True
    except ImportError:
        hay_pillow = False
    if not hay_pillow:
        print("  --    Pillow no esta: se saltean las comparaciones con el "
              "oraculo (no cuentan como comprobadas)")
    else:
        for nombre, pix in (("degradado", _degradado(64, 64)),
                            ("normal+mascara", _normal_con_mascara(64, 64)),
                            ("ruido", _ruido(64, 64, 7))):
            datos = comprimir(pix, 64, 64)
            suyo = _pillow_decodifica(datos, 64, 64)
            ok(suyo is not None and suyo == descomprimir(datos, 64, 64),
               "%s: Pillow decodifica lo mismo, byte a byte" % nombre)

    # i. la seleccion de modo no deja bloques invalidos: decodificar todo lo
    #    escrito no lanza (aqui y en el Pillow de arriba se probó igual)
    try:
        datos = comprimir(_ruido(128, 128, 11), 128, 128)
        vuelta = descomprimir(datos, 128, 128)
        ok(len(vuelta) == 128 * 128 * 4, "128x128 de ruido: ida y vuelta")
    except ValueError as e:
        ok(False, "128x128 de ruido: %s" % e)

    print("")
    if n == 0:
        print("  NO se comprobo NADA.")
        return False
    if fallos:
        print("  %d FALLAS de %d." % (fallos, n))
        return False
    print("  %d comprobaciones, sin fallas." % n)
    return True


def main(argv):
    if argv == ["--autotest"]:
        return 0 if autotest() else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
