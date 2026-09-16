# -*- coding: utf-8 -*-
"""parser_uv.py — censo de coordenadas UV del corpus vanilla. Python puro.

SIN dependencias. SIN Blender. SOLO LECTURA. Se apoya en parser_nif.Nif para la
cabecera y la tabla de bloques, y agrega la extraccion de UV y triangulos.

POR QUE NO USA BLENDER

Las UV estan en el NIF. Abrir 22.394 mallas en Blender son horas, y ademas no
funciona: las mallas skinneadas no se ensamblan al importar (trampa 26). Leer
los bytes son milisegundos por archivo.

EL OFFSET DE LAS UV SE DETERMINO MIDIENDO, NO ASUMIENDO

En un vertice de SSE, las UV son dos half-floats. La posicion dentro del
vertice se fijo probando offsets sobre un archivo conocido y mirando cual da
coordenadas sanas:

    offset +12   u -9264..6876      en [0,1]:   8 de 361
    offset +16   u 0.005..0.999     en [0,1]: 400 de 400   <--
    offset +20   u -9208..8004      en [0,1]:  74 de 367

Son 12 bytes de posicion XYZ + 4 de bitangente/padding. El flag de presencia
es el bit 1 de los flags de atributo, (vertex_desc >> 44) & 0x2.

DOS CAMINOS A LOS DATOS DE VERTICE

  estatico   -> inline en BSTriShape, despues de data_size
  skinneado  -> dentro del NiSkinPartition (BSTriShape declara numTriangles=0)

El recorrido de particiones NO se reescribe de memoria: es el mismo que
parser_nif._parse_skin_partition, que esta validado contra la identidad
`cursor == offset + size` en 42.243 particiones con 0 violaciones, y contra los
6.007 triangulos conocidos de steamcenturion.nif. Aca se repite el recorrido
recolectando geometria, y se CONSERVA esa comprobacion: si el cursor no termina
donde tiene que terminar, el shape entra al censo con error en vez de con
numeros.

SESGO CONOCIDO DEL RASTERIZADOR

Se muestrea por centro de celda. Un triangulo mas fino que una celda puede no
contener ningun centro y contarse como area cero. Eso subestima el area de las
islas con slivers. El sesgo es real, se mide en el autotest (converge como
O(1/R)) y NO se disimula: los casos analiticos reportan el error, no cero.

Uso:
  python parser_uv.py --autotest [<carpeta corpus>]
  python parser_uv.py --censo <carpeta> --salida censo_uv.jsonl
  python parser_uv.py <archivo.nif>
"""
import json
import math
import os
import struct
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parser_nif import Nif, Violacion   # noqa: E402

UV_OFFSET = 16          # medido, ver cabecera
BIT_UV = 0x2            # (vertex_desc >> 44) & BIT_UV
GRID = 512              # resolucion del rasterizador


# --- extraccion -------------------------------------------------------------

def _leer_vertices(d, base, n, stride, con_uv):
    """[(x,y,z)], [(u,v)]. Las UV son half-floats en UV_OFFSET."""
    pos, uv = [], []
    for i in range(n):
        o = base + i * stride
        pos.append(struct.unpack_from("<3f", d, o))
        if con_uv:
            uv.append(struct.unpack_from("<2e", d, o + UV_OFFSET))
    return pos, uv


