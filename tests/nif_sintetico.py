# -*- coding: utf-8 -*-
"""Construye un NIF de Skyrim SE valido byte a byte, en memoria.

POR QUE EXISTE

La verificacion que de verdad prueba que el parser anda es `--autotest`, y
necesita el corpus vanilla extraido, que no se versiona. Sin sustituto, CI
queda verde sobre codigo de parseo que nunca se ejecuta: se puede inyectar un
corrimiento de 4 bytes en la lectura de la cabecera --que destruiria la tabla
de strings y todos los offsets de bloque-- y la suite no se entera.

Este modulo cierra ese hueco. Los bytes se generan aca, asi que no hay ni un
byte de Bethesda, y las respuestas se declaran junto con los datos: el parser
tiene que recuperar exactamente lo que el constructor escribio.

NO reemplaza a `--autotest`. Cubre el camino de parseo (cabecera, tabla de
bloques, tabla de strings, offsets, jerarquia de nodos, BSXFlags) contra un
archivo minimo. Los layouts de geometria, skin y colision se siguen validando
solo contra archivos reales.

ESTRUCTURA DEL ARCHIVO QUE GENERA

    <raiz_tipo> "RaizDePrueba"     bloque 0, raiz, 1 hijo, 1 extra data
    +-- NiNode "HijoDePrueba"      bloque 1, trasladado a (10, 20, 30)
    BSXFlags  "BSX" = 203          bloque 2, referenciado como extra data
    BSFurnitureMarkerNode          bloque 3, TRAMPA deliberada

El tipo del bloque 0 sale de `construir(raiz_tipo)` y por defecto es
BSFadeNode. Cambiarlo cambia la tabla de tipos del archivo, y con eso
`esperado["cuenta_tipos"]`, que se deriva de los mismos `tipos` que se
escriben: la verdad declarada sigue al parametro.

203 no es un numero al azar: es el valor real de `soulgemgreater01.nif`, y sus
bits encendidos son 0+1+3+6+7.

LA TRAMPA DEL BLOQUE 3

`BSFurnitureMarkerNode` termina en "Node" pero hereda de `NiExtraData`, no de
`NiAVObject`. Un parser que lo meta en su tabla de tipos-nodo lee su contenido
con el layout de NiNode y saca un conteo de hijos absurdo. Medido sobre el
corpus real: 30 de 76 archivos de `meshes/furniture/` revientan con
"unpack_from requires a buffer of at least 4093659953 bytes".

El bloque de aca esta armado para reproducir ese modo de falla exacto: donde el
layout de NiNode espera `numChildren` hay un valor enorme. Un parser correcto
lo ignora; uno que lo trate como nodo revienta.

El sufijo del nombre no dice de que hereda.
"""
import struct

CABECERA = b"Gamebryo File Format, Version 20.2.0.7\n"
VERSION = 0x14020007
USER = 12
BS = 100

RAIZ_NOMBRE = "RaizDePrueba"
HIJO_NOMBRE = "HijoDePrueba"
BSX_NOMBRE = "BSX"
MARCADOR_NOMBRE = "MarcadorMueble"

PIEZA_NOMBRE = "PiezaDePrueba"
HUESOS_NOMBRE = ("HuesoA", "HuesoB")
HUESOS_TRASLACION = ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0))
BODY_PART = 32          # el unico valor que aparece en steamcenturion.nif
BSX_VALOR = 203
HIJO_TRASLACION = (10.0, 20.0, 30.0)

