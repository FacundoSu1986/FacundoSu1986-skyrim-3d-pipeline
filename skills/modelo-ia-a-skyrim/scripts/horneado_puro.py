# -*- coding: utf-8 -*-
"""Lo del horneado que NO necesita Blender, para que CI lo pruebe.

    python horneado_puro.py --autotest

`hornear.py` corre adentro de Blender y no se puede importar sin `bpy`. Todo
lo que se puede separar de Blender vive aca, con autotest:

  reducir / reducir_np   reduccion 2x2 filtrando cada mapa como lo que es
                         (trampa 35)
  dilatar                el margen alrededor de las islas, hecho aca
  rellenar_vacios        valor neutro donde ni el bake ni el margen llegan
  a_bytes / escribir_png PNG de 8 bits SIN alfa, con las filas en el orden
                         del PNG
  alineacion             control grueso de que la alta y la baja esten en el
                         mismo lugar
  solape_uv              que fraccion de la huella UV pisan dos triangulos;
                         en un bake, cada texel tiene que tener UN origen
  principled_conectado   el Principled que de verdad alimenta la salida de
                         un material (sobre nodos de Blender o imitaciones)
  densidad_texel         texeles por unidad de una pieza, para comparar piezas
  media / correlacion    estadisticas sobre los texeles CUBIERTOS

El autotest cuenta sus comprobaciones y dice cuantas SALTEO por no tener
numpy. Las que necesitan numpy son justo las que usa el bake real (dilatar,
rellenar_vacios, reducir_np): el CI instala numpy, y
tests/test_horneado_puro.py falla si en CI faltara.

REDUCCION (trampa 35)
---------------------
  color   sRGB -> lineal, promedio, -> sRGB. Promediar sRGB oscurece bordes.
  normal  promediar los VECTORES y renormalizar. El promedio de cuatro
          unitarios distintos es mas corto que 1: sin renormalizar, el relieve
          se aplana.
  lineal  promedio simple (AO, rugosidad, metalicidad).

Hay dos implementaciones con el mismo resultado: `reducir_np` con numpy, que
viene con Blender, y `reducir` en Python puro, para CI y la skill empaquetada.
La pura NO sirve para un bake real: una lista de Python gasta unos 32 bytes
por float, y un horneado de 4096^2 son 67 millones de floats, del orden de
2 GB por lista `[calculado, no medido]`. Con numpy en float32 son 4 bytes por
float: ~270 MB a 4096^2 y ~1 GB a 8192^2 `[calculado]`.

La entrada es la de `img.pixels` de Blender: floats RGBA en 0..1, con la fila
0 ABAJO. Medido con bpy 4.5.14 LTS: en una imagen de bytes sRGB, `pixels`
devuelve el valor YA codificado en sRGB (un gris lineal 0,5 horneado se lee
0,737), que es lo que `color` espera.

POR QUE UN PNG PROPIO, SIN ALFA
-------------------------------
Medido con bpy 4.5.14: el bake escribe alfa = 1 en todo texel horneado. Un
PNG guardado por Blender lleva ese alfa, y un `_n` convertido sin mirar sale
con la mascara especular al 100 % en todas las islas: el plastico del hacha
(trampa del 99,7 %). Aca se escribe RGB o gris, y el alfa del `_n` lo pone
quien fabrica la mascara especular, a proposito.
"""
import math
import struct
import sys
import zlib

MODOS = ("color", "normal", "lineal")

try:
    import numpy as np
except ImportError:          # CI y skill empaquetada: sin numpy
    np = None


def _a_lineal(c):
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _a_srgb(c):
    if c <= 0.0031308:
        v = c * 12.92
    else:
        v = 1.055 * (c ** (1.0 / 2.4)) - 0.055
    return min(1.0, max(0.0, v))


def _normal(r, g, b):
    """Promedio de vectores codificados en 0..1, renormalizado, recodificado."""
    x, y, z = r * 2.0 - 1.0, g * 2.0 - 1.0, b * 2.0 - 1.0
    largo = math.sqrt(x * x + y * y + z * z)
    if largo < 1e-8:
        # Cuatro normales que se anulan: no hay direccion. La del plano es la
        # unica que no inventa relieve.
        return 0.5, 0.5, 1.0
    return (x / largo + 1.0) * 0.5, (y / largo + 1.0) * 0.5, \
        (z / largo + 1.0) * 0.5


def _validar(modo, ancho, alto, n):
    if modo not in MODOS:
        raise ValueError("modo %r: tiene que ser uno de %s" % (modo, MODOS))
    if ancho < 2 or alto < 2 or ancho % 2 or alto % 2:
        raise ValueError("%dx%d: para reducir 2x2 los dos lados tienen que "
                         "ser pares y >= 2" % (ancho, alto))
    if n != ancho * alto * 4:
        raise ValueError("pixeles: %d floats, se esperaban %d (%dx%d RGBA)"
                         % (n, ancho * alto * 4, ancho, alto))