def geometria(nif):
    """[{nombre, uvs, tris, pos, ...}] por shape. Nunca inventa: si algo no
    cuadra, el shape sale con 'error' y sin numeros."""
    d = nif.d
    fuera = []
    for b_idx, o, s in nif.de_tipo("BSTriShape", "BSDynamicTriShape",
                                   "BSSubIndexTriShape"):
        tipo = nif.bloques[b_idx][0]
        try:
            p, nombre = nif._saltar_niavobject(o)
            p += 16                                  # bounding sphere
            if nif.bs >= 151:
                p += 24
            skin_idx, shader_idx, _alpha = struct.unpack_from("<3i", d, p)
            p += 12
            vdesc, = struct.unpack_from("<Q", d, p); p += 8
            if nif.bs < 130:
                n_tri, = struct.unpack_from("<H", d, p); p += 2
            else:
                n_tri, = struct.unpack_from("<I", d, p); p += 4
            n_ver, = struct.unpack_from("<H", d, p); p += 2
            data_size, = struct.unpack_from("<I", d, p); p += 4

            stride = (vdesc & 0xF) * 4
            con_uv = bool((vdesc >> 44) & BIT_UV)

            if data_size > 0 and n_ver > 0:
                # --- estatico: la identidad de tamano falsifica el layout ---
                esperado = n_ver * stride + n_tri * 6
                if esperado != data_size:
                    raise Violacion(
                        "inline: %d*%d + %d*6 = %d != data_size %d"
                        % (n_ver, stride, n_tri, esperado, data_size))
                pos, uv = _leer_vertices(d, p, n_ver, stride, con_uv)
                tb = p + n_ver * stride
                tris = [struct.unpack_from("<3H", d, tb + t * 6)
                        for t in range(n_tri)]
                fuera.append({"nombre": nombre, "tipo": tipo, "skin": False,
                              "shader_idx": shader_idx, "con_uv": con_uv,
                              "pos": pos, "uv": uv, "tris": tris})
                continue

            if n_tri == 0 and nif._ref_valida(skin_idx):
                g = _geometria_skin(nif, skin_idx, con_uv)
                g.update({"nombre": nombre, "tipo": tipo, "skin": True,
                          "shader_idx": shader_idx})
                fuera.append(g)
                continue

            fuera.append({"nombre": nombre, "tipo": tipo, "skin": False,
                          "shader_idx": shader_idx,
                          "error": "sin geometria (tri=%d, data_size=%d)"
                                   % (n_tri, data_size)})
        except Exception as e:
            fuera.append({"nombre": "?", "tipo": tipo,
                          "error": "%s: %s" % (type(e).__name__, e)})
    return fuera


def _geometria_skin(nif, skin_idx, con_uv_shape):
    """Recorre el NiSkinPartition recolectando vertices y triangulos.

    Mismo recorrido que parser_nif._parse_skin_partition, con la MISMA
    comprobacion de cierre: el cursor tiene que terminar exactamente en
    offset+size del bloque. Sin esa comprobacion, el recorrido es una
    suposicion; con ella, esta falsificado en 42.243 particiones.
    """
    d = nif.d
    tipo, so, _ = nif.bloques[skin_idx]
    if tipo not in ("NiSkinInstance", "BSDismemberSkinInstance"):
        return {"error": "skin instance inesperada: %s" % tipo}
    _data_ref, part_idx = struct.unpack_from("<2i", d, so)
    if not nif._ref_valida(part_idx):
        return {"error": "sin NiSkinPartition"}
    if nif.bloques[part_idx][0] != "NiSkinPartition":
        return {"error": "ref no es NiSkinPartition"}

    o, s = nif.bloques[part_idx][1], nif.bloques[part_idx][2]
    ptr = o
    n_parts, = struct.unpack_from("<I", d, ptr); ptr += 4
    data_size, stride = struct.unpack_from("<2I", d, ptr); ptr += 8
    vdesc, = struct.unpack_from("<Q", d, ptr); ptr += 8
    if stride == 0:
        return {"error": "vertexSize=0"}
    con_uv = bool((vdesc >> 44) & BIT_UV) or con_uv_shape
    n_ver = data_size // stride
    pos, uv = _leer_vertices(d, ptr, n_ver, stride, con_uv)
    ptr += data_size

    tris = []
    for _ in range(n_parts):
        num_v, num_t, num_b, num_s, num_w = struct.unpack_from("<5H", d, ptr)
        ptr += 10
        if num_w > 4:
            return {"error": "sanidad: pesos por vertice %d > 4" % num_w}
        ptr += 2 * num_b
        has_vmap, = struct.unpack_from("<?", d, ptr); ptr += 1
        vmap = None
        if has_vmap:
            vmap = struct.unpack_from("<%dH" % num_v, d, ptr)
            ptr += 2 * num_v
        has_vw, = struct.unpack_from("<?", d, ptr); ptr += 1
        if has_vw and num_w > 0:
            ptr += 4 * num_v * num_w
        strip_lengths = ()
        if num_s > 0:
            strip_lengths = struct.unpack_from("<%dH" % num_s, d, ptr)
            ptr += 2 * num_s
        has_faces, = struct.unpack_from("<?", d, ptr); ptr += 1
        if has_faces:
            if num_s > 0:
                for sl in strip_lengths:
                    ptr += 2 * sl
            else:
                cr = struct.unpack_from("<%dH" % (3 * num_t), d, ptr)
                ptr += 6 * num_t
                # EN SSE LOS INDICES YA SON GLOBALES. No se remapean por el
                # vertex map: eso es logica de LE, donde cada particion tenia
                # su propio buffer.
                #
                # Medido: armor/bandit/1stpersonbody1f_0.nif tiene una
                # particion de 44 vertices sobre un buffer global de 460, y su
                # indice de triangulo maximo es 345 -- imposible como indice
                # local. Remapeando reventaba con IndexError en 624 shapes.
                #
                # Y el archivo con el que se habia probado primero,
                # steamcenturion.nif, tiene 1.106 vertices de particion sobre
                # 1.106 globales: los dos espacios coinciden y el bug no se
                # nota. El caso de prueba era degenerado.
                for t in range(num_t):
                    tris.append((cr[t * 3], cr[t * 3 + 1], cr[t * 3 + 2]))
        has_bi, = struct.unpack_from("<?", d, ptr); ptr += 1
        if has_bi:
            ptr += num_v * num_w
        ptr += 1 + 1 + 8 + 6 * num_t     # tail SSE

    if ptr != o + s:
        return {"error": "particion: fin=%d != bloque=%d" % (ptr, o + s)}
    # Cota que atrapa un remapeo equivocado o un offset corrido: todo indice
    # tiene que caer dentro del buffer global de vertices.
    if tris:
        mx = max(max(t) for t in tris)
        if mx >= n_ver:
            return {"error": "indice de triangulo %d >= %d vertices globales"
                             % (mx, n_ver)}
    return {"con_uv": con_uv, "pos": pos, "uv": uv, "tris": tris}


