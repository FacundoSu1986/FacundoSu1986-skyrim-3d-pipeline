# -*- coding: utf-8 -*-
"""Lector de plugins de Bethesda (.esm/.esp/.esl), validado por identidad.

    python parser_esm.py --autotest <carpeta Data>
    python parser_esm.py <archivo.esm> [tipo]

POR QUE EXISTE
--------------
Un .nif en el disco no es un mod. Para que el juego vea un asset hace falta un
record que lo referencie, y el repo no sabia leer ni uno. Este parser es el
primer paso: leer 1,3 millones de records vanilla antes de escribir el primero.

COMO SE DETERMINO EL FORMATO
----------------------------
Midiendo, no leyendo una especificacion. Dos preguntas, dos falsificaciones:

  cabecera de 24 bytes  -> el bloque siguiente al TES4 es "GRUP"
  cabecera de 20 bytes  -> basura

  el tamano de un GRUP INCLUYE su cabecera -> el recorrido cierra EXACTO en los
                                              249.753.412 bytes de Skyrim.esm
  no la incluye                            -> muere en +9.743.809

LA IDENTIDAD QUE LO SOSTIENE TODO
---------------------------------
Los bloques tienen que EMBALDOSAR el archivo: sin huecos y sin solapes, y la
suma tiene que caer exactamente en el fin. Lo mismo dentro de cada GRUP y lo
mismo con los subrecords dentro de un record. Si el layout estuviera mal, el
recorrido se sale del archivo en el primer bloque torcido -- es la misma
identidad `cursor == offset + size` que valida el parser de NIF y el de DDS.

Medido sobre los 10 plugins de una instalacion SE: 1.328.055 records, 121 tipos,
0 violaciones.
"""
import collections
import os
import struct
import sys
import zlib

CABECERA = 24
SUB_CABECERA = 6

# Banderas del record. Solo se usa la de compresion; el resto no se toca
# porque no se midio que significan.
COMPRIMIDO = 0x00040000

# Subrecord de escape para datos que no entran en un uint16. Se detecta, no se
# asume: si aparece, el tamano real viene en el XXXX previo.
ESCAPE_TAMANO = b"XXXX"


class PluginInvalido(Exception):
    pass


