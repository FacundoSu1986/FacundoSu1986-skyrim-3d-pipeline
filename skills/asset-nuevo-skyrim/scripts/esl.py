# -*- coding: utf-8 -*-
"""Marca (o desmarca) un plugin de Skyrim SE como ESL, comprobando antes si puede.

Skyrim SE carga como mucho 255 plugins normales. Un plugin marcado como ESL no
entra en esa cuenta: va al espacio FE, que tiene 4096 huecos aparte. Para un mod
de dos o tres records, gastar un slot de los 255 es un desperdicio -- y el
usuario que instale tu mod lo va a notar antes que vos.

QUE HACE. Enciende el bit 0x200 en los flags del record TES4 de cabecera (offset
8 del archivo). Nada mas. NO renombra a .esl: un .esp con el flag puesto funciona
igual y asi no hay que retocar el gestor de mods ni el orden de carga.

EL REQUISITO QUE NADIE TE AVISA. Un ESL se carga en el espacio FE:xxx, donde el
indice de objeto tiene 12 bits: **0xFFF es el techo**. Con un record nuevo por
encima el juego NO da error al cargar: lo remapea, y el objeto aparece corrupto
o directamente no aparece. Por eso esto se comprueba ANTES de escribir, y si
falla no toca nada.

DOS COSAS QUE ESTE SCRIPT AFIRMABA Y EL CORPUS REFUTO

1. **El piso de 0x800 no es del motor, es del Creation Kit.** `_ResourcePack.esl`
   --un ESL que Bethesda distribuye y el juego carga-- tiene sus 373 records
   propios con indices de **0x001 a 0xD6A**, y **368 de ellos estan por debajo
   de 0x800**. Exigir 0x800 rechazaba un plugin valido. Ahora el piso se INFORMA
   con su medicion y no bloquea; lo que bloquea es el techo.

2. **Los OVERRIDES no cuentan.** Un record cuyo indice de mod apunta a un master
   no es nuevo: modifica uno del master y conserva su FormID, asi que el rango
   no lo toca. `ccQDRSSE001-SurvivalMode.esl` --otro ESL que el juego carga--
   trae **165** de esos, y la version anterior de este script los reportaba a
   todos como "fuera de rango".

Medido sobre los 3 `.esl` de una instalacion SE: **1.032 records propios, 0 por
encima de 0xFFF**.

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

Exit 0 si esta todo bien, 1 si no se puede leer, no cierra el recorrido, o hay
un record nuevo por encima del techo.
"""

import argparse
import os
import shutil
import struct
import sys

BANDERA_ESL = 0x200
BANDERA_ESM = 0x1
# El techo es del motor: 12 bits de indice de objeto en el espacio FE:xxx.
# Medido: 1.032 records propios de los 3 .esl de una instalacion, 0 por encima.
TECHO_ESL = 0xFFF
# El piso es una convencion del Creation Kit, NO del motor: _ResourcePack.esl
# trae 368 records propios por debajo y el juego lo carga. Se informa, no
# bloquea.
PISO_CREATION_KIT = 0x800


def masters(d):
    """Nombres de los masters, leidos de los MAST del TES4 de cabecera.

    Hace falta para distinguir un record NUEVO de un OVERRIDE: si el indice de
    mod del FormID (el byte alto) es menor que la cantidad de masters, el
    record modifica uno del master y conserva su FormID. El rango de ESL no lo
    toca.
    """
    if d[0:4] != b"TES4":
        return []
    tam, = struct.unpack_from("<I", d, 4)
    fin = 24 + tam
    fuera, i = [], 24
    while i + 6 <= fin:
        tipo = bytes(d[i:i + 4])
        largo, = struct.unpack_from("<H", d, i + 4)
        if tipo == b"MAST":
            fuera.append(bytes(d[i + 6:i + 6 + largo]).rstrip(b"\x00")
                         .decode("cp1252", "replace"))
        i += 6 + largo
    return fuera


def clasificar(formids, n_masters):
    """(nuevos, overrides). Un override tiene indice de mod < n_masters."""
    nuevos = [f for f in formids if (f >> 24) >= n_masters]
    over = [f for f in formids if (f >> 24) < n_masters]
    return nuevos, over


def recorrer_records(d):
    """([(tag, offset)], cerro) de cada record, TES4 incluido.

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

    Devuelve el OFFSET y no solo el FormID porque verificar_plugin.py lee otro
    campo de la misma cabecera (el formVersion, +20). Un solo recorrido para
    los dos: un segundo recorrido escrito aparte es como aparecieron en este
    repo dos parsers de plugins que nadie cruzo.
    """
    recs = []
    i = 0
    while i + 24 <= len(d):
        tag = d[i:i + 4]
        tam = struct.unpack_from("<I", d, i + 4)[0]
        if tag == b"GRUP":
            if tam < 24:
                return recs, False
            i += 24
            continue
        recs.append((bytes(tag), i))
        i += 24 + tam
    return recs, i == len(d)


def recorrer_formids(d):
    """(formids, cerro), sin el TES4. Ver recorrer_records."""
    recs, cerro = recorrer_records(d)
    return ([struct.unpack_from("<I", d, o + 12)[0]
             for tag, o in recs if tag != b"TES4"], cerro)


