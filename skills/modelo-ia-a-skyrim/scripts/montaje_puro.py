# -*- coding: utf-8 -*-
"""Lo del montaje y el rig que NO necesita Blender, para que CI lo pruebe.

    python montaje_puro.py --autotest

`montar.py` corre adentro de Blender. Todo lo que se puede separar de Blender
vive aca, con autotest:

  ajuste_segmento   lleva un segmento de la parte (dos puntos elegidos en
                    ella) al segmento entre dos huesos del donante
  ajuste_caja       lleva la caja de la parte a la caja de la pieza vanilla
  espejo_x          la parte izquierda hecha derecha
  pesos_por_vecino  los pesos de cada vertice nuevo, copiados del vertice
                    vanilla mas cercano
  controles_pesos   lo que el archivo tiene que cumplir despues

Las matrices son listas de 4 filas de 4 floats, en el orden de Blender
(`Matrix(M)` las toma tal cual) y se aplican a puntos columna: p' = M p.

EL METODO, Y DE DONDE SALE
--------------------------
Es el del replacer del centurion de vapor, que se probo en el juego con sus
48 animaciones (proyecto de origen, 2026-09-13):

  * cada pieza de la IA se monta en el lugar de una pieza del NIF vanilla
    --el DONANTE--, que pone el material, las particiones, las propiedades
    del shape y el esqueleto. Nada de eso se reconstruye a mano;
  * una pieza larga (muslo, antebrazo) se alinea con el segmento entre las
    cabezas de dos huesos: el suyo y el siguiente. Por defecto se estira SOLO
    a lo largo de ese eje: el largo lo ponen las animaciones, el grosor es
    diseno. Una pieza compacta (cabeza, hombrera) se encaja en la caja de la
    pieza vanilla;
  * los pesos se copian del vertice vanilla mas cercano. En el centurion, 12
    de las 15 piezas pesan a un solo hueso y la copia da peso 1 a ese hueso
    --el skin rigido del proyecto de origen--; las otras tres (los pies con
    el dedo, la cabeza con parpados y mandibula) heredan el reparto.

EL GIRO ALREDEDOR DEL EJE
-------------------------
Dos puntos no fijan el giro de la pieza alrededor de su propio eje. Sin mas
datos se usa la rotacion minima, que es la correcta si la parte vino con la
misma orientacion que el vanilla ("front facing", +Y, con Z arriba). Con
`frente` (una direccion de la parte) ese giro se fija: la direccion termina
apuntando a +Y del juego, proyectada sobre el plano perpendicular al eje. En
una pieza larga en Y (un pie) +Y es el eje mismo y no fija nada: para esa va
`arriba`, que apunta a +Z. Pedir una direccion paralela al eje es un error,
no una nota.

LOS CONTROLES
-------------
  REGLA  suma       los pesos de cada vertice suman 1
  REGLA  max4       como mucho 4 huesos por vertice [INVARIANT: el vertice
                    skinneado de BSTriShape en SSE tiene 4 indices de hueso]
  REGLA  particion  cada vertice en una sola particion de body-part
  REGLA  huesos     la pieza usa TODOS los huesos de la pieza vanilla. Perder
                    uno es perder una articulacion, sin error: sin Toe0 el
                    pie no rueda al caminar
  OBS    distancia  a que distancia quedo cada vertice nuevo del vanilla
                    mas cercano; lejos, la copia de pesos no significa nada
"""
import math
import sys

try:
    import numpy as np
except ImportError:          # CI y la skill empaquetada pueden no tenerlo
    np = None

# Un grupo de vertices que empieza asi es una particion de body-part, no un
# hueso: es el nombre que le pone PyNifly al importar (SBP_32_BODY).
PREFIJO_PARTICION = "SBP_"

# [INVARIANT] Un vertice skinneado de BSTriShape (SSE) guarda 4 indices de
# hueso y 4 pesos.
MAX_HUESOS_POR_VERTICE = 4

TOLERANCIA_SUMA = 0.01


class MontajeError(ValueError):
    pass