class Plugin(object):
    """Un plugin recorrido a nivel de record. Los datos se leen bajo demanda."""

    def __init__(self, ruta):
        self.ruta = ruta
        with open(ruta, "rb") as fh:
            self.d = fh.read()
        if self.d[:4] != b"TES4":
            raise PluginInvalido("no empieza con TES4: %r" % self.d[:4])
        if len(self.d) < CABECERA:
            raise PluginInvalido("mas corto que una cabecera")
        tam0, = struct.unpack_from("<I", self.d, 4)
        self.inicio_datos = CABECERA + tam0
        if self.inicio_datos > len(self.d):
            raise PluginInvalido(
                "el TES4 declara %d bytes y el archivo tiene %d" % (tam0, len(self.d)))
        self._indice = None

    # --- recorrido ----------------------------------------------------------

    def recorrer(self, ini=None, fin=None):
        """Genera (tipo, offset, tam_datos, profundidad) por cada record.

        Lanza PluginInvalido si el recorrido no embaldosa exactamente el rango:
        esa es toda la validacion del layout, y tiene que poder fallar.
        """
        if ini is None:
            # El TES4 de cabecera tambien es un record y cuenta. Dejarlo afuera
            # daba conteos uno mas bajos y un tipo menos.
            tam0, = struct.unpack_from("<I", self.d, 4)
            yield ("TES4", 0, tam0, 0)
        ini = self.inicio_datos if ini is None else ini
        fin = len(self.d) if fin is None else fin
        for x in self._recorrer(ini, fin, 0):
            yield x

    def _recorrer(self, ini, fin, prof):
        d = self.d
        p = ini
        while p + CABECERA <= fin:
            tipo = d[p:p + 4]
            tam, = struct.unpack_from("<I", d, p + 4)
            if tipo == b"GRUP":
                # El tamano de un GRUP incluye sus 24 bytes de cabecera. Medido:
                # la otra lectura no llega al final del archivo.
                if tam < CABECERA or p + tam > fin:
                    raise PluginInvalido(
                        "GRUP tam=%d en +%d no entra en [%d,%d)" % (tam, p, ini, fin))
                yield ("GRUP", p, tam - CABECERA, prof)
                for x in self._recorrer(p + CABECERA, p + tam, prof + 1):
                    yield x
                p += tam
                continue
            if p + CABECERA + tam > fin:
                raise PluginInvalido(
                    "%r tam=%d en +%d se pasa de %d" % (tipo, tam, p, fin))
            yield (tipo.decode("ascii", "replace"), p, tam, prof)
            p += CABECERA + tam
        if p != fin:
            raise PluginInvalido(
                "nivel %d: el recorrido termina en %d y no en %d (sobran %d bytes)"
                % (prof, p, fin, fin - p))

    # --- lectura de un record ------------------------------------------------

    def datos(self, offset):
        """Los bytes del record, descomprimidos si hace falta."""
        tam, = struct.unpack_from("<I", self.d, offset + 4)
        flags, = struct.unpack_from("<I", self.d, offset + 8)
        crudo = self.d[offset + CABECERA:offset + CABECERA + tam]
        if flags & COMPRIMIDO:
            if len(crudo) < 4:
                raise PluginInvalido("record comprimido sin tamano en +%d" % offset)
            esperado, = struct.unpack_from("<I", crudo, 0)
            suelto = zlib.decompress(crudo[4:])
            if len(suelto) != esperado:
                raise PluginInvalido(
                    "descomprimido da %d bytes y declaraba %d en +%d"
                    % (len(suelto), esperado, offset))
            return suelto
        return crudo

    def form_id(self, offset):
        return struct.unpack_from("<I", self.d, offset + 12)[0]

    @staticmethod
    def subrecords(datos):
        """[(tipo, bytes)]. Tienen que embaldosar `datos` exactamente.

        El escape XXXX lleva el tamano real del subrecord siguiente, porque un
        uint16 no alcanza. Se maneja si aparece; no se asume que aparezca.
        """
        fuera = []
        p = 0
        n = len(datos)
        pendiente = None
        while p + SUB_CABECERA <= n:
            tipo = datos[p:p + 4]
            tam, = struct.unpack_from("<H", datos, p + 4)
            p += SUB_CABECERA
            if tipo == ESCAPE_TAMANO:
                if tam != 4 or p + 4 > n:
                    raise PluginInvalido("XXXX mal formado en +%d" % (p - SUB_CABECERA))
                pendiente, = struct.unpack_from("<I", datos, p)
                p += 4
                continue
            if pendiente is not None:
                tam = pendiente
                pendiente = None
            if p + tam > n:
                raise PluginInvalido(
                    "subrecord %r tam=%d en +%d se pasa de %d"
                    % (tipo, tam, p - SUB_CABECERA, n))
            fuera.append((tipo.decode("ascii", "replace"), datos[p:p + tam]))
            p += tam
        if p != n:
            raise PluginInvalido(
                "los subrecords terminan en %d y no en %d (sobran %d)" % (p, n, n - p))
        return fuera

    def cuenta_tipos(self):
        c = collections.Counter()
        for tipo, _o, _t, _p in self.recorrer():
            c[tipo] += 1
        return c


def _texto(b):
    return b.rstrip(b"\x00").decode("cp1252", "replace")


def campos_stat(plugin, offset):
    """{EDID, MODL, OBND, ...} de un STAT, con los bytes crudos."""
    fuera = {}
    for tipo, valor in Plugin.subrecords(plugin.datos(offset)):
        fuera.setdefault(tipo, []).append(valor)
    return fuera


# --- Suite de falsificacion ---------------------------------------------------
# QUE ES CADA COSA, PARA NO CONFUNDIRLAS
#
# La falsificacion de verdad es la IDENTIDAD: el recorrido tiene que embaldosar
# el archivo exacto, sin huecos ni sobrantes, en los tres niveles (bloques de
# nivel superior, contenido de cada GRUP, subrecords de cada record). Eso no se
# puede cumplir por casualidad con un layout equivocado.
#
# Los numeros de abajo son ANCLAS DE REGRESION, no verificacion independiente:
# salieron de este mismo parser. Sirven para que un cambio futuro que altere los
# conteos tenga que justificarse, no para probar que el parser lee bien.
#
# La distincion no es academica. La primera version de esta tabla decia
# STAT: 4772 para Skyrim.esm -- un numero que nunca medi y puse de memoria. El
# autotest lo reprobo en la primera corrida. El valor real es 9720.

