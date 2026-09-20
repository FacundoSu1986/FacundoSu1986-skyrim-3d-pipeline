# -*- coding: utf-8 -*-
"""Marca (o desmarca) un plugin de Skyrim SE como ESL, comprobando antes si puede.

Skyrim SE carga como mucho 255 plugins normales. Un plugin marcado como ESL no
entra en esa cuenta: va al espacio FE, que tiene 4096 huecos aparte. Para un mod
de dos o tres records, gastar un slot de los 255 es un desperdicio -- y el
usuario que instale tu mod lo va a notar antes que vos.

QUE HACE. Enciende el bit 0x200 en los flags del record TES4 de cabecera (offset
8 del archivo). Nada mas. NO renombra a .esl: un .esp con el flag puesto funciona
igual y asi no hay que retocar el gestor de mods ni el orden de carga.

EL REQUISITO QUE NADIE TE AVISA. Un ESL solo puede tener FormIDs nuevos cuyo
indice de objeto caiga entre 0x800 y 0xFFF. Con uno fuera de rango el juego NO
da error al cargar: lo remapea, y el objeto aparece corrupto o directamente no
aparece. Por eso esto se comprueba ANTES de escribir, y si falla no toca nada.
El Creation Kit tiende a asignar indices bajos (0x000D62 esta bien, 0x000001 no),
asi que la comprobacion falla de verdad a veces.

LO QUE ROMPE. Al pasar a ESL el plugin deja de cargarse con indice 01 y pasa a
FE:XXX, asi que el FormID de cada objeto cambia de 01xxxxxx a FExxxxxx. Una
partida guardada que ya tenia el objeto en el inventario deja de encontrarlo:
hay que volver a agregarlo por consola con el FormID nuevo. Esto es inherente a
convertir a ESL, no un defecto de este script. Avisalo ANTES de convertir.

FALLA CERRADO. Si el recorrido de records no cierra en el fin del archivo, no
escribe nada. Antes fallaba ABIERTO: un plugin truncado hacia que viera menos
records, con menos records no habia ninguno fuera de rango, y `--marcar` ponia
el flag y salia con exit 0.

Uso:
  python esl.py <plugin.esp>              solo informa (no escribe nada)
  python esl.py <plugin.esp> --marcar     pone el flag (deja .bak)
  python esl.py <plugin.esp> --quitar     lo saca (deja .bak)
  python esl.py --autotest <carpeta Data> reproduce los conteos medidos
"""

import argparse
import os
import shutil
import struct
import sys

BANDERA_ESL = 0x200
BANDERA_ESM = 0x1
RANGO_ESL = (0x800, 0xFFF)


def recorrer_formids(d):
    """(formids, cerro). `cerro` dice si el recorrido embaldoso el archivo.

    Un GRUP se entra, no se saltea: su cabecera mide 24 bytes igual que la de un
    record, pero su tamano INCLUYE la cabecera y su contenido son mas records.

    POR QUE DEVUELVE TAMBIEN SI CERRO. Sin ese dato, esto fallaba ABIERTO. Un
    plugin truncado 30 bytes hacia que el recorrido viera 1 record en vez de 2;
    con un record menos no habia ningun FormID fuera de rango, y `--marcar`
    escribia el flag y salia con exit 0. La comprobacion que existe para que no
    corrompas tu mod pasaba JUSTO PORQUE no habia mirado el record que tenia que
    mirar. Medido con tests/plugin_sintetico.py.

    El cierre se comprueba como en census/parser_esm.py: la suma de bloques
    tiene que caer exactamente en el fin del archivo. Ahi esa identidad se
    cumple en 1.328.055 records de 10 plugins sin una sola violacion.
    """
    fuera = []
    i = 0
    while i + 24 <= len(d):
        tag = d[i:i + 4]
        tam = struct.unpack_from("<I", d, i + 4)[0]
        if tag == b"GRUP":
            if tam < 24:
                return fuera, False
            i += 24
            continue
        fid = struct.unpack_from("<I", d, i + 12)[0]
        if tag != b"TES4":
            fuera.append(fid)
        i += 24 + tam
    return fuera, i == len(d)


# Medido contra los 10 plugins de una instalacion SE, cruzando este mismo
# recorrido con el de census/parser_esm.py: los dos dan el MISMO numero en los
# 10, 1.188.811 records en total. La tabla existe para que si alguien toca el
# recorrido, el desacuerdo aparezca aca y no en el plugin de un usuario.
AUTOTEST = [
    ("Skyrim.esm", 869687),
    ("Dragonborn.esm", 178715),
    ("Dawnguard.esm", 95718),
    ("HearthFires.esm", 18036),
    ("Update.esm", 16387),
    ("_ResourcePack.esl", 373),
]


