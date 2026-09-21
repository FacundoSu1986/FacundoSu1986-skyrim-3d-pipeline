# -*- coding: utf-8 -*-
"""Mide si la malla se ROMPIO al decimarla. Python puro, sin Blender.

    python scripts/salud_malla.py <archivo>              informe
    python scripts/salud_malla.py <antes> <despues>      REGLA
    python scripts/salud_malla.py --autotest
    python scripts/salud_malla.py --falsificar <carpeta meshes>

Lee .nif (shapes estaticos) y .obj. Exit 0 si pasa, 1 si no pasa o si no hubo
NADA que medir, 2 si los argumentos no sirven.

POR QUE EXISTE

Un modelo de Tripo/Meshy trae los vertices PARTIDOS por cada costura del atlas
de UV. Para el modificador Decimate una costura sin soldar es un borde de
malla, y los bordes se conservan como bordes: cada isla queda como un parche
suelto. Con un atlas de una isla por triangulo eso rasga el modelo entero, y
nada da error -- el archivo se escribe bien, el juego lo carga, y el arma se ve
con agujeros por los que se ve el interior.

Medido en el hacha de Tencent: el GLB de origen tenia 1.500.000 triangulos,
ratio tri/vert 2,00 exacto y CERO aristas de borde. El OBJ decimado sin soldar
quedo con el 49,4 % de sus aristas abiertas, y la malla que llego al juego con
el 35,2 %. Soldando primero, la misma decimacion a 8.000 triangulos salio con
0 bordes y 1 pieza.

POR QUE LA REGLA NO ES "LA MALLA TIENE QUE ESTAR CERRADA"

Porque es falso, y escribirla asi habria bloqueado assets legitimos. Medido
sobre 1.347 shapes de una muestra de 700 NIF del corpus vanilla:

    cerradas (borde < 0,5 %)   15,1 %
    borde %  p25 4,5   mediana 15,4   p75 26,7   p90 38,8
    architecture: mediana 24,7 %, solo el 2,6 % cerradas
    actors:       mediana  1,6 %, el 36,4 % cerradas

La ropa, los carteles, las laminas de vegetacion y casi toda la arquitectura
son superficies abiertas a proposito. Lo que NO puede pasar es que decimar
ABRA lo que estaba cerrado. Por eso la regla es relacional.

CON QUE NUMERO ATRAS

Decimando 14 shapes vanilla al 25 % de sus triangulos, de las dos formas:

    soldando primero   el numero de aristas de borde NUNCA aumento
                       peor caso x0,70; las dos mallas cerradas siguieron en 0
    directo            crecio en 12 de los 14, hasta x25,5
                       y las dos cerradas pasaron de 0 a 956 y a 544 bordes

  REGLA  borde        el numero de aristas de borde no puede aumentar
  OBS    ratio        tri/vert soldado (~2 = cerrada, ~1 = sopa de triangulos)
  OBS    piezas       componentes conexas por posicion soldada
  OBS    no_manifold  aristas usadas por 3 triangulos o mas
  OBS    winding      aristas que sus dos triangulos recorren en el mismo
                      sentido (una de las dos caras queda invisible)

Las cuatro OBSERVACIONES se informan y no reprueban: no estan medidas sobre el
corpus con la densidad que hace falta para bloquear. Medirlas es trabajo
pendiente, no una regla implicita.

POR QUE SE SUELDA ANTES DE CONTAR

Contar aristas por indice de vertice en un NIF no mide nada: los vertices de
costura estan duplicados, asi que dos triangulos vecinos no comparten indice y
toda arista parece de borde. En el hacha eso daba 2.953 piezas donde habia
382, y 382 donde en realidad habia 1. Primero se sueldan las posiciones.
"""
import os
import struct
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import censo_nif  # noqa: E402

# Tolerancia de soldadura, relativa al lado mayor de la malla. 2e-5 junta lo
# que es el mismo punto escrito dos veces y no junta detalle real: sobre una
# malla de 100 unidades son 0,002 unidades.
SOLDAR_FRACCION = 2e-5

# Un shape con menos de esto no dice nada: un cartel de dos triangulos tiene el
# 100 % de aristas de borde y esta perfecto.
MIN_TRIANGULOS = 12


