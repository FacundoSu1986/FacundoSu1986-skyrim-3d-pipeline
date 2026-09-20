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

TRIANGULOS DE MALLAS SKINNEADAS: resuelto, pero no aca

Esta semilla NO los cuenta. La implementacion completa esta en
census/parser_nif.py (_parse_skin_partition), con el layout fijado contra un
valor conocido de antemano: steamcenturion.nif = 6.007 triangulos. Si
necesitas el conteo, usa ese parser; esta semilla se queda chica a proposito.

Como se llego ahi, porque el metodo importa mas que el dato: un primer intento
escrito de memoria devolvia enteros perfectamente formados que eran basura
--pesos por vertice = 1035, cuando el maximo del motor es 4-- porque leia desde
un offset corrido, y ese 1035 era un pedazo del vertexDesc del bloque anterior.
No tiro ninguna excepcion. Lo unico que lo delato fue tener un valor esperado
de antemano y una cota de sanidad.

Cota que SI vale: pesos por vertice <= 4. Medido: 42.243 de 42.243, sin
excepciones.

Cota que NO vale, aunque suene razonable: "huesos por particion <= cantidad de
NiNode del archivo". La recomendaba una version anterior de este comentario y
el censo la refuto: falla en 1.095 de 42.243 particiones porque el array Bones[]
viene con padding (4 ranuras tipicas sobre instancias de 1-3 huesos). Ver
census/hallazgos.md, entrada 2.

Es el mismo error que esta skill entera existe para evitar, cometido dentro de
una advertencia contra cometerlo.

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
TIPOS_SHAPE = ("BSTriShape", "BSDynamicTriShape", "BSSubIndexTriShape")
# Los mismos tres que census/parser_nif.py. BSSubIndexTriShape no aparece
# en este corpus (0 bloques en 22.394 archivos); va igual para que las dos
# listas no vuelvan a separarse.

# BSMasterParticleSystem: 93 archivos del corpus, todos con el tipo
# como RAIZ. El layout de NiNode parsea coherente en 93 de 93 bloques
# (1 hijo en 92, 2 en uno; cola de 14 a 30 bytes, que son sus campos
# propios). Lo contrario de BSFurnitureMarkerNode, que se saco de aca
# porque el sufijo enganaba y rompia 123 archivos de muebles.
# BSRangeNode: 0 bloques en el corpus. No lo ejercita nada; va en las
# tres listas para que no vuelvan a separarse.
# Las dos skin instances de SSE. El censo las cuenta desde siempre
# (es_skinneado); lo que se agrega aca es leer su CABECERA -- los cuatro
# refs y la lista de huesos -- que es lo unico que hace falta para saber
# que hueso mueve que pieza. El recorrido del NiSkinPartition (vertices,
# pesos, triangulos) sigue SIN implementarse en la skill: vive en
# census/parser_uv.py, validado contra 42.243 particiones.
TIPOS_SKIN = ("BSDismemberSkinInstance", "NiSkinInstance")

# mundo() redondea a esta cantidad de decimales. Esta nombrado porque
# verificar_export.TOLERANCIA se DERIVA de este numero: si alguien cambia el
# redondeo, la tolerancia tiene que moverse con el. Antes eran dos constantes
# en archivos distintos sin nada que las atara -- y mover cualquiera de las
# dos dejaba la suite en verde.
DECIMALES_MUNDO = 2
DECIMALES_ESCALA = 4
# Las componentes de una rotacion son cosenos directores, en [-1, 1]. Cuatro
# decimales son ~0,006 grados. Medido sobre los 1.216 pares `_0.nif`/`_1.nif`
# --el mismo asset-- 22.151 de 22.179 rotaciones de nodo son IDENTICAS con ese
# redondeo, y las 28 que no son TODAS de `InvMarker`, que no es un hueso.
DECIMALES_ROTACION = 4

