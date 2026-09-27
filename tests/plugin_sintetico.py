# -*- coding: utf-8 -*-
"""Un plugin de Bethesda construido byte a byte, con su verdad declarada.

Cero contenido de Bethesda: los bytes se generan. Misma tecnica que
nif_sintetico.py y que el fixture DDS -- lo que se versiona es el generador, no
un archivo del juego.

El fixture existe para que la suite pueda comprobar el parser sin la carpeta
Data instalada. El autotest sobre los plugins reales prueba otra cosa: que el
layout reproduce 1,3 millones de records. Los dos hacen falta, y ninguno
reemplaza al otro.
"""
import struct
import zlib

CABECERA = 24

AUTOR = "prueba"
DESCRIPCION = "plugin sintetico"
EDID_STAT = "PruebaEstaticoDePrueba"
MODL_STAT = r"Prueba\Estatico01.nif"
OBND_STAT = (-10, -20, -30, 10, 20, 30)
# Angulo, material y, desde la version 44, 4 bytes de bandera: los 711 STAT
# de 44 de los 10 plugins miden 12. Median 8 aca, con 44, y la REGLA 8 de
# verificar_plugin.py lo reprobo con razon: es el layout de antes de la 44.
DNAM_STAT = (0.0, 0, 1)

# El MODT de un record de version < 40: triples de 12 bytes (hash del archivo,
# extension, hash de la carpeta), sin encabezado. La extension es "dds": leida
# como u32 da 7.562.340, la cantidad de texturas que el motor leyo en el ESL de
# la issue #31 cuando el record decia 44. Los hashes son inventados.
MODT_TRIPLES = (struct.pack("<I4sI", 0x0BADF00D, b"dds\x00", 0x00C0FFEE)
                + struct.pack("<I4sI", 0x0DEADBEE, b"dds\x00", 0x00C0FFEE))


def _cstr(texto):
    return texto.encode("cp1252") + b"\x00"


def _sub(tipo, datos):
    """Subrecord: 4 de tipo, 2 de tamano, datos."""
    if len(datos) > 0xFFFF:
        raise ValueError("para eso hace falta el escape XXXX")
    return tipo + struct.pack("<H", len(datos)) + datos


def _record(tipo, datos, form_id, flags=0, comprimir=False, version=44):
    """Record: 4 tipo, 4 tam_datos, 4 flags, 4 formID, 4 control, 2+2 version.

    `version` es el formVersion (bytes 20-21). Se puede torcer para fabricar
    el defecto que tuvo el hacha: 0 en todos los records.
    """
    if comprimir:
        flags |= 0x00040000
        datos = struct.pack("<I", len(datos)) + zlib.compress(datos)
    return (tipo + struct.pack("<I", len(datos)) + struct.pack("<I", flags)
            + struct.pack("<I", form_id) + struct.pack("<I", 0)
            + struct.pack("<HH", version, 0) + datos)


def _grupo(etiqueta, contenido, tipo_grupo=0):
    """GRUP: el tamano INCLUYE la cabecera. Es la parte del formato que se
    determino por falsificacion -- la otra lectura no cierra el archivo."""
    return (b"GRUP" + struct.pack("<I", CABECERA + len(contenido))
            + etiqueta + struct.pack("<i", tipo_grupo)
            + struct.pack("<I", 0) + struct.pack("<I", 0) + contenido)


def construir(comprimir_stat=False, con_escape=False, masters=(), version=44):
    """Devuelve (bytes, esperado).

    `version` va a TODOS los records, TES4 incluido: así salió el hacha.

    `esperado` es la verdad declarada: lo que cualquier parser correcto tiene
    que recuperar de esos bytes.
    """
    stat = _sub(b"EDID", _cstr(EDID_STAT))
    stat += _sub(b"OBND", struct.pack("<6h", *OBND_STAT))
    stat += _sub(b"MODL", _cstr(MODL_STAT))
    stat += _sub(b"DNAM", struct.pack("<fII", *DNAM_STAT))
    subs_stat = ["EDID", "OBND", "MODL", "DNAM"]

    if con_escape:
        # Un subrecord mas grande de lo que entra en un uint16: el tamano real
        # va en un XXXX previo. Se prueba que el parser lo maneje, no se asume
        # que Bethesda lo use.
        grande = b"\x00" * 70000
        stat += _sub(b"XXXX", struct.pack("<I", len(grande)))
        stat += b"MNAM" + struct.pack("<H", 0) + grande
        subs_stat.append("MNAM")

    r_stat = _record(b"STAT", stat, 0x00000801, comprimir=comprimir_stat,
                     version=version)

    otro = _sub(b"EDID", _cstr("PruebaActivador"))
    r_acti = _record(b"ACTI", otro, 0x00000802, version=version)

    cuerpo = _grupo(b"STAT", r_stat) + _grupo(b"ACTI", r_acti)

    cab = _sub(b"HEDR", struct.pack("<fiI", 1.7, 2, 0x00000803))
    cab += _sub(b"CNAM", _cstr(AUTOR))
    cab += _sub(b"SNAM", _cstr(DESCRIPCION))
    # Cada master va como MAST + DATA, en ese orden, como en los plugins
    # reales. La cantidad de MAST es lo que separa un record NUEVO de un
    # OVERRIDE: si el indice de mod del FormID es menor, el record modifica
    # uno del master y conserva su FormID.
    for m in masters:
        cab += _sub(b"MAST", _cstr(m))
        cab += _sub(b"DATA", struct.pack("<Q", 0))
    tes4 = _record(b"TES4", cab, 0, version=version)

    datos = tes4 + cuerpo
    esperado = {
        "bytes": len(datos),
        "tipos": {"TES4": 1, "GRUP": 2, "STAT": 1, "ACTI": 1},
        "bloques": 5,
        "stat": {
            "form_id": 0x00000801,
            "subrecords": subs_stat,
            "edid": EDID_STAT,
            "modl": MODL_STAT,
            "obnd": OBND_STAT,
        },
        "autor": AUTOR,
        "masters": list(masters),
    }
    return datos, esperado


