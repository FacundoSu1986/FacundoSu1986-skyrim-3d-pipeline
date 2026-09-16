# -*- coding: utf-8 -*-
"""parser_nif.py — Parser binario de NIF para Skyrim SE (BS Version 100), Python puro.

SIN dependencias externas. SIN Blender. SOLO LECTURA sobre el corpus.

ALCANCE
  - Cabecera, tablas de tipos/bloques/strings, jerarquia de nodos.
  - Geometria: BSTriShape / BSDynamicTriShape / BSSubIndexTriShape, inline y
    skinneada (geometria en NiSkinPartition variante SSE).
  - Skinning: NiSkinInstance / BSDismemberSkinInstance, particiones body-part,
    huesos y pesos por vertice (histograma 0..4).
  - Shaders: BSLightingShaderProperty, BSEffectShaderProperty,
    BSSkyShaderProperty, BSWaterShaderProperty + BSShaderTextureSet.
  - Colision: bhkRigidBody(T) (layer, masa, motion system), Material de formas
    bhk* que lo exponen segun spec, y materiales por chunk de
    bhkCompressedMeshShapeData.

AUTORIDAD: EL ARCHIVO
  nif.xml es la especificacion legible por maquina, pero donde discrepa con los
  bytes observados gana el archivo y se anota. Discrepancias registradas:
   * BSLightingShaderProperty lleva un u32 ANTES del Name (el "Skyrim Shader
     Type", valores del enum BSLightingShaderType) que nif.xml no declara para
     #SKY_AND_LATER#. Medido: character assets/steamcenturion.nif primer u32=1
     (Environment Map); flags1 en +16 = 0x82400383.
   * BSEffect/BSSky/BSWater NO llevan ese u32: empiezan directo en NiObjectNET
     (name/numED/controller). Fijado por tamano de bloque exacto: el bloque
     BSEffectShaderProperty mas pequeno queda en 12+8+16+4+... (p.ej. 88 bytes
     en fxnocturnalbirdl.nif) y BSSky/BSWater en 44/40 bytes.

VERIFICACION
  Cada parser se fijo con la identidad de tamano: el cursor debe terminar
  EXACTAMENTE en offset+size que declara la cabecera de bloque, y los valores
  deben caer en los enums del spec. --autotest reproduce los valores medidos
  con un parser independiente (incluidos los 6007 triangulos de
  steamcenturion.nif). verificar.py audita el corpus entero.
"""
import json
import os
import re
import struct
import sys
from collections import Counter

_RE_DDS = re.compile(rb"[ -~]{4,160}\.dds")

# Tipos que heredan de NiNode (nif.xml). OJO: BSFurnitureMarkerNode NO es un
# nodo (hereda de BSFurnitureMarker <- NiExtraData): tratarlo como NiNode
# revienta al leer children. Los archivos de muebles lo contienen; medido:
# 123 archivos fallaban asi con el parser que lo incluia.
TIPOS_NODO = {
    "NiNode", "BSFadeNode", "BSLeafAnimNode", "BSTreeNode",
    "BSOrderedNode", "BSValueNode", "BSMultiBoundNode",
    "BSBlastNode", "BSDamageStage", "BSRangeNode", "NiBillboardNode",
    "NiSwitchNode",
}

TIPOS_SHAPE = ("BSTriShape", "BSDynamicTriShape", "BSSubIndexTriShape")

TIPOS_SKIN = ("BSDismemberSkinInstance", "NiSkinInstance")

# --- tablas de enums --------------------------------------------------------
# Fuente: nif.xml (NifSkope). Los VALORES son la medicion; los nombres son
# etiquetas del spec para poder leer las tablas. Donde un id no aparece en el
# enum se reporta UNKNOWN_<id> y el id crudo queda en el campo *_id.

SKYRIM_LAYERS = {
    0: "SKYL_UNIDENTIFIED", 1: "SKYL_STATIC", 2: "SKYL_ANIMSTATIC",
    3: "SKYL_TRANSPARENT", 4: "SKYL_CLUTTER", 5: "SKYL_WEAPON",
    6: "SKYL_PROJECTILE", 7: "SKYL_SPELL", 8: "SKYL_BIPED",
    9: "SKYL_TREES", 10: "SKYL_PROPS", 11: "SKYL_WATER",
    12: "SKYL_TRIGGER", 13: "SKYL_TERRAIN", 14: "SKYL_TRAP",
    15: "SKYL_NONCOLLIDABLE", 16: "SKYL_CLOUD_TRAP", 17: "SKYL_GROUND",
    18: "SKYL_PORTAL", 19: "SKYL_DEBRIS_SMALL", 20: "SKYL_DEBRIS_LARGE",
    21: "SKYL_ACOUSTIC_SPACE", 22: "SKYL_ACTORZONE", 23: "SKYL_PROJECTILEZONE",
    24: "SKYL_GASTRAP", 25: "SKYL_SHELLCASING", 26: "SKYL_TRANSPARENT_SMALL",
    27: "SKYL_INVISIBLE_WALL", 28: "SKYL_TRANSPARENT_SMALL_ANIM",
    29: "SKYL_WARD", 30: "SKYL_CHARCONTROLLER", 31: "SKYL_STAIRHELPER",
    32: "SKYL_DEADBIP", 33: "SKYL_BIPED_NO_CC", 34: "SKYL_AVOIDBOX",
    35: "SKYL_COLLISIONBOX", 36: "SKYL_CAMERASHPERE", 37: "SKYL_DOORDETECTION",
    38: "SKYL_CONEPROJECTILE", 39: "SKYL_CAMERAPICK", 40: "SKYL_ITEMPICK",
    41: "SKYL_LINEOFSIGHT", 42: "SKYL_PATHPICK", 43: "SKYL_CUSTOMPICK1",
    44: "SKYL_CUSTOMPICK2", 45: "SKYL_SPELLEXPLOSION", 46: "SKYL_DROPPINGPICK",
    47: "SKYL_DEADACTORZONE", 48: "SKYL_TRIGGER_FALLINGTRAP", 49: "SKYL_NAVCUT",
    50: "SKYL_CRITTER", 51: "SKYL_SPELLTRIGGER", 52: "SKYL_LIVING_AND_DEAD_ACTORS",
    53: "SKYL_DETECTION", 54: "SKYL_TRAP_TRIGGER",
}