IDENTIDAD = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
# Un cuarto de vuelta alrededor de Z. Un nodo HOJA con esto puesto queda en la
# MISMA posicion de mundo y con otros ejes: es la unica forma de torcer la
# orientacion sin tocar la posicion, y por eso hace falta.
CUARTO_DE_VUELTA = (0.0, -1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


def _corta(texto):
    """String con longitud de 1 byte, como las de ExportInfo."""
    b = texto.encode("cp1252")
    return struct.pack("<B", len(b)) + b


def _larga(texto):
    """String con longitud de 4 bytes, como las de la tabla de strings."""
    b = texto.encode("cp1252")
    return struct.pack("<I", len(b)) + b


def _avobject(nombre_idx, extra_refs, traslacion, hijos, escala=1.0,
              rot=IDENTIDAD):
    """NiObjectNET + NiAVObject + los campos de NiNode, en ese orden."""
    p = struct.pack("<i", nombre_idx)
    p += struct.pack("<I", len(extra_refs))
    p += b"".join(struct.pack("<i", r) for r in extra_refs)
    p += struct.pack("<i", -1)                       # controller
    p += struct.pack("<I", 14)                       # flags
    p += struct.pack("<3f", *traslacion)
    p += struct.pack("<9f", *rot)
    p += struct.pack("<f", escala)
    p += struct.pack("<i", -1)                       # collision object
    p += struct.pack("<I", len(hijos))
    p += b"".join(struct.pack("<i", h) for h in hijos)
    p += struct.pack("<I", 0)                        # numEffects
    return p


def _marcador_trampa(nombre_idx):
    """BSFurnitureMarkerNode armado para romper a quien lo trate como NiNode.

    Leido como NiExtraData --lo correcto-- es nombre + cantidad + datos.
    Leido con el layout de NiNode, el cursor cae en el offset 76 buscando
    `numChildren` y encuentra 0xFFFFFFF0: intenta leer 4.294.967.280 refs de
    hijo y revienta, igual que en los archivos reales.
    """
    b = bytearray(80)
    struct.pack_into("<i", b, 0, nombre_idx)         # name
    struct.pack_into("<I", b, 4, 1)                  # numPositions
    struct.pack_into("<I", b, 76, 0xFFFFFFF0)        # la mina
    return bytes(b)


def _avobject_sin_hijos(nombre_idx, traslacion, escala=1.0, rot=IDENTIDAD):
    """Solo NiObjectNET + NiAVObject: lo que comparten nodos y shapes.

    Un BSTriShape NO es un NiNode: no lleva children ni effects. Escribirle
    esos campos correria todo lo que viene despues (esfera envolvente, refs de
    skin) y el parser leeria basura sin dar error.
    """
    p = struct.pack("<i", nombre_idx)
    p += struct.pack("<I", 0)                        # numExtraData
    p += struct.pack("<i", -1)                       # controller
    p += struct.pack("<I", 14)                       # flags
    p += struct.pack("<3f", *traslacion)
    p += struct.pack("<9f", *rot)
    p += struct.pack("<f", escala)
    p += struct.pack("<i", -1)                       # collision object
    return p


def _trishape(nombre_idx, skin_ref, traslacion=(0.0, 0.0, 0.0), escala=1.0,
              rot=IDENTIDAD):
    """BSTriShape skinneado: sin geometria inline, con ref a la skin instance.

    numTriangles = numVertices = dataSize = 0 no es un atajo del fixture: es
    como se ve un shape skinneado en SSE de verdad. La geometria vive en el
    NiSkinPartition (ver la cabecera de censo_nif.py).
    """
    p = _avobject_sin_hijos(nombre_idx, traslacion, escala, rot)
    p += struct.pack("<4f", 0.0, 0.0, 0.0, 0.0)      # esfera envolvente
    p += struct.pack("<3i", skin_ref, -1, -1)        # skin, shader, alpha
    p += struct.pack("<Q", 0x0000000000000004)       # vertexDesc
    p += struct.pack("<H", 0)                        # numTriangles
    p += struct.pack("<H", 0)                        # numVertices
    p += struct.pack("<I", 0)                        # dataSize
    return p


def _trishape_estatico(nombre_idx, pos, tris, traslacion=(0.0, 0.0, 0.0),
                       escala=1.0, rot=IDENTIDAD, data_size=None, uvs=None,
                       shader_ref=-1):
    """BSTriShape ESTATICO: la geometria va inline, despues de dataSize.

    SIN uvs el vertexDesc declara stride 12 --solo XYZ-- porque
    `stride = (vdesc & 0xF) * 4`. CON uvs el stride pasa a 20, porque las UV
    viven en el byte 16 del vertice (12 de posicion + 4 de bitangente/relleno)
    y ocupan dos half-floats; y se enciende el bit de presencia,
    `(vdesc >> 44) & 0x2`. Los dos numeros estan medidos en la cabecera de
    census/parser_uv.py, no leidos de nif.xml.

    En los dos casos la identidad n_ver*stride + n_tri*6 == dataSize se
    cumple, que es lo que el lector usa para falsificar el layout.

    `data_size` deja escribir un tamano MENTIROSO a proposito: un lector
    correcto tiene que negarse a devolver numeros en vez de leer basura.
    """
    p = _avobject_sin_hijos(nombre_idx, traslacion, escala, rot)
    p += struct.pack("<4f", 0.0, 0.0, 0.0, 0.0)      # esfera envolvente
    p += struct.pack("<3i", -1, shader_ref, -1)      # skin, shader, alpha
    if uvs is None:
        vdesc = 0x0000000000000003                   # stride 12, sin UV
        cuerpo = b"".join(struct.pack("<3f", *v) for v in pos)
    else:
        vdesc = 0x0000000000000005 | (0x2 << 44)     # stride 20, con UV
        cuerpo = b"".join(
            struct.pack("<3f", *v) + struct.pack("<4s", b"\x00\x00\x00\x00")
            + struct.pack("<2e", *uv)
            for v, uv in zip(pos, uvs))
    p += struct.pack("<Q", vdesc)
    cuerpo += b"".join(struct.pack("<3H", *t) for t in tris)
    p += struct.pack("<H", len(tris))                # numTriangles
    p += struct.pack("<H", len(pos))                 # numVertices
    p += struct.pack("<I", len(cuerpo) if data_size is None else data_size)
    p += cuerpo
    return p


def construir_estatico(pos, tris, nombre_pieza=PIEZA_NOMBRE, data_size=None,
                       uvs=None):
    """(bytes, esperado) de un NIF con UNA pieza estatica con geometria inline.

    Existe para poder probar la lectura de geometria --y la medicion de salud
    de malla-- sin depender del corpus vanilla, que no esta en el repo.
    """
    tipos = ["BSFadeNode", "BSTriShape"]
    strings = [RAIZ_NOMBRE, nombre_pieza]
    bloques = [
        _avobject(0, [], (0.0, 0.0, 0.0), [1]),                  # 0: raiz
        _trishape_estatico(1, pos, tris, data_size=data_size,
                           uvs=uvs),                            # 1: pieza
    ]

    h = bytearray(CABECERA)
    h += struct.pack("<I", VERSION)
    h += struct.pack("<B", 1)                        # endian: little
    h += struct.pack("<I", USER)
    h += struct.pack("<I", len(bloques))
    h += struct.pack("<I", BS)
    h += _corta("")                                  # author
    h += _corta("")                                  # process script
    h += _corta("")                                  # export script
    h += struct.pack("<H", len(tipos))
    for t in tipos:
        h += _larga(t)
    for k in range(len(bloques)):
        h += struct.pack("<H", k)                    # un tipo por bloque
    for b in bloques:
        h += struct.pack("<I", len(b))
    h += struct.pack("<I", len(strings))
    h += struct.pack("<I", max(len(s) for s in strings))
    for s in strings:
        h += _larga(s)
    h += struct.pack("<I", 0)                        # numGroups

    datos = bytes(h) + b"".join(bloques)
    esperado = {"raiz": RAIZ_NOMBRE, "pieza": nombre_pieza,
                "pos": [tuple(float(c) for c in v) for v in pos],
                "tris": [tuple(int(i) for i in t) for t in tris],
                "uvs": None if uvs is None
                       else [tuple(float(c) for c in uv) for uv in uvs]}
    return datos, esperado


def _lighting_shader(tipo, flags1, flags2, texset_ref, glossiness, spec_str,
                     env_scale):
    """BSLightingShaderProperty de SSE (BS 100), escrito desde nif.xml.

    Va escrito aca y no importado de material_arma.py a proposito: si el
    lector y el fixture salieran del mismo codigo, un campo corrido en los dos
    lados pasaria igual. Solo los tipos Default (0), EnvMap (1) y Glow (2);
    EnvMap es el unico de los tres que agrega un campo al final.
    """
    if tipo not in (0, 1, 2):
        raise ValueError("este fixture solo arma los tipos 0, 1 y 2")
    p = struct.pack("<I", tipo)                      # Skyrim Shader Type
    p += struct.pack("<i", -1)                       # Name
    p += struct.pack("<I", 0)                        # numExtraData
    p += struct.pack("<i", -1)                       # controller
    p += struct.pack("<2I", flags1, flags2)
    p += struct.pack("<2f", 0.0, 0.0)                # UV offset
    p += struct.pack("<2f", 1.0, 1.0)                # UV scale
    p += struct.pack("<i", texset_ref)
    p += struct.pack("<3f", 0.0, 0.0, 0.0)           # emissive color
    p += struct.pack("<f", 1.0)                      # emissive multiple
    p += struct.pack("<I", 3)                        # texture clamp mode
    p += struct.pack("<f", 1.0)                      # alpha
    p += struct.pack("<f", 0.0)                      # refraction strength
    p += struct.pack("<f", glossiness)
    p += struct.pack("<3f", 1.0, 1.0, 1.0)           # specular color
    p += struct.pack("<f", spec_str)
    p += struct.pack("<2f", 0.3, 2.0)                # lighting effect 1 y 2
    if tipo == 1:
        p += struct.pack("<f", env_scale)            # environment map scale
    return p


def construir_con_material(tipo=1, flags1=0x80, flags2=0,
                           rutas=("a.dds", "a_n.dds", "", "",
                                  "textures\\cubemaps\\shinydull_e.dds",
                                  "a_m.dds", "", "", ""),
                           glossiness=80.0, spec_str=1.0, env_scale=1.0,
                           nombre_pieza="HojaDePrueba", con_shader=True):
    """(bytes, esperado) de un NIF con UNA pieza estatica y su material.

        0  BSFadeNode                   hijo: la pieza
        1  BSTriShape  <nombre_pieza>   un triangulo, shader -> 2
        2  BSLightingShaderProperty     texture set -> 3
        3  BSShaderTextureSet           `rutas`, nueve ranuras

    `con_shader=False` deja la pieza sin shader (ref -1) y sin los bloques 2
    y 3: un NIF sin material que medir.
    """
    tipos = ["BSFadeNode", "BSTriShape"]
    strings = [RAIZ_NOMBRE, nombre_pieza]
    pos = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0)]
    bloques = [
        _avobject(0, [], (0.0, 0.0, 0.0), [1]),
        _trishape_estatico(1, pos, [(0, 1, 2)],
                           shader_ref=2 if con_shader else -1),
    ]
    if con_shader:
        tipos += ["BSLightingShaderProperty", "BSShaderTextureSet"]
        texset = struct.pack("<i", len(rutas))
        for r in rutas:
            texset += _larga(r)
        bloques += [_lighting_shader(tipo, flags1, flags2, 3, glossiness,
                                     spec_str, env_scale),
                    texset]

    h = bytearray(CABECERA)
    h += struct.pack("<I", VERSION)
    h += struct.pack("<B", 1)
    h += struct.pack("<I", USER)
    h += struct.pack("<I", len(bloques))
    h += struct.pack("<I", BS)
    h += _corta("")
    h += _corta("")
    h += _corta("")
    h += struct.pack("<H", len(tipos))
    for t in tipos:
        h += _larga(t)
    for k in range(len(bloques)):
        h += struct.pack("<H", k)
    for b in bloques:
        h += struct.pack("<I", len(b))
    h += struct.pack("<I", len(strings))
    h += struct.pack("<I", max(len(s) for s in strings))
    for s in strings:
        h += _larga(s)
    h += struct.pack("<I", 0)
    esperado = {"pieza": nombre_pieza, "tipo": tipo, "gloss": glossiness,
                "spec_str": spec_str, "env_scale": env_scale,
                "rutas": list(rutas) if con_shader else []}
    return bytes(h) + b"".join(bloques), esperado


