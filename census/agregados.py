# -*- coding: utf-8 -*-
"""agregados.py — consultas del censo (censo.jsonl). Cada seccion a...j es una
consulta reproducible:  python agregados.py [a b c ...]   (sin args: todas)

Definiciones:
  clase   = primer segmento de ruta_relativa (carpeta de primer nivel).
  rige    = mismo corpus para todos los calculos: meshes/ (22.394 NIF).
"""
import json
import sys
from collections import Counter, defaultdict
from typing import Any

CENSO = "censo.jsonl"


def cargar():
    filas = []
    with open(CENSO, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if "error" not in r:
                partes = r["ruta_relativa"].split("/")
                r["_clase"] = partes[0] if len(partes) > 1 else "(raiz)"
                filas.append(r)
    return filas


def pct(n, d):
    return "%.2f%%" % (100.0 * n / d) if d else "-"


def mediana(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def p90(xs):
    xs = sorted(xs)
    if not xs:
        return None
    return xs[min(len(xs) - 1, int(round(0.9 * (len(xs) - 1))))]


# ---------------------------------------------------------------- secciones

def sec_a(filas):
    print("== a. tipo_nodo_raiz x carpeta de primer nivel ==")
    pares = Counter((f["tipo_nodo_raiz"], f["_clase"]) for f in filas)
    clases = [c for c, _ in Counter(f["_clase"] for f in filas).most_common(14)]
    raices = [r for r, _ in Counter(f["tipo_nodo_raiz"] for f in filas).most_common()]
    enc = " " * 18 + "".join("%9s" % c[:9] for c in clases)
    print(enc)
    for r in raices:
        fila = "".join("%9d" % pares.get((r, c), 0) for c in clases)
        print("%18s%s" % (r, fila))
    print("  (otras carpetas omitidas de la matriz)")
    print()
    print("  raiz x tiene_skin (todas las carpetas):")
    sk = Counter((f["tipo_nodo_raiz"], f["tiene_skin"]) for f in filas)
    for r in raices:
        total = sk.get((r, True), 0) + sk.get((r, False), 0)
        print("  %-18s total=%6d  skin=%6d (%s)  estatica=%6d" % (
            r, total, sk.get((r, True), 0), pct(sk.get((r, True), 0), total),
            sk.get((r, False), 0)))
    tot = Counter(f["tiene_skin"] for f in filas)
    print("  TOTAL skin=%d estaticas=%d" % (tot[True], tot[False]))


def sec_b(filas):
    print("== b. bsxflags_valor (frecuencia) y bsxflags x clase ==")
    val = Counter(f["bsxflags_valor"] for f in filas)
    n = len(filas)
    print("  valor xN (%):")
    for v, c in val.most_common(16):
        print("    %6s x%-6d %s" % (v, c, pct(c, n)))
    print("  valores distintos:", len(val), " sin BSXFlags:", val[None])
    print("  bits encendidos (posicion: frecuencia):")
    bits = Counter()
    for f in filas:
        for b in (f["bsxflags_bits"] or []):
            bits[b] += 1
    for b, c in sorted(bits.items()):
        print("    bit %2d x%-6d %s" % (b, c, pct(c, n)))
    print("  bsxflags x clase (top-30 celdas):")
    pc = Counter((f["_clase"], f["bsxflags_valor"]) for f in filas
                 if f["bsxflags_valor"] is not None)
    for (c, v), k in pc.most_common(30):
        print("    %-16s %6s x%d" % (c, v, k))


def sec_c(filas):
    print("== c. formas bhk* x clase  y  material_havok x clase ==")
    tb = Counter()
    for f in filas:
        for t in f["colision"]["tipos_bhk"]:
            tb[(f["_clase"], t)] += 1
    print("  bhk* x clase (celdas x>=20):")
    for (c, t), k in sorted(tb.items()):
        if k >= 20:
            print("    %-16s %-32s x%d" % (c, t, k))
    tipos = Counter(t for f in filas for t in f["colision"]["tipos_bhk"])
    print("  total por tipo (global):")
    for t, k in tipos.most_common():
        print("    %-36s x%d" % (t, k))
    print("  material_havok (campo Material del shape) x clase:")
    mat = Counter((f["_clase"], f["colision"]["material_havok"]) for f in filas
                  if f["colision"]["material_havok"] is not None)
    n_mat = sum(mat.values())
    print("  N (archivos con material explicito) =", n_mat)
    for (c, m), k in mat.most_common(40):
        print("    %-16s %-52s x%d" % (c, m, k))
    print("  materiales de chunk (bhkCompressedMeshShapeData) x clase (top):")
    ch = Counter((f["_clase"], m) for f in filas
                 for m in (f["colision"]["materiales_chunk"] or []))
    for (c, m), k in ch.most_common(20):
        print("    %-16s %-10s x%d" % (c, m, k))
    print("  layer x clase (top) y motion x clase:")
    lay = Counter((f["_clase"], f["colision"]["layer"]) for f in filas
                  if f["colision"]["layer"] is not None)
    for (c, l), k in lay.most_common(18):
        print("    layer    %-16s %-28s x%d" % (c, l, k))
    mov = Counter((f["_clase"], f["colision"]["motion_system"]) for f in filas
                  if f["colision"]["motion_system"] is not None)
    for (c, m), k in mov.most_common(18):
        print("    motion   %-16s %-28s x%d" % (c, m, k))


def sec_d(filas):
    print("== d. triangulos_totales por clase: mediana / p90 / max ==")
    porc = defaultdict(list)
    for f in filas:
        porc[f["_clase"]].append(f["triangulos_totales"])
    for c, xs in sorted(porc.items(), key=lambda kv: -len(kv[1])):
        n = len(xs)
        ceros = sum(1 for x in xs if x == 0)
        print("  %-16s N=%-6d mediana=%-8s p90=%-8s max=%-8d (con 0 tri: %d)" % (
            c, n, mediana(xs), p90(xs), max(xs), ceros))
    top = sorted(filas, key=lambda f: -f["triangulos_totales"])[:5]
    print("  top-5 archivos:")
    for f in top:
        print("    %8d  %s" % (f["triangulos_totales"], f["ruta_relativa"]))


def sec_e(filas):
    print("== e. vertices_por_shape: maximo global ==")
    mejor = None
    dist = Counter()
    n_shapes = 0
    for f in filas:
        for v in f["vertices_por_shape"]:
            n_shapes += 1
            dist[v // 10000] += 1
            if mejor is None or v > mejor[0]:
                mejor = (v, f["ruta_relativa"])
    print("  N shapes medidas:", n_shapes)
    if mejor is None:
        print("  maximo global: no hay shapes medidas")
    else:
        print("  maximo global:", mejor[0], "en", mejor[1])
    print("  shapes por rango de 10k verts:")
    for k in sorted(dist):
        print("    [%2d0k,%2d0k): %d" % (k, k + 1, dist[k]))
    cerca = sum(1 for f in filas for v in f["vertices_por_shape"]
                if v >= 0.75 * 65535)
    print("  shapes con >=49.151 verts (75%% de 65.535):", cerca)


def sec_f(filas):
    print("== f. max huesos por vertice por criatura (actors/) ==")
    porcr: defaultdict[str, dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "max": Counter(), "verts": Counter(), "skin": 0})
    for f in filas:
        if not f["ruta_relativa"].startswith("actors/"):
            continue
        partes = f["ruta_relativa"].split("/")
        if len(partes) < 2:
            continue
        cr = partes[1]
        d = porcr[cr]
        d["n"] += 1
        if f["pesos"]["max_huesos_por_vertice"] is not None:
            d["skin"] += 1
            d["max"][f["pesos"]["max_huesos_por_vertice"]] += 1
            for k, v in f["pesos"]["histograma"].items():
                d["verts"][int(k)] += v
    rigidas = 0
    skin_real = 0
    for cr, d in sorted(porcr.items()):
        if d["skin"] == 0:
            continue
        mx = max(d["max"])
        if mx <= 1:
            rigidas += 1
        else:
            skin_real += 1
    print("  carpetas de actors/ con mallas con skin: rigidas(max<=1)=%d  skin_real(max>=2)=%d"
          % (rigidas, skin_real))
    for cr, d in sorted(porcr.items()):
        if d["skin"] == 0:
            continue
        mx = max(d["max"])
        hist = ",".join("%s:%d" % (k, d["verts"][k])
                        for k in sorted(d["verts"]) if d["verts"][k])
        print("  %-22s mallas=%-4d con_skin=%-4d max=%-2d  histograma[%s]" % (
            cr, d["n"], d["skin"], mx, hist))
    tot = Counter()
    for f in filas:
        for k, v in f["pesos"]["histograma"].items():
            tot[int(k)] += v
    print("  histograma global de huesos/vertice (vertice: cuantos):",
          dict(sorted(tot.items())))


def sec_g(filas):
    print("== g. body_part_id: existencia, flags, assets ==")
    bp = Counter()
    bpf = Counter()
    bp_ej = {}
    for f in filas:
        for p in f["particiones"]:
            bp[p["body_part_id"]] += 1
            bpf[(p["body_part_id"], p["flags"])] += 1
            bp_ej.setdefault(p["body_part_id"], set()).add(f["_clase"])
    print("  ids distintos:", len(bp))
    for b, k in bp.most_common():
        flags = ",".join("%d:%d" % (fl, n) for (bb, fl), n in bpf.items() if bb == b)
        print("    id %-6d x%-6d  flags[%s]  clases: %s" % (
            b, k, flags, ",".join(sorted(bp_ej[b])[:6])))
    solo_flag = Counter(fl for (_, fl) in bpf)
    print("  flags globales:", dict(solo_flag))


def sec_h(filas):
    print("== h. combinaciones flags1/flags2 (por frecuencia) ==")
    comb = Counter()
    n = 0
    for f in filas:
        for s in f["shapes"]:
            if s["flags1"] is not None:
                n += 1
                comb[(s["flags1"], s["flags2"])] += 1
    print("  N shapes con flags:", n, " combinaciones distintas:", len(comb))
    for (a, b), k in comb.most_common(25):
        print("    f1=0x%08x f2=0x%08x x%-6d %s" % (a, b, k, pct(k, n)))
    una = sum(1 for k in comb.values() if k == 1)
    print("  combos vistas 1 sola vez:", una)


def sec_i(filas):
    print("== i. ranuras_textura_pobladas x shader_tipo ==")
    por = Counter()
    tot = Counter()
    sin = Counter()
    for f in filas:
        for s in f["shapes"]:
            t = s["shader_tipo"]
            tot[t] += 1
            if s["ranuras_textura_pobladas"]:
                por[(t, tuple(s["ranuras_textura_pobladas"]))] += 1
            else:
                sin[t] += 1
    for t, k in tot.most_common():
        print("  %s: N=%d" % (t, k))
        for (tt, slots), c in por.most_common():
            if tt == t:
                print("      ranuras %-18s x%-6d %s" % (
                    str(list(slots)), c, pct(c, k)))
        if sin[t]:
            print("      sin ranuras pobladas x%d" % sin[t])


def sec_j(filas):
    print("== j. archivos no parseables ==")
    errs = Counter()
    n_err = 0
    with open(CENSO, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if "error" in r:
                n_err += 1
                errs[r["error"]] += 1
    print("  total con error:", n_err, "de 22394")
    for e, k in errs.most_common():
        print("    x%d  %s" % (k, e))
    print("  (chequeos estructurales adicionales: ver verificar.py / verif_resumen.json)")


SECCIONES = {"a": sec_a, "b": sec_b, "c": sec_c, "d": sec_d, "e": sec_e,
             "f": sec_f, "g": sec_g, "h": sec_h, "i": sec_i, "j": sec_j}


def main():
    pedidas = sys.argv[1:] or sorted(SECCIONES)
    filas = cargar()
    print("censo.jsonl: %d filas validas de 22394" % len(filas))
    for s in pedidas:
        SECCIONES[s](filas)
        print()


if __name__ == "__main__":
    main()