HAVOK_MATERIALS = {
    0: "SKY_HAV_MAT_NONE", 131151687: "SKY_HAV_MAT_BROKEN_STONE",
    322207473: "SKY_HAV_MAT_MATERIAL_CARRIAGE_WHEEL",
    346811165: "SKY_HAV_MAT_MATERIAL_METAL_LIGHT",
    365420259: "SKY_HAV_MAT_LIGHT_WOOD", 398949039: "SKY_HAV_MAT_SNOW",
    428587608: "SKY_HAV_MAT_GRAVEL", 438912228: "SKY_HAV_MAT_MATERIAL_CHAIN_METAL",
    493553910: "SKY_HAV_MAT_BOTTLE", 500811281: "SKY_HAV_MAT_WOOD",
    591247106: "SKY_HAV_MAT_SKIN", 617099282: "SKY_HAV_MAT_UNKNOWN_617099282",
    732141076: "SKY_HAV_MAT_BARREL", 781661019: "SKY_HAV_MAT_MATERIAL_CERAMIC_MEDIUM",
    790784366: "SKY_HAV_MAT_MATERIAL_BASKET", 873356572: "SKY_HAV_MAT_ICE",
    880200008: "SKY_HAV_MAT_STAIRS_GLASS", 899511101: "SKY_HAV_MAT_STAIRS_STONE",
    1024582599: "SKY_HAV_MAT_WATER", 1028101969: "SKY_HAV_MAT_UNKNOWN_1028101969",
    1060167844: "SKY_HAV_MAT_MATERIAL_BLADE_1HAND",
    1264672850: "SKY_HAV_MAT_MATERIAL_BOOK", 1286705471: "SKY_HAV_MAT_MATERIAL_CARPET",
    1288358971: "SKY_HAV_MAT_SOLID_METAL", 1305674443: "SKY_HAV_MAT_MATERIAL_AXE_1HAND",
    1440721808: "SKY_HAV_MAT_UNKNOWN_1440721808", 1461712277: "SKY_HAV_MAT_STAIRS_WOOD",
    1486385281: "SKY_HAV_MAT_MUD", 1550912982: "SKY_HAV_MAT_MATERIAL_BOULDER_SMALL",
    1560365355: "SKY_HAV_MAT_STAIRS_SNOW", 1570821952: "SKY_HAV_MAT_HEAVY_STONE",
    1574477864: "SKY_HAV_MAT_UNKNOWN_1574477864", 1591009235: "SKY_HAV_MAT_UNKNOWN_1591009235",
    1607128641: "SKY_HAV_MAT_MATERIAL_BOWS_STAVES",
    1803571212: "SKY_HAV_MAT_MATERIAL_WOOD_AS_STAIRS", 1848600814: "SKY_HAV_MAT_GRASS",
    1885326971: "SKY_HAV_MAT_MATERIAL_BOULDER_LARGE",
    1886078335: "SKY_HAV_MAT_MATERIAL_STONE_AS_STAIRS",
    2022742644: "SKY_HAV_MAT_MATERIAL_BLADE_2HAND",
    2025794648: "SKY_HAV_MAT_MATERIAL_BOTTLE_SMALL", 2168343821: "SKY_HAV_MAT_SAND",
    2229413539: "SKY_HAV_MAT_HEAVY_METAL", 2290050264: "SKY_HAV_MAT_UNKNOWN_2290050264",
    2518321175: "SKY_HAV_MAT_DRAGON", 2617944780: "SKY_HAV_MAT_MATERIAL_BLADE_1HAND_SMALL",
    2632367422: "SKY_HAV_MAT_MATERIAL_SKIN_SMALL", 2742858142: "SKY_HAV_MAT_MATERIAL_POTS_PANS",
    2892392795: "SKY_HAV_MAT_STAIRS_BROKEN_STONE", 2965929619: "SKY_HAV_MAT_MATERIAL_SKIN_LARGE",
    2974920155: "SKY_HAV_MAT_ORGANIC", 3049421844: "SKY_HAV_MAT_MATERIAL_BONE",
    3070783559: "SKY_HAV_MAT_HEAVY_WOOD", 3074114406: "SKY_HAV_MAT_MATERIAL_CHAIN",
    3106094762: "SKY_HAV_MAT_DIRT", 3387452107: "SKY_HAV_MAT_MATERIAL_SKIN_METAL_LARGE",
    3424720541: "SKY_HAV_MAT_MATERIAL_ARMOR_LIGHT", 3448167928: "SKY_HAV_MAT_MATERIAL_SHIELD_LIGHT",
    3589100606: "SKY_HAV_MAT_MATERIAL_COIN", 3702389584: "SKY_HAV_MAT_MATERIAL_SHIELD_HEAVY",
    3708432437: "SKY_HAV_MAT_MATERIAL_ARMOR_HEAVY", 3725505938: "SKY_HAV_MAT_MATERIAL_ARROW",
    3739830338: "SKY_HAV_MAT_GLASS", 3741512247: "SKY_HAV_MAT_STONE",
    3764646153: "SKY_HAV_MAT_MATERIAL_WATER_PUDDLE", 3839073443: "SKY_HAV_MAT_CLOTH",
    3855001958: "SKY_HAV_MAT_MATERIAL_SKIN_METAL_SMALL", 3895166727: "SKY_HAV_MAT_WARD",
    3934839107: "SKY_HAV_MAT_WEB", 3969592277: "SKY_HAV_MAT_MATERIAL_BLUNT_2HAND",
    4239621792: "SKY_HAV_MAT_UNKNOWN_4239621792",
    4283869410: "SKY_HAV_MAT_MATERIAL_BOULDER_MEDIUM",
    2794252627: "SKY_HAV_MAT_UNKNOWN_2794252627", 1668849266: "SKY_HAV_MAT_UNKNOWN_1668849266",
    1734341287: "SKY_HAV_MAT_UNKNOWN_1734341287", 3974071006: "SKY_HAV_MAT_UNKNOWN_3974071006",
    3941234649: "SKY_HAV_MAT_UNKNOWN_3941234649", 1820198263: "SKY_HAV_MAT_UNKNOWN_1820198263",
}