# --------------------------------------------------------------------------
# medicion
# --------------------------------------------------------------------------
def soldar(pos, fraccion=SOLDAR_FRACCION):
    """Indice de vertice soldado por POSICION. Devuelve (lista, n_unicos)."""
    finitos = [p for p in pos if all(-1e9 < c < 1e9 for c in p)]
    if not finitos:
        return None, 0
    dim = max(max(p[k] for p in finitos) - min(p[k] for p in finitos)
              for k in range(3))
    if dim <= 0:
        return None, 0
    esc = 1.0 / (dim * fraccion)
    mapa = {}
    w = []
    for p in pos:
        if not all(-1e9 < c < 1e9 for c in p):
            w.append(None)
            continue
        k = (round(p[0] * esc), round(p[1] * esc), round(p[2] * esc))
        if k not in mapa:
            mapa[k] = len(mapa)
        w.append(mapa[k])
    return w, len(mapa)


def salud(pos, tris, min_triangulos=MIN_TRIANGULOS):
    """Las cinco medidas, sobre vertices soldados. None si no hay nada que
    medir (sin posiciones finitas, o menos de min_triangulos).

    El minimo es parametro para que el autotest pueda medir figuras chicas sin
    aflojar el que usa la herramienta de verdad."""
    if not pos or not tris:
        return None
    w, n_soldados = soldar(pos)
    if w is None or not n_soldados:
        return None

    sin_dir = defaultdict(int)
    dirigidas = defaultdict(int)
    adj = defaultdict(set)
    n_tri = 0
    degenerados = 0
    fuera_de_rango = 0
    for t in tris:
        if any(i >= len(w) for i in t):
            fuera_de_rango += 1
            continue
        a, b, c = w[t[0]], w[t[1]], w[t[2]]
        if a is None or b is None or c is None:
            fuera_de_rango += 1
            continue
        if a == b or b == c or a == c:
            degenerados += 1
            continue
        n_tri += 1
        for x, y in ((a, b), (b, c), (c, a)):
            sin_dir[(x, y) if x < y else (y, x)] += 1
            dirigidas[(x, y)] += 1
            adj[x].add(y)
            adj[y].add(x)
    if n_tri < min_triangulos or not sin_dir:
        return None

    borde = sum(1 for n in sin_dir.values() if n == 1)
    no_manifold = sum(1 for n in sin_dir.values() if n > 2)
    # Dos triangulos que comparten una arista tienen que recorrerla al reves.
    # Si los dos la recorren igual, uno esta dado vuelta. Hay que mirar los DOS
    # sentidos: la primera version solo contaba dirigidas[(min,max)] == 2 y se
    # perdia el par que recorre ambos de mayor a menor. Lo pesco el autotest --
    # un triangulo invertido en el cubo daba 2 aristas donde son 3.
    winding = sum(1 for (x, y), n in sin_dir.items()
                  if n == 2 and (dirigidas[(x, y)] == 2
                                 or dirigidas[(y, x)] == 2))

    vistos = set()
    piezas = 0
    for semilla in adj:
        if semilla in vistos:
            continue
        piezas += 1
        pila = [semilla]
        vistos.add(semilla)
        while pila:
            u = pila.pop()
            for v in adj[u]:
                if v not in vistos:
                    vistos.add(v)
                    pila.append(v)

    return {"verts": len(pos), "soldados": n_soldados, "tris": n_tri,
            "aristas": len(sin_dir), "borde": borde,
            "borde_pct": 100.0 * borde / len(sin_dir),
            "ratio": n_tri / float(n_soldados), "no_manifold": no_manifold,
            "winding": winding, "piezas": piezas,
            "degenerados": degenerados, "fuera_de_rango": fuera_de_rango}


def total(medidas):
    """Suma de shapes medibles, para comparar archivo contra archivo.

    Se compara el TOTAL y no shape por shape porque decimar puede unir o
    partir shapes, y entonces los nombres ya no aparean.
    """
    if not medidas:
        return None
    campos = ("verts", "soldados", "tris", "aristas", "borde", "no_manifold",
              "winding", "piezas", "degenerados", "fuera_de_rango")
    out = dict((c, sum(m[c] for m in medidas)) for c in campos)
    out["shapes"] = len(medidas)
    out["borde_pct"] = (100.0 * out["borde"] / out["aristas"]
                        if out["aristas"] else 0.0)
    out["ratio"] = (out["tris"] / float(out["soldados"])
                    if out["soldados"] else 0.0)
    return out


