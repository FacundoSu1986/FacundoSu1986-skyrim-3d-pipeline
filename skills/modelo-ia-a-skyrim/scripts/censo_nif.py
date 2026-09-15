# -*- coding: utf-8 -*-
"""Semilla para censar el corpus vanilla de Skyrim SE. Python puro, sin Blender.

Helper reducido / legado de la skill. La fuente de verdad del censo es
census/parser_nif.py (no importarlo desde aca: build_skill.py no empaqueta
census/). Este archivo se queda en la skill para --autotest y mediciones
de cabecera cuando se instala solo el .skill.

Parsea la cabecera de un NIF y expone lo que hace falta para medir miles de
archivos: tabla de tipos de bloque, offsets, tabla de strings, jerarquia de
nodos con posiciones de mundo, BSXFlags, conteo de triangulos y rutas de
textura.

QUE ESTA VERIFICADO Y QUE NO

Lo que hay aca se comprobo contra seis archivos vanilla cuyos valores se
conocian de antemano (correr --autotest). Todo lo demas que el censo necesita
--colision bhk*, particiones de body-part, pesos por vertice, flags de
shader-- NO esta implementado a proposito. Escribir esos parsers de memoria es
exactamente como se meten los errores que despues no dan error.

Para agregar un campo nuevo, el orden correcto es:
  1. Elegir un archivo donde YA SEPAS la respuesta (abrilo en NifSkope).
  2. Escribir el parser.
  3. Agregar el caso a AUTOTEST con el valor esperado.
  4. Recien entonces correrlo sobre el corpus.

HALLAZGO QUE CAMBIA EL CENSO

En SSE, un BSTriShape SKINNEADO no lleva la geometria adentro: numTriangles=0,
numVertices=0, dataSize=0. La geometria vive en el NiSkinPartition. Los
estaticos si la llevan inline. Medido:

  dwarvenshield.nif          estatico   1 shape    1.612 tri inline
  soulgemgreater01.nif       estatico   1 shape      316 tri inline
  dwarvensteamcenturion.nif  estatico   1 shape    6.154 tri inline
  steamcenturion.nif         SKINNEADO 15 shapes       0 tri inline

Contar triangulos de la forma obvia devuelve CERO para toda criatura y toda
armadura -- justo las clases que mas interesan. Por eso trishapes() reporta
"geometria_inline": sin esa marca, un censo de 40.000 archivos dice que la
mitad del juego no tiene poligonos y nadie se entera.

PENDIENTE #1 (el mas importante): triangulos de mallas skinneadas

No esta resuelto. Se intento leer NiSkinPartition asumiendo el layout
  numParticiones(u32) y luego por particion
  numVertices(u16) numTriangles(u16) numBones(u16) numStrips(u16)
  numWeightsPerVertex(u16)
y da basura: pesos-por-vertice = 1035 (el maximo real del motor es 4) y ese
1035 resulta ser un pedazo del vertexDesc del bloque anterior. O sea, el
offset de arranque esta mal para SSE.

No ajustes offsets hasta que salga el numero esperado: eso es ajustar ruido.
Saca el layout de nif.xml de NifSkope o de la libreria nifly, implementalo, y
falsificalo contra este valor conocido:

  steamcenturion.nif (el de ref/, NO el de out/) = 6.007 triangulos en total

Y contra estas dos cotas de sanidad, que atrapan el error de offset que tuve:
  - pesos por vertice <= 4 SIEMPRE
  - huesos por particion <= la cantidad de NiNode del archivo

Solo se valido con BS version 100 (Skyrim SE). Para Fallout 4 (BS >= 130) la
cabecera lleva un campo extra y BSTriShape cambia de layout: hay que volver a
falsificar antes de creerle nada.

Uso:
  python censo_nif.py --autotest <carpeta raiz del corpus>
  python censo_nif.py <archivo.nif> [<archivo.nif> ...]
  python censo_nif.py --censo <carpeta> --salida censo.jsonl
"""
import json
import os
import re
import struct
import sys