def reducir(pix, ancho, alto, modo):
    """Python puro. Devuelve (pix, ancho/2, alto/2)."""
    _validar(modo, ancho, alto, len(pix))
    aw, ah = ancho // 2, alto // 2
    fila = ancho * 4
    salida = [0.0] * (aw * ah * 4)
    for j in range(ah):
        base0 = (2 * j) * fila
        base1 = base0 + fila
        for i in range(aw):
            p = (base0 + i * 8, base0 + i * 8 + 4,
                 base1 + i * 8, base1 + i * 8 + 4)
            if modo == "color":
                rgb = [_a_srgb(sum(_a_lineal(pix[q + c]) for q in p) / 4.0)
                       for c in range(3)]
            else:
                rgb = [sum(pix[q + c] for q in p) / 4.0 for c in range(3)]
                if modo == "normal":
                    rgb = list(_normal(*rgb))
            a = sum(pix[q + 3] for q in p) / 4.0
            o = (j * aw + i) * 4
            salida[o:o + 4] = rgb[0], rgb[1], rgb[2], a
    return salida, aw, ah


def reducir_np(arr, modo):
    """numpy. `arr` (alto, ancho, 4) float; devuelve (alto/2, ancho/2, 4)."""
    alto, ancho = arr.shape[0], arr.shape[1]
    _validar(modo, ancho, alto, arr.size)
    # float32: la salida es de 8 bits, y float64 duplicaba el pico de memoria.
    a = arr.astype(np.float32, copy=False).reshape(alto // 2, 2, ancho // 2,
                                                   2, 4)
    rgb, alfa = a[..., :3], a[..., 3].mean(axis=(1, 3))
    if modo == "color":
        lin = np.where(rgb <= 0.04045, rgb / 12.92,
                       ((rgb + 0.055) / 1.055) ** 2.4).mean(axis=(1, 3))
        rgb = np.where(lin <= 0.0031308, lin * 12.92,
                       1.055 * np.power(lin, 1.0 / 2.4) - 0.055)
        rgb = np.clip(rgb, 0.0, 1.0)
    else:
        rgb = rgb.mean(axis=(1, 3))
        if modo == "normal":
            v = rgb * 2.0 - 1.0
            largo = np.sqrt((v * v).sum(axis=-1, keepdims=True))
            nulo = largo[..., 0] < 1e-8
            v = v / np.where(largo < 1e-8, 1.0, largo)
            v[nulo] = (0.0, 0.0, 1.0)
            rgb = (v + 1.0) * 0.5
    return np.concatenate([rgb, alfa[..., None]], axis=-1).astype(np.float32)


# Lo que va en el hueco del atlas, por mapa. El bake deja ahi RGB 0, y 0 no
# es neutro para nadie: un normal (0,0,0) no es un vector y se mezcla en los
# mipmaps, y una rugosidad 0 la fase de texturas la vuelve alfa 255 en el
# `_n` --especular al maximo--. Medido corriendo esa fase (PR #51) sobre un
# horneado con 24 % de cobertura: 24,7 % de bloques saturados antes del
# relleno. El albedo no tiene neutro: se rellena con su color medio, para que
# los mipmaps lejanos no se oscurezcan en los bordes.
RELLENO = {"normalgl": (0.5, 0.5, 1.0), "roughness": (1.0, 1.0, 1.0),
           "metallic": (0.0, 0.0, 0.0), "ao": (1.0, 1.0, 1.0),
           "albedo": None}


def dilatar(arr, pasos):
    """numpy, en el lugar: extiende lo horneado a los vecinos vacios.

    Es el margen del bake, hecho aca y no en Blender. Medido con bpy 4.5.14:
    con `margin` > 0 Blender deja el alfa en 1 en TODA la imagen, y ya no se
    sabe que texel quedo vacio -- el hueco del atlas salia con RGB 0 y alfa 1,
    y el relleno neutro no lo encontraba. Horneando con margen 0 el alfa
    marca exactamente lo horneado, y el margen se agrega aca: en cada paso,
    cada texel vacio con algun vecino lleno (de los 8) toma el promedio de sus
    vecinos llenos. Tambien tapa los agujeros de rayos fallidos dentro de una
    isla. Devuelve la fraccion que sigue vacia.
    """
    lleno = arr[..., 3] >= 0.5
    alto, ancho = lleno.shape
    # Planar (un plano contiguo por canal) con borde de ceros, y buffers
    # reservados una vez. El plano 3 cuenta vecinos llenos, asi color y
    # cuenta se suman en la misma pasada. La suma 3x3 es separable (4 sumas
    # en vez de 8) e incluye el centro, que en un texel vacio vale 0. Medido:
    # la primera version (RGBA intercalado, 8 sumas, indices booleanos)
    # tardaba lo mismo que todos los bakes juntos.
    buf = np.zeros((4, alto + 2, ancho + 2), np.float32)
    interior = buf[:, 1:-1, 1:-1]
    interior[:3] = np.moveaxis(arr[..., :3], -1, 0) * lleno
    interior[3] = lleno
    filas = np.empty((4, alto + 2, ancho), np.float32)
    suma = np.empty((4, alto, ancho), np.float32)
    for _ in range(pasos):
        if lleno.all():
            break
        np.add(buf[:, :, :-2], buf[:, :, 1:-1], out=filas)
        filas += buf[:, :, 2:]
        np.add(filas[:, :-2], filas[:, 1:-1], out=suma)
        suma += filas[:, 2:]
        nuevos = ~lleno & (suma[3] > 0)
        if not nuevos.any():
            break
        cuenta = np.maximum(suma[3], 1.0)
        for c in range(3):
            np.copyto(interior[c], suma[c] / cuenta, where=nuevos)
        lleno |= nuevos
        interior[3] = lleno
    arr[..., :3] = np.moveaxis(interior[:3], 0, -1)
    arr[..., 3] = lleno
    return float((~lleno).mean())