def comparar(antes, despues):
    """(fallas, notas). La REGLA: el borde no puede aumentar."""
    fallas, notas = [], []
    if antes is None or despues is None:
        fallas.append("no hubo nada que medir en uno de los dos archivos")
        return fallas, notas
    if despues["borde"] > antes["borde"]:
        fallas.append(
            "REGLA borde: %d aristas de borde contra %d del origen (x%.1f). "
            "La malla se ABRIO. Decimando 14 shapes vanilla al 25 %%, soldar "
            "antes de decimar nunca aumento el borde (peor caso x0,70); "
            "decimar directo lo multiplico hasta x25,5."
            % (despues["borde"], antes["borde"],
               despues["borde"] / float(antes["borde"])
               if antes["borde"] else float(despues["borde"])))
    for campo, texto in (("piezas", "piezas sueltas"),
                         ("no_manifold", "aristas no-manifold"),
                         ("winding", "aristas con winding incoherente")):
        if despues[campo] > antes[campo]:
            notas.append("OBS %s: %d contra %d del origen"
                         % (texto, despues[campo], antes[campo]))
    if despues["shapes"] != antes["shapes"]:
        notas.append("OBS shapes: %d contra %d del origen"
                     % (despues["shapes"], antes["shapes"]))
    notas.append("OBS ratio tri/vert: %.2f -> %.2f  (~2 cerrada, ~1 sopa)"
                 % (antes["ratio"], despues["ratio"]))
    return fallas, notas


# --------------------------------------------------------------------------
# lectura
# --------------------------------------------------------------------------
def _leer_obj(ruta):
    pos, tris = [], []
    with open(ruta, "r", errors="ignore") as fh:
        for linea in fh:
            if linea.startswith("v "):
                p = linea.split()
                pos.append((float(p[1]), float(p[2]), float(p[3])))
            elif linea.startswith("f "):
                idx = [int(t.split("/")[0]) - 1 for t in linea.split()[1:]]
                for i in range(1, len(idx) - 1):
                    tris.append((idx[0], idx[i], idx[i + 1]))
    return [{"nombre": os.path.basename(ruta), "pos": pos, "tris": tris}]


def leer(ruta):
    """([medidas], [avisos]). Un shape que no se pudo medir sale en avisos: no
    se omite en silencio."""
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".obj":
        shapes = _leer_obj(ruta)
    elif ext == ".nif":
        shapes = censo_nif.Nif(ruta).geometria()
    else:
        raise SystemExit("extension no soportada: %s (.nif o .obj)" % ext)

    medidas, avisos = [], []
    for s in shapes:
        if s.get("error"):
            avisos.append("%s: %s" % (s.get("nombre", "?"), s["error"]))
            continue
        m = salud(s.get("pos"), s.get("tris"))
        if m is None:
            avisos.append("%s: sin geometria medible (menos de %d triangulos "
                          "utiles)" % (s.get("nombre", "?"), MIN_TRIANGULOS))
            continue
        m["nombre"] = s.get("nombre", "?")
        medidas.append(m)
    return medidas, avisos


def informe(ruta):
    medidas, avisos = leer(ruta)
    print("== %s" % os.path.basename(ruta))
    for m in medidas:
        print("   %-24s verts %6d->%-6d tris %6d  ratio %.2f  borde %5d "
              "(%.1f%%)  nm %d  winding %d  piezas %d"
              % (m["nombre"][:24], m["verts"], m["soldados"], m["tris"],
                 m["ratio"], m["borde"], m["borde_pct"], m["no_manifold"],
                 m["winding"], m["piezas"]))
    for a in avisos:
        print("   AVISO %s" % a)
    return medidas, avisos