# Tipos que heredan de NiNode. BSFurnitureMarkerNode NO esta en la lista a
# proposito: pese al sufijo "Node", hereda de NiExtraData, no de NiAVObject.
# Incluirlo hace que se lea su contenido con el layout de NiNode y salga un
# conteo de hijos absurdo. Medido: 30 de 76 archivos de meshes/furniture/
# revientan con "unpack_from requires a buffer of at least 4093659953 bytes".
#
# El sufijo del nombre no dice de que hereda. Verificalo en nif.xml.
TIPOS_NODO = {"NiNode", "BSFadeNode", "BSLeafAnimNode", "BSTreeNode",
              "BSOrderedNode", "BSValueNode", "BSMultiBoundNode",
              "BSBlastNode", "BSDamageStage", "NiBillboardNode",
              "NiSwitchNode"}


class Nif(object):
    """Un NIF parseado a nivel de cabecera. Los bloques se leen bajo demanda."""

    def __init__(self, ruta):
        self.ruta = ruta
        with open(ruta, "rb") as fh:
            d = self.d = fh.read()
        i = d.index(b"\n") + 1
        self.version, = struct.unpack_from("<I", d, i); i += 4
        i += 1                                             # endian
        self.user, = struct.unpack_from("<I", d, i); i += 4
        n_bloques, = struct.unpack_from("<I", d, i); i += 4
        self.bs, = struct.unpack_from("<I", d, i); i += 4

        for _ in range(3):
            i += 1 + d[i]
        if self.bs >= 130:
            i += 1 + d[i]

        n_tipos, = struct.unpack_from("<H", d, i); i += 2
        tipos = []
        for _ in range(n_tipos):
            n, = struct.unpack_from("<I", d, i); i += 4
            tipos.append(d[i:i + n].decode("cp1252", "replace")); i += n
        idx = struct.unpack_from("<%dH" % n_bloques, d, i); i += 2 * n_bloques
        tam = struct.unpack_from("<%dI" % n_bloques, d, i); i += 4 * n_bloques

        n_str, = struct.unpack_from("<I", d, i); i += 4
        i += 4
        self.strings = []
        for _ in range(n_str):
            n, = struct.unpack_from("<I", d, i); i += 4
            self.strings.append(d[i:i + n].decode("cp1252", "replace")); i += n
        n_grupos, = struct.unpack_from("<I", d, i); i += 4 + 4 * n_grupos

        self.bloques, o = [], i
        for b in range(n_bloques):
            self.bloques.append((tipos[idx[b]], o, tam[b]))
            o += tam[b]

    def raiz(self):
        return self.bloques[0][0] if self.bloques else None

    def cuenta_tipos(self):
        c = {}
        for tipo, _, _ in self.bloques:
            c[tipo] = c.get(tipo, 0) + 1
        return c

    def de_tipo(self, *tipos):
        return [(o, n) for t, o, n in self.bloques if t in tipos]

    def bsxflags(self):
        for o, _ in self.de_tipo("BSXFlags"):
            _, valor = struct.unpack_from("<Ii", self.d, o)
            return valor
        return None

    def texturas(self):
        vistas = re.findall(rb"[ -~]{4,160}\.dds", self.d)
        return sorted(set(m.decode("cp1252", "replace") for m in vistas))

    def _saltar_niavobject(self, p):
        nombre_i, = struct.unpack_from("<i", self.d, p); p += 4
        n_ed, = struct.unpack_from("<I", self.d, p); p += 4 + 4 * n_ed
        p += 4
        p += 4
        p += 12 + 36 + 4
        p += 4
        nombre = (self.strings[nombre_i]
                  if 0 <= nombre_i < len(self.strings) else "?")
        return p, nombre

    def es_skinneado(self):
        c = self.cuenta_tipos()
        return ("BSDismemberSkinInstance" in c) or ("NiSkinInstance" in c)

    def trishapes(self):
        fuera = []
        for o, _ in self.de_tipo("BSTriShape"):
            p, nombre = self._saltar_niavobject(o)
            p += 16
            if self.bs >= 151:
                p += 24
            p += 4 + 4 + 4
            p += 8
            if self.bs < 130:
                tri, = struct.unpack_from("<H", self.d, p); p += 2
            else:
                tri, = struct.unpack_from("<I", self.d, p); p += 4
            ver, = struct.unpack_from("<H", self.d, p)
            fuera.append((nombre, tri, ver))
        return fuera

    def nodos(self):
        n = {}
        for b, (tipo, o, _) in enumerate(self.bloques):
            if tipo not in TIPOS_NODO:
                continue
            p = o
            nombre_i, = struct.unpack_from("<i", self.d, p); p += 4
            n_ed, = struct.unpack_from("<I", self.d, p); p += 4 + 4 * n_ed
            p += 4 + 4
            tr = struct.unpack_from("<3f", self.d, p); p += 12
            rot = struct.unpack_from("<9f", self.d, p); p += 36
            esc, = struct.unpack_from("<f", self.d, p); p += 4
            p += 4
            n_h, = struct.unpack_from("<I", self.d, p); p += 4
            hijos = struct.unpack_from("<%di" % n_h, self.d, p) if n_h else ()
            n[b] = {"tipo": tipo,
                    "nombre": (self.strings[nombre_i]
                               if 0 <= nombre_i < len(self.strings) else "?"),
                    "tr": tr, "rot": rot, "esc": esc,
                    "hijos": [h for h in hijos if h >= 0]}
        return n

    def mundo(self):
        nodos = self.nodos()
        hijos = set()
        for v in nodos.values():
            hijos.update(v["hijos"])
        fuera = {}

        def mul(Ma, ta, sa, Mb, tb, sb):
            M = [sum(Ma[r * 3 + k] * Mb[k * 3 + c] for k in range(3))
                 for r in range(3) for c in range(3)]
            t = tuple(ta[r] + sa * sum(Ma[r * 3 + k] * tb[k] for k in range(3))
                      for r in range(3))
            return M, t, sa * sb

        def bajar(b, M, t, s):
            v = nodos[b]
            M2, t2, s2 = mul(M, t, s, v["rot"], v["tr"], v["esc"])
            fuera[v["nombre"]] = (round(t2[0], 2), round(t2[1], 2),
                                  round(t2[2], 2), round(s2, 4))
            for h in v["hijos"]:
                if h in nodos:
                    bajar(h, M2, t2, s2)

        for r in [b for b in nodos if b not in hijos]:
            bajar(r, [1, 0, 0, 0, 1, 0, 0, 0, 1], (0.0, 0.0, 0.0), 1.0)
        return fuera

    def fila(self, base=""):
        tri = self.trishapes()
        return {
            "ruta": os.path.relpath(self.ruta, base) if base else self.ruta,
            "bytes": os.path.getsize(self.ruta),
            "version": ".".join(str((self.version >> s) & 0xFF)
                                for s in (24, 16, 8, 0)),
            "user": self.user,
            "bs": self.bs,
            "raiz": self.raiz(),
            "bloques": self.cuenta_tipos(),
            "bsxflags": self.bsxflags(),
            "n_shapes": len(tri),
            "skinneado": self.es_skinneado(),
            "triangulos_inline": sum(t for _, t, _ in tri),
            "geometria_inline": any(t for _, t, _ in tri) or not tri,
            "vertices_por_shape": [v for _, _, v in tri],
            "texturas": self.texturas(),
        }


