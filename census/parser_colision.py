# -*- coding: utf-8 -*-
"""Geometria de colision y colocacion en el mundo, leidas del NIF.

    python parser_colision.py --autotest <carpeta meshes>
    python parser_colision.py <archivo.nif>

POR QUE EXISTE
--------------
El contrato de fixtures/comparar.py valida que un NIF este BIEN FORMADO. No
mira donde queda la cosa. Dos casos independientes mostraron que ese hueco es
caro:

  * el barrido de 1.857 estaticos por PyNifly: 112 mallas (6,03 %) quedaron en
    otro lugar y 56 de 615 colisiones se movieron, y el contrato dio verde;
  * un escudo modelado a mano salio con la colision a 6 unidades de la malla,
    y el contrato tambien dio verde.

LO QUE SE DECODIFICA, Y COMO SE FALSIFICA
-----------------------------------------
bhkConvexVerticesShape:

    +0   material          +4   radio
    +32  numVertices       +36  vertices, Vector4
    +36+16*nv  numNormals  +40+16*nv  normales, Vector4

    identidad: 36 + 16*nv + 4 + 16*nn == tamano del bloque
    se cumple en 3.553 de 3.553 bloques del corpus

bhkBoxShape: medias extensiones en +16, tres float32.

Transformada de nodo (NiAVObject), despues de controller y flags:
translation 12 B + matriz de rotacion 36 B + escala 4 B.

EL FACTOR DE HAVOK
------------------
Las coordenadas de colision estan en unidades de Havok. El factor se midio, no
se copio: el escudo de prueba se construyo con un radio conocido de 27,62
unidades y el primer vertice del bloque salio 0,394650, o sea 69,99.
"""
import math
import os
import struct
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

import parser_nif  # noqa: E402
import parser_uv  # noqa: E402

HAVOK = 69.99

FORMAS = ("bhkConvexVerticesShape", "bhkBoxShape", "bhkSphereShape",
          "bhkCapsuleShape")


class ColisionIlegible(Exception):
    pass


# --- transformadas de nodo ---------------------------------------------------

def transform_nodo(nif, idx):
    """(traslacion, rotacion 3x3, escala) del bloque idx, o None si no la tiene.

    El parser del censo saltea estos 52 bytes con `p += 12 + 36 + 4`. Son los
    mismos, leidos en vez de salteados.

    Los SHAPES tambien la tienen: un BSTriShape es un NiAVObject con el mismo
    encabezado. Mirar solo los nodos daba bien sobre los archivos de Bethesda
    --que dejan el shape en identidad-- y mal sobre uno exportado por PyNifly,
    que pone ahi el desplazamiento. Dos archivos del mismo escudo, uno lo
    delataba y el otro no.
    """
    tipo, o, _s = nif.bloques[idx]
    if tipo not in parser_nif.TIPOS_NODO and tipo not in parser_nif.TIPOS_SHAPE:
        return None
    p = o
    p += 4                                        # nombre
    n_ed, = struct.unpack_from("<I", nif.d, p)
    p += 4 + 4 * n_ed
    p += 4 + 4                                    # controller, flags
    tr = struct.unpack_from("<3f", nif.d, p); p += 12
    rot = struct.unpack_from("<9f", nif.d, p); p += 36
    esc, = struct.unpack_from("<f", nif.d, p)
    return (list(tr), [list(rot[0:3]), list(rot[3:6]), list(rot[6:9])], esc)


def _aplicar(tr, rot, esc, v):
    x, y, z = v
    return (tr[0] + esc * (rot[0][0] * x + rot[0][1] * y + rot[0][2] * z),
            tr[1] + esc * (rot[1][0] * x + rot[1][1] * y + rot[1][2] * z),
            tr[2] + esc * (rot[2][0] * x + rot[2][1] * y + rot[2][2] * z))


def cadena_de_padres(nif):
    """bloque hijo -> bloque padre, para los nodos."""
    padre = {}
    for b, info in nif.nodos().items():
        for h in info["hijos"]:
            padre[h] = b
    return padre


def a_mundo(nif, idx_bloque, puntos):
    """Sube los puntos por la cadena de nodos hasta la raiz."""
    padre = cadena_de_padres(nif)
    actual = idx_bloque
    fuera = list(puntos)
    vistos = set()
    while actual is not None and actual not in vistos:
        vistos.add(actual)
        xf = transform_nodo(nif, actual)
        if xf:
            tr, rot, esc = xf
            fuera = [_aplicar(tr, rot, esc, v) for v in fuera]
        actual = padre.get(actual)
    return fuera


# --- geometria de colision ---------------------------------------------------