def rellenar_vacios(arr, rgb):
    """numpy, en el lugar. Texel con alfa < 0,5 (el bake no lo toco) -> `rgb`.

    `rgb` None = el color medio de lo horneado. Devuelve la fraccion vacia.
    """
    vacio = arr[..., 3] < 0.5
    if vacio.all():
        return 1.0
    if rgb is None:
        rgb = arr[..., :3][~vacio].mean(axis=0)
    arr[..., :3][vacio] = rgb
    return float(vacio.mean())


def a_bytes(pix, ancho, alto, canales):
    """Floats RGBA de Blender (fila 0 abajo) -> bytes de PNG (fila 0 arriba).

    `canales` 3 = RGB, 1 = gris (se toma R). El alfa se descarta siempre.
    Acepta una lista plana o un array numpy de cualquier forma con
    ancho*alto*4 elementos.
    """
    if canales not in (1, 3):
        raise ValueError("canales %r: 1 (gris) o 3 (RGB)" % canales)
    if np is not None and hasattr(pix, "reshape"):
        a = np.asarray(pix, dtype=np.float64).reshape(alto, ancho, 4)
        a = np.clip(np.rint(a[::-1, :, :canales] * 255.0), 0, 255)
        return a.astype(np.uint8).tobytes()
    if len(pix) != ancho * alto * 4:
        raise ValueError("pixeles: %d, se esperaban %d" % (len(pix),
                                                           ancho * alto * 4))
    salida = bytearray()
    for j in range(alto - 1, -1, -1):
        for i in range(ancho):
            o = (j * ancho + i) * 4
            for c in range(canales):
                salida.append(max(0, min(255, int(pix[o + c] * 255.0 + 0.5))))
    return bytes(salida)


def escribir_png(ruta, ancho, alto, canales, datos):
    """PNG de 8 bits, gris (1) o RGB (3), sin alfa. `datos` fila 0 arriba."""
    tipo = {1: 0, 3: 2}[canales]
    paso = ancho * canales
    if len(datos) != paso * alto:
        raise ValueError("datos: %d bytes, se esperaban %d"
                         % (len(datos), paso * alto))
    crudo = b"".join(b"\x00" + datos[j * paso:(j + 1) * paso]
                     for j in range(alto))

    def trozo(tipo_trozo, cuerpo):
        c = struct.pack(">I", len(cuerpo)) + tipo_trozo + cuerpo
        return c + struct.pack(">I", zlib.crc32(tipo_trozo + cuerpo)
                               & 0xFFFFFFFF)

    with open(ruta, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(trozo(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, tipo,
                                           0, 0, 0)))
        f.write(trozo(b"IDAT", zlib.compress(crudo, 6)))
        f.write(trozo(b"IEND", b""))


def _leer_png_simple(ruta):
    """Solo para el autotest: lee lo que escribe `escribir_png`."""
    with open(ruta, "rb") as f:
        d = f.read()
    ancho, alto, _, tipo = struct.unpack(">IIBB", d[16:26])
    canales = {0: 1, 2: 3}[tipo]
    datos, p = b"", 8
    while p < len(d):
        n = struct.unpack(">I", d[p:p + 4])[0]
        if d[p + 4:p + 8] == b"IDAT":
            datos += d[p + 8:p + 8 + n]
        p += 12 + n
    crudo = zlib.decompress(datos)
    paso = ancho * canales
    filas = [crudo[j * (paso + 1) + 1:(j + 1) * (paso + 1)]
             for j in range(alto)]
    return ancho, alto, canales, b"".join(filas)