TIPOS_NODO = {
    "NiNode", "BSFadeNode", "BSLeafAnimNode", "BSTreeNode",
    "BSOrderedNode", "BSValueNode", "BSMultiBoundNode",
    "BSBlastNode", "BSDamageStage", "BSRangeNode", "NiBillboardNode",
    "NiSwitchNode", "BSMasterParticleSystem",
}

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
            # Sin validar contra un solo archivo: el corpus tiene 22.393 con
            # BS=100, uno con BS=83 y CERO con BS>=130. Adivinar este campo
            # corre todos los offsets de bloque.
            raise ValueError(
                "header: BS version %d (>=130) no esta validada contra ningun "
                "archivo del corpus" % self.bs)

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
        # Los bytes no cambian despues de esto, asi que los dos recorridos
        # caros se calculan una vez. Sin cache, un comparar() hacia SEIS
        # recorridos de jerarquia --mundo(), mundo_shapes() y
        # nombres_repetidos() por archivo-- y 38 lecturas de nodos() en
        # steamcenturion, una por skin instance. Con cache, los mismos dos
        # numeros son 2 y 2: uno por archivo. Mismo patron que
        # census/parser_nif.py, que ya trae _nodos_cache.
        self._nodos_cache = None
        self._mundo_cache = None

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
            # El valor es uint32, como lo lee census/parser_nif.py. Leerlo
            # con signo divergia solo para flags con el bit 31 encendido;
            # el fixture y el corpus usan valores bajos y no lo delataban.
            _, valor = struct.unpack_from("<II", self.d, o)
            return valor
        return None

    def texturas(self):
        vistas = re.findall(rb"[ -~]{4,160}\.dds", self.d, re.IGNORECASE)
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
        """Los TRES tipos de shape, no solo BSTriShape.

        Iterar solo BSTriShape hacia que 3.803 archivos del corpus -- el 17 % --
        reportaran n_shapes = 0 sin avisar: son los que traen BSDynamicTriShape
        y ningun BSTriShape (cabezas, barbas, todo lo que anima vertices).
        En el corpus no hay un solo archivo que mezcle los dos tipos, asi que el
        sintoma era silencioso y total: 0 shapes, no "faltan algunos".

        El layout de cabecera es el mismo para los tres -- BSDynamicTriShape
        extiende BSTriShape agregando campos al final -- que es por lo que
        census/parser_nif.py los lee con estos mismos offsets.
        """
        fuera = []
        for o, _ in self.de_tipo(*TIPOS_SHAPE):
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

    def _ref_valida(self, r):
        return 0 <= r < len(self.bloques)

    def _skin_de_shape(self, o):
        """Indice de bloque de la skin instance del shape en `o`, o None.

        Los tres refs (skin, shader, alpha) van juntos despues de la esfera
        envolvente. Los offsets son los mismos que usa trishapes() y los
        mismos que census/parser_nif.py: si se corren, los dos se enteran.
        """
        p, _nombre = self._saltar_niavobject(o)
        p += 16                                     # esfera envolvente
        if self.bs >= 151:
            p += 24
        skin_idx, _shader, _alpha = struct.unpack_from("<3i", self.d, p)
        if not self._ref_valida(skin_idx):
            return None
        if self.bloques[skin_idx][0] not in TIPOS_SKIN:
            return None
        return skin_idx

    def _lee_skin_instance(self, skin_idx):
        """(huesos, body_parts) de una skin instance.

        NiSkinInstance: data(ref) partition(ref) raiz(ptr) numBones(u32)
                        bones(ptr * numBones)
        BSDismemberSkinInstance agrega: numParticiones(u32) y por particion
                        (flags u16, body_part u16).

        Un hueso es un NiNode referenciado desde aca. Si la ref no cae en un
        nodo se devuelve "?<indice>" en vez de descartarla: un hueso que no
        resuelve es justo lo que hay que ver, no algo que esconder.
        """
        tipo, o, _s = self.bloques[skin_idx]
        nodos = self.nodos()
        p = o
        _data, _part, _raiz, n_huesos = struct.unpack_from("<4i", self.d, p)
        p += 16
        huesos = []
        if n_huesos > 0:
            refs = struct.unpack_from("<%di" % n_huesos, self.d, p)
            p += 4 * n_huesos
            huesos = [nodos[b]["nombre"] if b in nodos else "?%d" % b
                      for b in refs]
        partes = []
        if tipo == "BSDismemberSkinInstance":
            n_part, = struct.unpack_from("<I", self.d, p); p += 4
            for _ in range(n_part):
                _flags, body_part = struct.unpack_from("<2H", self.d, p)
                p += 4
                partes.append(body_part)
        return huesos, partes

    def skin_por_shape(self):
        """{nombre de shape: {"huesos": [...], "body_parts": [...]}}.

        POR SHAPE Y NO GLOBAL, a proposito. El total de huesos del archivo no
        dice cual pieza perdio una atadura, y perder una atadura NO da error:
        steamcenturion.nif reparte 20 huesos entre 15 piezas, y doce de esas
        piezas usan uno solo -- pero SteamLFoot y SteamRFoot usan tres, y
        SteamCenturion usa cuatro, dos de ellos los parpados. Quedarse con el
        conteo global no distingue "20 huesos bien repartidos" de "20 huesos
        con el parpado colgando del torso".
        """
        fuera = {}
        for _b, (tipo, o, _s) in enumerate(self.bloques):
            if tipo not in TIPOS_SHAPE:
                continue
            _p, nombre = self._saltar_niavobject(o)
            skin_idx = self._skin_de_shape(o)
            if skin_idx is None:
                fuera[nombre] = {"huesos": [], "body_parts": [],
                                 "skin": None}
                continue
            huesos, partes = self._lee_skin_instance(skin_idx)
            fuera[nombre] = {"huesos": huesos, "body_parts": partes,
                             "skin": self.bloques[skin_idx][0]}
        return fuera

    def _avobject_transform(self, o):
        """(nombre, tr, rot, esc) de un bloque con layout NiAVObject.

        _saltar_niavobject pasa POR ENCIMA de estos campos sin leerlos. Un
        BSTriShape los tiene igual que un NiNode -- y son los que dicen donde
        quedo la pieza. No leerlos hacia que, sobre un estatico, comparar un
        NIF con el shape corrido 140 unidades diera CERO fallas.
        """
        p = o
        nombre_i, = struct.unpack_from("<i", self.d, p); p += 4
        n_ed, = struct.unpack_from("<I", self.d, p); p += 4 + 4 * n_ed
        p += 4 + 4                                  # controller, flags
        tr = struct.unpack_from("<3f", self.d, p); p += 12
        rot = struct.unpack_from("<9f", self.d, p); p += 36
        esc, = struct.unpack_from("<f", self.d, p); p += 4
        nombre = (self.strings[nombre_i]
                  if 0 <= nombre_i < len(self.strings) else "?")
        return nombre, tr, rot, esc, p + 4          # +4: collision object

    def nodos(self):
        if self._nodos_cache is not None:
            return self._nodos_cache
        n = {}
        for b, (tipo, o, _) in enumerate(self.bloques):
            if tipo not in TIPOS_NODO:
                continue
            nombre, tr, rot, esc, p = self._avobject_transform(o)
            n_h, = struct.unpack_from("<I", self.d, p); p += 4
            hijos = struct.unpack_from("<%di" % n_h, self.d, p) if n_h else ()
            n[b] = {"tipo": tipo, "nombre": nombre,
                    "tr": tr, "rot": rot, "esc": esc,
                    "hijos": [h for h in hijos if h >= 0]}
        self._nodos_cache = n
        return n

    def _recorrer_mundo(self):
        """{nodos, shapes, repetidos, rot_nodos, rot_shapes}.

        Un solo recorrido para los dos: un BSTriShape es hijo de un NiNode y
        su transformada se compone igual, solo que no tiene hijos propios.

        Tres cosas que antes no hacia:

        - Coloca los SHAPES. Sin esto, sobre un estatico --donde el unico nodo
          es la raiz-- no quedaba ni una posicion que comparar.
        - Lleva `vistos`, asi un ciclo en la jerarquia no la cuelga y un
          subarbol compartido no se recorre dos veces (sin memo, el recorrido
          es exponencial).
        - Devuelve los nombres REPETIDOS en vez de dejar que el ultimo tape al
          primero. Medido sobre el corpus: 557 de 22.394 archivos (2,49 %)
          tienen un nombre de nodo repetido --casi siempre `InvMarker`-- y 222
          (0,99 %) tienen dos shapes con el mismo nombre; en
          `_resourcepack/landscape/trees/mugopine01.nif` los dos se llaman "?"
          porque no tienen nombre, y indexar por nombre los reducia a UNO.
          Quien compara por nombre necesita saberlo.
        """
        if self._mundo_cache is not None:
            return self._mundo_cache
        nodos = self.nodos()
        shapes = {}
        for b, (tipo, o, _s) in enumerate(self.bloques):
            if tipo in TIPOS_SHAPE:
                nombre, tr, rot, esc, _p = self._avobject_transform(o)
                shapes[b] = {"nombre": nombre, "tr": tr, "rot": rot,
                             "esc": esc}
        hijos = set()
        for v in nodos.values():
            hijos.update(v["hijos"])

        pos_n, pos_s, repetidos = {}, {}, []
        rot_n, rot_s = {}, {}

        def mul(Ma, ta, sa, Mb, tb, sb):
            M = [sum(Ma[r * 3 + k] * Mb[k * 3 + c] for k in range(3))
                 for r in range(3) for c in range(3)]
            t = tuple(ta[r] + sa * sum(Ma[r * 3 + k] * tb[k] for k in range(3))
                      for r in range(3))
            return M, t, sa * sb

        def anotar(destino, rotes, nombre, M, t, s):
            v = (round(t[0], DECIMALES_MUNDO), round(t[1], DECIMALES_MUNDO),
                 round(t[2], DECIMALES_MUNDO), round(s, DECIMALES_ESCALA))
            if nombre in destino:
                repetidos.append(nombre)
            destino[nombre] = v
            # La ORIENTACION va aparte de la posicion: un hueso hoja girado en
            # su lugar tiene la misma posicion y arrastra la malla con el. Sin
            # esto, dos huesos girados 90 grados daban "pasa, 0 fallas".
            rotes[nombre] = tuple(round(x, DECIMALES_ROTACION) for x in M)

        vistos = set()

        def bajar(b, M, t, s):
            if b in vistos:
                return
            vistos.add(b)
            if b in shapes:
                v = shapes[b]
                M2, t2, s2 = mul(M, t, s, v["rot"], v["tr"], v["esc"])
                anotar(pos_s, rot_s, v["nombre"], M2, t2, s2)
                return
            v = nodos[b]
            M2, t2, s2 = mul(M, t, s, v["rot"], v["tr"], v["esc"])
            anotar(pos_n, rot_n, v["nombre"], M2, t2, s2)
            for h in v["hijos"]:
                if h in nodos or h in shapes:
                    bajar(h, M2, t2, s2)

        I = [1, 0, 0, 0, 1, 0, 0, 0, 1]
        for r in [b for b in nodos if b not in hijos]:
            bajar(r, I, (0.0, 0.0, 0.0), 1.0)
        # Un shape que no cuelga de ninguna raiz se coloca con su transformada
        # local. Se compara igual; lo que no se puede es inventarle un padre.
        for b, v in shapes.items():
            if b not in vistos:
                anotar(pos_s, rot_s, v["nombre"], list(v["rot"]), v["tr"],
                       v["esc"])
        self._mundo_cache = {"nodos": pos_n, "shapes": pos_s,
                             "repetidos": sorted(set(repetidos)),
                             "rot_nodos": rot_n, "rot_shapes": rot_s}
        return self._mundo_cache

    def mundo(self):
        return self._recorrer_mundo()["nodos"]

    def mundo_shapes(self):
        """{nombre de shape: (x, y, z, escala)} en espacio de mundo."""
        return self._recorrer_mundo()["shapes"]

    def rotaciones(self):
        """{nombre de nodo: 9 cosenos directores} en espacio de mundo."""
        return self._recorrer_mundo()["rot_nodos"]

    def rotaciones_shapes(self):
        """{nombre de shape: 9 cosenos directores} en espacio de mundo."""
        return self._recorrer_mundo()["rot_shapes"]

    def nombres_repetidos(self):
        """Nombres que aparecen mas de una vez. Comparar por nombre no puede
        decidir nada sobre ellos, asi que quien compare tiene que saberlo."""
        return self._recorrer_mundo()["repetidos"]

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
                  "NiAlphaProperty": 15, "BSShaderTextureSet": 1},
      # Abierto en NifSkope antes de escribir el parser. Doce piezas con un
      # hueso, dos pies con tres y el torso con cuatro: el reparto desparejo
      # es el punto -- un parser que devolviera "1 hueso" para todas pasaria
      # un promedio y fallaria esto.
      "huesos_por_shape": {
          "SteamRForearm": 1, "SteamLPauldron": 1, "SteamRPauldron": 1,
          "SteamLFoot": 3, "SteamRFoot": 3, "SteamLCalf": 1,
          "SteamRCalf": 1, "SteamRThigh": 1, "SteamLThigh": 1,
          "SteamPelvis": 1, "SteamSpine": 1, "SteamCenturion": 4,
          "SteamLUpperarm": 1, "SteamLForearm": 1, "SteamRUpperarm": 1},
      "huesos_de": {
          "SteamLFoot": ["NPC L Calf [LClf]", "NPC L Foot [Ltft ]",
                         "NPC L Toe0 [LToe]"],
          "SteamCenturion": ["NPC Spine2 [Spn2]", "NPC UpperLid",
                             "NPC LowerLid", "NPC LowerJaw"]},
      "body_parts": [32]}),
    ("actors/character/character assets/childbody.nif",
     {"raiz": "NiNode", "skinneado": True,
      "huesos_por_shape": {"BODY": 24}, "body_parts": [32]}),
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
        sk = n.skin_por_shape()
        real = {"n_bloques": len(n.bloques), "raiz": n.raiz(),
                "bsxflags": n.bsxflags(), "bloques": n.cuenta_tipos(),
                "skinneado": n.es_skinneado(),
                "triangulos_inline": sum(t for _, t, _ in n.trishapes()),
                "huesos_por_shape": {k: len(v["huesos"])
                                     for k, v in sk.items()},
                "huesos_de": {k: v["huesos"] for k, v in sk.items()},
                "body_parts": sorted({p for v in sk.values()
                                      for p in v["body_parts"]})}
        for campo, valor in esperado.items():
            if campo not in real:
                fallo += 1
                print("  [FALLA]  %s :: campo desconocido %r"
                      % (os.path.basename(rel), campo))
                continue
            if campo == "huesos_de":
                # Solo los shapes declarados; el resto ya lo cubre
                # huesos_por_shape. Un shape declarado que no exista es fallo.
                sub = {k: real[campo].get(k) for k in valor}
                if sub == valor:
                    ok += 1
                else:
                    fallo += 1
                    print("  [FALLA]  %s :: %s"
                          % (os.path.basename(rel), campo))
                    print("           esperado %r" % (valor,))
                    print("           obtenido %r" % (sub,))
                continue
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
    if ok == 0:
        # Cero comprobaciones no es exito. Apuntar --autotest a una carpeta
        # vacia o equivocada devolvia 0 y el README promete que "avisa si no
        # esta listo para censar": con cero reproducciones no avisaba nada.
        print("  NO se comprobo NADA. Revisa la ruta del corpus.")
        return False
    if fallo:
        print("  El parser NO esta listo para censar.")
    elif falta:
        print("  Ok hasta donde se pudo comprobar, pero faltan archivos.")
    else:
        print("  Parser validado. Ahora si, censar.")
    # Corpus incompleto no es validacion: antes con falta>0 y fallo==0 se
    # imprimia "El parser NO esta listo" y sin embargo se devolvia True
    # (exit 0). Mensaje y exit code tienen que decir lo mismo.
    return fallo == 0 and falta == 0


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    if a[0] == "--autotest":
        if len(a) < 2:
            print("Uso: --autotest <carpeta del corpus>")
            raise SystemExit(2)
        if not autotest(a[1]):
            raise SystemExit(1)
        return
    if a[0] == "--censo":
        if len(a) < 2 or (a[-1] == "--salida"):
            print("Uso: --censo <carpeta> [--salida censo.jsonl]")
            raise SystemExit(2)
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