MOTION_SYSTEMS = {
    0: "MO_SYS_INVALID", 1: "MO_SYS_DYNAMIC", 2: "MO_SYS_SPHERE_INERTIA",
    3: "MO_SYS_SPHERE_STABILIZED", 4: "MO_SYS_BOX_INERTIA",
    5: "MO_SYS_BOX_STABILIZED", 6: "MO_SYS_KEYFRAMED", 7: "MO_SYS_FIXED",
    8: "MO_SYS_THIN_BOX", 9: "MO_SYS_CHARACTER",
}

SHADER_TYPES = {
    0: "Default", 1: "Environment Map", 2: "Glow Shader", 3: "Parallax",
    4: "Face Tint", 5: "Skin Tint", 6: "Hair Tint", 7: "Parallax Occ",
    8: "Multitexture Landscape", 9: "LOD Landscape", 10: "Snow",
    11: "MultiLayer Parallax", 12: "Tree Anim", 13: "LOD Objects",
    14: "Sparkle Snow", 15: "LOD Objects HD", 16: "Eye Envmap",
    17: "Cloud", 18: "LOD Landscape Noise", 19: "Multitexture Landscape LOD Blend",
    20: "FO4 Dismemberment",
}

# Ranuras del enum BSLightingShaderType presentes en los archivos del corpus
# -> nombre legible; el resto se reporta por id.