def alineacion(caja_baja, caja_alta, tol_centro=0.10, tol_escala=1.25):
    """Control GRUESO de que la alta este donde esta la baja.

    Cajas ((xmin, ymin, zmin), (xmax, ymax, zmax)) en coordenadas de mundo.
    Devuelve una lista de motivos; vacia es que pasa. Las tolerancias son
    criterio, no medicion `[no medido]`: estan para atrapar el olvido de una
    transformacion (una alta sin girar, sin escalar, corrida), no para medir
    un ajuste fino. No se compara un eje:

      * casi plano en la baja (menos del 1 % de la diagonal): una pieza plana
        puede venir con espesor en la alta;
      * casi plano en la alta si en la baja es DELGADO (menos del 25 %): una
        cascara abierta de la IA se solidifica en la baja antes de las UV
        (hd-texturas.md, paso 4) y la alta sigue sin espesor. Sin esto, el
        caso que el flujo recomienda no se podia hornear. Si en la baja ese
        eje es largo, una alta plana ahi es una alta girada, y se compara.
    """
    lo_b, hi_b = caja_baja
    lo_a, hi_a = caja_alta
    lados_b = [hi_b[i] - lo_b[i] for i in range(3)]
    lados_a = [hi_a[i] - lo_a[i] for i in range(3)]
    diag = math.sqrt(sum(x * x for x in lados_b))
    if diag < 1e-9:
        return ["la baja no tiene tamano"]
    motivos = []
    centro_b = [(lo_b[i] + hi_b[i]) / 2.0 for i in range(3)]
    centro_a = [(lo_a[i] + hi_a[i]) / 2.0 for i in range(3)]
    corrido = math.sqrt(sum((centro_a[i] - centro_b[i]) ** 2
                            for i in range(3))) / diag
    if corrido > tol_centro:
        motivos.append("centro corrido %.1f %% de la diagonal (tope %.0f %%)"
                       % (corrido * 100, tol_centro * 100))
    for i, eje in enumerate("XYZ"):
        if lados_b[i] < 0.01 * diag:
            continue
        if lados_a[i] < 0.01 * diag and lados_b[i] < 0.25 * diag:
            continue
        r = lados_a[i] / lados_b[i]
        if r > tol_escala or r < 1.0 / tol_escala:
            motivos.append("eje %s: la alta mide %.2f veces la baja"
                           % (eje, r))
    return motivos


# Resolucion del rasterizador y tope de solape: los mismos del censo
# (census/parser_uv.py: GRID; hallazgos_uv.md, hallazgo 3: "nada de solape" es
# < 0,001).
GRID_UV = 512
TOPE_SOLAPE = 0.001


def rasterizar_uv(tris_uv, res=GRID_UV):
    """{(gx, gy): cuantos triangulos cubren el centro de esa celda}.

    COPIA de `census/parser_uv.rasterizar`, porque la skill empaquetada no
    lleva census/. tests/test_horneado_puro.py exige que las dos den lo
    mismo. La regla de relleno TOP-LEFT es la que importa: sin ella, cada
    arista compartida cuenta como una linea de celdas solapadas (el censo
    midio 816 falsas en un atlas de 4 islas separadas).
    """
    g = {}
    paso = 1.0 / res
    eps = 1e-12
    for p0, p1, p2 in tris_uv:
        if ((p1[0] - p0[0]) * (p2[1] - p0[1]) -
                (p2[0] - p0[0]) * (p1[1] - p0[1])) < 0:
            p1, p2 = p2, p1
        x0, y0 = p0
        x1, y1 = p1
        x2, y2 = p2
        if abs((x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)) < 1e-15:
            continue
        tl = []
        for (ax, ay), (bx, by) in (((x0, y0), (x1, y1)),
                                   ((x1, y1), (x2, y2)),
                                   ((x2, y2), (x0, y0))):
            dx, dy = bx - ax, by - ay
            tl.append(dy > 0 or (dy == 0 and dx < 0))
        gx0 = max(0, min(res - 1, int(min(x0, x1, x2) * res)))
        gx1 = max(0, min(res - 1, int(max(x0, x1, x2) * res)))
        gy0 = max(0, min(res - 1, int(min(y0, y1, y2) * res)))
        gy1 = max(0, min(res - 1, int(max(y0, y1, y2) * res)))
        a0, b0 = -(y1 - y0), (x1 - x0)
        a1, b1 = -(y2 - y1), (x2 - x1)
        a2, b2 = -(y0 - y2), (x0 - x2)
        px0 = (gx0 + 0.5) * paso
        py0 = (gy0 + 0.5) * paso
        f0 = a0 * (px0 - x0) + b0 * (py0 - y0)
        f1 = a1 * (px0 - x1) + b1 * (py0 - y1)
        f2 = a2 * (px0 - x2) + b2 * (py0 - y2)
        dx0, dx1, dx2 = a0 * paso, a1 * paso, a2 * paso
        dy0, dy1, dy2 = b0 * paso, b1 * paso, b2 * paso
        tl0, tl1, tl2 = tl
        for gy in range(gy0, gy1 + 1):
            e0, e1, e2 = f0, f1, f2
            for gx in range(gx0, gx1 + 1):
                if ((e0 > eps or (e0 > -eps and tl0)) and
                        (e1 > eps or (e1 > -eps and tl1)) and
                        (e2 > eps or (e2 > -eps and tl2))):
                    g[(gx, gy)] = g.get((gx, gy), 0) + 1
                e0 += dx0
                e1 += dx1
                e2 += dx2
            f0 += dy0
            f1 += dy1
            f2 += dy2
    return g