# --- geometria --------------------------------------------------------------

def area3(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    x, y, z = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    return 0.5 * math.sqrt(x * x + y * y + z * z)


def area2(a, b, c):
    return 0.5 * abs((b[0] - a[0]) * (c[1] - a[1]) -
                     (c[0] - a[0]) * (b[1] - a[1]))


def rasterizar(tris_uv, res=GRID):
    """{celda: cuantos triangulos la cubren}. Muestreo por centro de celda.

    REGLA DE RELLENO TOP-LEFT, y no es un detalle: dos triangulos que comparten
    una arista cubren las mismas celdas sobre esa arista. Con un test de
    inclusion con tolerancia simetrica, cada arista interna de la malla aparece
    como una linea de celdas "solapadas". Medido: un atlas de 4 islas bien
    separadas --cada una de dos triangulos-- reportaba 816 celdas solapadas en
    vez de 0, solo por las cuatro diagonales.

    Sobre una malla real eso son miles de aristas internas, y el solape del
    censo entero habria salido inflado por un borde falso. Es exactamente la
    clase de numero plausible y equivocado que este repo existe para atrapar.

    La regla estandar: un punto justo sobre una arista pertenece a UNO solo de
    los dos triangulos. Se normaliza el sentido de giro primero, porque las UV
    espejadas invierten la orientacion y la regla la necesita consistente.

    Sesgo que SI queda: un triangulo mas fino que una celda puede no contener
    ningun centro y contar como area cero. Es real, se mide en el autotest, y
    no se disimula.
    """
    g = defaultdict(int)
    paso = 1.0 / res
    eps = 1e-12
    for p0, p1, p2 in tris_uv:
        # sentido antihorario, que es lo que asume la regla
        if ((p1[0] - p0[0]) * (p2[1] - p0[1]) -
                (p2[0] - p0[0]) * (p1[1] - p0[1])) < 0:
            p1, p2 = p2, p1
        x0, y0 = p0
        x1, y1 = p1
        x2, y2 = p2
        if abs((x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)) < 1e-15:
            continue
        # una arista es top-left si sube, o si es horizontal y va hacia la
        # izquierda. Esas incluyen sus puntos de borde; las otras los excluyen.
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
        # Funciones de arista INCREMENTALES. Son lineales en (px, py), asi que
        # avanzar una celda es sumar una constante en vez de recalcular tres
        # productos. El perfil decia que el 94 % del censo se iba aca; sin
        # esto, la muestra tardaba 2,4 s por archivo.
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
                    g[(gx, gy)] += 1
                e0 += dx0
                e1 += dx1
                e2 += dx2
            f0 += dy0
            f1 += dy1
            f2 += dy2
    return g


def metricas_uv(uv, tris, pos, res=GRID):
    if not tris or not uv:
        return None
    tris_uv = [(uv[a], uv[b], uv[c]) for a, b, c in tris
               if a < len(uv) and b < len(uv) and c < len(uv)]
    if not tris_uv:
        return None
    celda = 1.0 / (res * res)
    g = rasterizar(tris_uv, res)
    cubiertas = len(g)
    solapadas = sum(1 for v in g.values() if v >= 2)
    pasadas = sum(g.values())
    exceso = sum(v - 1 for v in g.values() if v >= 2)

    # Densidad de texel = area 3D / area UV. Dos cuidados que NO son cosmeticos:
    #
    #  * Un umbral absoluto (au > 1e-12) deja pasar triangulos degenerados: con
    #    area UV 1e-11 y area 3D 100 sale una densidad de 1e13. Medido: 111 de
    #    7.751 shapes daban ratios sobre 1e6, con casos de 1e36.
    #  * Peor: los no finitos ENVENENAN EL ORDEN. NaN compara falso contra todo,
    #    asi que sorted() devuelve una lista que no esta ordenada y los
    #    percentiles salen incoherentes -- se vio un p10 (4,2) MAYOR que la
    #    mediana (1,5), que es aritmeticamente imposible y delata el problema.
    #
    # El umbral es relativo al area UV tipica del shape, no absoluto.
    crudas = []
    for (a, b, c) in tris:
        if max(a, b, c) >= len(uv) or max(a, b, c) >= len(pos):
            continue
        au = area2(uv[a], uv[b], uv[c])
        a3 = area3(pos[a], pos[b], pos[c])
        crudas.append((au, a3))
    if crudas:
        aus = sorted(x[0] for x in crudas)
        mediana_au = aus[len(aus) // 2]
        piso = max(1e-12, mediana_au * 1e-4)
    else:
        piso = 1e-12
    dens = []
    n_degenerados = 0
    for au, a3 in crudas:
        if au <= piso:
            n_degenerados += 1
            continue
        d = a3 / au
        if d == d and d not in (float("inf"), float("-inf")):
            dens.append(d)
    dens.sort()

    def q(p):
        if not dens:
            return None
        return dens[min(len(dens) - 1, int(len(dens) * p))]

    us = [p[0] for p in uv]
    vs = [p[1] for p in uv]
    fuera = sum(1 for a, b, c in tris
                if max(a, b, c) < len(uv) and
                any(not (-1e-4 <= uv[i][0] <= 1 + 1e-4 and
                         -1e-4 <= uv[i][1] <= 1 + 1e-4) for i in (a, b, c)))
    return {
        "n_tris": len(tris_uv),
        "area_cubierta": round(cubiertas * celda, 6),
        "solape_huella": round(solapadas / float(cubiertas), 6) if cubiertas else 0.0,
        "solape_exceso": round(exceso / float(pasadas), 6) if pasadas else 0.0,
        "desperdicio_01": round(1.0 - cubiertas * celda, 6),
        "densidad_p10": round(q(0.10), 4) if dens else None,
        "densidad_p50": round(q(0.50), 4) if dens else None,
        "densidad_p90": round(q(0.90), 4) if dens else None,
        "tris_fuera_01": fuera,
        "tris_uv_degenerados": n_degenerados,
        "uv_rango": [round(min(us), 4), round(max(us), 4),
                     round(min(vs), 4), round(max(vs), 4)],
    }


# --- falsificacion ----------------------------------------------------------

def _cuadrado(x0, y0, x1, y1):
    return [((x0, y0), (x1, y0), (x1, y1)), ((x0, y0), (x1, y1), (x0, y1))]


def autotest(raiz=None):
    print("")
    print("SUITE DE FALSIFICACION")
    print("")
    fallos = 0

    # a. solape analitico 25%, y su convergencia. NO se afirma error cero:
    #    el muestreo por centro de celda tiene sesgo y se reporta.
    print("  a. dos cuadrados con solape analitico 0.250000")
    tris = _cuadrado(0, 0, 1, 1) + _cuadrado(0.5, 0.5, 1.5, 1.5)
    err_ant = None
    for r in (64, 128, 256, 512, 1024):
        g = rasterizar(tris, r)
        area = sum(1.0 / (r * r) for v in g.values() if v >= 2)
        err = abs(area - 0.25)
        # El criterio es que el error NO CREZCA, no que baje estrictamente.
        # Con la regla de relleno este caso da exacto en toda resolucion
        # --los bordes en 0.5 y 1.0 se resuelven sin ambiguedad-- y exigir
        # err < err_ant marcaba como falla que el error ya fuera cero.
        marca = ""
        if err_ant is not None:
            if err <= err_ant + 1e-12:
                marca = "exacto" if err < 1e-12 else "converge"
            else:
                marca = "EL ERROR CRECE"
                fallos += 1
        print("     %5d  area=%.6f  error=%+.6f  %s" % (r, area, area - 0.25, marca))
        err_ant = err

    # b. disjuntos
    t1 = ((0.1, 0.1), (0.4, 0.1), (0.1, 0.4))
    t2 = ((0.6, 0.6), (0.9, 0.6), (0.6, 0.9))
    g = rasterizar([t1, t2], 512)
    sol = sum(1 for v in g.values() if v >= 2)
    ok = sol == 0
    fallos += 0 if ok else 1
    print("  b. triangulos disjuntos: celdas solapadas=%d  %s"
          % (sol, "ok" if ok else "FALLA"))

    # c. triangulo consigo mismo: el solape es su area
    t = ((0.1, 0.1), (0.8, 0.1), (0.1, 0.7))
    esperada = area2(*t)
    g = rasterizar([t, t], 1024)
    area = sum(1.0 / (1024 * 1024) for v in g.values() if v >= 2)
    ok = abs(area - esperada) < 0.002
    fallos += 0 if ok else 1
    print("  c. triangulo duplicado: area=%.6f esperada=%.6f err=%+.6f  %s"
          % (area, esperada, area - esperada, "ok" if ok else "FALLA"))

    # d. atlas bien armado
    at = []
    for (x, y) in ((0.05, 0.05), (0.55, 0.05), (0.05, 0.55), (0.55, 0.55)):
        at += _cuadrado(x, y, x + 0.40, y + 0.40)
    g = rasterizar(at, 512)
    sol = sum(1 for v in g.values() if v >= 2)
    ok = sol == 0
    fallos += 0 if ok else 1
    print("  d. atlas de 4 islas separadas: celdas solapadas=%d  %s"
          % (sol, "ok" if ok else "FALLA"))

    # e. la firma del bug: N islas sobre el cuadro entero -> exceso (N-1)/N
    n = 15
    pat = []
    for _ in range(n):
        pat += _cuadrado(0, 0, 1, 1)
    g = rasterizar(pat, 512)
    pasadas = sum(g.values())
    exceso = sum(v - 1 for v in g.values() if v >= 2)
    ratio = exceso / float(pasadas)
    teor = (n - 1) / float(n)
    ok = abs(ratio - teor) < 0.005
    fallos += 0 if ok else 1
    print("  e. %d islas sobre 0..1: exceso=%.6f teorico=%.6f  %s"
          % (n, ratio, teor, "ok" if ok else "FALLA"))

    # f. half-floats
    malos = []
    for bits, esp in ((0x3C00, 1.0), (0xC000, -2.0), (0x0000, 0.0),
                      (0x3800, 0.5), (0xBC00, -1.0)):
        v = struct.unpack("<e", struct.pack("<H", bits))[0]
        if v != esp:
            malos.append((bits, v, esp))
    fallos += len(malos)
    print("  f. half-floats: %d discrepancias  %s"
          % (len(malos), "ok" if not malos else "FALLA"))

    # h. LA FALSIFICACION MAS FUERTE: el area rasterizada contando
    #    profundidad tiene que coincidir con la suma analitica de areas de
    #    triangulo. Son dos caminos independientes al mismo numero: uno por
    #    conteo de celdas, otro por formula del cordon. Si el rasterizador
    #    tuviera sesgo de borde, doble conteo o un error de regla de relleno,
    #    aca se separan.
    if raiz:
        print("  h. rasterizado vs suma analitica de areas (archivos reales)")
        n_h = 0
        peor = 0.0
        for base, _, archivos in os.walk(raiz):
            for f in archivos:
                if not f.lower().endswith(".nif") or n_h >= 12:
                    continue
                try:
                    nif = Nif(os.path.join(base, f))
                except Exception:
                    continue
                for sh in geometria(nif):
                    if "error" in sh or not sh.get("con_uv") or not sh["tris"]:
                        continue
                    uv = sh["uv"]
                    tu = [(uv[a], uv[b], uv[c]) for a, b, c in sh["tris"]
                          if max(a, b, c) < len(uv)]
                    if len(tu) < 50:
                        continue
                    ana = sum(area2(*t) for t in tu)
                    if ana < 1e-6:
                        continue
                    g = rasterizar(tu, 512)
                    ras = sum(v / (512.0 * 512.0) for v in g.values())
                    dif = abs(ras - ana) / ana
                    peor = max(peor, dif)
                    n_h += 1
                    if n_h >= 12:
                        break
        # n_h >= 1 es parte del criterio: con la ruta equivocada el bucle no
        # entra nunca, peor queda en 0.0 y "0.0 < 0.02" imprimia "ok". Cero
        # comprobaciones no es exito; es la misma guarda que census/parser_dds.
        ok = n_h >= 1 and peor < 0.02
        fallos += 0 if ok else 1
        print("     %d shapes, peor desvio %.3f%%  %s"
              % (n_h, 100 * peor, "ok" if ok else "FALLA"))
        if n_h == 0:
            print("     NO se comprobo NADA contra el corpus. Revisa la ruta.")

    # g. identidad de tamano por shape, sobre el corpus
    if raiz:
        n_ok = n_err = 0
        malos_ej = []
        for base, _, archivos in os.walk(raiz):
            for f in archivos:
                if not f.lower().endswith(".nif"):
                    continue
                ruta = os.path.join(base, f)
                try:
                    for sh in geometria(Nif(ruta)):
                        if "error" in sh:
                            if "sin geometria" not in sh["error"]:
                                n_err += 1
                                if len(malos_ej) < 3:
                                    malos_ej.append((f, sh["error"][:60]))
                        else:
                            n_ok += 1
                except Exception:
                    n_err += 1
        print("  g. shapes con geometria leida sin violar la identidad: %d" % n_ok)
        print("     shapes con error: %d" % n_err)
        for f, m in malos_ej:
            print("       %s  %s" % (f, m))
        # n_mal se inicializaba en 0 y NUNCA se incrementaba: "fallos += n_mal"
        # era sumar cero. El caso g imprimia los errores y no podia fallar --
        # la cuarta vez en este repo que escribo una garantia inofensiva.
        fallos += n_err
        if n_ok == 0:
            print("     NO se leyo NINGUN shape. Revisa la ruta del corpus.")
            fallos += 1

    print("")
    if fallos:
        print("  %d FALLAS. El medidor NO esta listo." % fallos)
        return False
    print("  Sin fallas. Nota: el error de a/c no es cero y no se pretende que")
    print("  lo sea -- el muestreo por centro de celda tiene sesgo conocido.")
    return True


# --- cli --------------------------------------------------------------------

def _texset_de(nif, shader_idx):
    """Indice del BSShaderTextureSet que usa ese shader, o -1."""
    if not nif._ref_valida(shader_idx):
        return -1
    tipo, o, s = nif.bloques[shader_idx]
    if tipo != "BSLightingShaderProperty":
        return -1
    try:
        _st, = struct.unpack_from("<I", nif.d, o)
        _n, num_ed = struct.unpack_from("<iI", nif.d, o + 4)
        q = o + 16 + 4 * num_ed
        if q + 28 > o + s:
            return -1
        tex_ref, = struct.unpack_from("<i", nif.d, q + 24)
        if nif._ref_valida(tex_ref) and                 nif.bloques[tex_ref][0] == "BSShaderTextureSet":
            return tex_ref
    except Exception:
        pass
    return -1


def fila(ruta, base):
    nif = Nif(ruta)
    rel = os.path.relpath(ruta, base).replace(os.sep, "/")
    shapes = []
    por_texset = defaultdict(list)
    for sh in geometria(nif):
        if "error" in sh:
            shapes.append({"nombre": sh.get("nombre"), "error": sh["error"]})
            continue
        m = metricas_uv(sh["uv"], sh["tris"], sh["pos"]) if sh.get("con_uv") else None
        e = {"nombre": sh["nombre"], "tipo": sh["tipo"], "skin": sh["skin"],
             "con_uv": sh.get("con_uv", False),
             "n_vertices": len(sh["pos"]), "n_triangulos": len(sh["tris"])}
        if m:
            e.update(m)
        shapes.append(e)
        if sh.get("con_uv") and sh["tris"]:
            # Por TEXTURE SET, no por indice de bloque de shader: cada shape
            # tiene su propia BSLightingShaderProperty, asi que agrupar por
            # shader_idx no agrupa nunca nada. Se comprobo: archivos con 7
            # shapes daban 0 grupos. Lo que se comparte de verdad es el
            # BSShaderTextureSet -- el Steam Centurion tiene 15 shapes y UN
            # solo texture set.
            por_texset[_texset_de(nif, sh["shader_idx"])].append(sh)

    # la pregunta central: shapes que comparten shader, se pisan entre si?
    compartidos = []
    for sidx, grupo in por_texset.items():
        if sidx < 0 or len(grupo) < 2:
            continue
        todos = []
        for sh in grupo:
            todos += [(sh["uv"][a], sh["uv"][b], sh["uv"][c])
                      for a, b, c in sh["tris"]
                      if max(a, b, c) < len(sh["uv"])]
        g = rasterizar(todos)
        cub = len(g)
        sol = sum(1 for v in g.values() if v >= 2)
        compartidos.append({
            "texset_idx": sidx, "n_shapes": len(grupo),
            "nombres": [s["nombre"] for s in grupo][:8],
            "solape_huella": round(sol / float(cub), 6) if cub else 0.0,
        })
    return {"archivo": rel, "shapes": shapes, "grupos_shader": compartidos}


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    if a[0] == "--autotest":
        sys.exit(0 if autotest(a[1] if len(a) > 1 else None) else 1)
    if a[0] == "--censo":
        raiz = a[1]
        salida = a[a.index("--salida") + 1] if "--salida" in a else "censo_uv.jsonl"
        # Reanudable, y cada fila se vuelca en el momento. El censo tarda horas
        # y un corte a mitad de camino no tiene por que costar todo lo hecho:
        # la primera corrida se murio a los 4.401 archivos y sin esto habria
        # que rehacerlos.
        hechos = set()
        if "--continuar" in a and os.path.exists(salida):
            with open(salida, encoding="utf-8") as fh:
                for linea in fh:
                    try:
                        hechos.add(json.loads(linea)["archivo"])
                    except Exception:
                        pass
            print("reanudando: %d archivos ya estaban" % len(hechos))
        n_ok = n_err = n_salt = 0
        with open(salida, "a" if hechos else "w", encoding="utf-8") as fh:
            for base, _, archivos in os.walk(raiz):
                for f in archivos:
                    if not f.lower().endswith(".nif"):
                        continue
                    ruta = os.path.join(base, f)
                    rel = os.path.relpath(ruta, raiz).replace(os.sep, "/")
                    if rel in hechos:
                        n_salt += 1
                        continue
                    try:
                        r = fila(ruta, raiz)
                        n_ok += 1
                    except Exception as e:
                        r = {"archivo": rel,
                             "error": "%s: %s" % (type(e).__name__, e)}
                        n_err += 1
                    fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                    fh.flush()
        print("%s -> %d nuevos, %d con error, %d ya estaban"
              % (salida, n_ok, n_err, n_salt))
        return
    for ruta in a:
        print(json.dumps(fila(ruta, os.path.dirname(ruta) or "."),
                         ensure_ascii=False, indent=1)[:3000])


if __name__ == "__main__":
    main()