AUTOTEST = [
    ("Skyrim.esm", {"bytes": 249753412, "bloques": 920182, "tipos": 120,
                    "STAT": 9720}),
    ("Update.esm", {"bloques": 21233, "tipos": 74, "STAT": 379}),
    ("Dawnguard.esm", {"bloques": 103757, "tipos": 108, "STAT": 930}),
    ("HearthFires.esm", {"bloques": 19263, "tipos": 63, "STAT": 186}),
    ("Dragonborn.esm", {"bloques": 251500, "tipos": 106, "STAT": 1085}),
]


def autotest(raiz):
    print("SUITE DE FALSIFICACION")
    print("")
    ok = fallo = falta = 0
    for nombre, esperado in AUTOTEST:
        ruta = os.path.join(raiz, nombre)
        if not os.path.exists(ruta):
            print("  %-24s NO ESTA" % nombre)
            falta += 1
            continue
        try:
            p = Plugin(ruta)
            tipos = p.cuenta_tipos()
        except PluginInvalido as e:
            print("  %-24s VIOLA LA IDENTIDAD: %s" % (nombre, e))
            fallo += 1
            continue
        obtenido = {"bytes": len(p.d), "bloques": sum(tipos.values()),
                    "tipos": len(tipos), "STAT": tipos.get("STAT", 0)}
        for k, v in sorted(esperado.items()):
            if obtenido.get(k) == v:
                ok += 1
            else:
                fallo += 1
                print("  %-24s %s: esperado %s, obtenido %s"
                      % (nombre, k, v, obtenido.get(k)))
        print("  %-24s %d bloques, %d tipos%s"
              % (nombre, obtenido["bloques"], obtenido["tipos"],
                 "" if not fallo else "  <-- con fallas"))

    # Los subrecords de cada STAT tambien tienen que embaldosar.
    n_stat = n_mal = 0
    for nombre, _e in AUTOTEST:
        ruta = os.path.join(raiz, nombre)
        if not os.path.exists(ruta):
            continue
        try:
            p = Plugin(ruta)
            for tipo, off, _tam, _prof in p.recorrer():
                if tipo != "STAT":
                    continue
                n_stat += 1
                try:
                    Plugin.subrecords(p.datos(off))
                except Exception as e:
                    n_mal += 1
                    if n_mal <= 3:
                        print("    %s %08X: %s" % (nombre, p.form_id(off), e))
        except PluginInvalido as e:
            # El recorrido tiene que poder reprobar sin reventar: un layout mal
            # leido es un resultado del autotest, no un accidente del script.
            print("    %s: el recorrido viola la identidad: %s" % (nombre, e))
            n_mal += 1
    print("")
    print("  %d STAT con subrecords que embaldosan, %d rotos" % (n_stat - n_mal, n_mal))
    fallo += n_mal

    print("")
    print("  %d comprobaciones ok, %d fallidas, %d archivos no encontrados"
          % (ok, fallo, falta))
    if ok == 0 and fallo == 0:
        # Cero comprobaciones no es exito: es no haber mirado nada. Va antes que
        # el reporte de fallas pero DESPUES de comprobar que no hubo ninguna:
        # con 10 fallas y 0 aciertos, el problema no es la ruta.
        print("  NO se comprobo NADA. Revisa la ruta de la carpeta Data.")
        return False
    if fallo:
        print("  El parser NO esta listo para censar.")
    elif falta:
        print("  Ok hasta donde se pudo comprobar, pero faltan archivos.")
    else:
        print("  Parser validado. Ahora si, censar.")
    return fallo == 0 and falta == 0


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        raise SystemExit(2)
    if a[0] == "--autotest":
        if len(a) < 2:
            print("Uso: --autotest <carpeta Data>")
            raise SystemExit(2)
        raise SystemExit(0 if autotest(a[1]) else 1)

    p = Plugin(a[0])
    filtro = a[1] if len(a) > 1 else None
    tipos = collections.Counter()
    for tipo, off, _tam, _prof in p.recorrer():
        tipos[tipo] += 1
        if filtro and tipo == filtro and tipos[tipo] <= 5:
            campos = campos_stat(p, off)
            print("  %08X %s" % (p.form_id(off),
                                 " ".join("%s(%d)" % (k, len(v[0]))
                                          for k, v in sorted(campos.items()))))
    print("%s: %d bloques, %d tipos" % (os.path.basename(a[0]),
                                        sum(tipos.values()), len(tipos)))
    for t, n in tipos.most_common(15):
        print("  %-8s %8d" % (t, n))


if __name__ == "__main__":
    main()