def solape_uv(tris_uv, res=GRID_UV):
    """Fraccion de la huella UV cubierta por dos o mas triangulos (la
    `solape_huella` del censo). 0.0 si no hay huella.

    En vanilla, pisar UV es el reuso normal (hallazgos_uv.md: 8 de cada 9
    mallas lo hacen), y por eso el censo no lo trata como defecto. En un BAKE
    si lo es: cada texel recibe el color de UN punto de la alta, y dos islas
    en el mismo lugar se pisan --gana la ultima que se horneo--.
    """
    g = rasterizar_uv(tris_uv, res)
    if not g:
        return 0.0
    return sum(1 for v in g.values() if v >= 2) / float(len(g))


def principled_conectado(salida):
    """Los Principled BSDF que alimentan la entrada Surface de `salida`, en el
    orden en que se los alcanza yendo hacia atras por los vinculos.

    Sirve con nodos de Blender o con cualquier objeto que tenga `type`,
    `inputs` (con `["Surface"]` e iterable) y, en cada entrada, `links` con
    `from_node`. Buscar "el primer Principled del arbol" tomaba uno suelto o
    el de otra rama; lo que se hornea es lo que llega a la salida.
    """
    vistos, encontrados = set(), []
    cola = [l.from_node for l in salida.inputs["Surface"].links]
    while cola:
        n = cola.pop(0)
        if id(n) in vistos:
            continue
        vistos.add(id(n))
        if n.type == "BSDF_PRINCIPLED":
            encontrados.append(n)
            continue
        for entrada in n.inputs:
            for l in entrada.links:
                cola.append(l.from_node)
    return encontrados


def densidad_texel(area_3d, area_uv, res):
    """Texeles por unidad de largo de una pieza, a resolucion `res`.

    sqrt(area_uv * res^2 / area_3d). Sirve para COMPARAR piezas de un mismo
    atlas: si una sale con el doble que otra, una se ve borrosa al lado de la
    otra. None si la pieza no tiene area 3D o UV.
    """
    if area_3d <= 0 or area_uv <= 0:
        return None
    return math.sqrt(area_uv * res * res / area_3d)


def media(valores, mascara):
    """Media de `valores` donde `mascara` es verdadera; None si no hay."""
    sel = [v for v, m in zip(valores, mascara) if m]
    return sum(sel) / len(sel) if sel else None