def construir_con_colision(dims, radio, masa, inercia, motion=3,
                           cuerpo_tipo="bhkRigidBodyT", tam_cuerpo=250):
    """(bytes, esperado) de un NIF con un bhkRigidBody(T) y su bhkBoxShape.

    Los offsets que se escriben son los que el lector va a buscar, y estan
    fijados por correlacion contra PyNifly sobre archivos reales:

        bhkBoxShape    +4   radio          +16  medias extensiones
        bhkRigidBody   +116 Ixx  +136 Iyy  +156 Izz
                       +180 masa           +224 motionSystem

    `tam_cuerpo` deja escribir un bloque CORTO a proposito: un lector correcto
    tiene que negarse a leer campos que no entran en el bloque, en vez de
    devolver lo que haya despues.
    """
    tipos = ["BSFadeNode", cuerpo_tipo, "bhkBoxShape"]
    strings = [RAIZ_NOMBRE]

    caja = bytearray(32)
    struct.pack_into("<I", caja, 0, 1000)             # material
    struct.pack_into("<f", caja, 4, radio)
    struct.pack_into("<3f", caja, 16, *dims)

    cuerpo = bytearray(tam_cuerpo)
    struct.pack_into("<i", cuerpo, 0, 2)              # ref a la forma
    for k, v in zip((116, 136, 156), inercia):
        if k + 4 <= tam_cuerpo:
            struct.pack_into("<f", cuerpo, k, v)
    if 184 <= tam_cuerpo:
        struct.pack_into("<f", cuerpo, 180, masa)
    if 225 <= tam_cuerpo:
        cuerpo[224] = motion

    bloques = [_avobject(0, [], (0.0, 0.0, 0.0), []),  # 0: raiz
               bytes(cuerpo),                          # 1: cuerpo rigido
               bytes(caja)]                            # 2: la caja

    h = bytearray(CABECERA)
    h += struct.pack("<I", VERSION)
    h += struct.pack("<B", 1)
    h += struct.pack("<I", USER)
    h += struct.pack("<I", len(bloques))
    h += struct.pack("<I", BS)
    h += _corta("")
    h += _corta("")
    h += _corta("")
    h += struct.pack("<H", len(tipos))
    for t in tipos:
        h += _larga(t)
    for k in range(len(bloques)):
        h += struct.pack("<H", k)
    for b in bloques:
        h += struct.pack("<I", len(b))
    h += struct.pack("<I", len(strings))
    h += struct.pack("<I", max(len(s) for s in strings))
    for s in strings:
        h += _larga(s)
    h += struct.pack("<I", 0)

    esperado = {"dims": [float(x) for x in dims], "radio": float(radio),
                "masa": float(masa), "inercia": [float(x) for x in inercia],
                "motion": motion, "cuerpo": cuerpo_tipo}
    return bytes(h) + b"".join(bloques), esperado