# --------------------------------------------------------------------------
# autotest: enumera la familia, no el caso que ya encontramos
# --------------------------------------------------------------------------
def _cubo():
    """Cubo cerrado: 8 vertices, 12 triangulos, winding coherente hacia
    afuera."""
    pos = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
           (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
    tris = [(0, 2, 1), (0, 3, 2),        # z-
            (4, 5, 6), (4, 6, 7),        # z+
            (0, 1, 5), (0, 5, 4),        # y-
            (2, 3, 7), (2, 7, 6),        # y+
            (1, 2, 6), (1, 6, 5),        # x+
            (0, 4, 7), (0, 7, 3)]        # x-
    return pos, tris


def _partir_por_costura(pos, tris):
    """Cada triangulo con sus PROPIOS vertices: ningun indice compartido.
    Es lo que hace un exportador con una isla de UV por triangulo."""
    p2, t2 = [], []
    for a, b, c in tris:
        base = len(p2)
        p2.extend([pos[a], pos[b], pos[c]])
        t2.append((base, base + 1, base + 2))
    return p2, t2


def autotest():
    fallas = []

    def exigir(cond, texto):
        if not cond:
            fallas.append(texto)

    pos, tris = _cubo()
    m = salud(pos, tris, 1)
    exigir(m is not None, "el cubo cerrado no se pudo medir")
    exigir(m["borde"] == 0, "cubo cerrado: borde %d, se esperaba 0" % m["borde"])
    exigir(m["aristas"] == 18, "cubo: %d aristas, se esperaban 18" % m["aristas"])
    exigir(m["ratio"] == 1.5, "cubo: ratio %.2f (12 tri / 8 vert)" % m["ratio"])
    exigir(m["piezas"] == 1, "cubo: %d piezas" % m["piezas"])
    exigir(m["no_manifold"] == 0, "cubo: %d no-manifold" % m["no_manifold"])
    exigir(m["winding"] == 0, "cubo: %d winding" % m["winding"])

    # el caso que importa: mismo cubo con los vertices partidos por costura.
    # Contando por indice pareceria 36 vertices y todo borde; soldando, es el
    # mismo cubo cerrado.
    pp, tt = _partir_por_costura(pos, tris)
    mp = salud(pp, tt, 1)
    exigir(mp["soldados"] == 8,
           "cubo partido: %d soldados, se esperaban 8" % mp["soldados"])
    exigir(mp["borde"] == 0,
           "cubo partido: borde %d tras soldar, se esperaba 0" % mp["borde"])
    exigir(mp["verts"] == 36, "cubo partido: %d verts crudos" % mp["verts"])

    # un agujero: sacar las dos caras de z-
    m_hueco = salud(pos, tris[2:], 1)
    exigir(m_hueco["borde"] == 4,
           "cubo con una cara menos: borde %d, se esperaban 4"
           % m_hueco["borde"])

    # dos cubos separados
    pos2 = pos + [(x + 10, y, z) for x, y, z in pos]
    tris2 = tris + [(a + 8, b + 8, c + 8) for a, b, c in tris]
    m2 = salud(pos2, tris2, 1)
    exigir(m2["piezas"] == 2, "dos cubos: %d piezas" % m2["piezas"])
    exigir(m2["borde"] == 0, "dos cubos: borde %d" % m2["borde"])

    # un triangulo dado vuelta: sus tres aristas quedan recorridas igual que
    # las del vecino
    tris_flip = list(tris)
    tris_flip[0] = (tris[0][0], tris[0][1], tris[0][2])[::-1]
    mf = salud(pos, tris_flip, 1)
    exigir(mf["winding"] == 3,
           "un triangulo invertido: winding %d, se esperaban 3" % mf["winding"])

    # triangulo degenerado: se descarta, no cuenta como triangulo
    md = salud(pos, tris + [(0, 0, 1)], 1)
    exigir(md["degenerados"] == 1,
           "degenerado: %d" % md["degenerados"])
    exigir(md["tris"] == m["tris"],
           "el degenerado se conto como triangulo")

    # tres triangulos sobre la misma arista
    m_nm = salud(pos + [(0.5, 0.5, 2.0)], tris + [(0, 1, 8)], 1)
    exigir(m_nm["no_manifold"] == 1,
           "no-manifold: %d, se esperaba 1" % m_nm["no_manifold"])

    # --- la REGLA -----------------------------------------------------------
    cerrada = total([salud(pos, tris, 1)])
    rota = total([salud(*_partir_por_costura(pos, tris[2:]), min_triangulos=1)])
    f, _ = comparar(cerrada, rota)
    exigir(f, "cerrada -> rota: la REGLA no reprobo")

    f, _ = comparar(cerrada, total([salud(pos, tris, 1)]))
    exigir(not f, "misma malla contra si misma: la REGLA reprobo")

    abierta = total([salud(pos, tris[2:], 1)])           # borde 4
    mas_abierta = total([salud(pos, tris[4:], 1)])       # borde 8
    f, _ = comparar(abierta, mas_abierta)
    exigir(f, "abierta -> mas abierta: la REGLA no reprobo")
    f, _ = comparar(mas_abierta, abierta)
    exigir(not f, "abierta -> menos abierta: la REGLA reprobo (es valido)")

    f, _ = comparar(cerrada, None)
    exigir(f, "contra un archivo sin nada medible: la REGLA no reprobo")

    print("autotest: %d comprobaciones, %d fallas"
          % (18, len(fallas)))
    for x in fallas:
        print("  FALLA %s" % x)
    return 1 if fallas else 0


# --------------------------------------------------------------------------
# falsificar: mutar archivos REALES y exigir que el control los pesque
# --------------------------------------------------------------------------
def _triangulos_interiores(pos, tris):
    """Indices de los triangulos cuyas TRES aristas son interiores.

    Hace falta elegirlos: sacar o invertir un triangulo cualquiera no rompe
    nada comprobable. En boundarrow.nif, sacar el primero BAJABA el borde de 20
    a 19 --era una punta que ya aportaba dos aristas de borde--, asi que la
    mutacion no falsificaba nada. Lo pesco este mismo banco.
    """
    w, n = soldar(pos)
    if w is None:
        return []
    cuenta = defaultdict(int)
    for t in tris:
        if any(i >= len(w) or w[i] is None for i in t):
            continue
        a, b, c = w[t[0]], w[t[1]], w[t[2]]
        if a == b or b == c or a == c:
            continue
        for x, y in ((a, b), (b, c), (c, a)):
            cuenta[(x, y) if x < y else (y, x)] += 1
    fuera = []
    for i, t in enumerate(tris):
        if any(j >= len(w) or w[j] is None for j in t):
            continue
        a, b, c = w[t[0]], w[t[1]], w[t[2]]
        if a == b or b == c or a == c:
            continue
        if all(cuenta[(x, y) if x < y else (y, x)] == 2
               for x, y in ((a, b), (b, c), (c, a))):
            fuera.append(i)
    return fuera


def _rasgar(pos, tris):
    """Cada triangulo con sus propios vertices Y encogido hacia su centroide.

    Duplicar indices sin mover nada NO rompe la malla para este control, y esta
    bien que no la rompa: se mide soldando por posicion, asi que un vertice
    escrito dos veces en el mismo lugar sigue siendo el mismo vertice. Lo que
    rompe de verdad --y lo que hace una decimacion sin soldar-- es que las
    copias se SEPAREN. Por eso se encogen: el desplazamiento es 1e-3 del lado
    mayor, cincuenta veces la tolerancia de soldadura.
    """
    dim = max(max(p[k] for p in pos) - min(p[k] for p in pos)
              for k in range(3))
    salto = dim * 1e-3
    p2, t2 = [], []
    for t in tris:
        vs = [pos[i] for i in t]
        cx = sum(v[0] for v in vs) / 3.0
        cy = sum(v[1] for v in vs) / 3.0
        cz = sum(v[2] for v in vs) / 3.0
        base = len(p2)
        for v in vs:
            d = [cx - v[0], cy - v[1], cz - v[2]]
            n = max(1e-12, (d[0] ** 2 + d[1] ** 2 + d[2] ** 2) ** 0.5)
            p2.append((v[0] + d[0] / n * salto,
                       v[1] + d[1] / n * salto,
                       v[2] + d[2] / n * salto))
        t2.append((base, base + 1, base + 2))
    return p2, t2


def _mutaciones(pos, tris):
    """(nombre, pos, tris, que_tiene_que_crecer) para cada rotura."""
    interiores = _triangulos_interiores(pos, tris)
    yield ("rasgar",) + _rasgar(pos, tris) + ("borde",)
    if interiores:
        sin_uno = [t for i, t in enumerate(tris) if i != interiores[0]]
        yield ("agujerear", pos, sin_uno, "borde")
        volteado = list(tris)
        volteado[interiores[0]] = tuple(reversed(volteado[interiores[0]]))
        yield ("invertir un triangulo", pos, volteado, "winding")
    # El desplazamiento es 2x el lado mayor de la malla, no un numero grande.
    # La tolerancia de soldadura es RELATIVA a la caja: con una copia a 1e4
    # unidades la caja se dispara y la tolerancia pasa de 0,002 a 0,2, que
    # funde vertices distintos -- las piezas BAJABAN de 9 a 6 en vez de
    # duplicarse. Lo pesco este banco.
    dim = max(max(p[k] for p in pos) - min(p[k] for p in pos)
              for k in range(3))
    base = len(pos)
    pos2 = list(pos) + [(x + dim * 2.0, y, z) for x, y, z in pos]
    tris2 = list(tris) + [(a + base, b + base, c + base) for a, b, c in tris]
    yield ("duplicar al lado", pos2, tris2, "piezas")


def falsificar(raiz):
    archivos = []
    for base, _, nombres in os.walk(raiz):
        for n in sorted(nombres):
            if n.lower().endswith(".nif"):
                archivos.append(os.path.join(base, n))
    if not archivos:
        print("no hay .nif en %s" % raiz)
        return 1

    usados = 0
    roturas = 0
    fallas = []
    for ruta in archivos:
        if usados >= 10:
            break
        try:
            shapes = censo_nif.Nif(ruta).geometria()
        except Exception:
            continue
        bueno = None
        for s in shapes:
            if s.get("error"):
                continue
            m = salud(s.get("pos"), s.get("tris"))
            if m is not None and m["tris"] >= 200:
                bueno = (s["pos"], s["tris"], m)
                break
        if bueno is None:
            continue
        usados += 1
        pos, tris, m = bueno
        base_total = total([m])
        for nombre, p2, t2, campo in _mutaciones(pos, tris):
            roturas += 1
            m2 = salud(p2, t2)
            if m2 is None:
                fallas.append("%s / %s: la mutacion dejo la malla sin medir"
                              % (os.path.basename(ruta), nombre))
                continue
            if m2[campo] <= m[campo]:
                fallas.append("%s / %s: %s no crecio (%d -> %d)"
                              % (os.path.basename(ruta), nombre, campo,
                                 m[campo], m2[campo]))
            if campo == "borde":
                f, _ = comparar(base_total, total([m2]))
                if not f:
                    fallas.append("%s / %s: la REGLA no reprobo"
                                  % (os.path.basename(ruta), nombre))

    print("falsificar: %d archivos x %d roturas = %d comprobaciones, %d fallas"
          % (usados, roturas // max(1, usados), roturas, len(fallas)))
    for x in fallas:
        print("  FALLA %s" % x)
    if usados == 0:
        print("FALLA: cero archivos medibles -- no comprobar nada no es exito")
        return 1
    return 1 if fallas else 0


def main(argv):
    if len(argv) == 1 and argv[0] == "--autotest":
        return autotest()
    if len(argv) == 2 and argv[0] == "--falsificar":
        return falsificar(argv[1])
    if len(argv) == 1:
        medidas, avisos = informe(argv[0])
        return 0 if medidas else 1
    if len(argv) == 2:
        if os.path.abspath(argv[0]) == os.path.abspath(argv[1]):
            print("los dos caminos son el mismo archivo: no hay que comparar")
            return 2
        ma, aa = informe(argv[0])
        mb, ab = informe(argv[1])
        fallas, notas = comparar(total(ma), total(mb))
        print()
        for n in notas:
            print("   %s" % n)
        for f in fallas:
            print("   FALLA %s" % f)
        if not ma or not mb:
            print("   FALLA: no hubo nada que medir -- cero comprobaciones no "
                  "es exito")
            return 1
        return 1 if fallas else 0
    print(__doc__.strip().splitlines()[0])
    print("uso: salud_malla.py <archivo> | <antes> <despues> | --autotest | "
          "--falsificar <carpeta>")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