AUTOTEST = [
    ("actors/dwarvensteamcenturion/character assets/steamcenturion.nif",
     {"raiz": "NiNode", "n_bloques": 112, "bsxflags": None,
      "skinneado": True, "triangulos_inline": 0,
      "bloques": {"NiNode": 21, "BSTriShape": 15,
                  "BSDismemberSkinInstance": 15, "NiSkinData": 15,
                  "NiSkinPartition": 15, "BSLightingShaderProperty": 15,
                  "NiAlphaProperty": 15, "BSShaderTextureSet": 1}}),
    ("actors/dwarvensteamcenturion/dwarvensteamcenturion.nif",
     {"raiz": "BSFadeNode", "n_bloques": 9, "bsxflags": 130,
      "skinneado": False, "triangulos_inline": 6154}),
    ("armor/dwarven/dwarvenshield.nif",
     {"raiz": "BSFadeNode", "n_bloques": 10, "bsxflags": 194,
      "triangulos_inline": 1612}),
    ("clutter/soulgem/soulgemgreater01.nif",
     {"raiz": "BSFadeNode", "n_bloques": 20, "bsxflags": 203,
      "triangulos_inline": 316}),
    ("dungeons/caves/ice/clutter/caveiiciclemed01.nif",
     {"bsxflags": 130}),
    ("dungeons/dwemer/animated/astrolabe/lens/dweastrolabelens01.nif",
     {"bsxflags": 523}),
]