# ---------------------------------------------------------------------------
# algebra minima
# ---------------------------------------------------------------------------

def identidad():
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def traslacion(t):
    m = identidad()
    for i in range(3):
        m[i][3] = float(t[i])
    return m


def de_3x3(r):
    m = identidad()
    for i in range(3):
        for j in range(3):
            m[i][j] = float(r[i][j])
    return m


def multiplicar(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)]
            for i in range(4)]


def componer(*ms):
    """componer(A, B, C) = A @ B @ C: C se aplica primero."""
    out = identidad()
    for m in ms:
        out = multiplicar(out, m)
    return out


def aplicar(m, puntos):
    return [tuple(m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3]
                  for i in range(3)) for p in puntos]


def determinante(m):
    """Del bloque 3x3: negativo = la matriz espeja (invierte las caras)."""
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def _resta(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _punto(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cruz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norma(a):
    return math.sqrt(_punto(a, a))


def _unitario(a):
    n = _norma(a)
    if n < 1e-12:
        raise MontajeError("vector nulo: %r" % (a,))
    return (a[0] / n, a[1] / n, a[2] / n)


def rotacion_eje(u, ang):
    """Rodrigues: giro de `ang` radianes alrededor del unitario `u`."""
    x, y, z = u
    c, s, t = math.cos(ang), math.sin(ang), 1 - math.cos(ang)
    return [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
            [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
            [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]


def rotacion_entre(u, w):
    """La rotacion minima que lleva el unitario `u` al unitario `w`.

    Con u y w opuestos la rotacion minima no es unica: se gira 180 grados
    alrededor de un eje perpendicular cualquiera.
    """
    c = max(-1.0, min(1.0, _punto(u, w)))
    eje = _cruz(u, w)
    if _norma(eje) < 1e-9:
        if c > 0:
            return rotacion_eje((1.0, 0.0, 0.0), 0.0)
        otro = (1.0, 0.0, 0.0) if abs(u[0]) < 0.9 else (0.0, 1.0, 0.0)
        return rotacion_eje(_unitario(_cruz(u, otro)), math.pi)
    return rotacion_eje(_unitario(eje), math.acos(c))


def _mat3_vec(r, v):
    return tuple(r[i][0] * v[0] + r[i][1] * v[1] + r[i][2] * v[2]
                 for i in range(3))


def _mat3_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
            for i in range(3)]


# ---------------------------------------------------------------------------
# montaje
# ---------------------------------------------------------------------------

ESCALAS_SEGMENTO = ("eje", "uniforme")
ESCALAS_CAJA = ("contener", "llenar", "ejes")


def ajuste_segmento(a, b, A, B, escala="eje", frente=None,
                    frente_destino=(0.0, 1.0, 0.0)):
    """(M, notas): M lleva el segmento a->b de la parte al A->B del donante.

    escala "eje": estira solo a lo largo del segmento (el grosor queda);
    "uniforme": escala pareja. `frente`, si viene, fija el giro alrededor del
    eje (ver la cabecera).
    """
    if escala not in ESCALAS_SEGMENTO:
        raise MontajeError("escala %r: se admite %s" % (escala,
                                                         ESCALAS_SEGMENTO))
    v, w = _resta(b, a), _resta(B, A)
    if _norma(v) < 1e-9 or _norma(w) < 1e-9:
        raise MontajeError("segmento de largo cero: desde y hasta son el "
                           "mismo punto (parte %r->%r, destino %r->%r)"
                           % (a, b, A, B))
    u, wu = _unitario(v), _unitario(w)
    k = _norma(w) / _norma(v)
    if escala == "eje":
        s = [[(1.0 if i == j else 0.0) + (k - 1.0) * u[i] * u[j]
              for j in range(3)] for i in range(3)]
    else:
        s = [[k if i == j else 0.0 for j in range(3)] for i in range(3)]
    r = rotacion_entre(u, wu)
    notas = []
    if frente is not None:
        f = _mat3_vec(r, frente)
        fp = _resta(f, tuple(_punto(f, wu) * c for c in wu))
        dp = _resta(frente_destino,
                    tuple(_punto(frente_destino, wu) * c for c in wu))
        if _norma(fp) < 0.1 * _norma(f) or _norma(dp) < 0.1:
            # Pedir una direccion y no poder cumplirla no es una nota: el
            # giro quedaria en la rotacion minima y la pieza, girada sin
            # aviso. Medido en --falsificar: el pie del centurion (largo en
            # Y) volvio corrido 26 unidades con "frente".
            raise MontajeError(
                "la direccion de giro es casi paralela al eje de la pieza: "
                "no fija el giro. Usa la otra (%s)"
                % ("arriba" if frente_destino[1] else "frente"))
        else:
            fp, dp = _unitario(fp), _unitario(dp)
            ang = math.atan2(_punto(_cruz(fp, dp), wu), _punto(fp, dp))
            r = _mat3_mul(rotacion_eje(wu, ang), r)
    m = componer(traslacion(A), de_3x3(_mat3_mul(r, s)),
                 traslacion(tuple(-c for c in a)))
    return m, notas


def caja(puntos):
    """((xmin, ymin, zmin), (xmax, ymax, zmax))."""
    if not puntos:
        raise MontajeError("caja de una pieza sin vertices")
    return (tuple(min(p[i] for p in puntos) for i in range(3)),
            tuple(max(p[i] for p in puntos) for i in range(3)))


def ajuste_caja(caja_parte, caja_destino, escala="contener"):
    """(M, notas): lleva la caja de la parte a la de la pieza vanilla.

    "contener": escala pareja, la menor de las tres razones: la parte entra
    en la caja vanilla sin pasarse en ningun eje. "llenar": la mayor. "ejes":
    una razon por eje, deforma. Los centros coinciden.
    """
    if escala not in ESCALAS_CAJA:
        raise MontajeError("escala %r: se admite %s" % (escala, ESCALAS_CAJA))
    dp = [caja_parte[1][i] - caja_parte[0][i] for i in range(3)]
    dd = [caja_destino[1][i] - caja_destino[0][i] for i in range(3)]
    razones = [dd[i] / dp[i] if dp[i] > 1e-9 else None for i in range(3)]
    validas = [x for x in razones if x is not None]
    if not validas:
        raise MontajeError("la parte no tiene tamano en ningun eje")
    notas = []
    if escala == "ejes":
        diag = [x if x is not None else 1.0 for x in razones]
        if max(validas) > 1.5 * min(validas):
            notas.append("escala por eje dispar (%.2f a %.2f): la pieza se "
                         "deforma" % (min(validas), max(validas)))
    else:
        k = min(validas) if escala == "contener" else max(validas)
        diag = [k, k, k]
    cp = [(caja_parte[0][i] + caja_parte[1][i]) / 2 for i in range(3)]
    cd = [(caja_destino[0][i] + caja_destino[1][i]) / 2 for i in range(3)]
    s = [[diag[i] if i == j else 0.0 for j in range(3)] for i in range(3)]
    return componer(traslacion(cd), de_3x3(s),
                    traslacion(tuple(-c for c in cp))), notas


def espejo_x():
    """X -> -X. Espeja: las caras quedan del reves y hay que invertirlas."""
    m = identidad()
    m[0][0] = -1.0
    return m


# ---------------------------------------------------------------------------
# el plan
# ---------------------------------------------------------------------------

EXT_PARTE = (".obj", ".glb", ".gltf", ".blend")
_CLAVES_PLAN = {"donante", "esqueleto", "salida", "piezas"}
_CLAVES_PIEZA = {"parte", "objeto", "modo", "desde", "hasta", "huesos",
                 "frente", "arriba", "escala", "espejar"}

# La direccion del juego a la que apunta cada forma de fijar el giro.
DIRECCIONES_GIRO = {"frente": (0.0, 1.0, 0.0), "arriba": (0.0, 0.0, 1.0)}


def _es_punto(x):
    return (isinstance(x, (list, tuple)) and len(x) == 3
            and all(isinstance(c, (int, float)) and not isinstance(c, bool)
                    and math.isfinite(c) for c in x))


def validar_plan(plan):
    """Lista de problemas del plan (vacia = sirve). Junta TODOS de una vez:
    un plan de 15 piezas no se corrige de a un error por corrida de Blender.
    Una clave desconocida es un problema: un "escla" mal escrito caeria en
    silencio al valor por defecto."""
    p = []
    if not isinstance(plan, dict):
        return ["el plan no es un objeto JSON"]
    for k in sorted(set(plan) - _CLAVES_PLAN):
        p.append("clave desconocida en el plan: %r" % k)
    for k in ("donante", "salida"):
        if not isinstance(plan.get(k), str) or \
                not plan[k].lower().endswith(".nif"):
            p.append("%s: tiene que ser la ruta de un .nif" % k)
    if "esqueleto" in plan and (not isinstance(plan["esqueleto"], str) or
                                not plan["esqueleto"].lower().endswith(".nif")):
        p.append("esqueleto: tiene que ser la ruta de un .nif")
    if isinstance(plan.get("donante"), str) and \
            plan.get("donante") == plan.get("salida"):
        p.append("salida: es el mismo archivo que el donante; se pisaria el "
                 "vanilla con el que se compara")
    piezas = plan.get("piezas")
    if not isinstance(piezas, dict) or not piezas:
        p.append("piezas: hace falta al menos una, {nombre del shape: {...}}")
        return p
    for nombre, pz in sorted(piezas.items()):
        pre = "pieza %r: " % nombre
        if not isinstance(pz, dict):
            p.append(pre + "no es un objeto")
            continue
        for k in sorted(set(pz) - _CLAVES_PIEZA):
            p.append(pre + "clave desconocida %r" % k)
        parte = pz.get("parte")
        if not isinstance(parte, str) or \
                not parte.lower().endswith(EXT_PARTE):
            p.append(pre + "parte: ruta a %s" % "/".join(EXT_PARTE))
        if "espejar" in pz and not isinstance(pz["espejar"], bool):
            p.append(pre + "espejar: true o false")
        modo = pz.get("modo")
        if modo == "segmento":
            for k in ("desde", "hasta"):
                if not _es_punto(pz.get(k)):
                    p.append(pre + "%s: un punto [x, y, z] de la parte" % k)
            h = pz.get("huesos")
            if not (isinstance(h, list) and len(h) == 2 and
                    all(isinstance(x, str) or _es_punto(x) for x in h)):
                p.append(pre + "huesos: [desde, hasta], cada uno el nombre "
                               "de un hueso o un punto [x, y, z]")
            for k in DIRECCIONES_GIRO:
                if k in pz and not _es_punto(pz[k]):
                    p.append(pre + "%s: una direccion [x, y, z]" % k)
            if all(k in pz for k in DIRECCIONES_GIRO):
                p.append(pre + "frente y arriba a la vez: el giro se fija "
                               "con una sola")
            if pz.get("escala", "eje") not in ESCALAS_SEGMENTO:
                p.append(pre + "escala: %s" % " o ".join(ESCALAS_SEGMENTO))
        elif modo == "caja":
            for k in ("desde", "hasta", "huesos", "frente", "arriba"):
                if k in pz:
                    p.append(pre + "%s no se usa en modo caja" % k)
            if pz.get("escala", "contener") not in ESCALAS_CAJA:
                p.append(pre + "escala: %s" % ", ".join(ESCALAS_CAJA))
        else:
            p.append(pre + "modo: \"segmento\" o \"caja\"")
    return p


# ---------------------------------------------------------------------------
# rig
# ---------------------------------------------------------------------------

def vecinos(nuevos, donante):
    """(indice del vertice del donante mas cercano, distancia) por vertice
    nuevo. Con numpy si esta; el resultado es el mismo (ante un empate, el
    indice menor)."""
    if not donante:
        raise MontajeError("el donante no tiene vertices")
    if np is not None:
        d = np.asarray(donante, dtype=np.float64)
        n = np.asarray(nuevos, dtype=np.float64).reshape(-1, 3)
        # Cada tanda es (tanda, donante, 3) floats: se la limita a ~24 MB
        # para que un donante de 20.000 vertices no pida 1 GB por tanda.
        tanda = max(1, 1000000 // len(d))
        idx, dist = [], []
        for i in range(0, len(n), tanda):
            t = n[i:i + tanda]
            d2 = ((t[:, None, :] - d[None, :, :]) ** 2).sum(-1)
            k = d2.argmin(1)
            idx.extend(int(x) for x in k)
            dist.extend(float(math.sqrt(x)) for x in d2[np.arange(len(t)), k])
        return idx, dist
    idx, dist = [], []
    for p in nuevos:
        mejor, md = 0, None
        for j, q in enumerate(donante):
            dd = ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                  + (p[2] - q[2]) ** 2)
            if md is None or dd < md:
                mejor, md = j, dd
        idx.append(mejor)
        dist.append(math.sqrt(md))
    return idx, dist


def pesos_por_vecino(nuevos, donante, pesos_donante):
    """(pesos, distancias): cada vertice nuevo copia el dict {grupo: peso} del
    vertice vanilla mas cercano, particiones incluidas."""
    if len(donante) != len(pesos_donante):
        raise MontajeError("donante con %d vertices y %d juegos de pesos"
                           % (len(donante), len(pesos_donante)))
    idx, dist = vecinos(nuevos, donante)
    return [dict(pesos_donante[i]) for i in idx], dist


def es_particion(grupo):
    return grupo.startswith(PREFIJO_PARTICION)


def controles_pesos(pesos, huesos_donante, distancias=None, diagonal=None):
    """(fallas, notas) sobre los pesos de una pieza ya montada."""
    fallas, notas = [], []
    if not pesos:
        return ["la pieza no tiene vertices: no hay nada que controlar"], notas
    mal_suma = mas_de_4 = sin_part = varias_part = 0
    usados = set()
    for p in pesos:
        huesos = {g: w for g, w in p.items() if not es_particion(g) and w > 0}
        parts = [g for g, w in p.items() if es_particion(g) and w > 0]
        usados.update(huesos)
        if abs(sum(huesos.values()) - 1.0) > TOLERANCIA_SUMA:
            mal_suma += 1
        if len(huesos) > MAX_HUESOS_POR_VERTICE:
            mas_de_4 += 1
        if not parts:
            sin_part += 1
        elif len(parts) > 1:
            varias_part += 1
    n = len(pesos)
    if mal_suma:
        fallas.append("REGLA suma: %d de %d vertices con pesos que no suman 1"
                      % (mal_suma, n))
    if mas_de_4:
        fallas.append("REGLA max4: %d vertices con mas de %d huesos; el "
                      "vertice de BSTriShape guarda %d"
                      % (mas_de_4, MAX_HUESOS_POR_VERTICE,
                         MAX_HUESOS_POR_VERTICE))
    if sin_part or varias_part:
        fallas.append("REGLA particion: %d vertices sin particion y %d en mas "
                      "de una" % (sin_part, varias_part))
    faltan = sorted(set(huesos_donante) - usados)
    if faltan:
        fallas.append("REGLA huesos: la pieza no usa %s, que la vanilla si. "
                      "Es una articulacion perdida, y no da error"
                      % ", ".join(faltan))
    sobran = sorted(usados - set(huesos_donante))
    if sobran:
        fallas.append("REGLA huesos: la pieza usa %s, que la vanilla no"
                      % ", ".join(sobran))
    if distancias:
        orden = sorted(distancias)
        med, peor = orden[len(orden) // 2], orden[-1]
        txt = "OBS distancia al vanilla: mediana %.3g, maxima %.3g" % (med,
                                                                        peor)
        if diagonal:
            txt += " (%.1f %% y %.1f %% de la diagonal de la pieza vanilla)" % (
                100.0 * med / diagonal, 100.0 * peor / diagonal)
        notas.append(txt)
    return fallas, notas


# ---------------------------------------------------------------------------
# autotest
# ---------------------------------------------------------------------------

def _cerca(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def autotest():
    fallas = []
    hechas = [0]

    def exigir(cond, texto):
        hechas[0] += 1
        if not cond:
            fallas.append(texto)

    # a. segmento: los extremos caen donde tienen que caer, en los dos modos
    a, b = (0.0, 0.0, 0.0), (0.0, 0.0, 2.0)
    A, B = (10.0, 5.0, 3.0), (10.0, 9.0, 3.0)
    for modo in ESCALAS_SEGMENTO:
        m, _n = ajuste_segmento(a, b, A, B, modo)
        pa, pb = aplicar(m, [a, b])
        exigir(_cerca(pa, A) and _cerca(pb, B),
               "segmento %s: los extremos no caen en los huesos" % modo)

    # b. "eje" conserva el grosor; "uniforme" lo escala igual que el largo
    lado = (1.0, 0.0, 1.0)            # a 1 del eje, a mitad del segmento
    m_eje, _n = ajuste_segmento(a, b, A, B, "eje")
    m_uni, _n = ajuste_segmento(a, b, A, B, "uniforme")
    centro = (10.0, 7.0, 3.0)
    d_eje = _norma(_resta(aplicar(m_eje, [lado])[0], centro))
    d_uni = _norma(_resta(aplicar(m_uni, [lado])[0], centro))
    exigir(abs(d_eje - 1.0) < 1e-6,
           "eje: el grosor cambio (%.4f, se esperaba 1)" % d_eje)
    exigir(abs(d_uni - 2.0) < 1e-6,
           "uniforme: el grosor no se escalo x2 (%.4f)" % d_uni)

    # c. segmentos opuestos: la rotacion de 180 grados no degenera
    m, _n = ajuste_segmento((0, 0, 0), (0, 0, 1), (0, 0, 0), (0, 0, -1),
                            "uniforme")
    exigir(_cerca(aplicar(m, [(0, 0, 1)])[0], (0, 0, -1)),
           "segmento invertido: el extremo no llego")

    # d. frente: un giro arbitrario alrededor del eje se deshace
    r = rotacion_eje((0.0, 0.0, 1.0), 1.1)
    frente_girado = _mat3_vec(r, (0.0, 1.0, 0.0))
    m, notas = ajuste_segmento((0, 0, 0), (0, 0, 1), (0, 0, 0), (0, 0, 1),
                               "uniforme", frente=frente_girado)
    exigir(_cerca(aplicar(m, [frente_girado])[0], (0.0, 1.0, 0.0)) and
           not notas, "frente: el giro alrededor del eje no se deshizo")

    # e. caja: centros y escala
    cp = ((0.0, 0.0, 0.0), (1.0, 2.0, 4.0))
    cdst = ((10.0, 10.0, 10.0), (12.0, 16.0, 14.0))
    m, _n = ajuste_caja(cp, cdst, "contener")
    exigir(_cerca(aplicar(m, [(0.5, 1.0, 2.0)])[0], (11.0, 13.0, 12.0)),
           "caja: los centros no coinciden")
    cm = caja(aplicar(m, [cp[0], cp[1]]))
    exigir(all(cm[1][i] - cm[0][i] <= cdst[1][i] - cdst[0][i] + 1e-9
               for i in range(3)), "contener: la parte se pasa de la caja")
    m, _n = ajuste_caja(cp, cdst, "ejes")
    exigir(_cerca(caja(aplicar(m, [cp[0], cp[1]]))[0], cdst[0]) and
           _cerca(caja(aplicar(m, [cp[0], cp[1]]))[1], cdst[1]),
           "ejes: la caja no quedo igual a la vanilla")

    # f. espejo: determinante negativo, y el montaje no lo esconde
    exigir(determinante(espejo_x()) < 0, "espejo: determinante no negativo")
    m, _n = ajuste_segmento(a, b, A, B, "eje")
    exigir(determinante(componer(m, espejo_x())) < 0,
           "espejo compuesto con el montaje: se perdio el signo")

    # g. pesos por vecino
    donante = [(0.0, 0.0, 0.0), (0.0, 0.0, 10.0)]
    pd = [{"Muslo": 1.0, "SBP_32_BODY": 1.0},
          {"Pantorrilla": 1.0, "SBP_32_BODY": 1.0}]
    nuevos = [(0.1, 0.0, 1.0), (0.0, 0.2, 9.0), (0.0, 0.0, 5.0)]
    p, dist = pesos_por_vecino(nuevos, donante, pd)
    exigir(p[0].get("Muslo") == 1.0 and p[1].get("Pantorrilla") == 1.0,
           "vecino: el peso no vino del vertice mas cercano")
    exigir(p[2].get("Muslo") == 1.0, "vecino: el empate no dio el indice menor")
    p[0]["Muslo"] = 0.5
    exigir(pd[0]["Muslo"] == 1.0, "vecino: los pesos del donante se pisaron")

    # h. controles
    bien = [{"Muslo": 1.0, "SBP_32_BODY": 1.0}] * 3
    f, _n = controles_pesos(bien, ["Muslo"])
    exigir(not f, "controles: una pieza sana reprobo: %s" % f)
    f, _n = controles_pesos(bien, ["Muslo", "Dedo"])
    exigir(any("Dedo" in x for x in f), "controles: el hueso perdido no se vio")
    f, _n = controles_pesos([{"Muslo": 0.7, "SBP_32_BODY": 1.0}], ["Muslo"])
    exigir(any("REGLA suma" in x for x in f), "controles: la suma no se vio")
    cinco = dict(("H%d" % i, 0.2) for i in range(5))
    cinco["SBP_32_BODY"] = 1.0
    f, _n = controles_pesos([cinco], ["H%d" % i for i in range(5)])
    exigir(any("REGLA max4" in x for x in f), "controles: 5 huesos no se vio")
    f, _n = controles_pesos([{"Muslo": 1.0}], ["Muslo"])
    exigir(any("REGLA particion" in x for x in f),
           "controles: sin particion no se vio")
    f, _n = controles_pesos([], ["Muslo"])
    exigir(f, "controles: una pieza vacia paso")

    # i. el plan
    bueno = {"donante": "v.nif", "salida": "n.nif", "piezas": {
        "Muslo": {"parte": "m.obj", "modo": "segmento", "desde": [0, 0, 0],
                  "hasta": [0, 0, 1], "huesos": ["NPC L Thigh", [0, 0, 5]]},
        "Cabeza": {"parte": "c.glb", "modo": "caja", "escala": "llenar"}}}
    exigir(validar_plan(bueno) == [], "plan: uno bueno tuvo problemas: %s"
           % validar_plan(bueno))
    malo = {"donante": "v.nif", "salida": "v.nif", "extra": 1, "piezas": {
        "A": {"parte": "a.fbx", "modo": "segmento", "desde": [0, 0],
              "hasta": [0, 0, 1], "huesos": ["x"], "escla": "eje"},
        "B": {"parte": "b.obj", "modo": "caja", "huesos": ["x", "y"]},
        "C": {"parte": "c.obj", "modo": "rigido"}}}
    problemas = validar_plan(malo)
    for trozo in ("'extra'", "mismo archivo", "'escla'", "parte:", "desde:",
                  "huesos:", "no se usa en modo caja", "modo:"):
        exigir(any(trozo in x for x in problemas),
               "plan: no se vio %r en %s" % (trozo, problemas))

    if not hechas[0]:
        print("autotest: NO se comprobo NADA")
        return 1
    print("autotest: %d comprobaciones, %d fallas%s"
          % (hechas[0], len(fallas),
             "" if np is not None else " (sin numpy: vecinos en Python puro)"))
    for x in fallas:
        print("  FALLA %s" % x)
    return 1 if fallas else 0


def main(argv):
    if argv == ["--autotest"]:
        return autotest()
    print(__doc__.strip().splitlines()[0])
    print("uso: montaje_puro.py --autotest")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