def vertices_convexos(nif, o, s):
    nv, = struct.unpack_from("<I", nif.d, o + 32)
    fin_v = 36 + 16 * nv
    if nv > 100000 or fin_v + 4 > s:
        raise ColisionIlegible("numVertices %d no entra en %d bytes" % (nv, s))
    nn, = struct.unpack_from("<I", nif.d, o + fin_v)
    esperado = fin_v + 4 + 16 * nn
    if esperado != s:
        raise ColisionIlegible(
            "36 + 16*%d + 4 + 16*%d = %d != %d" % (nv, nn, esperado, s))
    fuera = []
    for k in range(nv):
        x, y, z, _w = struct.unpack_from("<4f", nif.d, o + 36 + 16 * k)
        fuera.append((x * HAVOK, y * HAVOK, z * HAVOK))
    return fuera


def vertices_caja(nif, o, s):
    """Las 8 esquinas. Medias extensiones en +16, tres float32.

    El offset salio de comparar el mismo bloque antes y despues de un
    round-trip: los tres valores que cambiaban de orden eran las dimensiones.
    """
    if s < 32:
        raise ColisionIlegible("bhkBoxShape de %d bytes" % s)
    hx, hy, hz = struct.unpack_from("<3f", nif.d, o + 16)
    hx, hy, hz = hx * HAVOK, hy * HAVOK, hz * HAVOK
    return [(sx * hx, sy * hy, sz * hz)
            for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]


def transform_rigidbody(nif, o):
    """(cuaternion, traslacion) de un bhkRigidBody(T).

    Los dos offsets salieron de correlacion, no de una especificacion:

      +52  traslacion, 3 float32 en unidades de Havok. Se encontro buscando
           en el bloque del cartel de Whiterun los tres floats que, por 69,99,
           dieran los (-46,392, -0,858, 0) que Blender mide para su colision.
           Dio (-46,391, -0,857, 0,000).
      +68  cuaternion (x, y, z, w). Se encontro exigiendo norma 1 sobre los
           14.586 bloques del corpus:

             +32    17 de 14.586      +64    602 de 14.586
             +36     0 de 14.586      +68  14.586 de 14.586   <--
             +40     0 de 14.586      +72  13.276 de 14.586

           Yo habia supuesto +36 leyendo el ORDEN en que el exportador de
           PyNifly asigna los campos (rotacion y despues traslacion). El orden
           en el archivo es el contrario. La medicion lo corrigio; la lectura
           del codigo ajeno no alcanzaba.

    Un bhkRigidBody sin T no aplica la transformada; uno con T, si.
    """
    q = struct.unpack_from("<4f", nif.d, o + 68)
    t = struct.unpack_from("<3f", nif.d, o + 52)
    return q, [v * HAVOK for v in t]


def _rotar(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    # v + 2w(q x v) + 2(q x (q x v))
    ux = y * vz - z * vy
    uy = z * vx - x * vz
    uz = x * vy - y * vx
    wx = y * uz - z * uy
    wy = z * ux - x * uz
    wz = x * uy - y * ux
    return (vx + 2 * (w * ux + wx),
            vy + 2 * (w * uy + wy),
            vz + 2 * (w * uz + wz))


def cuerpos_por_forma(nif):
    """bloque de forma -> (tipo de cuerpo, offset del cuerpo).

    El cuerpo referencia su forma con un indice de bloque en su offset 0, que
    es el mismo campo que ya lee parser_nif.colision_info.
    """
    fuera = {}
    for idx, (tipo, o, s) in enumerate(nif.bloques):
        if not tipo.startswith("bhkRigidBody"):
            continue
        ref, = struct.unpack_from("<i", nif.d, o)
        if 0 <= ref < len(nif.bloques):
            fuera[ref] = (tipo, o)
    return fuera


def formas_de_colision(nif):
    """[{tipo, vertices, caja}] por forma, ya con la transformada del cuerpo."""
    fuera = []
    cuerpos = cuerpos_por_forma(nif)
    for idx, (tipo, o, s) in enumerate(nif.bloques):
        if tipo not in FORMAS:
            continue
        d = {"tipo": tipo, "bloque": idx}
        try:
            if tipo == "bhkConvexVerticesShape":
                vs = vertices_convexos(nif, o, s)
            elif tipo == "bhkBoxShape":
                vs = vertices_caja(nif, o, s)
            else:
                d["error"] = "forma sin decodificar: %s" % tipo
                fuera.append(d)
                continue
        except ColisionIlegible as e:
            d["error"] = str(e)
            fuera.append(d)
            continue

        cuerpo = cuerpos.get(idx)
        if cuerpo:
            tipo_cuerpo, off = cuerpo
            d["cuerpo"] = tipo_cuerpo
            # Solo la variante T aplica transformada. El nombre lo dice y el
            # corpus lo confirma: el cartel de Whiterun usa bhkRigidBodyT y su
            # caja esta a 46 unidades del origen; el escudo usa bhkRigidBody y
            # la suya ya viene en el lugar.
            if tipo_cuerpo.endswith("T"):
                q, t = transform_rigidbody(nif, off)
                vs = [tuple(a + b for a, b in zip(_rotar(q, v), t)) for v in vs]
        d["vertices"] = vs
        d["caja"] = caja(vs)
        fuera.append(d)
    return fuera


# --- cajas -------------------------------------------------------------------

def caja(puntos):
    if not puntos:
        return None
    return [[min(p[i] for p in puntos), max(p[i] for p in puntos)]
            for i in range(3)]


def centro(c):
    return [(e[0] + e[1]) / 2.0 for e in c] if c else None


def tamano(c):
    return [e[1] - e[0] for e in c] if c else None


def distancia(a, b):
    ca, cb = centro(a), centro(b)
    if not ca or not cb:
        return None
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(ca, cb)))