class Violacion(Exception):
    """Invariante estructural violada: el parser no pudo seguir."""


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

        for _ in range(3):                          # author/process/export
            i += 1 + d[i]
        if self.bs >= 130:                          # NO validado en este corpus
            i += 1 + d[i]

        n_tipos, = struct.unpack_from("<H", d, i); i += 2
        tipos = []
        for _ in range(n_tipos):
            n, = struct.unpack_from("<I", d, i); i += 4
            tipos.append(d[i:i + n].decode("cp1252", "replace")); i += n
        idx = struct.unpack_from("<%dH" % n_bloques, d, i); i += 2 * n_bloques
        tam = struct.unpack_from("<%dI" % n_bloques, d, i); i += 4 * n_bloques

        n_str, = struct.unpack_from("<I", d, i); i += 4
        i += 4                                      # max string length
        self.strings = []
        for _ in range(n_str):
            n, = struct.unpack_from("<I", d, i); i += 4
            self.strings.append(d[i:i + n].decode("cp1252", "replace")); i += n
        n_grupos, = struct.unpack_from("<I", d, i); i += 4 + 4 * n_grupos

        self.bloques, o = [], i
        for b in range(n_bloques):
            self.bloques.append((tipos[idx[b]], o, tam[b]))
            o += tam[b]
        # Algunos archivos traen una cola de padding despues del ultimo bloque.
        # Se tolera y se expone para verificar.py (no afecta offsets).
        self.header_tail = len(d) - o
        if self.header_tail < 0:
            raise Violacion("header: bloques exceden el archivo (fin=%d, bytes=%d)"
                            % (o, len(d)))

        self._nodos_cache = None

    # --- consultas basicas --------------------------------------------------

    def raiz(self):
        return self.bloques[0][0] if self.bloques else None

    def cuenta_tipos(self):
        c = {}
        for tipo, _, _ in self.bloques:
            c[tipo] = c.get(tipo, 0) + 1
        return c

    def de_tipo(self, *tipos):
        return [(i, o, n) for i, (t, o, n) in enumerate(self.bloques)
                if t in tipos]

    def bsxflags_info(self):
        """(valor, posiciones de bit encendidas). Sin nombres: nif.xml no
        documenta nombres para los bits de BSXFlags."""
        for _, o, n in self.de_tipo("BSXFlags"):
            if n < 8:
                continue
            valor, = struct.unpack_from("<I", self.d, o + 4)
            bits = [b for b in range(32) if (valor >> b) & 1]
            return valor, bits
        return None, None

    def texturas(self):
        """Rutas .dds visibles por regex (control independiente del parseo)."""
        vistas = set()
        for m in _RE_DDS.finditer(self.d):
            vistas.add(m.group(0).decode("cp1252", "replace"))
        return sorted(vistas)

    # --- nodos y skinning ---------------------------------------------------

    def _saltar_niavobject(self, p):
        """Avanza sobre NiObjectNET + NiAVObject. Devuelve (offset, nombre)."""
        nombre_i, = struct.unpack_from("<i", self.d, p); p += 4
        n_ed, = struct.unpack_from("<I", self.d, p); p += 4 + 4 * n_ed
        p += 4                                      # controller
        p += 4                                      # flags
        p += 12 + 36 + 4                            # translation, rot, escala
        p += 4                                      # collision object
        nombre = (self.strings[nombre_i]
                  if 0 <= nombre_i < len(self.strings) else "?")
        return p, nombre

    def _ref_valida(self, r):
        return 0 <= r < len(self.bloques)

    def es_skinneado(self):
        return any(t in TIPOS_SKIN for t, _, _ in self.bloques)

    def tipo_skin_instance(self):
        for t, _, _ in self.bloques:
            if t in TIPOS_SKIN:
                return t
        return None

    def nodos(self):
        if self._nodos_cache is not None:
            return self._nodos_cache
        n = {}
        for b, (tipo, o, _) in enumerate(self.bloques):
            if tipo not in TIPOS_NODO:
                continue
            p = o
            nombre_i, = struct.unpack_from("<i", self.d, p); p += 4
            n_ed, = struct.unpack_from("<I", self.d, p); p += 4 + 4 * n_ed
            p += 4 + 4                              # controller, flags
            p += 12 + 36 + 4                        # transform
            p += 4                                  # collision object
            n_h, = struct.unpack_from("<I", self.d, p); p += 4
            hijos = struct.unpack_from("<%di" % n_h, self.d, p) if n_h else ()
            n[b] = {
                "tipo": tipo,
                "nombre": (self.strings[nombre_i]
                           if 0 <= nombre_i < len(self.strings) else "?"),
                "hijos": [h for h in hijos if h >= 0],
            }
        self._nodos_cache = n
        return n

    def _parse_skin_partition(self, o, s):
        """NiSkinPartition SSE (BS=100). Layout fijado contra 6007 triangulos
        de steamcenturion.nif y contra las cotas de sanidad del censo.
        Devuelve dict con triangulos, vertices y pesos + violaciones."""
        d = self.d
        ptr = o
        num_partitions, = struct.unpack_from("<I", d, ptr); ptr += 4
        data_size, vertex_size = struct.unpack_from("<2I", d, ptr); ptr += 8
        vertex_desc, = struct.unpack_from("<Q", d, ptr); ptr += 8
        viol = []
        if vertex_size == 0:
            raise Violacion("NiSkinPartition: vertexSize=0")
        if data_size % vertex_size != 0:
            viol.append("partition:dataSize%%vertexSize!=0")
        num_vertices = data_size // vertex_size
        ptr += data_size

        total_tri = 0
        total_part_verts = 0
        hist = Counter()
        max_bones = 0
        max_bones_particion = 0
        suma_rara = 0
        n_parts = 0
        ws = []

        for _ in range(num_partitions):
            num_v, num_t, num_b, num_s, num_w = struct.unpack_from("<5H", d, ptr)
            ptr += 10
            ws.append(num_w)
            if num_w > 4:
                raise Violacion("sanidad: pesos por vertice %d > 4" % num_w)
            if num_b > 128:
                raise Violacion("sanidad: huesos por particion %d > 128" % num_b)
            if num_b > max_bones_particion:
                max_bones_particion = num_b
            ptr += 2 * num_b                        # Bones
            has_vmap, = struct.unpack_from("<?", d, ptr); ptr += 1
            if has_vmap:
                ptr += 2 * num_v
            has_vw, = struct.unpack_from("<?", d, ptr); ptr += 1
            if has_vw and num_w > 0:
                pesos = struct.unpack_from("<%df" % (num_v * num_w), d, ptr)
                ptr += 4 * num_v * num_w
                for vi in range(num_v):
                    vw = pesos[vi * num_w:(vi + 1) * num_w]
                    nz = sum(1 for w in vw if w > 1e-4)
                    hist[nz] += 1
                    if nz > max_bones:
                        max_bones = nz
                    sm = sum(vw)
                    if sm > 1e-6 and abs(sm - 1.0) > 0.01:
                        suma_rara += 1
            if num_s > 0:
                strip_lengths = struct.unpack_from("<%dH" % num_s, d, ptr)
                ptr += 2 * num_s
            has_faces, = struct.unpack_from("<?", d, ptr); ptr += 1
            if has_faces:
                if num_s > 0:
                    for sl in strip_lengths:
                        ptr += 2 * sl
                else:
                    ptr += 6 * num_t
            has_bone_idx, = struct.unpack_from("<?", d, ptr); ptr += 1
            if has_bone_idx:
                ptr += num_v * num_w
            # tail SSE: LOD Level (u8) + Global VB (u8) + Vertex Desc (u64)
            #           + copia de triangulos (Triangle x num_t)
            ptr += 1 + 1 + 8 + 6 * num_t
            total_tri += num_t
            total_part_verts += num_v
            n_parts += 1

        if ptr != o + s:
            viol.append("partition:fin=%d!=bloque=%d" % (ptr, o + s))
        if suma_rara:
            viol.append("partition:%d pesos con suma!=1" % suma_rara)
        return {
            "triangulos": total_tri,
            "vertices": num_vertices if num_vertices > 0 else total_part_verts,
            "histograma": dict(hist),
            "max_huesos": max_bones,
            "max_bones_particion": max_bones_particion,
            "n_particiones": n_parts,
            "num_w": ws,
            "violaciones": viol,
        }

    def _particion_de_shape(self, skin_idx):
        """Resuelve el NiSkinPartition de una skin instance. Devuelve dict o None."""
        if not self._ref_valida(skin_idx):
            return None
        tipo, so, _ = self.bloques[skin_idx]
        if tipo not in TIPOS_SKIN:
            return None
        _, part_idx = struct.unpack_from("<2i", self.d, so)
        if not self._ref_valida(part_idx):
            return None
        if self.bloques[part_idx][0] != "NiSkinPartition":
            return None
        return self._parse_skin_partition(self.bloques[part_idx][1],
                                          self.bloques[part_idx][2])

    def _parse_dismember_instances(self):
        """Particiones (body_part_id, flags) y huesos de las skin instances."""
        d = self.d
        particiones = []
        huesos = []
        nodos = self.nodos()
        for idx, o, s in self.de_tipo(*TIPOS_SKIN):
            t = self.bloques[idx][0]
            ptr = o
            data_ref, part_ref, root_ref, num_bones = struct.unpack_from(
                "<4i", d, ptr); ptr += 16
            if num_bones > 0:
                bone_refs = struct.unpack_from("<%di" % num_bones, d, ptr)
                ptr += 4 * num_bones
                for b_ref in bone_refs:
                    if b_ref in nodos:
                        nombre = nodos[b_ref]["nombre"]
                        if nombre not in huesos:
                            huesos.append(nombre)
            if t == "BSDismemberSkinInstance":
                num_parts, = struct.unpack_from("<I", d, ptr); ptr += 4
                for _ in range(num_parts):
                    part_flag, body_part = struct.unpack_from("<2H", d, ptr)
                    ptr += 4
                    particiones.append({"body_part_id": body_part,
                                        "flags": part_flag})
        return particiones, {"cantidad": len(huesos), "nombres": huesos}

    # --- shaders ------------------------------------------------------------

    def _parse_texture_set(self, o, s):
        """BSShaderTextureSet: NumTextures (u32) + SizedString[] inline."""
        d = self.d
        ptr = o
        num_tex, = struct.unpack_from("<I", d, ptr); ptr += 4
        slots, rutas = [], []
        for i in range(num_tex):
            if ptr + 4 > o + s:
                return slots, rutas, ["texset:corta"]
            length, = struct.unpack_from("<I", d, ptr); ptr += 4
            if ptr + length > o + s or length > 4096:
                return slots, rutas, ["texset:string fuera de bloque"]
            txt = d[ptr:ptr + length].decode("cp1252", "replace")
            ptr += length
            txt = txt.rstrip("\x00")
            if txt:
                slots.append(i)
                rutas.append(txt)
        viol = [] if ptr == o + s else ["texset:fin=%d!=bloque=%d" % (ptr, o + s)]
        return slots, rutas, viol

    def _parse_shader_property(self, shader_idx):
        """Devuelve dict: bloque, shader_tipo, shader_tipo_id, flags1, flags2,
        ranuras_textura_pobladas, rutas_textura, violaciones."""
        vacio = {"bloque": None, "shader_tipo": None, "shader_tipo_id": None,
                 "flags1": None, "flags2": None,
                 "ranuras_textura_pobladas": [], "rutas_textura": [],
                 "violaciones": []}
        if not self._ref_valida(shader_idx):
            return vacio
        tipo, o, s = self.bloques[shader_idx]
        d = self.d
        vacio["bloque"] = tipo
        viol = []

        if tipo == "BSLightingShaderProperty":
            # [Shader Type u32][Name][numED][ED refs][controller][f1][f2]
            #  [UV offset 2f][UV scale 2f][Texture Set ref]
            st_id, = struct.unpack_from("<I", d, o)
            nombre_i, num_ed = struct.unpack_from("<iI", d, o + 4)
            q = o + 16 + 4 * num_ed
            if num_ed > 8:
                viol.append("lighting:numED=%d" % num_ed)
            f1, f2 = struct.unpack_from("<2I", d, q) if q + 8 <= o + s else (None, None)
            tex_ref = struct.unpack_from("<i", d, q + 24)[0] if q + 28 <= o + s else -1
            slots, rutas = [], []
            if self._ref_valida(tex_ref) and self.bloques[tex_ref][0] == "BSShaderTextureSet":
                v = self._parse_texture_set(self.bloques[tex_ref][1],
                                            self.bloques[tex_ref][2])
                slots, rutas, vv = v
                viol.extend(vv)
            elif tex_ref != -1:
                viol.append("lighting:texset ref invalida %d" % tex_ref)
            vacio.update({"shader_tipo": SHADER_TYPES.get(st_id, "ST_%d" % st_id),
                          "shader_tipo_id": st_id, "flags1": f1, "flags2": f2,
                          "ranuras_textura_pobladas": slots, "rutas_textura": rutas})

        elif tipo == "BSEffectShaderProperty":
            # NiObjectNET(12) + [f1][f2][UV off][UV scale][src SizedString]
            #  + 4B (clamp/lit/lod/unused) + 4f falloff + Color4 base
            #  + f baseScale + f softFalloff + greyscale SizedString.
            # SSE (BS=100) termina ahi (los SizedString extra son BS>=130).
            num_ed, _ = struct.unpack_from("<II", d, o + 4)
            q = o + 12 + 4 * num_ed
            f1, f2 = struct.unpack_from("<2I", d, q)
            ptr = q + 24
            src_len, = struct.unpack_from("<I", d, ptr); ptr += 4
            src = d[ptr:ptr + src_len].decode("cp1252", "replace").rstrip("\x00")
            ptr += src_len + 44
            grey_len, = struct.unpack_from("<I", d, ptr); ptr += 4
            grey = d[ptr:ptr + grey_len].decode("cp1252", "replace").rstrip("\x00")
            ptr += grey_len
            if ptr != o + s:
                viol.append("effect:fin=%d!=bloque=%d" % (ptr, o + s))
            slots = [i for i, t in ((0, src), (1, grey)) if t]
            rutas = [t for t in (src, grey) if t]
            vacio.update({"shader_tipo": "Effect", "flags1": f1, "flags2": f2,
                          "ranuras_textura_pobladas": slots, "rutas_textura": rutas})

        elif tipo == "BSSkyShaderProperty":
            num_ed, _ = struct.unpack_from("<II", d, o + 4)
            q = o + 12 + 4 * num_ed
            f1, f2 = struct.unpack_from("<2I", d, q)
            ptr = q + 24
            src_len, = struct.unpack_from("<I", d, ptr); ptr += 4
            src = d[ptr:ptr + src_len].decode("cp1252", "replace").rstrip("\x00")
            ptr += src_len
            sky_type, = struct.unpack_from("<I", d, ptr); ptr += 4
            if ptr != o + s:
                viol.append("sky:fin=%d!=bloque=%d" % (ptr, o + s))
            slots = [0] if src else []
            rutas = [src] if src else []
            vacio.update({"shader_tipo": "Sky", "flags1": f1, "flags2": f2,
                          "ranuras_textura_pobladas": slots, "rutas_textura": rutas})

        elif tipo == "BSWaterShaderProperty":
            num_ed, _ = struct.unpack_from("<II", d, o + 4)
            q = o + 12 + 4 * num_ed
            f1, f2 = struct.unpack_from("<2I", d, q)
            if q + 28 != o + s:
                viol.append("water:fin=%d!=bloque=%d" % (q + 28, o + s))
            vacio.update({"shader_tipo": "Water", "flags1": f1, "flags2": f2})

        else:
            vacio["shader_tipo"] = tipo

        vacio["violaciones"] = viol
        return vacio

    # --- geometria -----------------------------------------------------------

    def trishapes_detalle(self):
        """Geometria por BSTriShape/Dynamic/SubIndex: inline si esta, si no en
        la particion de skin. Devuelve (total_tri, vertices_por_shape,
        shapes_info, histograma_pesos, max_huesos, violaciones)."""
        d = self.d
        shapes_info = []
        verts_por_shape = []
        hist_global = Counter()
        max_bones = 0
        total_tri = 0
        viol = []

        for b_idx, o, s in self.de_tipo(*TIPOS_SHAPE):
            p, nombre = self._saltar_niavobject(o)
            p += 16                                  # bounding sphere
            if self.bs >= 151:
                p += 24                              # NO validado
            skin_idx, shader_idx, alpha_idx = struct.unpack_from("<3i", d, p)
            p += 12
            vdesc, = struct.unpack_from("<Q", d, p); p += 8
            if self.bs < 130:
                tri_inline, = struct.unpack_from("<H", d, p); p += 2
            else:
                tri_inline, = struct.unpack_from("<I", d, p); p += 4
            ver_inline, = struct.unpack_from("<H", d, p); p += 2
            data_size, = struct.unpack_from("<I", d, p); p += 4

            shape_tri = tri_inline
            shape_ver = ver_inline
            if tri_inline == 0 and self._ref_valida(skin_idx):
                part = self._particion_de_shape(skin_idx)
                if part is not None:
                    shape_tri = part["triangulos"]
                    shape_ver = part["vertices"]
                    hist_global.update(part["histograma"])
                    if part["max_huesos"] > max_bones:
                        max_bones = part["max_huesos"]
                    viol.extend(part["violaciones"])
                else:
                    viol.append("shape:%s sin particion resoluble" % nombre)
            elif tri_inline == 0 and data_size == 0:
                viol.append("shape:%s sin geometria (tri=0,dataSize=0)" % nombre)

            total_tri += shape_tri
            verts_por_shape.append(shape_ver)

            sh = self._parse_shader_property(shader_idx)
            viol.extend(sh["violaciones"])
            shapes_info.append({
                "nombre": nombre,
                "tipo_bloque": self.bloques[b_idx][0],
                "shader_tipo": sh["shader_tipo"],
                "shader_tipo_id": sh["shader_tipo_id"],
                "flags1": sh["flags1"],
                "flags2": sh["flags2"],
                "ranuras_textura_pobladas": sh["ranuras_textura_pobladas"],
                "rutas_textura": sh["rutas_textura"],
            })

        return total_tri, verts_por_shape, shapes_info, dict(hist_global), max_bones, viol

    # --- colision ------------------------------------------------------------

    def _material_de_shape(self, idx, vistos=None):
        """(id, nombre) del campo Material del shape si el spec lo expone."""
        vistos = vistos or set()
        if idx in vistos or not self._ref_valida(idx):
            return None, None
        vistos.add(idx)
        tipo, o, s = self.bloques[idx]
        d = self.d

        def _mat(off):
            if off + 4 > o + s:
                return None, None
            mid, = struct.unpack_from("<I", d, off)
            return mid, HAVOK_MATERIALS.get(mid, "UNKNOWN_%d" % mid)

        if tipo in ("bhkBoxShape", "bhkSphereShape", "bhkCapsuleShape",
                    "bhkConvexVerticesShape", "bhkCylinderShape", "bhkMultiSphereShape"):
            return _mat(o)                       # Material @0 (bhkSphereRepShape)
        if tipo in ("bhkTransformShape", "bhkConvexTransformShape"):
            return _mat(o + 4)                   # Shape ref @0
        if tipo == "bhkListShape":
            n, = struct.unpack_from("<I", d, o)
            return _mat(o + 4 + 4 * n)           # Num@0, refs, Material
        if tipo == "bhkMoppBvTreeShape":
            child, = struct.unpack_from("<i", d, o)
            return self._material_de_shape(child, vistos)
        return None, None

    def _materiales_chunk(self):
        """Materiales por chunk de bhkCompressedMeshShapeData (id unicos)."""
        d = self.d
        out = []
        for idx, o, s in self.de_tipo("bhkCompressedMeshShapeData"):
            p = o + 4 * 4 + 4 + 32 + 2               # bits x4, error, AABB, weld+matType
            n32, = struct.unpack_from("<I", d, p); p += 4 + 4 * n32
            n16, = struct.unpack_from("<I", d, p); p += 4 + 4 * n16
            n8, = struct.unpack_from("<I", d, p); p += 4 + 4 * n8
            nm, = struct.unpack_from("<I", d, p); p += 4
            if nm > 256 or p + 8 * nm > o + s:
                continue
            for k in range(nm):
                mid, = struct.unpack_from("<I", d, p + 8 * k)
                if mid not in out:
                    out.append(mid)
        return sorted(out)

    def colision_info(self):
        """tipos_bhk, layer(+id), material(+id), materiales de chunk,
        motion system(+id), masa. Del primer bhkRigidBody(T) del archivo."""
        d = self.d
        tipos_bhk = sorted({t for t, _, _ in self.bloques if t.startswith("bhk")})
        info = {
            "tipos_bhk": tipos_bhk,
            "layer": None, "layer_id": None,
            "material_havok": None, "material_havok_id": None,
            "materiales_chunk": None,
            "motion_system": None, "motion_system_id": None,
            "mass": None,
        }

        rbs = self.de_tipo("bhkRigidBody", "bhkRigidBodyT")
        if rbs:
            _, o, s = rbs[0]
            if s >= 246:
                layer_b = d[o + 4]
                info["layer_id"] = layer_b
                info["layer"] = SKYRIM_LAYERS.get(layer_b, "LAYER_%d" % layer_b)
                mass_f, = struct.unpack_from("<f", d, o + 180)
                info["mass"] = round(mass_f, 4)
                motion_b = d[o + 224]
                info["motion_system_id"] = motion_b
                info["motion_system"] = MOTION_SYSTEMS.get(motion_b,
                                                           "MOTION_%d" % motion_b)
                shape_ref, = struct.unpack_from("<i", d, o)
                mid, nom = self._material_de_shape(shape_ref)
                info["material_havok_id"] = mid
                info["material_havok"] = nom

        if info["material_havok"] is None:
            for idx, o, s in self.de_tipo(
                    "bhkBoxShape", "bhkSphereShape", "bhkCapsuleShape",
                    "bhkConvexVerticesShape", "bhkListShape", "bhkMoppBvTreeShape"):
                mid, nom = self._material_de_shape(idx)
                if nom is not None:
                    info["material_havok_id"] = mid
                    info["material_havok"] = nom
                    break

        chunk = self._materiales_chunk()
        if chunk:
            info["materiales_chunk"] = chunk
        return info

    # --- fila del censo -------------------------------------------------------

    def fila_censo(self, base=""):
        (tri, verts, shapes, hist, max_bones,
         viol_geom) = self.trishapes_detalle()
        particiones, huesos = self._parse_dismember_instances()
        bsx_val, bsx_bits = self.bsxflags_info()
        colision = self.colision_info()

        rel = os.path.relpath(self.ruta, base).replace("\\", "/") if base else self.ruta

        return {
            "ruta_relativa": rel,
            "bytes": os.path.getsize(self.ruta),
            "version": ".".join(str((self.version >> s) & 0xFF)
                                for s in (24, 16, 8, 0)),
            "user_version": self.user,
            "bs_version": self.bs,
            "tipo_nodo_raiz": self.raiz(),
            "bloques": self.cuenta_tipos(),
            "tiene_skin": self.es_skinneado(),
            "tipo_skin_instance": self.tipo_skin_instance(),
            "n_shapes": len(shapes),
            "triangulos_totales": tri,
            "vertices_por_shape": verts,
            "bsxflags_valor": bsx_val,
            "bsxflags_bits": bsx_bits,
            "colision": colision,
            "particiones": particiones,
            "huesos": huesos,
            "pesos": {
                "max_huesos_por_vertice": max_bones if hist else None,
                "histograma": {str(k): v for k, v in sorted(hist.items())},
            },
            "shapes": shapes,
        }


