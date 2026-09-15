import json
import math
from collections import Counter, defaultdict

def compute_all():
    with open("censo.jsonl", "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    total_n = len(lines)
    ok_entries = []
    err_entries = []
    
    for line in lines:
        entry = json.loads(line)
        if "error" in entry:
            err_entries.append(entry)
        else:
            ok_entries.append(entry)
            
    print(f"Total N = {total_n} (Ok: {len(ok_entries)}, Errores: {len(err_entries)})")
    
    # -------------------------------------------------------------
    # j. Archivos no parseables agrupados por causa
    # -------------------------------------------------------------
    print("\n" + "="*80)
    print("j. ARCHIVOS NO PARSEABLES AGRUPADOS POR CAUSA")
    print("="*80)
    err_counts = Counter()
    err_by_type = defaultdict(list)
    for e in err_entries:
        err_msg = e["error"]
        # categorize
        err_type = err_msg.split(":")[0]
        err_counts[err_msg] += 1
        err_by_type[err_type].append(e["ruta_relativa"])
        
    for msg, count in err_counts.most_common():
        print(f"  [{count:4d}] {msg}")
        for sample in err_by_type[msg.split(':')[0]][:3]:
            print(f"         ejemplo: {sample}")

    # -------------------------------------------------------------
    # a. tipo_nodo_raiz x carpeta de primer nivel (y mezclas estático/skin)
    # -------------------------------------------------------------
    print("\n" + "="*80)
    print("a. TIPO DE NODO RAIZ x CARPETA DE PRIMER NIVEL")
    print("="*80)
    raiz_by_folder = defaultdict(Counter)
    skin_by_raiz = defaultdict(lambda: {"total": 0, "tiene_skin": 0, "estatico": 0})
    
    for e in ok_entries:
        rel = e["ruta_relativa"].replace("\\", "/")
        top = rel.split("/")[0] if "/" in rel else "root"
        r = e.get("tipo_nodo_raiz") or "None"
        raiz_by_folder[top][r] += 1
        
        skin_by_raiz[r]["total"] += 1
        if e.get("tiene_skin"):
            skin_by_raiz[r]["tiene_skin"] += 1
        else:
            skin_by_raiz[r]["estatico"] += 1

    folders = sorted(raiz_by_folder.keys())
    all_roots = sorted(list(skin_by_raiz.keys()))
    
    print(f"{'Carpeta':<20} | " + " | ".join(f"{r:>15}" for r in all_roots) + " | Total")
    print("-" * 120)
    for fld in folders:
        row = [f"{fld:<20}"]
        tot = 0
        for r in all_roots:
            cnt = raiz_by_folder[fld][r]
            tot += cnt
            row.append(f"{cnt:>15}")
        row.append(f"{tot:>8}")
        print(" | ".join(row))

    print("\n¿BSFadeNode es exclusivo de estáticos y NiNode de skinneados?:")
    for r in all_roots:
        info = skin_by_raiz[r]
        pct_skin = (info["tiene_skin"] / info["total"] * 100) if info["total"] else 0
        print(f"  {r:<20}: Total={info['total']:<6} | Skinneados={info['tiene_skin']:<6} ({pct_skin:.1f}%) | Estáticos={info['estatico']:<6} ({100-pct_skin:.1f}%)")

    # -------------------------------------------------------------
    # b. bsxflags_valor x clase de asset (tabla de frecuencias)
    # -------------------------------------------------------------
    print("\n" + "="*80)
    print("b. BSXFLAGS_VALOR x CLASE DE ASSET (FRECUENCIAS)")
    print("="*80)
    bsx_by_class = defaultdict(Counter)
    bsx_global = Counter()
    for e in ok_entries:
        top = e["ruta_relativa"].replace("\\", "/").split("/")[0]
        val = e.get("bsxflags_valor")
        bsx_by_class[top][val] += 1
        bsx_global[val] += 1
        
    print("Top 15 BSXFlags globales:")
    for val, count in bsx_global.most_common(15):
        print(f"  BSXFlags = {str(val):<8}: {count:6d} ({count/len(ok_entries)*100:.2f}%)")

    print("\nFrecuencias por carpeta principal (Top 5 clases y sus valores principales):")
    for fld in sorted(bsx_by_class.keys()):
        top_vals = bsx_by_class[fld].most_common(5)
        vals_str = ", ".join(f"{v}: {c}" for v, c in top_vals)
        print(f"  {fld:<15} (N={sum(bsx_by_class[fld].values())}): {vals_str}")

    # -------------------------------------------------------------
    # c. Formas bhk* x clase, y material_havok x clase
    # -------------------------------------------------------------
    print("\n" + "="*80)
    print("c. FORMAS BHK* x CLASE Y MATERIAL_HAVOK x CLASE")
    print("="*80)
    bhk_by_class = defaultdict(Counter)
    mat_by_class = defaultdict(Counter)
    for e in ok_entries:
        top = e["ruta_relativa"].replace("\\", "/").split("/")[0]
        col = e.get("colision", {})
        for bhk in col.get("tipos_bhk", []):
            if bhk.endswith("Shape") or bhk == "bhkMoppBvTreeShape":
                bhk_by_class[top][bhk] += 1
        mat = col.get("material_havok")
        if mat:
            mat_by_class[top][mat] += 1
            
    print("Formas bhk* por clase:")
    for fld in sorted(bhk_by_class.keys()):
        shapes = bhk_by_class[fld].most_common(4)
        s_str = ", ".join(f"{s}: {c}" for s, c in shapes)
        print(f"  {fld:<15}: {s_str}")

    print("\nMateriales Havok más frecuentes por clase:")
    for fld in sorted(mat_by_class.keys()):
        mats = mat_by_class[fld].most_common(4)
        m_str = ", ".join(f"{m}: {c}" for m, c in mats)
        print(f"  {fld:<15}: {m_str}")

    # -------------------------------------------------------------
    # d. Triángulos: mediana, p90, máximo por clase
    # -------------------------------------------------------------
    print("\n" + "="*80)
    print("d. TRIÁNGULOS: MEDIANA, P90 Y MÁXIMO POR CLASE DE ASSET")
    print("="*80)
    tris_by_class = defaultdict(list)
    for e in ok_entries:
        top = e["ruta_relativa"].replace("\\", "/").split("/")[0]
        tris_by_class[top].append(e.get("triangulos_totales", 0))

    def percentile(arr, p):
        if not arr: return 0
        arr_s = sorted(arr)
        k = (len(arr_s) - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return arr_s[int(k)]
        return arr_s[f] * (c - k) + arr_s[c] * (k - f)

    print(f"{'Clase':<20} | {'N':>6} | {'Mediana':>10} | {'P90':>10} | {'Máximo':>10}")
    print("-" * 65)
    for fld in sorted(tris_by_class.keys()):
        arr = tris_by_class[fld]
        med = percentile(arr, 0.50)
        p90 = percentile(arr, 0.90)
        mx = max(arr) if arr else 0
        print(f"{fld:<20} | {len(arr):>6} | {med:>10.1f} | {p90:>10.1f} | {mx:>10d}")

    # -------------------------------------------------------------
    # e. vertices_por_shape: máximo global, cerca de 65.535?
    # -------------------------------------------------------------
    print("\n" + "="*80)
    print("e. VERTICES POR SHAPE: MÁXIMO GLOBAL")
    print("="*80)
    max_v = 0
    max_v_file = ""
    v_over_30k = []
    total_shapes = 0
    for e in ok_entries:
        for v in e.get("vertices_por_shape", []):
            total_shapes += 1
            if v > max_v:
                max_v = v
                max_v_file = e["ruta_relativa"]
            if v > 30000:
                v_over_30k.append((v, e["ruta_relativa"]))

    print(f"Total shapes analizados: {total_shapes}")
    print(f"Máximo global de vértices en un BSTriShape: {max_v} en {max_v_file}")
    print(f"Límite uint16: 65.535 (diferencia con máximo: {65535 - max_v})")
    print(f"Cantidad de shapes con > 30.000 vértices: {len(v_over_30k)}")
    for v, f in sorted(v_over_30k, reverse=True)[:10]:
        print(f"  {v:>6d} vértices en {f}")

    # -------------------------------------------------------------
    # f. max_huesos_por_vertice por criatura: rígidas vs skinneadas
    # -------------------------------------------------------------
    print("\n" + "="*80)
    print("f. HUESOS POR VÉRTICE POR CRIATURA (ACTORS)")
    print("="*80)
    creatures = {}
    for e in ok_entries:
        rel = e["ruta_relativa"].replace("\\", "/")
        if not rel.startswith("actors/"):
            continue
        parts = rel.split("/")
        c_name = parts[1] if len(parts) > 1 else "actors"
        mb = e.get("pesos", {}).get("max_huesos_por_vertice", 0)
        h = e.get("pesos", {}).get("histograma", {})
        if c_name not in creatures:
            creatures[c_name] = {"files": 0, "max_bones": 0, "hist": Counter(), "pure_rigid": True}
        creatures[c_name]["files"] += 1
        if mb > creatures[c_name]["max_bones"]:
            creatures[c_name]["max_bones"] = mb
        if mb > 1:
            creatures[c_name]["pure_rigid"] = False
        for k, cnt in h.items():
            creatures[c_name]["hist"][int(k)] += cnt

    rigid_creatures = []
    skinned_creatures = []
    for c, info in sorted(creatures.items()):
        if info["max_bones"] <= 1:
            rigid_creatures.append((c, info))
        else:
            skinned_creatures.append((c, info))

    print(f"Criaturas estrictamente rígidas (max huesos/vértice <= 1): {len(rigid_creatures)}")
    for c, info in rigid_creatures:
        print(f"  {c:<25} (N={info['files']} mallas): max={info['max_bones']}, hist={dict(info['hist'])}")

    print(f"\nCriaturas skinneadas de verdad (max huesos/vértice >= 2): {len(skinned_creatures)}")
    for c, info in skinned_creatures:
        h_str = ", ".join(f"{k}h:{cnt}" for k, cnt in sorted(info['hist'].items()))
        print(f"  {c:<25} (N={info['files']} mallas): max={info['max_bones']} | {h_str}")

    # -------------------------------------------------------------
    # g. body_part_id que existen de verdad, con sus flags
    # -------------------------------------------------------------
    print("\n" + "="*80)
    print("g. BODY_PART_ID QUE EXISTEN DE VERDAD Y SUS FLAGS")
    print("="*80)
    bp_dict = defaultdict(lambda: {"count": 0, "flags": Counter(), "assets": set()})
    for e in ok_entries:
        for p in e.get("particiones", []):
            bpid = p.get("body_part_id")
            fl = p.get("flags")
            bp_dict[bpid]["count"] += 1
            bp_dict[bpid]["flags"][fl] += 1
            if len(bp_dict[bpid]["assets"]) < 5:
                bp_dict[bpid]["assets"].add(e["ruta_relativa"])

    print(f"{'BodyPartID':<12} | {'Ocurrencias':>12} | {'Flags observados':<30} | Ejemplos")
    print("-" * 80)
    for bpid in sorted(bp_dict.keys()):
        info = bp_dict[bpid]
        fl_str = ", ".join(f"{fl}:{cnt}" for fl, cnt in info["flags"].items())
        samples = list(info["assets"])[:2]
        print(f"{bpid:<12} | {info['count']:>12d} | {fl_str:<30} | {', '.join(samples)}")

    # -------------------------------------------------------------
    # h. Combinaciones de flags1/flags2 por frecuencia
    # -------------------------------------------------------------
    print("\n" + "="*80)
    print("h. COMBINACIONES DE FLAGS1/FLAGS2 POR FRECUENCIA")
    print("="*80)
    flags_combos = Counter()
    for e in ok_entries:
        for sh in e.get("shapes", []):
            f1 = sh.get("flags1")
            f2 = sh.get("flags2")
            if f1 is not None and f2 is not None:
                flags_combos[(f1, f2)] += 1

    total_combos = sum(flags_combos.values())
    print(f"Total shapes con flags: {total_combos}. Combinaciones únicas: {len(flags_combos)}")
    for (f1, f2), count in flags_combos.most_common(25):
        pct = count / total_combos * 100
        print(f"  flags1 = 0x{f1:08x} ({f1:>10d}), flags2 = 0x{f2:08x} ({f2:>6d}) : {count:>6d} ({pct:>5.2f}%)")

    # -------------------------------------------------------------
    # i. Ranuras de textura pobladas x shader_tipo
    # -------------------------------------------------------------
    print("\n" + "="*80)
    print("i. RANURAS DE TEXTURA POBLADAS x SHADER_TIPO")
    print("="*80)
    slots_by_shader = defaultdict(Counter)
    for e in ok_entries:
        for sh in e.get("shapes", []):
            st = sh.get("shader_tipo")
            slots = tuple(sh.get("ranuras_textura_pobladas", []))
            slots_by_shader[st][slots] += 1

    for st in sorted(slots_by_shader.keys(), key=lambda x: str(x)):
        c = slots_by_shader[st]
        tot_st = sum(c.values())
        print(f"\nShader Tipo: {st} (Total shapes={tot_st}):")
        for slots, cnt in c.most_common(8):
            pct = cnt / tot_st * 100
            print(f"  Ranuras {list(slots)} : {cnt:>6d} ({pct:>5.1f}%)")

if __name__ == "__main__":
    compute_all()