def _dismember(bone_refs, body_parts, con_particiones=True):
    """La skin instance: los cuatro refs, los huesos y --solo en la variante
    dismember-- las particiones de body-part.

    `con_particiones=False` da un `NiSkinInstance` pelado. Hace falta porque
    el corpus tiene 11.644 bloques `NiSkinInstance` contra 16.368
    `BSDismemberSkinInstance` (el 41,6 %), y ni el fixture ni las dos entradas
    skinneadas del AUTOTEST --steamcenturion y childbody, las dos dismember--
    tocaban esa rama.
    """
    p = struct.pack("<4i", -1, -1, 0, len(bone_refs))
    p += b"".join(struct.pack("<i", r) for r in bone_refs)
    if con_particiones:
        p += struct.pack("<I", len(body_parts))
        for bp in body_parts:
            p += struct.pack("<2H", 0, bp)
    return p


def construir(raiz_tipo="BSFadeNode"):
    """Devuelve (bytes_del_nif, esperado).

    `esperado` es la verdad declarada: lo que cualquier parser correcto tiene
    que recuperar de esos bytes.

    `raiz_tipo` deja cambiar el tipo del bloque raiz. El nombre del tipo va en
    la tabla con su largo adelante, asi que cambiarlo corre donde empiezan los
    bloques -- por eso se reconstruye la cabecera entera aca en vez de parchear
    bytes sobre un archivo ya armado. Un parser correcto no se entera.
    """
    tipos = [raiz_tipo, "NiNode", "BSXFlags", "BSFurnitureMarkerNode"]
    strings = [RAIZ_NOMBRE, HIJO_NOMBRE, BSX_NOMBRE, MARCADOR_NOMBRE]

    bloques = [
        _avobject(0, [2], (0.0, 0.0, 0.0), [1]),     # 0: raiz
        _avobject(1, [], HIJO_TRASLACION, []),       # 1: hijo
        struct.pack("<i", 2) + struct.pack("<i", BSX_VALOR),   # 2: BSXFlags
        _marcador_trampa(3),                         # 3: la trampa
    ]

    h = bytearray(CABECERA)
    h += struct.pack("<I", VERSION)
    h += struct.pack("<B", 1)                        # endian: little
    h += struct.pack("<I", USER)
    h += struct.pack("<I", len(bloques))
    h += struct.pack("<I", BS)
    h += _corta("")                                  # author
    h += _corta("")                                  # process script
    h += _corta("")                                  # export script
    h += struct.pack("<H", len(tipos))
    for t in tipos:
        h += _larga(t)
    for k in range(len(bloques)):
        h += struct.pack("<H", k)                    # un tipo por bloque
    for b in bloques:
        h += struct.pack("<I", len(b))
    h += struct.pack("<I", len(strings))
    h += struct.pack("<I", max(len(s) for s in strings))
    for s in strings:
        h += _larga(s)
    h += struct.pack("<I", 0)                        # numGroups

    datos = bytes(h) + b"".join(bloques)

    esperado = {
        "version": VERSION,
        "user": USER,
        "bs": BS,
        "n_bloques": len(bloques),
        "raiz": raiz_tipo,
        "cuenta_tipos": {t: tipos.count(t) for t in tipos},
        "strings": list(strings),
        "tamanos": [len(b) for b in bloques],
        "bsxflags": BSX_VALOR,
        "bsxflags_bits": [0, 1, 3, 6, 7],
        # El marcador NO aparece: no es un nodo, aunque se llame *Node.
        "nombres_nodo": {RAIZ_NOMBRE, HIJO_NOMBRE},
        "nombre_marcador": MARCADOR_NOMBRE,
        "hijo_en_mundo": HIJO_TRASLACION,
        "cola_esperada": 0,
    }
    return datos, esperado


