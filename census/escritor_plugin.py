# -*- coding: utf-8 -*-
"""Escribe plugins de Bethesda. Pensado para ESL.

    python escritor_plugin.py --autotest

POR QUE ESL Y NO ESP
--------------------
Un ESP ocupa uno de los 255 slots del orden de carga. Un ESL no: el juego los
mete a todos en el indice FE, hasta 4096. Para un mod de un solo item, gastar
un slot es caro.

A cambio, el ESL impone una restriccion REAL sobre los FormID: la parte de
objeto tiene que entrar en 12 bits (0x000..0xFFF), porque los otros 12 se usan
para numerar el propio ESL dentro del FE. Eso NO es una convencion: si un
record se pasa, el juego no puede direccionarlo. El escritor lo exige.

LO QUE ESTA VERIFICADO Y LO QUE NO
----------------------------------
Verificado contra el corpus: la estructura entera. El recorrido de records,
grupos y subrecords cae exacto en el fin del archivo en los 6 plugins de la
instalacion -- 1.176.548 records y 136.361 grupos, incluido Skyrim.esm con
869.688 records en 250 MB. Un tamano mal interpretado desalinea el recorrido y
no termina donde termina el archivo.

NO verificado: el bit 0x200 de la bandera ESL. En esta instalacion no hay
ningun .esl para medir, asi que ese numero sale de la documentacion de Bethesda
y no del corpus. Lo que si se puede comprobar, y en un minuto: cargar el plugin
y mirar si el juego le da un FormID que empieza con FE.
"""
import os
import struct
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

import parser_plugin  # noqa: E402

BANDERA_ESM = parser_plugin.BANDERA_ESM
BANDERA_ESL = parser_plugin.BANDERA_ESL

CABECERA = parser_plugin.CABECERA_RECORD    # records y GRUP miden lo mismo
MAX_OBJETO_ESL = 0xFFF


class ErrorPlugin(Exception):
    pass


def sub(tipo, datos):
    """Un subrecord: 4 de tipo + 2 de tamano + datos."""
    if isinstance(tipo, str):
        tipo = tipo.encode("ascii")
    if len(tipo) != 4:
        raise ErrorPlugin("tipo de subrecord de %d caracteres: %r" % (len(tipo), tipo))
    if len(datos) > 0xFFFF:
        raise ErrorPlugin("subrecord %s de %d bytes: no entra en un u16"
                          % (tipo, len(datos)))
    return tipo + struct.pack("<H", len(datos)) + datos


def zstr(texto):
    """Cadena terminada en cero, como las guarda el formato."""
    return texto.encode("cp1252") + b"\x00"


def record(tipo, form_id, subrecords, banderas=0, version=44):
    """Un record: 24 bytes de encabezado + los datos.

    El dataSize del encabezado NO se cuenta a si mismo ni al encabezado, que es
    lo contrario de como lo hace un GRUP. Las dos convenciones conviven en el
    mismo archivo y confundirlas desalinea todo lo que sigue.
    """
    if isinstance(tipo, str):
        tipo = tipo.encode("ascii")
    datos = b"".join(subrecords)
    return (tipo + struct.pack("<IIIHHHH", len(datos), banderas, form_id,
                               0, 0, version, 0) + datos)


def grupo(etiqueta, records, tipo_grupo=0):
    """Un grupo de nivel superior. groupSize SI incluye sus 24 bytes."""
    if isinstance(etiqueta, str):
        etiqueta = etiqueta.encode("ascii")
    cuerpo = b"".join(records)
    return (b"GRUP" + struct.pack("<I", len(cuerpo) + 24) + etiqueta
            + struct.pack("<iHHHH", tipo_grupo, 0, 0, 0, 0) + cuerpo)


def tes4(maestros, n_bloques, siguiente_id, autor="", esl=True, descripcion=""):
    """`n_bloques` es lo que pide HEDR: records + grupos, sin el TES4.

    Medido en los 5 masters del corpus: HEDR.numRecords == bloques totales - 1
    (TES4) exacto en los cinco. No es la cantidad de FormID nuevos.
    """
    subs = [sub("HEDR", struct.pack("<fiI", 1.71, n_bloques, siguiente_id))]
    if autor:
        subs.append(sub("CNAM", zstr(autor)))
    if descripcion:
        subs.append(sub("SNAM", zstr(descripcion)))
    for m in maestros:
        subs.append(sub("MAST", zstr(m)))
        subs.append(sub("DATA", struct.pack("<Q", 0)))
    subs.append(sub("INTV", struct.pack("<I", 1)))
    banderas = BANDERA_ESL if esl else 0
    return record("TES4", 0, subs, banderas=banderas)


def comprobar_esl(form_ids):
    """La restriccion dura del ESL: la parte de objeto en 12 bits."""
    malos = [f for f in form_ids if (f & 0x00FFFFFF) > MAX_OBJETO_ESL]
    if malos:
        raise ErrorPlugin(
            "estos FormID no entran en un ESL (parte de objeto > 0xFFF): %s"
            % ", ".join("0x%08X" % f for f in malos))


