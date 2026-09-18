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
BSX_VALOR = 203
HIJO_TRASLACION = (10.0, 20.0, 30.0)

IDENTIDAD = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def _corta(texto):
    """String con longitud de 1 byte, como las de ExportInfo."""
    b = texto.encode("cp1252")
    return struct.pack("<B", len(b)) + b


def _larga(texto):
    """String con longitud de 4 bytes, como las de la tabla de strings."""
    b = texto.encode("cp1252")
    return struct.pack("<I", len(b)) + b


def _avobject(nombre_idx, extra_refs, traslacion, hijos):
    """NiObjectNET + NiAVObject + los campos de NiNode, en ese orden."""
    p = struct.pack("<i", nombre_idx)
    p += struct.pack("<I", len(extra_refs))
    p += b"".join(struct.pack("<i", r) for r in extra_refs)
    p += struct.pack("<i", -1)                       # controller
    p += struct.pack("<I", 14)                       # flags
    p += struct.pack("<3f", *traslacion)
    p += struct.pack("<9f", *IDENTIDAD)
    p += struct.pack("<f", 1.0)                      # escala
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