def correlacion(xs, ys, mascara):
    """Pearson entre xs e ys donde `mascara`; None si no se puede calcular."""
    pares = [(x, y) for x, y, m in zip(xs, ys, mascara) if m]
    n = len(pares)
    if n < 2:
        return None
    mx = sum(p[0] for p in pares) / n
    my = sum(p[1] for p in pares) / n
    sxy = sum((x - mx) * (y - my) for x, y in pares)
    sxx = sum((x - mx) ** 2 for x, _ in pares)
    syy = sum((y - my) ** 2 for _, y in pares)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def autotest():
    import os
    import tempfile

    fallas = []
    cuenta = [0]

    def exigir(cond, texto):
        cuenta[0] += 1
        if not cond:
            fallas.append(texto)

    def exigir_error(fn, args, que):
        try:
            fn(*args)
        except ValueError:
            exigir(True, que)
        else:
            exigir(False, "%s no fallo" % que)

    # --- reducir (puro) ---
    pix = [0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0,
           0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0]
    out, w, h = reducir(pix, 2, 2, "lineal")
    exigir((w, h) == (1, 1), "lineal: tamano %dx%d" % (w, h))
    exigir(abs(out[0] - 0.5) < 1e-9, "lineal: %r no es 0,5" % out[0])
    exigir(abs(out[3] - 0.5) < 1e-9, "lineal: alfa %r no es 0,5" % out[3])
    # color: negro + blanco en sRGB NO da 0,5; da ~0,735 (el medio lineal).
    out, _, _ = reducir(pix, 2, 2, "color")
    exigir(abs(out[0] - 0.7354) < 1e-3,
           "color: %r, se esperaba ~0,735 (promedio en lineal)" % out[0])
    gris = [0.3, 0.3, 0.3, 1.0] * 4
    out, _, _ = reducir(gris, 2, 2, "color")
    exigir(abs(out[0] - 0.3) < 1e-9, "color uniforme se movio: %r" % out[0])
    # normal: +-45 grados en X. El promedio simple da z=0,707; renormalizado 1.
    s = math.sqrt(0.5)

    def enc(x, y, z):
        return [(x + 1) / 2, (y + 1) / 2, (z + 1) / 2, 1.0]

    pix_n = enc(s, 0, s) + enc(-s, 0, s) + enc(s, 0, s) + enc(-s, 0, s)
    out, _, _ = reducir(pix_n, 2, 2, "normal")
    exigir(abs(out[2] * 2 - 1 - 1.0) < 1e-9, "normal: no se renormalizo")
    # el verde NO se invierte (trampa 30)
    out, _, _ = reducir(enc(0, s, s) * 4, 2, 2, "normal")
    exigir(out[1] > 0.5, "normal: el verde se invirtio (%r)" % out[1])
    pix_0 = enc(1, 0, 0) + enc(-1, 0, 0) + enc(1, 0, 0) + enc(-1, 0, 0)
    out, _, _ = reducir(pix_0, 2, 2, "normal")
    exigir(out[:3] == [0.5, 0.5, 1.0], "normal nula: %r" % out[:3])
    # posicion: el texel (1,0) de la salida sale del bloque correcto
    pos = [0.0] * (4 * 2 * 4)
    for q in (2, 3, 6, 7):
        pos[q * 4] = 1.0
    out, w, h = reducir(pos, 4, 2, "lineal")
    exigir((w, h) == (2, 1) and out[0] == 0.0 and out[4] == 1.0,
           "posicion: %r" % out)
    for args, que in (((pos, 3, 2, "lineal"), "lado impar"),
                      ((pos[:-1], 4, 2, "lineal"), "largo corto"),
                      ((pos, 4, 2, "srgb"), "modo invalido")):
        exigir_error(reducir, args, que)

    # --- reducir_np == reducir (solo si hay numpy) ---
    if np is not None:
        import random
        rnd = random.Random(7)
        for modo in MODOS:
            lista = [rnd.random() for _ in range(8 * 6 * 4)]
            ref, _, _ = reducir(lista, 8, 6, modo)
            got = reducir_np(np.array(lista).reshape(6, 8, 4), modo)
            dif = max(abs(a - b) for a, b in zip(ref, got.ravel().tolist()))
            exigir(dif < 1e-5, "reducir_np %s difiere de reducir: %g"
                   % (modo, dif))
        got = reducir_np(np.array(pix_0).reshape(2, 2, 4), "normal")
        exigir(got.ravel()[:3].tolist() == [0.5, 0.5, 1.0],
               "reducir_np normal nula: %r" % got.ravel()[:3].tolist())

        # rellenar_vacios: lo horneado (alfa 1) no se toca; el hueco toma el
        # neutro, o el medio de lo horneado si no hay neutro.
        a = np.array([[[0.2, 0.4, 0.6, 1.0], [0.0, 0.0, 0.0, 0.0]],
                      [[0.4, 0.6, 0.8, 1.0], [0.0, 0.0, 0.0, 0.0]]],
                     dtype=np.float32)
        b = a.copy()
        frac = rellenar_vacios(b, RELLENO["roughness"])
        exigir(frac == 0.5, "rellenar: fraccion vacia %r" % frac)
        exigir(b[0, 1, :3].tolist() == [1.0, 1.0, 1.0],
               "rellenar: rugosidad del hueco %r" % b[0, 1, :3].tolist())
        exigir((b[:, 0] == a[:, 0]).all(), "rellenar toco lo horneado")
        b = a.copy()
        rellenar_vacios(b, RELLENO["albedo"])
        exigir(np.allclose(b[1, 1, :3], [0.3, 0.5, 0.7]),
               "rellenar albedo: %r" % b[1, 1, :3].tolist())
        todo_vacio = np.zeros((2, 2, 4), np.float32)
        exigir(rellenar_vacios(todo_vacio, None) == 1.0,
               "rellenar sin nada horneado tiene que dar 1,0")

        # dilatar: un texel lleno en (2,2) de un 5x5; 1 paso llena el anillo
        # de 8 vecinos y nada mas; los bordes no se envuelven.
        d = np.zeros((5, 5, 4), np.float32)
        d[2, 2] = (0.8, 0.6, 0.4, 1.0)
        resto = dilatar(d, 1)
        exigir(abs(resto - 16 / 25.0) < 1e-9, "dilatar 1 paso: resto %r" % resto)
        exigir(np.allclose(d[1, 1, :3], (0.8, 0.6, 0.4)) and d[1, 1, 3] == 1,
               "dilatar: el vecino no tomo el valor")
        exigir(d[0, 0, 3] == 0 and d[0, 0, :3].tolist() == [0, 0, 0],
               "dilatar: un paso llego a distancia 2")
        # dos horneados VECINOS y distintos: no se promedian entre si (con
        # uno solo, promediarlo consigo mismo no cambia nada y la prueba no
        # veia la mutacion que pisa lo horneado)
        g = np.zeros((1, 3, 4), np.float32)
        g[0, 0] = (1, 1, 1, 1)
        g[0, 1] = (0, 0, 0, 1)
        dilatar(g, 1)
        exigir(g[0, 0, 0] == 1.0 and g[0, 1, 0] == 0.0,
               "dilatar toco lo horneado: %r" % g[0, :2, 0].tolist())
        exigir(abs(g[0, 2, 0] - 0.0) < 1e-6,
               "dilatar: el vacio toma el promedio de SUS vecinos llenos")
        exigir(dilatar(d, 5) == 0.0, "dilatar: 5 pasos no llenaron un 5x5")
        # promedio de vecinos llenos, no de todos
        e = np.zeros((1, 3, 4), np.float32)
        e[0, 0] = (1, 1, 1, 1)
        e[0, 2] = (0, 0, 0, 1)
        dilatar(e, 1)
        exigir(np.allclose(e[0, 1, :3], 0.5), "dilatar: promedio %r"
               % e[0, 1, :3].tolist())
        # borde derecho no se envuelve al izquierdo
        f = np.zeros((1, 4, 4), np.float32)
        f[0, 0] = (1, 0, 0, 1)
        dilatar(f, 1)
        exigir(f[0, 3, 3] == 0, "dilatar: el borde se envolvio")

    # --- a_bytes: voltea filas, descarta alfa ---
    # 2x2: fila de ABAJO roja, fila de ARRIBA verde; alfa en 1 (el del bake)
    abajo_arriba = ([1, 0, 0, 1] * 2) + ([0, 1, 0, 1] * 2)
    b3 = a_bytes(abajo_arriba, 2, 2, 3)
    exigir(len(b3) == 12, "a_bytes RGB: %d bytes, no 12" % len(b3))
    exigir(b3[:3] == bytes((0, 255, 0)),
           "a_bytes: la primera fila del PNG tiene que ser la de ARRIBA")
    exigir(a_bytes(abajo_arriba, 2, 2, 1) == bytes((0, 0, 255, 255)),
           "a_bytes gris: toma R y voltea")
    if np is not None:
        exigir(a_bytes(np.array(abajo_arriba, dtype=np.float32), 2, 2, 3)
               == b3, "a_bytes numpy difiere del puro")

    # --- escribir_png: ida y vuelta, sin alfa ---
    tmp = tempfile.mkdtemp()
    try:
        for canales, datos in ((3, b3), (1, bytes((0, 64, 128, 255)))):
            ruta = os.path.join(tmp, "t%d.png" % canales)
            escribir_png(ruta, 2, 2, canales, datos)
            w, h, c, leido = _leer_png_simple(ruta)
            exigir((w, h, c) == (2, 2, canales),
                   "png %d: cabecera %r" % (canales, (w, h, c)))
            exigir(leido == datos, "png %d: los datos no vuelven" % canales)
        exigir_error(escribir_png, (os.path.join(tmp, "x.png"), 2, 2, 3,
                                    b"\x00"), "png con datos cortos")
    finally:
        for f in os.listdir(tmp):
            os.remove(os.path.join(tmp, f))
        os.rmdir(tmp)

    # --- alineacion ---
    caja = ((0, 0, 0), (1, 2, 3))
    exigir(alineacion(caja, caja) == [], "misma caja no paso")
    exigir(alineacion(caja, ((0.02, 0, 0), (1.02, 2, 3))) == [],
           "un corrimiento chico no tiene que reprobar")
    girada = ((0, 0, 0), (2, 1, 3))            # X e Y intercambiados
    exigir(alineacion(caja, girada) != [], "alta girada 90 grados paso")
    escalada = ((0, 0, 0), (100, 200, 300))    # sin la escala de la baja
    exigir(alineacion(caja, escalada) != [], "alta sin escalar paso")
    lejos = ((5, 0, 0), (6, 2, 3))
    exigir(any("corrido" in m for m in alineacion(caja, lejos)),
           "alta corrida paso")
    plana = ((0, 0, 0), (1, 2, 0))             # baja plana en Z
    exigir(alineacion(plana, ((0, 0, -0.05), (1, 2, 0.05))) == [],
           "una baja plana no compara el eje plano")
    # la cascara de la IA solidificada en la baja (paso 4) y la alta sin
    # espesor: tiene que pasar. Reprobaba: "la alta mide 0.02 veces la baja".
    exigir(alineacion(((0, 0, -0.5), (30, 10, 0.5)),
                      ((0, 0, -0.01), (30, 10, 0.01))) == [],
           "una baja solidificada sobre una alta sin espesor no paso")
    # pero una alta plana GIRADA 90 grados (plana en el eje largo de la baja)
    # no se saltea: eso no es un Solidify
    exigir(alineacion(((0, 0, 0), (30, 10, 0)),
                      ((15, 0, -15), (15, 10, 15))) != [],
           "una alta plana girada 90 grados paso")

    # --- solape de UV ---
    quad = [((0.1, 0.1), (0.4, 0.1), (0.4, 0.4)),
            ((0.1, 0.1), (0.4, 0.4), (0.1, 0.4))]
    exigir(solape_uv(quad) == 0.0,
           "dos triangulos que comparten arista contaron solape: %r"
           % solape_uv(quad))
    otra = [((0.6, 0.6), (0.9, 0.6), (0.9, 0.9))]
    exigir(solape_uv(quad + otra) == 0.0, "islas separadas contaron solape")
    exigir(solape_uv(quad + quad) == 1.0, "una isla apilada no dio 1,0")
    espejada = [tuple((1.0 - u - 0.5, v) for u, v in t) for t in quad]
    exigir(solape_uv(quad + espejada) == 1.0,
           "una isla espejada encima (giro invertido) no dio 1,0: %r"
           % solape_uv(quad + espejada))
    medio = solape_uv(quad + [((0.1, 0.1), (0.4, 0.1), (0.4, 0.4))])
    exigir(0.4 < medio < 0.6, "medio quad apilado: %r" % medio)
    exigir(solape_uv([]) == 0.0, "sin triangulos")
    # aristas compartidas que pasan JUSTO por centros de celda, en las tres
    # orientaciones (vertical, horizontal, diagonal): sin la regla top-left
    # esos centros se cuentan dos veces y aparece un solape que no existe
    c = [(k + 0.5) / 64.0 for k in (8, 24, 40, 48, 60)]
    abanico = [((c[0], c[0]), (c[1], c[0]), (c[1], c[1])),
               ((c[0], c[0]), (c[1], c[1]), (c[0], c[1])),
               ((c[1], c[0]), (c[2], c[0]), (c[2], c[1])),
               ((c[1], c[0]), (c[2], c[1]), (c[1], c[1])),
               ((c[0], c[1]), (c[1], c[1]), (c[1], c[2])),
               ((c[0], c[1]), (c[1], c[2]), (c[0], c[2])),
               # la arista compartida en la SEGUNDA posicion del triangulo
               ((c[4], c[3]), (c[4], c[4]), (c[3], c[3])),
               ((c[3], c[4]), (c[3], c[3]), (c[4], c[4]))]
    exigir(solape_uv(abanico, 64) == 0.0,
           "aristas sobre centros de celda contaron solape: %r"
           % solape_uv(abanico, 64))

    # --- el Principled que llega a la salida ---
    class Nodo(object):
        def __init__(self, tipo, **entradas):
            self.type = tipo
            self._e = {k: Entrada(v) for k, v in entradas.items()}
            self.inputs = self

        def __getitem__(self, k):
            return self._e[k]

        def __iter__(self):
            return iter(self._e.values())

    class Entrada(object):
        def __init__(self, nodos):
            self.links = [Vinculo(n) for n in nodos]

    class Vinculo(object):
        def __init__(self, n):
            self.from_node = n

    a = Nodo("BSDF_PRINCIPLED")
    b = Nodo("BSDF_PRINCIPLED")
    suelto = Nodo("BSDF_PRINCIPLED")
    mezcla = Nodo("MIX_SHADER", Fac=[], Shader=[a], Shader_001=[b])
    salida = Nodo("OUTPUT_MATERIAL", Surface=[mezcla])
    encontrados = principled_conectado(salida)
    exigir([n is a for n in encontrados] == [True, False]
           and encontrados[1] is b and suelto not in encontrados,
           "principled_conectado: tomo el suelto o perdio uno de la mezcla")
    exigir(principled_conectado(Nodo("OUTPUT_MATERIAL", Surface=[a])) == [a],
           "principled_conectado: el directo")
    exigir(principled_conectado(Nodo("OUTPUT_MATERIAL", Surface=[])) == [],
           "principled_conectado: sin vinculo tiene que dar []")

    # --- densidad ---
    exigir(densidad_texel(1.0, 1.0, 1024) == 1024.0, "densidad 1:1")
    exigir(abs(densidad_texel(4.0, 1.0, 1024) - 512.0) < 1e-9,
           "densidad: 4x area 3D = mitad de texeles por unidad")
    exigir(densidad_texel(0.0, 1.0, 1024) is None, "densidad sin area 3D")

    # --- media y correlacion sobre texeles cubiertos ---
    exigir(media([0, 10, 2], [False, True, True]) == 6.0, "media mascarada")
    exigir(media([1, 2], [False, False]) is None, "media sin cubiertos")
    r = correlacion([0, 1, 2, 3, 99], [0, 2, 4, 6, -5],
                    [True, True, True, True, False])
    exigir(r is not None and abs(r - 1.0) < 1e-9,
           "correlacion perfecta ignorando lo no cubierto: %r" % r)
    exigir(correlacion([1, 1, 1], [1, 2, 3], [True] * 3) is None,
           "correlacion con varianza 0 tiene que dar None")

    for f in fallas:
        print("[FALLA] %s" % f)
    print("autotest: %d comprobaciones, %d fallas%s"
          % (cuenta[0], len(fallas),
             "" if np is not None else
             "  -- SIN NUMPY: salteadas las de reducir_np, dilatar y "
             "rellenar_vacios, que son las que usa el bake"))
    return 1 if fallas else 0


def main(argv):
    if argv == ["--autotest"]:
        return autotest()
    print("uso: horneado_puro.py --autotest  (es un modulo de hornear.py)")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