def construir_arma(prn="WeaponBack"):
    """Un NIF de arma minimo: la raiz con un NiStringExtraData `Prn` y el
    BSXFlags. `prn=None` lo arma sin Prn.

    En SSE un NiStringExtraData son dos indices a la tabla de strings: el
    nombre ("Prn") y el valor ("WeaponBack"). El Prn es el nodo del esqueleto
    del que cuelga el arma envainada (census/hallazgos_plugins.md, entrada 17).
    """
    tipos = ["BSFadeNode", "BSXFlags"]
    strings = [RAIZ_NOMBRE, BSX_NOMBRE]
    extra = [1]
    bloques_extra = []
    if prn is not None:
        tipos.append("NiStringExtraData")
        strings += ["Prn", prn]
        extra = [1, 2]
        bloques_extra = [struct.pack("<ii", 2, 3)]
    bloques = [
        _avobject(0, extra, (0.0, 0.0, 0.0), []),
        struct.pack("<i", 1) + struct.pack("<i", BSX_VALOR),
    ] + bloques_extra

    h = bytearray(CABECERA)
    h += struct.pack("<I", VERSION)
    h += struct.pack("<B", 1)
    h += struct.pack("<I", USER)
    h += struct.pack("<I", len(bloques))
    h += struct.pack("<I", BS)
    h += _corta("")
    h += _corta("")
    h += _corta("")
    h += struct.pack("<H", len(tipos))
    for t in tipos:
        h += _larga(t)
    for k in range(len(bloques)):
        h += struct.pack("<H", k)
    for b in bloques:
        h += struct.pack("<I", len(b))
    h += struct.pack("<I", len(strings))
    h += struct.pack("<I", max(len(s) for s in strings))
    for s in strings:
        h += _larga(s)
    h += struct.pack("<I", 0)
    return bytes(h) + b"".join(bloques), {"strings": list(strings),
                                          "prn": prn}