def _buscar(raiz, rel):
    cola = rel.replace("/", os.sep).lower()
    encontrados = []
    for base, _, archivos in os.walk(raiz):
        for f in archivos:
            ruta = os.path.join(base, f)
            if ruta.lower().endswith(cola):
                encontrados.append(ruta)
    if len(encontrados) > 1:
        raise SystemExit(
            "AMBIGUO: %d archivos terminan en %s.\n%s\n"
            "Apunta --autotest a la carpeta donde BAE extrajo el vanilla, no "
            "a un proyecto que tenga copias." % (
                len(encontrados), rel, "\n".join("  " + e for e in encontrados)))
    return encontrados[0] if encontrados else None


def autotest(raiz):
    ok = fallo = falta = 0
    for rel, esperado in AUTOTEST:
        ruta = _buscar(raiz, rel)
        if ruta is None:
            print("  [falta]  %s" % rel)
            falta += 1
            continue
        n = Nif(ruta)
        real = {"n_bloques": len(n.bloques), "raiz": n.raiz(),
                "bsxflags": n.bsxflags(), "bloques": n.cuenta_tipos(),
                "skinneado": n.es_skinneado(),
                "triangulos_inline": sum(t for _, t, _ in n.trishapes())}
        for campo, valor in esperado.items():
            if real[campo] == valor:
                ok += 1
            else:
                fallo += 1
                print("  [FALLA]  %s :: %s" % (os.path.basename(rel), campo))
                print("           esperado %r" % (valor,))
                print("           obtenido %r" % (real[campo],))
    print("")
    print("  %d comprobaciones ok, %d fallidas, %d archivos no encontrados"
          % (ok, fallo, falta))
    if fallo:
        print("  El parser NO esta listo para censar.")
    elif falta:
        print("  Ok hasta donde se pudo comprobar, pero faltan archivos.")
    else:
        print("  Parser validado. Ahora si, censar.")
    return fallo == 0


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    if a[0] == "--autotest":
        if not autotest(a[1]):
            raise SystemExit(1)
        return
    if a[0] == "--censo":
        raiz = a[1]
        salida = a[a.index("--salida") + 1] if "--salida" in a else "censo.jsonl"
        n_ok = n_err = 0
        with open(salida, "w", encoding="utf-8") as fh:
            for base, _, archivos in os.walk(raiz):
                for f in archivos:
                    if not f.lower().endswith(".nif"):
                        continue
                    ruta = os.path.join(base, f)
                    try:
                        fila = Nif(ruta).fila(raiz)
                        n_ok += 1
                    except Exception as e:
                        fila = {"ruta": os.path.relpath(ruta, raiz),
                                "error": "%s: %s" % (type(e).__name__, e)}
                        n_err += 1
                    fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
        print("%s  ->  %d ok, %d con error" % (salida, n_ok, n_err))
        return
    for ruta in a:
        print(json.dumps(Nif(ruta).fila(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
