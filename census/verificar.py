# -*- coding: utf-8 -*-
"""verificar.py — auditoria estructural del corpus completo, bloque por bloque.

No produce el censo: produce la evidencia de que cada parser del censo sigue
la identidad de tamano (cursor == offset + size declarado por la cabecera del
bloque) y los enums del spec, sobre los 22.394 NIF.

Uso:
  python verificar.py <carpeta raiz>            (imprime reporte)
  python verificar.py <carpeta raiz> --json salida.json
"""
import json
import os
import struct
import sys
from collections import Counter, defaultdict
from multiprocessing import Pool, cpu_count

from parser_nif import Nif, TIPOS_SHAPE, HAVOK_MATERIALS


def _chequear(ruta):
    ev = []          # (categoria, detalle)
    try:
        n = Nif(ruta)
    except Exception as e:
        return ruta, [("header_exc", "%s: %s" % (type(e).__name__, e))]

    d = n.d
    ver = ".".join(str((n.version >> s) & 0xFF) for s in (24, 16, 8, 0))
    if (ver, n.user, n.bs) != ("20.2.0.7", 12, 100):
        ev.append(("version_anomala", "%s/%s/%s" % (ver, n.user, n.bs)))
    if n.header_tail:
        ev.append(("header_cola", str(n.header_tail)))

    # 1) sweep de geometria completo (incluye violaciones de shaders/particiones)
    try:
        _, _, shapes, _, _, viols = n.trishapes_detalle()
        for v in viols:
            ev.append(("geom", v))
    except Exception as e:
        ev.append(("geom_exc", "%s: %s" % (type(e).__name__, e)))

    # 2) todas las particiones, aunque no cuelguen de un shape
    ws_vistos = Counter()
    for idx, o, s in n.de_tipo("NiSkinPartition"):
        try:
            p = n._parse_skin_partition(o, s)
            for v in p["violaciones"]:
                ev.append(("partition", v))
            ws_vistos.update(p["num_w"])
        except Exception as e:
            ev.append(("partition_exc", "%s: %s" % (type(e).__name__, e)))
    for w, c in ws_vistos.items():
        for _ in range(c):
            ev.append(("numw", str(w)))

    # 3) texture sets
    for idx, o, s in n.de_tipo("BSShaderTextureSet"):
        _, _, viol = n._parse_texture_set(o, s)
        for v in viol:
            ev.append(("texset", v))
        num_tex, = struct.unpack_from("<I", d, o)
        ev.append(("texset_num", str(num_tex)))

    # 4) shader properties
    for t in ("BSLightingShaderProperty", "BSEffectShaderProperty",
              "BSSkyShaderProperty", "BSWaterShaderProperty"):
        for idx, o, s in n.de_tipo(t):
            sh = n._parse_shader_property(idx)
            for v in sh["violaciones"]:
                ev.append(("shader", "%s %s" % (t, v)))
            off = 8 if t == "BSLightingShaderProperty" else 4
            if o + off + 4 <= len(d):
                n_ed, = struct.unpack_from("<I", d, o + off)
                if n_ed > 0:
                    ev.append(("shader_numed", "%s %d" % (t, n_ed)))

    # 5) identidad de tamano del cuerpo de los shapes.
    # Regla MEDIDA (2324/2324 bloques de muestra sistematica): despues de
    # Data Size viene ParticleDataSize (u32); si >0 le siguen 2*ParticleDataSize
    # bytes de arrays (vert/norm/tri half-floats). BSDynamicTriShape agrega
    # DynamicDataSize (u32) + esos bytes (== v*16 en toda la muestra).
    for idx, o, s in n.de_tipo(*TIPOS_SHAPE):
        tipo = n.bloques[idx][0]
        try:
            p, _ = n._saltar_niavobject(o)
            p += 16 + 12 + 8
            tri, = struct.unpack_from("<H", d, p); p += 2
            v, = struct.unpack_from("<H", d, p); p += 2
            dsz, = struct.unpack_from("<I", d, p); p += 4
            pdsz, = struct.unpack_from("<I", d, p + dsz)
            fin = p + dsz + 4 + 2 * pdsz
            if tipo == "BSDynamicTriShape":
                dynsz, = struct.unpack_from("<I", d, fin)
                fin += 4 + dynsz
            ev.append(("shape_tail", "%s:%d" % (tipo, (o + s) - fin)))
        except Exception as e:
            ev.append(("shape_tail_exc", "%s: %s" % (type(e).__name__, e)))

    # 5b) trailer de archivo: los ultimos 8 bytes tras el ultimo bloque
    if n.bloques:
        cola = d[n.bloques[-1][1] + n.bloques[-1][2]:]
        if cola == b"\x01\x00\x00\x00\x00\x00\x00\x00":
            ev.append(("trailer", "estandar_01_00"))
        else:
            ev.append(("trailer", "otro:" + cola.hex()[:24]))
    else:
        # numBlocks = 0: antes IndexError crudo y se perdia toda la corrida.
        ev.append(("trailer", "sin_bloques"))

    # 5c) BSXFlags: bloque de 8 bytes exactos, name idx valido
    for idx, o, s in n.de_tipo("BSXFlags"):
        if s != 8:
            ev.append(("bsxflags_size", str(s)))
        nombre_i, = struct.unpack_from("<i", d, o)
        if not (0 <= nombre_i < len(n.strings)):
            ev.append(("bsxflags_nombre", str(nombre_i)))

    # 5d) skin instances: tamano exacto 16+4*nb (+4+4*np si dismember)
    for idx, o, s in n.de_tipo("BSDismemberSkinInstance", "NiSkinInstance"):
        tipo = n.bloques[idx][0]
        nb, = struct.unpack_from("<i", d, o + 12)
        esperado = 16 + 4 * max(nb, 0)
        if tipo == "BSDismemberSkinInstance":
            if o + esperado + 4 <= o + s:
                np_, = struct.unpack_from("<I", d, o + esperado)
                esperado += 4 + 4 * np_
        if esperado != s:
            ev.append(("skin_inst_size", "%s %d!=%d" % (tipo, esperado, s)))

    # 6) rigid bodies: size == 250 + 4*numConstraints
    for idx, o, s in n.de_tipo("bhkRigidBody", "bhkRigidBodyT"):
        if s < 250:
            ev.append(("rigidbody_size", "corto:%d" % s))
            continue
        c, = struct.unpack_from("<I", d, o + 244)
        if s != 250 + 4 * c:
            ev.append(("rigidbody_size", "size=%d c=%d" % (s, c)))
        if d[o + 4] > 54:
            ev.append(("layer_fuera_enum", str(d[o + 4])))
        if d[o + 224] > 9:
            ev.append(("motion_fuera_enum", str(d[o + 224])))

    # 7) materiales de chunk de mallas comprimidas
    for idx, o, s in n.de_tipo("bhkCompressedMeshShapeData"):
        p = o + 4 * 4 + 4 + 32 + 2
        if p + 4 > o + s:
            ev.append(("chunk_mats", "bloque corto"))
            continue
        n32, = struct.unpack_from("<I", d, p); p += 4 + 4 * n32
        n16, = struct.unpack_from("<I", d, p); p += 4 + 4 * n16
        n8, = struct.unpack_from("<I", d, p); p += 4 + 4 * n8
        nm, = struct.unpack_from("<I", d, p); p += 4
        if nm > 256 or p + 8 * nm > o + s:
            ev.append(("chunk_mats", "tabla fuera de bloque nm=%d" % nm))
            continue
        for k in range(nm):
            mid, = struct.unpack_from("<I", d, p + 8 * k)
            if mid in HAVOK_MATERIALS:
                ev.append(("chunk_mat_known", "1"))
            else:
                ev.append(("chunk_mat_unknown", str(mid)))

    # 7b) nodos: jerarquia parseable sin explosiones
    try:
        n.nodos()
    except Exception as e:
        ev.append(("nodos_exc", "%s: %s" % (type(e).__name__, e)))

    # 8) particiones dismember: rangos de flags y body parts
    for idx, o, s in n.de_tipo("BSDismemberSkinInstance"):
        data_ref, part_ref, root_ref, num_bones = struct.unpack_from("<4i", d, o)
        p = o + 16 + 4 * max(num_bones, 0)
        if p + 4 > o + s:
            ev.append(("dismember", "bloque corto"))
            continue
        num_parts, = struct.unpack_from("<I", d, p); p += 4
        if p + 4 * num_parts > o + s:
            ev.append(("dismember", "particiones fuera de bloque"))
            continue
        for _ in range(num_parts):
            flag, bp = struct.unpack_from("<2H", d, p); p += 4
            ev.append(("dismember_flag", str(flag)))
            ev.append(("dismember_bp", str(bp)))

    return ruta, ev


