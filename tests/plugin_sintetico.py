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
DNAM_STAT = (0.0, 0)          # dos campos de 4 bytes


def _cstr(texto):
    return texto.encode("cp1252") + b"\x00"


def _sub(tipo, datos):
    """Subrecord: 4 de tipo, 2 de tamano, datos."""
    if len(datos) > 0xFFFF:
        raise ValueError("para eso hace falta el escape XXXX")
    return tipo + struct.pack("<H", len(datos)) + datos


def _record(tipo, datos, form_id, flags=0, comprimir=False):
    """Record: 4 tipo, 4 tam_datos, 4 flags, 4 formID, 4 control, 2+2 version."""
    if comprimir:
        flags |= 0x00040000
        datos = struct.pack("<I", len(datos)) + zlib.compress(datos)
    return (tipo + struct.pack("<I", len(datos)) + struct.pack("<I", flags)
            + struct.pack("<I", form_id) + struct.pack("<I", 0)
            + struct.pack("<HH", 44, 0) + datos)


def _grupo(etiqueta, contenido, tipo_grupo=0):
    """GRUP: el tamano INCLUYE la cabecera. Es la parte del formato que se
    determino por falsificacion -- la otra lectura no cierra el archivo."""
    return (b"GRUP" + struct.pack("<I", CABECERA + len(contenido))
            + etiqueta + struct.pack("<i", tipo_grupo)
            + struct.pack("<I", 0) + struct.pack("<I", 0) + contenido)


def construir(comprimir_stat=False, con_escape=False, masters=()):
    """Devuelve (bytes, esperado).

    `esperado` es la verdad declarada: lo que cualquier parser correcto tiene
    que recuperar de esos bytes.
    """
    stat = _sub(b"EDID", _cstr(EDID_STAT))
    stat += _sub(b"OBND", struct.pack("<6h", *OBND_STAT))
    stat += _sub(b"MODL", _cstr(MODL_STAT))
    stat += _sub(b"DNAM", struct.pack("<fI", *DNAM_STAT))
    subs_stat = ["EDID", "OBND", "MODL", "DNAM"]

    if con_escape:
        # Un subrecord mas grande de lo que entra en un uint16: el tamano real
        # va en un XXXX previo. Se prueba que el parser lo maneje, no se asume
        # que Bethesda lo use.
        grande = b"\x00" * 70000
        stat += _sub(b"XXXX", struct.pack("<I", len(grande)))
        stat += b"MNAM" + struct.pack("<H", 0) + grande
        subs_stat.append("MNAM")

    r_stat = _record(b"STAT", stat, 0x00000801, comprimir=comprimir_stat)

    otro = _sub(b"EDID", _cstr("PruebaActivador"))
    r_acti = _record(b"ACTI", otro, 0x00000802)

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
    tes4 = _record(b"TES4", cab, 0)

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
