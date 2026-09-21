# -*- coding: utf-8 -*-
"""Las proporciones de un arma, contra las de su clase en el corpus.

    python scripts/proporciones_arma.py <malla.nif> [--clase <clase>]
    python scripts/proporciones_arma.py --autotest
    python scripts/proporciones_arma.py --censo <carpeta meshes/weapons>

Exit 0 si pasa, 1 si no pasa o si no hubo NADA que medir, 2 si los argumentos
no sirven. Python puro, sin Blender.

POR QUE POR CLASE, Y NO "ARMAS"

Una daga y un martillo a dos manos no comparten una sola proporcion. Medido
sobre 219 armas vanilla: el largo mediano va de 40,5 (daga) a 120,7 (baston), y
el grosor relativo de 0,034 (mandoble) a 0,260 (maza). Una tabla unica para
"armas" no dice nada de ninguna.

POR QUE EN COORDENADAS DE MUNDO

Varias mallas vanilla viven dentro de un nodo con rotacion y escala. Leer los
vertices locales da numeros sin sentido: `daedricwarhammer.nif` mide 1.128
unidades en local y 341 al componer la transformada. La primera version de esta
medicion descartaba esos archivos por "largo implausible" en vez de arreglarlos.

QUE PUEDE Y QUE NO PUEDE ESTA HERRAMIENTA

  REGLA  cada proporcion tiene que caer dentro del [min, max] de su clase.
         Es una red de seguridad, no una regla de gusto: el rango vanilla es
         ANCHO. En el hacha de Tencent el mango media 0,112 del largo y el
         rango de las hachas a dos manos es [0,037, 0,185] -- o sea que
         ESTA REGLA NO LO HABRIA MARCADO, aunque a ojo se veia grueso.

  OBS    en que percentil de su clase cae cada medida. Eso si lo habria dicho:
         0,112 esta por encima de la mediana (0,083) de su clase. El numero
         que le pone palabras a "se ve grueso" es el percentil, no el rango.

La tabla se regenera con `--censo <carpeta meshes/weapons>` sobre un corpus
extraido.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import censo_nif  # noqa: E402

# Fraccion del largo que define cada extremo al buscar la empunadura.
TRAMO = 0.20
MIN_PUNTOS = 50
# Una unidad del redondeo con que se guarda la tabla.
TOLERANCIA = 1e-4

# (min, mediana, max) por clase, medido sobre 219 armas de meshes/weapons/.
# Solo se incluyen las clases con al menos 10 ejemplares: con menos, un rango
# no es un rango.
CLASES = {
    "espada": {"n": 35, "largo": (24.6386, 79.3390, 95.4290),
               "grosor_largo": (0.0104, 0.0528, 0.1268),
               "ancho_largo": (0.0817, 0.1687, 0.6858),
               "mango_largo": (0.0220, 0.0640, 0.2051)},
    "flecha": {"n": 29, "largo": (42.0953, 58.2204, 66.2290),
               "grosor_largo": (0.0174, 0.0661, 0.2250),
               "ancho_largo": (0.0622, 0.0900, 0.5752),
               "mango_largo": (0.0268, 0.0592, 0.2780)},
    "hacha2m": {"n": 26, "largo": (40.3796, 97.2015, 122.8557),
                "grosor_largo": (0.0431, 0.0530, 0.1383),
                "ancho_largo": (0.1383, 0.3593, 0.8783),
                "mango_largo": (0.0369, 0.0827, 0.1854)},
    "maza": {"n": 22, "largo": (28.5972, 59.8748, 79.5068),
             "grosor_largo": (0.1898, 0.2597, 0.6516),
             "ancho_largo": (0.1898, 0.2606, 0.6516),
             "mango_largo": (0.0552, 0.1061, 0.1693)},
    "mandoble": {"n": 21, "largo": (34.7914, 114.0823, 120.9295),
                 "grosor_largo": (0.0160, 0.0337, 0.0729),
                 "ancho_largo": (0.0912, 0.1592, 0.5613),
                 "mango_largo": (0.0104, 0.0457, 0.1979)},
    "baston": {"n": 18, "largo": (104.7355, 120.6752, 142.8540),
               "grosor_largo": (0.0313, 0.0824, 0.1241),
               "ancho_largo": (0.0507, 0.1138, 0.2379),
               "mango_largo": (0.0144, 0.0421, 0.0687)},
    "daga": {"n": 16, "largo": (20.6383, 40.5412, 49.1056),
             "grosor_largo": (0.0430, 0.0721, 0.1315),
             "ancho_largo": (0.1362, 0.2094, 0.4999),
             "mango_largo": (0.0544, 0.0866, 0.1265)},
    "martillo2m": {"n": 16, "largo": (84.4936, 93.5476, 107.5893),
                   "grosor_largo": (0.0595, 0.0978, 0.1427),
                   "ancho_largo": (0.2473, 0.2997, 0.3747),
                   "mango_largo": (0.0475, 0.0881, 0.1168)},
    "hacha1m": {"n": 14, "largo": (21.7952, 54.8884, 67.8794),
                "grosor_largo": (0.0552, 0.0745, 0.2018),
                "ancho_largo": (0.2481, 0.4300, 0.8808),
                "mango_largo": (0.0776, 0.1417, 0.5206)},
}

# El arco queda AFUERA a proposito: con el clasificador que se envia solo
# matchean 2 archivos --el resto son *bowskinned*, y un shape skinneado no
# lleva la geometria inline-- y con 2 ejemplares un rango no es un rango.
# Como se adivina la clase desde el nombre del archivo. El orden importa:
# "battleaxe" tiene que probarse antes que "waraxe".
#
# NO hay comodin "axe". Lo hubo, y metia en la clase de las hachas de una mano
# a axeofysgramor (99 unidades), executioneraxe (145) y las seis piezas de
# brokenaxe* (de 10 a 20): con ese comodin la REGLA rechazaba el 6,36 % del
# corpus del que salio. Un nombre que no matchea una pista concreta sale sin
# clase y la herramienta la pide, que es mejor que meterlo en la clase
# equivocada.
PISTAS = (("battleaxe", "hacha2m"), ("greatsword", "mandoble"),
          ("warhammer", "martillo2m"), ("waraxe", "hacha1m"),
          ("crossbow", "arco"), ("dagger", "daga"), ("mace", "maza"),
          ("staff", "baston"), ("arrow", "flecha"), ("sword", "espada"),
          ("bow", "arco"))

CAMPOS = (("largo", "largo (unidades)"), ("grosor_largo", "grosor / largo"),
          ("ancho_largo", "ancho / largo"), ("mango_largo", "mango / largo"))


def clase_por_nombre(nombre):
    n = os.path.basename(nombre).lower()
    for clave, clase in PISTAS:
        if clave in n:
            return clase
    return None


def puntos_mundo(nif):
    """Los puntos de la malla mas grande, en coordenadas de mundo.

    p_mundo = t + escala * (M . p_local), que es la misma composicion que usa
    censo_nif._recorrer_mundo para encadenar padres.
    """
    mejor = None
    for sh in nif.geometria():
        if sh.get("error") or not sh.get("pos") or not sh.get("tris"):
            continue
        if mejor is None or len(sh["tris"]) > len(mejor["tris"]):
            mejor = sh
    if mejor is None:
        return None, "ningun shape con geometria inline legible"
    tr = nif.mundo_shapes().get(mejor["nombre"])
    rot = nif.rotaciones_shapes().get(mejor["nombre"])
    if tr is None or rot is None:
        return None, "el shape %r no aparece en el recorrido de mundo" % \
            mejor["nombre"]
    x, y, z, esc = tr
    fuera = []
    for p in mejor["pos"]:
        if not all(-1e9 < c < 1e9 for c in p):
            continue
        fuera.append((
            x + esc * (rot[0] * p[0] + rot[1] * p[1] + rot[2] * p[2]),
            y + esc * (rot[3] * p[0] + rot[4] * p[1] + rot[5] * p[2]),
            z + esc * (rot[6] * p[0] + rot[7] * p[1] + rot[8] * p[2])))
    if len(fuera) < MIN_PUNTOS:
        return None, "solo %d puntos finitos" % len(fuera)
    return fuera, None


def medir(pts):
    lo = [min(p[k] for p in pts) for k in range(3)]
    hi = [max(p[k] for p in pts) for k in range(3)]
    dim = [hi[k] - lo[k] for k in range(3)]
    eje = max(range(3), key=lambda k: dim[k])
    largo = dim[eje]
    if largo <= 0:
        return None
    otros = [k for k in range(3) if k != eje]

    def extension(a, b):
        sel = [p for p in pts if a <= (p[eje] - lo[eje]) / largo <= b]
        if len(sel) < 20:
            return None
        return max(max(p[k] for p in sel) - min(p[k] for p in sel)
                   for k in otros)

    bajo, alto = extension(0.0, TRAMO), extension(1.0 - TRAMO, 1.0)
    if bajo is None or alto is None:
        return None
    mango = min(bajo, alto)          # el extremo mas fino es la empunadura
    return {"largo": largo, "eje": "XYZ"[eje],
            "grosor_largo": min(dim[k] for k in otros) / largo,
            "ancho_largo": max(dim[k] for k in otros) / largo,
            "mango": mango, "mango_largo": mango / largo}


def juzgar(m, clase):
    """(fallas, notas). REGLA: dentro del [min, max] de la clase."""
    if clase not in CLASES:
        return (["clase %r desconocida. Las medidas son: %s"
                 % (clase, ", ".join(sorted(CLASES)))], [])
    ref = CLASES[clase]
    fallas, notas = [], []
    for campo, etiqueta in CAMPOS:
        lo, med, hi = ref[campo]
        v = m[campo]
        # La tabla esta redondeada a 4 decimales, asi que el archivo que DEFINE
        # un borde puede caer del lado de afuera por el redondeo: elvenbattleaxe
        # tiene grosor/largo 0,043099 y el minimo guardado es 0,0431. Una regla
        # que reprueba al archivo que fija su propio limite esta mal. Se compara
        # con una unidad de redondeo de tolerancia.
        if v < lo - TOLERANCIA or v > hi + TOLERANCIA:
            fallas.append(
                "REGLA %s: %.4f, fuera del rango vanilla [%.4f, %.4f] de la "
                "clase %s (n=%d)." % (etiqueta, v, lo, hi, clase, ref["n"]))
        else:
            donde = ("por DEBAJO de la mediana" if v < med
                     else "por encima de la mediana" if v > med else
                     "en la mediana")
            notas.append("OBS %-16s %.4f   vanilla [%.4f .. %.4f] mediana "
                         "%.4f -- %s" % (etiqueta, v, lo, hi, med, donde))
    return fallas, notas


def revisar(ruta, clase):
    if clase is None:
        clase = clase_por_nombre(ruta)
    print("== %s" % os.path.basename(ruta))
    if clase is None:
        print("   no se pudo adivinar la clase desde el nombre. Pasala con "
              "--clase: %s" % ", ".join(sorted(CLASES)))
        return 1
    try:
        nif = censo_nif.Nif(ruta)
    except Exception as e:
        print("   no se pudo leer: %s: %s" % (type(e).__name__, e))
        return 1
    pts, error = puntos_mundo(nif)
    if pts is None:
        print("   no hay nada que medir: %s" % error)
        return 1
    m = medir(pts)
    if m is None:
        print("   la malla no tiene forma medible (extremos sin puntos)")
        return 1
    print("   clase %s (n=%d en el corpus)   eje largo %s   mango %.2f "
          "unidades" % (clase, CLASES.get(clase, {}).get("n", 0), m["eje"],
                        m["mango"]))
    fallas, notas = juzgar(m, clase)
    for n in notas:
        print("   %s" % n)
    for f in fallas:
        print("   FALLA %s" % f)
    return 1 if fallas else 0


# --------------------------------------------------------------------------
def autotest():
    fallas = []

    def exigir(cond, texto):
        if not cond:
            fallas.append(texto)

    # una figura con respuesta conocida: barra de 100 de largo, 10 de grosor,
    # con un extremo mas fino
    pts = []
    for i in range(101):
        y = float(i)
        # El tramo fino llega hasta 25 y no hasta 20: el extremo que se mide es
        # el 20 %% del largo, y con el corte justo en 20 el ultimo punto ya
        # pertenece a la parte gruesa. El fixture media 10 en vez de 2.
        r = 1.0 if y < 25 else 5.0
        for sx in (-r, r):
            for sz in (-r, r):
                pts.append((sx, y, sz))
    m = medir(pts)
    exigir(m is not None, "la barra no se midio")
    exigir(abs(m["largo"] - 100.0) < 1e-6, "largo %.3f" % m["largo"])
    exigir(abs(m["mango"] - 2.0) < 1e-6,
           "el mango tendria que ser el extremo FINO: %.3f" % m["mango"])
    exigir(abs(m["mango_largo"] - 0.02) < 1e-9, "mango/largo %.4f"
           % m["mango_largo"])
    exigir(m["eje"] == "Y", "eje %s" % m["eje"])

    # el extremo fino puede estar de cualquier lado
    pts2 = [(x, 100.0 - y, z) for x, y, z in pts]
    m2 = medir(pts2)
    exigir(abs(m2["mango"] - 2.0) < 1e-6,
           "con la barra dada vuelta el mango cambio: %.3f" % m2["mango"])

    # la REGLA, en los dos bordes de una clase
    ref = CLASES["hacha2m"]
    dentro = {"largo": ref["largo"][1], "grosor_largo": ref["grosor_largo"][1],
              "ancho_largo": ref["ancho_largo"][1],
              "mango_largo": ref["mango_largo"][1]}
    exigir(not juzgar(dentro, "hacha2m")[0],
           "la mediana de la clase reprobo")
    for campo, _ in CAMPOS:
        torcido = dict(dentro)
        torcido[campo] = ref[campo][2] * 1.5
        f = juzgar(torcido, "hacha2m")[0]
        exigir(bool(f), "%s por encima del maximo no reprobo" % campo)
        torcido[campo] = ref[campo][0] * 0.5
        f = juzgar(torcido, "hacha2m")[0]
        exigir(bool(f), "%s por debajo del minimo no reprobo" % campo)

    # el hacha de Tencent: el rango NO la marcaba, y hay que decirlo
    tencent = dict(dentro)
    tencent["mango_largo"] = 0.1124
    f, n = juzgar(tencent, "hacha2m")
    exigir(not f, "el mango del hacha (0,1124) tendria que estar DENTRO del "
                  "rango [0,037 .. 0,185]: la regla no lo marca")
    exigir(any("mango / largo" in x and "por encima" in x for x in n),
           "no informo que el mango esta por encima de la mediana")

    # clase desconocida
    exigir(bool(juzgar(dentro, "no-existe")[0]),
           "una clase desconocida no reprobo")

    # adivinar la clase por el nombre
    for nombre, esperada in (("elvenbattleaxe.nif", "hacha2m"),
                             ("ironsword.nif", "espada"),
                             ("daedricgreatsword.nif", "mandoble"),
                             ("steelwaraxe.nif", "hacha1m"),
                             ("longbow.nif", "arco")):
        exigir(clase_por_nombre(nombre) == esperada,
               "%s -> %s, se esperaba %s"
               % (nombre, clase_por_nombre(nombre), esperada))

    print("autotest: %d comprobaciones, %d fallas" % (22, len(fallas)))
    for x in fallas:
        print("  FALLA %s" % x)
    return 1 if fallas else 0


def censo(raiz):
    """Regenera la tabla sobre un corpus extraido."""
    datos = {}
    n = 0
    for base, _, nombres in os.walk(raiz):
        for nom in sorted(nombres):
            if not nom.lower().endswith(".nif"):
                continue
            clase = clase_por_nombre(nom)
            if clase is None:
                continue
            try:
                pts, _e = puntos_mundo(censo_nif.Nif(os.path.join(base, nom)))
            except Exception:
                continue
            if pts is None:
                continue
            m = medir(pts)
            if m is None:
                continue
            n += 1
            datos.setdefault(clase, []).append(m)
    print("armas medidas: %d" % n)
    for clase in sorted(datos, key=lambda c: -len(datos[c])):
        v = datos[clase]
        if len(v) < 10:
            print("   (%s: solo %d, no alcanza para un rango)"
                  % (clase, len(v)))
            continue
        linea = []
        for campo, _ in CAMPOS:
            x = sorted(i[campo] for i in v)
            linea.append("%s (%.4f, %.4f, %.4f)"
                         % (campo, x[0], x[len(x) // 2], x[-1]))
        print('    "%s": {"n": %d, %s},' % (clase, len(v), ", ".join(linea)))
    return 0 if n else 1


def main(argv):
    if len(argv) == 1 and argv[0] == "--autotest":
        return autotest()
    if len(argv) == 2 and argv[0] == "--censo":
        return censo(argv[1])
    clase = None
    if len(argv) == 3 and argv[1] == "--clase":
        clase = argv[2]
        argv = argv[:1]
    if len(argv) == 1 and argv[0].lower().endswith(".nif"):
        return revisar(argv[0], clase)
    print("uso: proporciones_arma.py <malla.nif> [--clase <clase>] | "
          "--autotest | --censo <carpeta>")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