# Medido contra los 10 plugins de una instalacion SE, cruzando este mismo
# recorrido con el de census/parser_esm.py: los dos dan el MISMO numero en los
# 10, 1.188.811 records en total. La tabla existe para que si alguien toca el
# recorrido, el desacuerdo aparezca aca y no en el plugin de un usuario.
AUTOTEST = [
    ("Skyrim.esm", {"records": 869687}),
    ("Dragonborn.esm", {"records": 178715}),
    ("Dawnguard.esm", {"records": 95718}),
    ("HearthFires.esm", {"records": 18036}),
    ("Update.esm", {"records": 16387}),
    # Los tres .esl de la instalacion: son ESL que el juego CARGA, asi que
    # cualquier cosa que este script rechace en ellos esta rechazando de mas.
    # Ninguno tiene un record propio por encima del techo -- 1.032 en total.
    ("_ResourcePack.esl",
     {"records": 373, "masters": 3, "nuevos": 373, "overrides": 0,
      "sobre_el_techo": 0, "bajo_el_piso_del_ck": 368}),
    ("ccBGSSSE037-Curios.esl",
     {"records": 151, "masters": 5, "nuevos": 151, "overrides": 0,
      "sobre_el_techo": 0, "bajo_el_piso_del_ck": 0}),
    ("ccQDRSSE001-SurvivalMode.esl",
     {"records": 673, "masters": 5, "nuevos": 508, "overrides": 165,
      "sobre_el_techo": 0, "bajo_el_piso_del_ck": 0}),
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
        try:
            with open(ruta, "rb") as fh:
                d = bytearray(fh.read())
            ids, cerro = recorrer_formids(d)
        except Exception as e:
            fallo += 1
            print("  [ilegible] %s :: %s" % (nombre, type(e).__name__))
            continue
        if not cerro:
            fallo += 1
            print("  [FALLA]  %s :: el recorrido no cierra" % nombre)
            continue
        mast = masters(d)
        nuevos, over = clasificar(ids, len(mast))
        real = {"records": len(ids), "masters": len(mast),
                "nuevos": len(nuevos), "overrides": len(over),
                "sobre_el_techo": sum(1 for f in nuevos
                                      if (f & 0xFFFFFF) > TECHO_ESL),
                "bajo_el_piso_del_ck": sum(1 for f in nuevos
                                           if (f & 0xFFFFFF)
                                           < PISO_CREATION_KIT)}
        for campo, valor in esperado.items():
            if campo not in real:
                fallo += 1
                print("  [FALLA]  %s :: campo desconocido %r"
                      % (nombre, campo))
                continue
            if real[campo] == valor:
                ok += 1
            else:
                fallo += 1
                print("  [FALLA]  %s :: %s esperado %d, obtenido %d"
                      % (nombre, campo, valor, real[campo]))
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

    try:
        with open(args.plugin, "rb") as fh:
            d = bytearray(fh.read())
    except OSError as e:
        print("No se pudo leer %s: %s" % (args.plugin, e))
        return 1
    # 24 bytes es la cabecera de un record. Menos que eso no alcanza ni para
    # leer los flags, y salia por un struct.error crudo.
    if len(d) < 24 or d[0:4] != b"TES4":
        print("No parece un plugin: hacen falta 24 bytes de cabecera TES4 y "
              "hay %d." % len(d))
        return 1

    flags = struct.unpack_from("<I", d, 8)[0]
    print("%s" % args.plugin)
    print("  flags TES4 = 0x%08X   (ESL=%s, ESM=%s)"
          % (flags, bool(flags & BANDERA_ESL), bool(flags & BANDERA_ESM)))

    formids, cerro = recorrer_formids(d)
    n_mast = len(masters(d))
    nuevos, overrides = clasificar(formids, n_mast)
    fuera = [f for f in nuevos if (f & 0xFFFFFF) > TECHO_ESL]
    bajos = [f for f in nuevos if (f & 0xFFFFFF) < PISO_CREATION_KIT]
    print("  %d record(s) no-TES4: %d nuevo(s) y %d override(s) de los %d "
          "master(s)" % (len(formids), len(nuevos), len(overrides), n_mast))
    print("  nuevos: %s"
          % (", ".join("%08X" % f for f in nuevos[:12]) or "(ninguno)"))
    if not cerro:
        print("  El recorrido NO cierra en el fin del archivo: el plugin esta "
              "truncado o algun tamano miente.")
    if bajos:
        print("  %d nuevo(s) con indice por debajo de 0x%03X. Eso es la "
              "convencion del Creation Kit, NO un requisito del motor: "
              "_ResourcePack.esl trae 368 asi y el juego lo carga. Se informa."
              % (len(bajos), PISO_CREATION_KIT))
    if fuera:
        print("  POR ENCIMA del techo de ESL (indice de objeto > 0x%03X):"
              % TECHO_ESL)
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
        print("  NO se marca: cero records. Un plugin sin nada que convertir "
              "no es un plugin listo, es uno que no se leyo.")
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