def construir_weap(data_len=10, dnam_len=100, wnam="propio", comprimir=False,
                   con_escape=False, masters=("Skyrim.esm",), basura=0, anim=6,
                   modl=r"Weapons\Prueba\arma.nif", version=44, modt=None):
    """Un plugin con un WEAP y el STAT de su primera persona.

    `version` va a los tres records, como en construir(): con 0 es el hacha.
    `modt` son los bytes del MODT del WEAP (None: sin MODT). El hacha del
    20/9 llevaba (2, 0, 0) -- el encabezado de la 44, sin texturas -- con 0.

    Lo que mide el corpus (census/hallazgos_plugins.md): DATA de 10 bytes y
    DNAM de 100 en las 3.359 WEAP vanilla; el WNAM de las 463 que lo tienen
    apunta a un STAT.

    `wnam`: "propio" -> el STAT de este plugin; "roto" -> un FormID propio que
    no existe; "a_si_mismo" -> el propio WEAP; "master" -> un FormID de un
    master (no verificable sin el master); None -> sin WNAM.

    `anim` va en DNAM[0], el tipo de animacion (6 = hacha de dos manos).
    `modl` es la ruta del NIF, relativa a meshes/ y sin ese prefijo.

    `basura`: bytes sueltos al final del WEAP, dentro del tamano declarado del
    record: los subrecords dejan de embaldosarlo.
    """
    n = len(masters)
    fid_weap = (n << 24) | 0x800
    fid_stat = (n << 24) | 0x801
    destino = {"propio": fid_stat, "roto": (n << 24) | 0xABC,
               "a_si_mismo": fid_weap, "master": 0x00012345, None: None}[wnam]

    stat = _sub(b"EDID", _cstr("PruebaArma1aPersona"))
    stat += _sub(b"MODL", _cstr(r"Weapons\Prueba\arma.nif"))
    r_stat = _record(b"STAT", stat, fid_stat, version=version)

    w = _sub(b"EDID", _cstr("PruebaArma"))
    w += _sub(b"MODL", _cstr(modl))
    if modt is not None:
        w += _sub(b"MODT", modt)
    if con_escape:
        grande = b"\x00" * 70000
        w += _sub(b"XXXX", struct.pack("<I", len(grande)))
        w += b"DESC" + struct.pack("<H", 0) + grande
    if destino is not None:
        w += _sub(b"WNAM", struct.pack("<I", destino))
    w += _sub(b"DATA", (struct.pack("<IfH", 2750, 27.0, 26)
                        + b"\x00" * max(0, data_len - 10))[:data_len])
    w += _sub(b"DNAM", bytes([anim]) + b"\x00" * (dnam_len - 1))
    w += b"\xAA" * basura
    r_weap = _record(b"WEAP", w, fid_weap, comprimir=comprimir,
                     version=version)

    cuerpo = _grupo(b"STAT", r_stat) + _grupo(b"WEAP", r_weap)
    cab = _sub(b"HEDR", struct.pack("<fiI", 1.71, 4, (n << 24) | 0x802))
    for m in masters:
        cab += _sub(b"MAST", _cstr(m))
        cab += _sub(b"DATA", struct.pack("<Q", 0))
    datos = _record(b"TES4", cab, 0, version=version) + cuerpo
    return datos, {"fid_weap": fid_weap, "fid_stat": fid_stat,
                   "wnam": destino}


