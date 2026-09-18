# -*- coding: utf-8 -*-
"""Lee la jerarquia de NiNode de un NIF de Skyrim SE y da posiciones de mundo.

No usa Blender ni PyNifly: parsea el binario. Existe porque PyNifly, al
importar, puede sustituir un esqueleto de referencia y devolver posiciones que
no son las del archivo -- y eso no da error, solo numeros equivocados.

Layout de un NiNode en SSE (version 20.2.0.7, user 12, BS 100):
  NiObjectNET : name(uint32 indice de string)
                numExtraData(uint32) + refs(int32 c/u)
                controller(int32)
  NiAVObject  : flags(uint32)
                translation(3 float) rotation(9 float) scale(float)
                collisionObject(int32)
  NiNode      : numChildren(uint32) + refs(int32 c/u)
                numEffects(uint32) + refs

Solo se parsea hasta children, que es lo unico que hace falta.
"""
import os
import struct
import sys

# BSFurnitureMarkerNode NO hereda de NiNode (BSFurnitureMarker <- NiExtraData).
# Incluirlo revienta al leer children: 123 archivos de muebles en el corpus.
# BSMasterParticleSystem: 93 archivos del corpus, todos con el tipo
# como RAIZ. El layout de NiNode parsea coherente en 93 de 93 bloques
# (1 hijo en 92, 2 en uno; cola de 14 a 30 bytes, que son sus campos
# propios). Lo contrario de BSFurnitureMarkerNode, que se saco de aca
# porque el sufijo enganaba y rompia 123 archivos de muebles.
# BSRangeNode: 0 bloques en el corpus. No lo ejercita nada; va en las
# tres listas para que no vuelvan a separarse.
TIPOS_NODO = {
    "NiNode", "BSFadeNode", "BSLeafAnimNode", "BSTreeNode",
    "BSOrderedNode", "BSValueNode", "BSMultiBoundNode",
    "BSBlastNode", "BSDamageStage", "BSRangeNode", "NiBillboardNode",
    "NiSwitchNode", "BSMasterParticleSystem",
}

def _sized(datos, i):
    (n,) = struct.unpack_from("<I", datos, i)
    return datos[i + 4:i + 4 + n].decode("cp1252", "replace"), i + 4 + n


def _short(datos, i):
    n = datos[i]
    return datos[i + 1:i + 1 + n].rstrip(b"\x00").decode("cp1252", "replace"), i + 1 + n


def leer(ruta):
    with open(ruta, "rb") as fh:
        datos = fh.read()
    i = datos.index(b"\n") + 1
    version, = struct.unpack_from("<I", datos, i); i += 4
    i += 1                                              # endian
    user, = struct.unpack_from("<I", datos, i); i += 4
    n_bloques, = struct.unpack_from("<I", datos, i); i += 4
    bs, = struct.unpack_from("<I", datos, i); i += 4
    if bs >= 130:
        # Este script leia el campo de proceso como SizedString EN EL MEDIO de
        # los tres shorts; los parsers del censo leian un cuarto ShortString
        # DESPUES. Las dos lecturas no pueden ser ambas correctas y ninguna esta
        # validada: el corpus tiene 22.393 archivos con BS=100, uno con BS=83 y
        # CERO con BS>=130. Elegir una a ojo corre todos los offsets de bloque.
        raise ValueError(
            "BS version %d (>=130, Fallout 4/76): la cabecera no esta validada "
            "contra ningun archivo del corpus" % bs)
    _a, i = _short(datos, i)
    _p, i = _short(datos, i)
    _e, i = _short(datos, i)

    n_tipos, = struct.unpack_from("<H", datos, i); i += 2
    tipos = []
    for _ in range(n_tipos):
        t, i = _sized(datos, i)
        tipos.append(t)
    idx = struct.unpack_from("<%dH" % n_bloques, datos, i); i += 2 * n_bloques
    tam = struct.unpack_from("<%dI" % n_bloques, datos, i); i += 4 * n_bloques
    n_str, = struct.unpack_from("<I", datos, i); i += 4
    i += 4
    strings = []
    for _ in range(n_str):
        s, i = _sized(datos, i)
        strings.append(s)
    n_grupos, = struct.unpack_from("<I", datos, i); i += 4
    i += 4 * n_grupos

    # --- offsets de cada bloque ---
    base = i
    offs, o = [], base
    for t in tam:
        offs.append(o)
        o += t

    nodos = {}
    for b in range(n_bloques):
        tipo = tipos[idx[b]]
        if tipo not in TIPOS_NODO:
            continue
        p = offs[b]
        nombre_i, = struct.unpack_from("<i", datos, p); p += 4
        n_ed, = struct.unpack_from("<I", datos, p); p += 4 + 4 * n_ed
        p += 4                                          # controller
        p += 4                                          # flags
        tr = struct.unpack_from("<3f", datos, p); p += 12
        rot = struct.unpack_from("<9f", datos, p); p += 36
        esc, = struct.unpack_from("<f", datos, p); p += 4
        p += 4                                          # collision
        n_hijos, = struct.unpack_from("<I", datos, p); p += 4
        hijos = struct.unpack_from("<%di" % n_hijos, datos, p) if n_hijos else ()
        nodos[b] = {
            "tipo": tipo,
            "nombre": strings[nombre_i] if 0 <= nombre_i < len(strings) else "?",
            "tr": tr, "rot": rot, "esc": esc,
            "hijos": [h for h in hijos if h >= 0],
        }
    return {"archivo": os.path.basename(ruta), "version": "0x%08X" % version,
            "bs": bs, "n_bloques": n_bloques, "nodos": nodos}


def mundo(nif):
    """Acumula transformadas desde la raiz. Devuelve {nombre: (x,y,z,escala)}."""
    nodos = nif["nodos"]
    hijos_de_alguien = {h for n in nodos.values() for h in n["hijos"]}
    raices = [b for b in nodos if b not in hijos_de_alguien]
    fuera, prof = {}, {}

    def mul(Ma, ta, sa, Mb, tb, sb):
        """(Ma,ta,sa) padre compuesto con (Mb,tb,sb) hijo."""
        M = [sum(Ma[r * 3 + k] * Mb[k * 3 + c] for k in range(3))
             for r in range(3) for c in range(3)]
        t = tuple(ta[r] + sa * sum(Ma[r * 3 + k] * tb[k] for k in range(3))
                  for r in range(3))
        return M, t, sa * sb

    def bajar(b, M, t, s, d):
        n = nodos[b]
        M2, t2, s2 = mul(M, t, s, n["rot"], n["tr"], n["esc"])
        fuera[n["nombre"]] = (round(t2[0], 2), round(t2[1], 2),
                              round(t2[2], 2), round(s2, 4))
        prof[n["nombre"]] = d
        for h in n["hijos"]:
            if h in nodos:
                bajar(h, M2, t2, s2, d + 1)

    I = [1, 0, 0, 0, 1, 0, 0, 0, 1]
    for r in raices:
        bajar(r, I, (0.0, 0.0, 0.0), 1.0, 0)
    return fuera, prof


def main():
    for ruta in sys.argv[1:]:
        nif = leer(ruta)
        pos, prof = mundo(nif)
        print("=== %s  (bloques=%d, BS=%d, nodos=%d)" % (
            nif["archivo"], nif["n_bloques"], nif["bs"], len(pos)))
        for nom, p in sorted(pos.items(), key=lambda kv: -kv[1][2]):
            print("   %s%-28s %9.2f %9.2f %9.2f  esc=%.3f" % (
                "  " * prof[nom], nom, p[0], p[1], p[2], p[3]))
        print()


if __name__ == "__main__":
    main()