def construir_skinneado(raiz_tipo="NiNode", nombre_pieza=PIEZA_NOMBRE,
                        huesos=HUESOS_NOMBRE,
                        traslaciones=HUESOS_TRASLACION,
                        body_parts=(BODY_PART,), bloque_extra=False,
                        tr_pieza=(0.0, 0.0, 0.0), esc_pieza=1.0,
                        skin_tipo="BSDismemberSkinInstance",
                        nombre_raiz=None, tr_raiz=(0.0, 0.0, 0.0),
                        esc_raiz=1.0, escalas=None, rot_pieza=IDENTIDAD,
                        rot_huesos=None, bs=BS):
    """Un NIF skinneado minimo, con TODO parametrizado para poder torcerlo.

    Va aparte de construir() y no como un flag suyo para no tocar el
    `esperado` que ya usan los tests del parser: un fixture que cambia de
    forma segun un flag obliga a leer el flag para saber que se esta
    comprobando.

    Cada parametro existe porque hay un control que tiene que reprobar cuando
    cambia: el nombre de la pieza, el juego de huesos, donde esta cada hueso,
    las particiones de dismember y la cuenta de bloques. Un fixture que solo
    se pueda construir bien no puede falsificar nada.

        0  raiz (raiz_tipo)          hijos: la pieza y los huesos
        1  BSTriShape  <pieza>       skin -> 2
        2  BSDismemberSkinInstance   huesos -> 3, 4, ...
        3+ NiNode  <hueso>
        ultimo (opcional) NiNode suelto, para mover la cuenta de bloques
    """
    if len(huesos) != len(traslaciones):
        raise ValueError("un hueso, una traslacion")
    if skin_tipo not in ("BSDismemberSkinInstance", "NiSkinInstance"):
        raise ValueError("skin instance desconocida: %r" % skin_tipo)
    tipos = [raiz_tipo, "BSTriShape", skin_tipo, "NiNode"]
    strings = [nombre_raiz or RAIZ_NOMBRE, nombre_pieza] + list(huesos)

    n_huesos = len(huesos)
    idx_huesos = list(range(3, 3 + n_huesos))
    hijos = [1] + idx_huesos
    dismember = skin_tipo == "BSDismemberSkinInstance"
    escalas = tuple(escalas) if escalas else (1.0,) * n_huesos
    if len(escalas) != n_huesos:
        raise ValueError("un hueso, una escala")
    rot_huesos = tuple(rot_huesos) if rot_huesos else (IDENTIDAD,) * n_huesos
    if len(rot_huesos) != n_huesos:
        raise ValueError("un hueso, una rotacion")
    bloques = [_avobject(0, [], tr_raiz, hijos, esc_raiz),
               _trishape(1, 2, tr_pieza, esc_pieza, rot_pieza),
               _dismember(idx_huesos, body_parts, dismember)]
    tipo_de = [0, 1, 2]
    for i, t in enumerate(traslaciones):
        bloques.append(_avobject(2 + i, [], t, [], escalas[i], rot_huesos[i]))
        tipo_de.append(3)
    if bloque_extra:
        strings.append("NodoDeMas")
        bloques.append(_avobject(len(strings) - 1, [], (0.0, 0.0, 0.0), []))
        tipo_de.append(3)

    h = bytearray(CABECERA)
    h += struct.pack("<I", VERSION)
    h += struct.pack("<B", 1)
    h += struct.pack("<I", USER)
    h += struct.pack("<I", len(bloques))
    h += struct.pack("<I", bs)
    h += _corta("") + _corta("") + _corta("")
    h += struct.pack("<H", len(tipos))
    for t in tipos:
        h += _larga(t)
    for k in tipo_de:
        h += struct.pack("<H", k)
    for b in bloques:
        h += struct.pack("<I", len(b))
    h += struct.pack("<I", len(strings))
    h += struct.pack("<I", max(len(s) for s in strings))
    for s in strings:
        h += _larga(s)
    h += struct.pack("<I", 0)

    datos = bytes(h) + b"".join(bloques)
    esperado = {
        "n_bloques": len(bloques),
        "raiz": raiz_tipo,
        "nombre_raiz": nombre_raiz or RAIZ_NOMBRE,
        "raiz_en_mundo": tuple(tr_raiz) + (esc_raiz,),
        "skinneado": True,
        "skin_tipo": skin_tipo,
        "pieza": nombre_pieza,
        "pieza_en_mundo": tuple(tr_pieza) + (esc_pieza,),
        "huesos": list(huesos),
        "body_parts": list(body_parts) if dismember else [],
        "huesos_en_mundo": {n: t for n, t in zip(huesos, traslaciones)},
    }
    return datos, esperado