# --- Suite de falsificacion --------------------------------------------------
# Valores medidos con un parser independiente sobre archivos vanilla. Si el
# parser no los reproduce, el bug esta en el parser, no en los datos.

AUTOTEST = [
    # 1. Skinneado: 112 bloques, raiz NiNode, 15 shapes, 6007 triangulos
    # totales (geometria en particiones), pesos <= 4, huesos <= 21.
    # 15 shapes comparten UN BSShaderTextureSet (archivo atlaseado).
    ("actors/dwarvensteamcenturion/character assets/steamcenturion.nif", {
        "version": "20.2.0.7", "user_version": 12, "bs_version": 100,
        "raiz": "NiNode", "n_bloques": 112, "bsxflags": None,
        "tiene_skin": True, "tipo_skin_instance": "BSDismemberSkinInstance",
        "n_shapes": 15, "triangulos_totales": 6007,
        "bloques": {
            "NiNode": 21, "BSTriShape": 15,
            "BSDismemberSkinInstance": 15, "NiSkinData": 15,
            "NiSkinPartition": 15, "BSLightingShaderProperty": 15,
            "NiAlphaProperty": 15, "BSShaderTextureSet": 1,
        },
        "max_huesos_por_vertice": 2,
        "histograma": {"1": 5466, "2": 120},
        "particion0": {"body_part_id": 32, "flags": 257},
        "shape0_nombre": "SteamRForearm",
        "shape0_shader": "Environment Map",
        "shape0_flags1": 0x82400383,
        "shape0_flags2": 0x8021,
        "shape0_slots": [0, 1, 4, 5],
        "huesos_cantidad": 20,
    }),
    # 2. Estatico centurion: 9 bloques, BSFadeNode, BSXFlags=130,
    # bhkBoxShape + bhkRigidBodyT, masa 10.0, layer STATIC, motion BOX_STABILIZED.
    ("actors/dwarvensteamcenturion/dwarvensteamcenturion.nif", {
        "raiz": "BSFadeNode", "n_bloques": 9, "bsxflags": 130,
        "bsxflags_bits": [1, 7],
        "tiene_skin": False, "triangulos_totales": 6154,
        "tipos_bhk": ["bhkBoxShape", "bhkCollisionObject", "bhkRigidBodyT"],
        "layer_id": 1, "motion_system_id": 5, "mass": 10.0,
        "material_havok_id": 1288358971,
    }),
    # 3. Escudo: 10 bloques, BSFadeNode, BSXFlags=194.
    ("armor/dwarven/dwarvenshield.nif", {
        "raiz": "BSFadeNode", "n_bloques": 10, "bsxflags": 194,
        "bsxflags_bits": [1, 6, 7],
        "triangulos_totales": 1612,
        "layer_id": 5, "material_havok_id": 3702389584,
    }),
    # 4. Gema de alma: 20 bloques, BSFadeNode, BSXFlags=203.
    ("clutter/soulgem/soulgemgreater01.nif", {
        "raiz": "BSFadeNode", "n_bloques": 20, "bsxflags": 203,
        "bsxflags_bits": [0, 1, 3, 6, 7],
        "triangulos_totales": 316,
        "layer_id": 4, "motion_system_id": 3, "mass": 15.0,
        "material_havok_id": 3739830338,
    }),
    # 5. Carambano: BSXFlags = 130.
    ("dungeons/caves/ice/clutter/caveiiciclemed01.nif", {
        "bsxflags": 130, "bsxflags_bits": [1, 7],
    }),
    # 6. Astrolabio: BSXFlags = 523.
    ("dungeons/dwemer/animated/astrolabe/lens/dweastrolabelens01.nif", {
        "bsxflags": 523, "bsxflags_bits": [0, 1, 3, 9],
    }),
    # 7. BSEffectShaderProperty (layout corregido): nombre=-1@0, ctrl@8,
    # flags1@12=0x8000003A, flags2@16=0x30, fuente de textura@36 y
    # greyscale al final. Dos rutas pobladas.
    ("actors/canine/character assets wolf/wolffire.nif", {
        "shape0_shader": "Effect",
        "shape0_flags1": 0x8000003A,
        "shape0_flags2": 0x30,
        "shape0_slots": [0, 1],
        "shape0_ruta0": "textures\\effects\\FXFireScrollTile02.dds",
        "shape0_ruta1": "textures\\effects\\gradients\\GradFireExplosion.dds",
    }),
    # 8. BSSkyShaderProperty: 44 bytes exactos (12+8+16+4+4).
    ("sky/atmosphere.nif", {
        "shape0_shader": "Sky",
        "shape0_flags1": 0x80000000,
        "shape0_flags2": 0x21,
        "shape0_slots": [],
    }),
    # 9. BSWaterShaderProperty: 40 bytes exactos (12+8+16+4).
    ("architecture/markarth/water/markarthwatersystemstream.nif", {
        "flags1": 0x80000008, "flags2": 0x21, "shader": "Water",
    }),
    # 10. BSDynamicTriShape SKINNEADO (barba): geometria en particion, 248
    # triangulos sobre 155 vertices, 1 hueso por vertice (rigida).
    ("actors/character/character assets/beards/humanbeardlong07.nif", {
        "raiz": "NiNode", "n_shapes": 1, "triangulos_totales": 248,
        "vertices_por_shape": [155],
        "max_huesos_por_vertice": 1, "histograma": {"1": 155},
        "huesos_cantidad": 1,
        "shape0_tipo": "BSDynamicTriShape",
        "shape0_shader": "Hair Tint",
        "shape0_flags1": 0x8E44030B,
        "shape0_slots": [0, 1],
    }),
]