def cajas_de_shapes(nif):
    """[{nombre, caja}] de cada shape, en espacio de mundo."""
    fuera = []
    porbloque = {}
    for idx, (tipo, o, s) in enumerate(nif.bloques):
        if tipo in parser_nif.TIPOS_SHAPE:
            porbloque[idx] = True
    for sh in parser_uv.geometria(nif):
        if "error" in sh or not sh.get("pos"):
            fuera.append({"nombre": sh.get("nombre"),
                          "error": sh.get("error", "sin posiciones")})
            continue
        idx = None
        for i, (tipo, o, s) in enumerate(nif.bloques):
            if tipo in parser_nif.TIPOS_SHAPE:
                try:
                    _p, nom = nif._saltar_niavobject(o)
                except Exception:
                    continue
                if nom == sh["nombre"]:
                    idx = i
                    break
        pts = a_mundo(nif, idx, sh["pos"]) if idx is not None else sh["pos"]
        fuera.append({"nombre": sh["nombre"], "caja": caja(pts),
                      "bloque": idx})
    return fuera


# --- autotest ----------------------------------------------------------------

def autotest(raiz):
    """La identidad de tamano sobre todas las formas convexas del corpus.

    Cero comprobaciones NO es exito: si la carpeta no tiene NIF, falla.
    """
    print("SUITE DE FALSIFICACION - parser_colision")
    print("")
    n_ok = n_mal = n_arch = 0
    ejemplos = []
    for base, _, fs in os.walk(raiz):
        for f in fs:
            if not f.lower().endswith(".nif"):
                continue
            try:
                nif = parser_nif.Nif(os.path.join(base, f))
            except Exception:
                continue
            n_arch += 1
            for tipo, o, s in nif.bloques:
                if tipo != "bhkConvexVerticesShape":
                    continue
                try:
                    vertices_convexos(nif, o, s)
                    n_ok += 1
                except ColisionIlegible as e:
                    n_mal += 1
                    if len(ejemplos) < 3:
                        ejemplos.append((f, str(e)[:60]))

    print("  archivos leidos: %d" % n_arch)
    print("  a. identidad 36 + 16*nv + 4 + 16*nn == tamano del bloque")
    print("     %d formas convexas ok, %d violadas" % (n_ok, n_mal))
    for f, m in ejemplos:
        print("       %s  %s" % (f, m))

    if n_arch == 0:
        print("")
        print("  NO se leyo NINGUN archivo. Revisa la ruta del corpus.")
        return False
    if n_ok == 0:
        print("")
        print("  NO se comprobo NINGUNA forma de colision.")
        return False
    if n_mal:
        print("")
        print("  El decodificador NO esta validado.")
        return False
    print("")
    print("  Sin fallas.")
    return True


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        raise SystemExit(2)
    if a[0] == "--autotest":
        if len(a) < 2:
            print("Uso: --autotest <carpeta meshes>")
            raise SystemExit(2)
        raise SystemExit(0 if autotest(a[1]) else 1)

    nif = parser_nif.Nif(a[0])
    print("formas de colision:")
    for fc in formas_de_colision(nif):
        if "error" in fc:
            print("  %-26s ERROR %s" % (fc["tipo"], fc["error"]))
            continue
        c = fc["caja"]
        print("  %-26s %d vertices  tamano %.2f x %.2f x %.2f  centro (%.2f, %.2f, %.2f)"
              % (fc["tipo"], len(fc["vertices"]),
                 tamano(c)[0], tamano(c)[1], tamano(c)[2],
                 centro(c)[0], centro(c)[1], centro(c)[2]))
    print("shapes:")
    for sh in cajas_de_shapes(nif):
        if "error" in sh:
            print("  %-26s ERROR %s" % (sh["nombre"], sh["error"]))
            continue
        c = sh["caja"]
        print("  %-26s tamano %.2f x %.2f x %.2f  centro (%.2f, %.2f, %.2f)"
              % (sh["nombre"], tamano(c)[0], tamano(c)[1], tamano(c)[2],
                 centro(c)[0], centro(c)[1], centro(c)[2]))


if __name__ == "__main__":
    main()