def construir_mundo(banderas_ref=0x400, grupo_ref=8, ofst=None, rnam=0,
                    full=b"Carrera Blanca\x00", localizado=False):
    """Un override de WhiterunWorld con su celda persistente y un REFR, con
    la anidacion de grupos de un plugin real:

        GRUP WRLD (0) > WRLD 0001A26F
                      > GRUP World Children (1) > CELL 0001A270
                        > GRUP Cell Children (6) > GRUP `grupo_ref` > REFR

    Con los valores por defecto es el v1.2 de RetreteVIP. El v1.1 es
    `banderas_ref=0, ofst=[57966, 393059], rnam=40, full=b" L\x00\x00"`.
    `ofst` son las entradas del OFST (None: sin OFST)."""
    wrld = _sub(b"EDID", _cstr("WhiterunWorld"))
    if full is not None:
        wrld += _sub(b"FULL", full)
    for i in range(rnam):
        wrld += _sub(b"RNAM", struct.pack("<hhI", 0, i, 0))
    if ofst is not None:
        wrld += _sub(b"OFST", struct.pack("<%dI" % len(ofst), *ofst))
    celda = _record(b"CELL", _sub(b"DATA", struct.pack("<H", 2)),
                    0x0001A270, flags=0x400)
    ref = _record(b"REFR", _sub(b"NAME", struct.pack("<I", 0x01000800))
                  + _sub(b"DATA", struct.pack("<6f", 0, 0, 0, 0, 0, 0)),
                  0x01000801, flags=banderas_ref)
    etiqueta_celda = struct.pack("<I", 0x0001A270)
    hijos = _grupo(etiqueta_celda, ref, grupo_ref)
    celda += _grupo(etiqueta_celda, hijos, 6)
    mundo = _record(b"WRLD", wrld, 0x0001A26F)
    mundo += _grupo(struct.pack("<I", 0x0001A26F), celda, 1)
    stat = _record(b"STAT", _sub(b"EDID", _cstr("Retrete")), 0x01000800)
    cuerpo = _grupo(b"STAT", stat) + _grupo(b"WRLD", mundo)
    cab = _sub(b"HEDR", struct.pack("<fiI", 1.71, 8, 0x01000802))
    cab += _sub(b"MAST", _cstr("Skyrim.esm"))
    cab += _sub(b"DATA", struct.pack("<Q", 0))
    return _record(b"TES4", cab, 0, flags=0x80 if localizado else 0) + cuerpo


def modt_con_encabezado(triples=MODT_TRIPLES, extra=()):
    """El MODT de un record de version >= 40: tres u32 (2, n, m), los n
    triples y m u32 mas. (2, n, 0) con los mismos triples es como Update.esm y
    los DLC pasaron a 44 los records 39 de Skyrim.esm (trampa 26 de
    asset-nuevo-skyrim)."""
    return (struct.pack("<III", 2, len(triples) // 12, len(extra)) + triples
            + b"".join(struct.pack("<I", x) for x in extra))


def record_estatico(form_id, version=39, cabecera=None, modt="auto",
                    dnam="auto", sub_modelo=b"MODT", tipo=b"STAT",
                    comprimir=False):
    """Un record con los subrecords de un STAT vanilla -- EDID, OBND, MODL, el
    de hashes y DNAM --, copiado con el layout de `version`.

    `cabecera` es la version que se escribe en el record; por defecto, la
    misma. El v1 del mod de la #31, el que cerraba el juego, es `version=39,
    cabecera=44`: los bytes de un 39 con 44. El v2 es `version=39`.
    `modt="auto"` da triples antes de la 40 y (2, n, 0) desde la 40; None, sin
    subrecord de hashes. `dnam="auto"` da 8 bytes antes de la 44 y 12 desde la
    44; None, sin DNAM. `sub_modelo` es el subrecord de hashes: MODT, MO2T a
    MO5T o DMDT. Con otro `tipo` (un ACTI) el DNAM ya no es el de un STAT."""
    if modt == "auto":
        modt = MODT_TRIPLES if version < 40 else modt_con_encabezado()
    if dnam == "auto":
        dnam = struct.pack("<fII", *DNAM_STAT)[:12 if version >= 44 else 8]
    subs = _sub(b"EDID", _cstr("PruebaCopia%X" % form_id))
    subs += _sub(b"OBND", struct.pack("<6h", *OBND_STAT))
    subs += _sub(b"MODL", _cstr(MODL_STAT))
    if modt is not None:
        subs += _sub(sub_modelo, modt)
    if dnam is not None:
        subs += _sub(b"DNAM", dnam)
    return _record(tipo, subs, form_id, comprimir=comprimir,
                   version=version if cabecera is None else cabecera)


def construir_estaticos(records, masters=("Skyrim.esm",)):
    """Un ESL con `records`, [(tipo, bytes de record_estatico)]: un GRUP por
    tipo, en el orden en que aparece cada uno."""
    orden, por_tipo = [], {}
    for tipo, r in records:
        if tipo not in por_tipo:
            orden.append(tipo)
            por_tipo[tipo] = b""
        por_tipo[tipo] += r
    cuerpo = b"".join(_grupo(t, por_tipo[t]) for t in orden)
    n = len(masters)
    cab = _sub(b"HEDR", struct.pack("<fiI", 1.71, len(records) + len(orden),
                                    (n << 24) | (0x800 + len(records))))
    for m in masters:
        cab += _sub(b"MAST", _cstr(m))
        cab += _sub(b"DATA", struct.pack("<Q", 0))
    return _record(b"TES4", cab, 0, flags=0x200) + cuerpo


def construir_estatico(**kw):
    """Un ESL con un solo `record_estatico`, el 01000800: propio, con
    Skyrim.esm de master."""
    return construir_estaticos([(kw.get("tipo", b"STAT"),
                                 record_estatico(0x01000800, **kw))])