def _buscar(raiz, rel):
    """Ruta unica que termina en `rel`. Si hay varias, falla en vez de elegir."""
    cola = rel.replace("/", os.sep).lower()
    encontrados = []
    for base, _, archivos in os.walk(raiz):
        for f in archivos:
            ruta = os.path.join(base, f)
            if ruta.lower().endswith(cola):
                encontrados.append(ruta)
    if len(encontrados) > 1:
        raise SystemExit(
            "AMBIGUO: %d archivos terminan en %s.\n%s" % (
                len(encontrados), rel, "\n".join("  " + e for e in encontrados)))
    return encontrados[0] if encontrados else None


def _valor_autotest(fila, nombre):
    """Extrae un campo anidado del formato de caso de AUTOTEST."""
    col = fila["colision"]
    sh0 = fila["shapes"][0] if fila["shapes"] else {}
    mapa = {
        "version": fila["version"],
        "user_version": fila["user_version"],
        "bs_version": fila["bs_version"],
        "n_bloques": sum(fila["bloques"].values()),
        "raiz": fila["tipo_nodo_raiz"],
        "bsxflags": fila["bsxflags_valor"],
        "bsxflags_bits": fila["bsxflags_bits"],
        "bloques": fila["bloques"],
        "tiene_skin": fila["tiene_skin"],
        "tipo_skin_instance": fila["tipo_skin_instance"],
        "n_shapes": fila["n_shapes"],
        "triangulos_totales": fila["triangulos_totales"],
        "vertices_por_shape": fila["vertices_por_shape"],
        "max_huesos_por_vertice": fila["pesos"]["max_huesos_por_vertice"],
        "histograma": fila["pesos"]["histograma"],
        "particion0": fila["particiones"][0] if fila["particiones"] else None,
        "huesos_cantidad": fila["huesos"]["cantidad"],
        "tipos_bhk": col["tipos_bhk"],
        "layer_id": col["layer_id"],
        "motion_system_id": col["motion_system_id"],
        "mass": col["mass"],
        "material_havok_id": col["material_havok_id"],
        "shape0_nombre": sh0.get("nombre"),
        "shape0_tipo": sh0.get("tipo_bloque"),
        "shape0_shader": sh0.get("shader_tipo"),
        "shape0_flags1": sh0.get("flags1"),
        "shape0_flags2": sh0.get("flags2"),
        "shape0_slots": sh0.get("ranuras_textura_pobladas"),
        "shape0_ruta0": (sh0.get("rutas_textura") or [None])[0],
        "shape0_ruta1": (sh0.get("rutas_textura") or [None, None])[1]
                        if len(sh0.get("rutas_textura") or []) > 1 else None,
        "shader": next((s["shader_tipo"] for s in fila["shapes"]
                        if s.get("shader_tipo") in ("Sky", "Water")), None),
        "flags1": next((s["flags1"] for s in fila["shapes"]
                        if s.get("shader_tipo") in ("Sky", "Water")), None),
        "flags2": next((s["flags2"] for s in fila["shapes"]
                        if s.get("shader_tipo") in ("Sky", "Water")), None),
    }
    return mapa[nombre]