def contar_bloques(serializados):
    """records + grupos de una secuencia de bloques serializados, sin TES4.

    Recorre los encabezados con el mismo contrato que exige el parser: si
    `serializados` no embaldosa, la escritura esta mal armada y se rechaza
    antes de producir un archivo. El total es el campo HEDR (ver `tes4()`).
    """
    total = 0
    for bloque in serializados:
        p = 0
        n = len(bloque)
        while p < n:
            if n - p < CABECERA:
                raise ErrorPlugin(
                    "bloque en %d: cola de %d bytes, no entra un encabezado"
                    % (p, n - p))
            tam, = struct.unpack_from("<I", bloque, p + 4)
            if bloque[p:p + 4] == b"GRUP":
                if tam < CABECERA or p + tam > n:
                    raise ErrorPlugin(
                        "GRUP en %d con tamano %d no entra en %d bytes"
                        % (p, tam, n))
                sub = bloque[p + CABECERA:p + tam]
                total += 1 + (contar_bloques([sub]) if sub else 0)
                p += tam
            else:
                if p + CABECERA + tam > n:
                    raise ErrorPlugin(
                        "record en %d declara %d bytes y no entra en %d"
                        % (p, tam, n))
                total += 1
                p += CABECERA + tam
    return total


def escribir(ruta, maestros, grupos, form_ids_nuevos, autor="", esl=True,
             descripcion=""):
    """Arma el archivo entero. `grupos` ya vienen serializados."""
    if esl:
        comprobar_esl(form_ids_nuevos)
    siguiente = (max(f & 0x00FFFFFF for f in form_ids_nuevos) + 1
                 if form_ids_nuevos else 0x800)
    n_bloques = contar_bloques(grupos)
    cabecera = tes4(maestros, n_bloques, siguiente, autor, esl, descripcion)
    with open(ruta, "wb") as fh:
        fh.write(cabecera)
        for g in grupos:
            fh.write(g)
    return ruta


# --- autotest ----------------------------------------------------------------

def autotest():
    """Escribe y relee con parser_plugin. Cero casos NO es exito."""
    import tempfile
    print("SUITE DE FALSIFICACION - escritor_plugin")
    print("")
    tmp = tempfile.mkdtemp()
    fallos = n = 0

    print("  a. lo escrito se recorre entero y cae en el fin del archivo")
    r1 = record("ARMO", 0x01000800, [sub("EDID", zstr("PruebaArmo")),
                                     sub("FULL", zstr("Prueba")),
                                     sub("DATA", struct.pack("<If", 100, 5.0))])
    r2 = record("ARMA", 0x01000801, [sub("EDID", zstr("PruebaArma")),
                                     sub("RNAM", struct.pack("<I", 0x19))])
    ruta = escribir(os.path.join(tmp, "prueba.esl"), ["Skyrim.esm"],
                    [grupo("ARMO", [r1]), grupo("ARMA", [r2])],
                    [0x01000800, 0x01000801], autor="prueba")
    try:
        p = parser_plugin.Plugin(ruta)
        ok = True
    except Exception as e:
        p, ok = None, False
        print("     no se pudo releer: %s" % e)
    n += 1
    fallos += 0 if ok else 1
    if p:
        print("     %d bytes, %d records, %d grupos  ok"
              % (len(p.d), len(p.records), len(p.grupos)))

    print("")
    print("  b. los campos vuelven como se escribieron")
    if p:
        tipos = p.cuenta_tipos()
        bien = (tipos.get("TES4") == 1 and tipos.get("ARMO") == 1
                and tipos.get("ARMA") == 1
                and p.maestros() == ["Skyrim.esm"] and p.es_esl)
        n += 1
        fallos += 0 if bien else 1
        print("     tipos=%s maestros=%s esl=%s  %s"
              % (tipos, p.maestros(), p.es_esl, "ok" if bien else "FALLA"))

        edid = None
        for tipo, off, _t, _f in p.records:
            if tipo == "ARMO":
                for st, so, sn in p.subrecords(off):
                    if st == "EDID":
                        edid = p.d[so:so + sn].rstrip(b"\x00").decode("cp1252")
        n += 1
        fallos += 0 if edid == "PruebaArmo" else 1
        print("     EDID del ARMO = %r  %s"
              % (edid, "ok" if edid == "PruebaArmo" else "FALLA"))

    print("")
    print("  c. un FormID fuera del rango ESL se rechaza")
    try:
        comprobar_esl([0x01001000])       # 0x1000 > 0xFFF
        rechazo = False
    except ErrorPlugin:
        rechazo = True
    n += 1
    fallos += 0 if rechazo else 1
    print("     0x01001000 rechazado: %s  %s" % (rechazo, "ok" if rechazo else "FALLA"))

    try:
        comprobar_esl([0x01000FFF])       # el limite exacto, tiene que pasar
        limite = True
    except ErrorPlugin:
        limite = False
    n += 1
    fallos += 0 if limite else 1
    print("     0x01000FFF aceptado: %s  %s" % (limite, "ok" if limite else "FALLA"))

    print("")
    print("  d. un subrecord que no entra en un u16 se rechaza")
    try:
        sub("EDID", b"x" * 70000)
        rechazo2 = False
    except ErrorPlugin:
        rechazo2 = True
    n += 1
    fallos += 0 if rechazo2 else 1
    print("     70.000 bytes rechazados: %s  %s"
          % (rechazo2, "ok" if rechazo2 else "FALLA"))

    print("")
    if n == 0:
        print("  NO se comprobo NADA.")
        return False
    if fallos:
        print("  %d FALLAS de %d. El escritor NO esta validado." % (fallos, n))
        return False
    print("  %d comprobaciones, sin fallas." % n)
    return True


def main():
    a = sys.argv[1:]
    if not a or a[0] != "--autotest":
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(0 if autotest() else 1)


if __name__ == "__main__":
    main()
