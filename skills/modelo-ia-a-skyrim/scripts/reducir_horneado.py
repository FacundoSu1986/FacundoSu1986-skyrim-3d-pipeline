# -*- coding: utf-8 -*-
"""Reduce un horneado 2x2 filtrando cada mapa como lo que es (trampa 35).

    python reducir_horneado.py --autotest

POR QUE EXISTE
--------------
El bake de Cycles lee UN punto del modelo alto por texel. Si la textura del
generador es mas grande que el destino, eso es muestreo puntual: bordes
dentados, sobre todo en el normal map. El arreglo es hornear al doble y
reducir. Pero cada mapa se promedia distinto:

  color   sRGB -> lineal, promedio, -> sRGB. Promediar sRGB oscurece bordes.
  normal  promediar los VECTORES y renormalizar. El promedio de cuatro
          unitarios distintos es mas corto que 1: sin renormalizar, el relieve
          se aplana.
  lineal  promedio simple (AO, metal, rugosidad, mascaras).

ENTRADA Y SALIDA
----------------
Listas planas de floats RGBA en 0..1, ancho*alto*4 --el formato de
`img.pixels[:]` en Blender (trampa 18: leer entero, nunca con paso)--. No
usa numpy ni nada de afuera para que corra igual dentro de Blender, en CI y
desde la skill empaquetada. El costo es tiempo: Python puro sobre 4096^2 tarda
del orden de un minuto por mapa [no medido en este repo].

El alfa se promedia siempre en lineal, en los tres modos.
"""
import math
import sys

MODOS = ("color", "normal", "lineal")


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


def reducir(pix, ancho, alto, modo):
    """Devuelve (pix, ancho/2, alto/2). Ancho y alto pares; si no, error."""
    if modo not in MODOS:
        raise ValueError("modo %r: tiene que ser uno de %s" % (modo, MODOS))
    if ancho < 2 or alto < 2 or ancho % 2 or alto % 2:
        raise ValueError("%dx%d: para reducir 2x2 los dos lados tienen que "
                         "ser pares y >= 2" % (ancho, alto))
    if len(pix) != ancho * alto * 4:
        raise ValueError("pixeles: %d floats, se esperaban %d (%dx%d RGBA)"
                         % (len(pix), ancho * alto * 4, ancho, alto))
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


def autotest():
    fallas = []

    def exigir(cond, texto):
        if not cond:
            fallas.append(texto)

    # lineal: promedio exacto
    pix = [0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0,
           0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0]
    out, w, h = reducir(pix, 2, 2, "lineal")
    exigir((w, h) == (1, 1), "lineal: tamano %dx%d" % (w, h))
    exigir(abs(out[0] - 0.5) < 1e-9, "lineal: %r no es 0,5" % out[0])
    exigir(abs(out[3] - 0.5) < 1e-9, "lineal: alfa %r no es 0,5" % out[3])

    # color: negro + blanco en sRGB NO da 0,5; da ~0,735 (el medio lineal).
    # Si alguien lo cambia a promedio simple, esto lo pesca.
    out, _, _ = reducir(pix, 2, 2, "color")
    exigir(abs(out[0] - 0.7354) < 1e-3,
           "color: %r, se esperaba ~0,735 (promedio en lineal)" % out[0])
    # color uniforme no se mueve
    gris = [0.3, 0.3, 0.3, 1.0] * 4
    out, _, _ = reducir(gris, 2, 2, "color")
    exigir(abs(out[0] - 0.3) < 1e-9, "color uniforme se movio: %r" % out[0])

    # normal: cuatro unitarios inclinados en X +-45 grados. El promedio simple
    # da (0, 0, 0,707): corto. Renormalizado tiene que dar (0, 0, 1).
    s = math.sqrt(0.5)
    enc = lambda x, y, z: [(x + 1) / 2, (y + 1) / 2, (z + 1) / 2, 1.0]
    pix = enc(s, 0, s) + enc(-s, 0, s) + enc(s, 0, s) + enc(-s, 0, s)
    out, _, _ = reducir(pix, 2, 2, "normal")
    z = out[2] * 2 - 1
    exigir(abs(z - 1.0) < 1e-9, "normal: z=%r, no se renormalizo" % z)
    x, y = out[0] * 2 - 1, out[1] * 2 - 1
    largo = math.sqrt(x * x + y * y + z * z)
    exigir(abs(largo - 1.0) < 1e-9, "normal: largo %r != 1" % largo)
    # el verde NO se invierte (trampa 30): un +Y sigue siendo +Y
    pix = enc(0, s, s) * 4
    out, _, _ = reducir(pix, 2, 2, "normal")
    exigir(out[1] > 0.5, "normal: el verde se invirtio (%r)" % out[1])
    # normales opuestas que se anulan: plano, no NaN
    pix = enc(1, 0, 0) + enc(-1, 0, 0) + enc(1, 0, 0) + enc(-1, 0, 0)
    out, _, _ = reducir(pix, 2, 2, "normal")
    exigir(out[:3] == [0.5, 0.5, 1.0], "normal nula: %r" % out[:3])

    # posicion: el texel (1,0) de la salida sale del bloque correcto
    pix = [0.0] * (4 * 2 * 4)
    for q in (2, 3, 6, 7):          # columnas 2-3 de un 4x2
        pix[q * 4] = 1.0
    out, w, h = reducir(pix, 4, 2, "lineal")
    exigir((w, h) == (2, 1) and out[0] == 0.0 and out[4] == 1.0,
           "posicion: %r" % out)

    # entradas invalidas fallan con ValueError, no con basura
    for args, que in (((pix, 3, 2, "lineal"), "lado impar"),
                      ((pix[:-1], 4, 2, "lineal"), "largo corto"),
                      ((pix, 4, 2, "srgb"), "modo invalido")):
        try:
            reducir(*args)
            fallas.append("%s no fallo" % que)
        except ValueError:
            pass

    for f in fallas:
        print("[FALLA] %s" % f)
    print("autotest: %s" % ("OK" if not fallas else "%d fallas" % len(fallas)))
    return 1 if fallas else 0


def main(argv):
    if argv == ["--autotest"]:
        return autotest()
    print("uso: reducir_horneado.py --autotest\n"
          "  (como modulo: reducir(pix, ancho, alto, 'color'|'normal'|'lineal'))")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