def autotest(raiz):
    ok = fallo = falta = 0
    print("Iniciando Suite de Falsificacion...")
    for rel, esperado in AUTOTEST:
        ruta = _buscar(raiz, rel)
        if ruta is None:
            print("  [falta]  %s" % rel)
            falta += 1
            continue
        fila = Nif(ruta).fila_censo(raiz)
        for campo, valor in esperado.items():
            real = _valor_autotest(fila, campo)
            if real == valor:
                ok += 1
            else:
                fallo += 1
                print("  [FALLA]  %s :: %s" % (os.path.basename(rel), campo))
                print("           esperado %r" % (valor,))
                print("           obtenido %r" % (real,))
    print("")
    print("  %d comprobaciones ok, %d fallidas, %d archivos no encontrados"
          % (ok, fallo, falta))
    if ok == 0:
        # Cero comprobaciones no es exito. Apuntar --autotest a una carpeta
        # vacia o equivocada devolvia 0 y el README promete que "avisa si no
        # esta listo para censar": con cero reproducciones no avisaba nada.
        print("  NO se comprobo NADA. Revisa la ruta del corpus.")
        return False
    if fallo or falta:
        print("  El parser NO esta listo para censar.")
    elif falta:
        print("  Ok hasta donde se pudo comprobar, pero faltan archivos.")
    else:
        print("  Parser validado. Ahora si, censar.")
    return fallo == 0