def _chequear_seguro(ruta):
    # Red por archivo: una excepcion cruda en una seccion sin guarda propia
    # (la 8 lee offsets sin cota, por ejemplo) antes mataba la corrida entera
    # del Pool por UN NIF degenerado. El lote sigue y el fallo queda contado
    # como evento, igual que header_exc.
    try:
        return _chequear(ruta)
    except Exception as e:
        return ruta, [("chequeo_exc", "%s: %s" % (type(e).__name__, e))]


def main():
    if len(sys.argv) < 2:
        print("Uso: python verificar.py <carpeta raiz> [--json salida.json]")
        raise SystemExit(2)
    raiz = sys.argv[1]
    archivos = []
    for base, _, files in os.walk(raiz):
        for f in files:
            if f.lower().endswith(".nif"):
                archivos.append(os.path.join(base, f))
    print("Verificando %d archivos..." % len(archivos))

    conteos = defaultdict(Counter)
    ejemplos = defaultdict(dict)      # cat -> detalle -> ruta (primer caso)
    n_ok = 0
    with Pool(max(1, cpu_count() - 1)) as pool:
        for i, (ruta, ev) in enumerate(pool.imap_unordered(_chequear_seguro, archivos, 50), 1):
            if not ev:
                n_ok += 1
            for cat, det in ev:
                d = conteos[cat]
                if d[det] < 10 ** 9:
                    d[det] += 1
                if det not in ejemplos[cat] and len(ejemplos[cat]) < 200:
                    ejemplos[cat][det] = os.path.relpath(ruta, raiz)
            if i % 4000 == 0:
                print("  %d/%d" % (i, len(archivos)))
    print("Archivos sin ningun evento estructural: %d" % n_ok)
    print()
    for cat in sorted(conteos):
        total = sum(conteos[cat].values())
        top = conteos[cat].most_common(12)
        print("== %s (%d eventos, %d valores distintos)" % (cat, total, len(conteos[cat])))
        for det, c in top:
            ej = ejemplos[cat].get(det)
            print("   %s x%d   ej: %s" % (det, c, ej))
        print()

    if "--json" in sys.argv:
        if sys.argv[-1] == "--json":
            print("Falta el valor de --json")
            raise SystemExit(2)
        out = sys.argv[sys.argv.index("--json") + 1]
        datos = {"sin_eventos": n_ok, "total": len(archivos),
                 "categorias": {c: {"total": sum(d.values()),
                                    "detalle": dict(d.most_common(200))}
                                for c, d in conteos.items()},
                 "ejemplos": {c: dict(list(e.items())[:200])
                              for c, e in ejemplos.items()}}
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(datos, fh, ensure_ascii=False, indent=1)
        print("Resumen escrito en", out)


if __name__ == "__main__":
    main()