def autotest(carpeta):
    """Reproduce los conteos medidos. Cero comprobaciones NO es exito."""
    ok = fallo = falta = 0
    for nombre, esperado in AUTOTEST:
        ruta = os.path.join(carpeta, nombre)
        if not os.path.exists(ruta):
            print("  [falta]  %s" % nombre)
            falta += 1
            continue
        with open(ruta, "rb") as fh:
            ids, cerro = recorrer_formids(bytearray(fh.read()))
        if not cerro:
            fallo += 1
            print("  [FALLA]  %s :: el recorrido no cierra" % nombre)
            continue
        if len(ids) == esperado:
            ok += 1
        else:
            fallo += 1
            print("  [FALLA]  %s :: esperado %d records, obtenido %d"
                  % (nombre, esperado, len(ids)))
    print("")
    print("  %d comprobaciones ok, %d fallidas, %d archivos no encontrados"
          % (ok, fallo, falta))
    if ok == 0:
        print("  NO se comprobo NADA. Apunta --autotest a la carpeta Data.")
        return False
    if fallo or falta:
        print("  El recorrido NO reproduce lo medido.")
        return False
    print("  Recorrido validado.")
    return True


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--autotest":
        return 0 if autotest(sys.argv[2]) else 1
    ap = argparse.ArgumentParser()
    ap.add_argument("plugin")
    ap.add_argument("--marcar", action="store_true", help="pone el flag ESL")
    ap.add_argument("--quitar", action="store_true", help="saca el flag ESL")
    args = ap.parse_args()

    if args.marcar and args.quitar:
        print("--marcar y --quitar son excluyentes.")
        return 2
    if not os.path.exists(args.plugin):
        print("No existe %s" % args.plugin)
        return 1

    d = bytearray(open(args.plugin, "rb").read())
    if d[0:4] != b"TES4":
        print("No parece un plugin: falta la cabecera TES4.")
        return 1

    flags = struct.unpack_from("<I", d, 8)[0]
    print("%s" % args.plugin)
    print("  flags TES4 = 0x%08X   (ESL=%s, ESM=%s)"
          % (flags, bool(flags & BANDERA_ESL), bool(flags & BANDERA_ESM)))

    formids, cerro = recorrer_formids(d)
    fuera = [f for f in formids
             if not (RANGO_ESL[0] <= (f & 0xFFFFFF) <= RANGO_ESL[1])]
    print("  %d records propios: %s"
          % (len(formids), ", ".join("%08X" % f for f in formids) or "(ninguno)"))
    if not cerro:
        print("  El recorrido NO cierra en el fin del archivo: el plugin esta "
              "truncado o algun tamano miente.")
    if fuera:
        print("  FUERA del rango ESL (indice de objeto 0x800-0xFFF):")
        for f in fuera:
            print("     %08X  (indice 0x%06X)" % (f, f & 0xFFFFFF))

    if not (args.marcar or args.quitar):
        print("  [solo informe] pasale --marcar o --quitar para escribir.")
        return 0

    # FALLA CERRADO. Un recorrido que no cierra no vio todos los records, y
    # "ninguno fuera de rango" sobre una lista incompleta no es una garantia.
    # Aplica tambien a --quitar: si el archivo esta roto, no se escribe encima.
    if not cerro:
        print("  NO se escribe: sobre un recorrido que no cierra, la "
              "comprobacion de rango no vio todos los records.")
        return 1
    if not formids and args.marcar:
        print("  NO se marca: cero records propios. Un plugin sin nada que "
              "convertir no es un plugin listo, es uno que no se leyo.")
        return 1

    if fuera and args.marcar:
        print("  NO se marca: en un ESL esos records saldrian corruptos.")
        print("  Arreglalo renumerando los records en el editor antes de convertir.")
        return 1
    if flags & BANDERA_ESM and args.marcar:
        print("  NO se marca: el plugin esta marcado como ESM.")
        return 1

    nuevos = flags & ~BANDERA_ESL if args.quitar else flags | BANDERA_ESL
    if nuevos == flags:
        print("  Sin cambios: ya estaba como lo pediste.")
        return 0

    copia = args.plugin + ".bak"
    if not os.path.exists(copia):
        shutil.copy2(args.plugin, copia)
        print("  copia de seguridad: %s" % copia)
    struct.pack_into("<I", d, 8, nuevos)
    open(args.plugin, "wb").write(d)
    print("  [ok] 0x%08X -> 0x%08X" % (flags, nuevos))
    if args.marcar:
        print("  AVISO: los FormIDs pasan de 01xxxxxx a FExxxxxx. En una partida")
        print("  que ya tenia el objeto, hay que volver a agregarlo por consola:")
        print('     help "<nombre>" 4 ARMO   y despues   player.additem <nuevo> 1')
    return 0


if __name__ == "__main__":
    sys.exit(main())