# --- censo -------------------------------------------------------------------

def censar_archivo(args):
    ruta, raiz = args
    try:
        return json.dumps(Nif(ruta).fila_censo(raiz), ensure_ascii=False)
    except Exception as e:
        rel = os.path.relpath(ruta, raiz).replace("\\", "/")
        return json.dumps({"ruta_relativa": rel,
                           "error": "%s: %s" % (type(e).__name__, e)},
                          ensure_ascii=False)


def ejecutar_censo(raiz, salida):
    from multiprocessing import Pool, cpu_count

    archivos = []
    for base, _, files in os.walk(raiz):
        for f in files:
            if f.lower().endswith(".nif"):
                archivos.append(os.path.join(base, f))
    total = len(archivos)
    print("Total NIFs a censar: %d" % total)
    workers = max(1, cpu_count() - 1)
    print("Procesando con %d workers..." % workers)

    n_ok = n_err = 0
    tareas = [(p, raiz) for p in archivos]
    with open(salida, "w", encoding="utf-8") as fh:
        with Pool(processes=workers) as pool:
            for idx, line in enumerate(pool.imap_unordered(censar_archivo, tareas, 50), 1):
                fh.write(line + "\n")
                if '"error":' in line:
                    n_err += 1
                else:
                    n_ok += 1
                if idx % 4000 == 0 or idx == total:
                    print("  %d/%d (ok=%d err=%d)" % (idx, total, n_ok, n_err))

    # orden estable por ruta para reproducibilidad
    with open(salida, encoding="utf-8") as fh:
        lineas = fh.readlines()
    lineas.sort(key=lambda l: json.loads(l)["ruta_relativa"])
    with open(salida, "w", encoding="utf-8") as fh:
        fh.writelines(lineas)
    print("Censo completo en %s: %d ok, %d con error" % (salida, n_ok, n_err))


def main():
    a = sys.argv[1:]
    if not a:
        print("Uso: python parser_nif.py --autotest <carpeta raiz>")
        print("     python parser_nif.py --censo <carpeta> --salida censo.jsonl")
        print("     python parser_nif.py <archivo.nif> [...]")
        return
    if a[0] == "--autotest":
        # El valor de retorno TIENE que mover el exit code. Estaba descartado:
        # el parser que produce el censo era el unico que no podia romper un
        # build, mientras la semilla si lo hacia. Orden de severidad invertido.
        if not autotest(a[1]):
            raise SystemExit(1)
        return
    if a[0] == "--censo":
        raiz = a[1]
        salida = a[a.index("--salida") + 1] if "--salida" in a else "censo.jsonl"
        ejecutar_censo(raiz, salida)
        return
    for ruta in a:
        print(json.dumps(Nif(ruta).fila_censo(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
