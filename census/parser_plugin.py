# -*- coding: utf-8 -*-
"""Lee plugins de Bethesda (esm/esp/esl): grupos, records y subrecords.

    python parser_plugin.py --autotest <carpeta Data>
    python parser_plugin.py <archivo.esp>

LA IDENTIDAD QUE FALSIFICA EL PARSEO
------------------------------------
Es la misma forma que ya usamos en NIF y DDS: recorrer la estructura tiene que
caer EXACTO en el fin del archivo.

  record:  24 bytes de encabezado + dataSize bytes de datos
  grupo:   24 bytes de encabezado, y groupSize INCLUYE esos 24
  subrecord dentro de un record: 4 de tipo + 2 de tamano + tamano bytes

Cuando el subrecord mide mas de lo que entra en un u16, Bethesda lo precede de
un subrecord XXXX (4 + 2 + 4) con el tamano real. Se decodifica: en los masters
del corpus no aparece (medido: 0 en 1,17 millones de records), pero un plugin
de mod valido puede tenerlo y leerlo como subrecord comun corre todos los
offsets que siguen.

Si alguno de esos tres tamanos estuviera mal interpretado, el recorrido se
desalinea y no termina donde termina el archivo. Sobre un .esm de 250 MB eso no
pasa por casualidad.

LO QUE NO SE PUEDE VERIFICAR ACA
-------------------------------
La bandera ESL. No hay ningun .esl en esta instalacion para medir, asi que el
bit que la marca no sale del corpus: sale de la documentacion de Bethesda y
queda como NO VERIFICADO. La forma de confirmarlo es cargar el plugin y mirar
si el juego le da un FormID que empieza con FE.
"""
import os
import struct
import sys

# Banderas del encabezado TES4. Solo la primera esta confirmada contra el
# corpus: los cinco .esm de esta instalacion la tienen y el .esp no.
BANDERA_ESM = 0x00000001
BANDERA_ESL = 0x00000200          # NO VERIFICADO contra el corpus

CABECERA_RECORD = 24
CABECERA_GRUPO = 24

# Escape de tamano extendido: un subrecord de mas de 65535 bytes se precede de
# un XXXX con el tamano real en un u32.
ESCAPE_TAMANO = b"XXXX"


class PluginInvalido(Exception):
    pass


class Plugin(object):
    """Un plugin parseado a nivel de estructura. Los datos quedan crudos."""

    def __init__(self, ruta):
        self.ruta = ruta
        with open(ruta, "rb") as fh:
            self.d = fh.read()
        if len(self.d) < CABECERA_RECORD or self.d[:4] != b"TES4":
            raise PluginInvalido("no empieza con un record TES4")

        (self.tam_tes4, self.banderas, self.form_id,
         _t, _v, self.version, _u) = struct.unpack_from("<IIIHHHH", self.d, 4)
        self.es_esm = bool(self.banderas & BANDERA_ESM)
        self.es_esl = bool(self.banderas & BANDERA_ESL)

        self.records = []          # (tipo, offset, tam_datos, form_id)
        self.grupos = []           # (etiqueta, offset, tam_total, tipo_grupo)
        self._recorrer()

    # --- recorrido ----------------------------------------------------------

    def _recorrer(self):
        fin = len(self.d)
        p = self._record(0)
        while p < fin:
            if fin - p < CABECERA_GRUPO:
                raise PluginInvalido(
                    "cola de %d bytes en %d: no entra un encabezado" % (fin - p, p))
            tipo = self.d[p:p + 4]
            if tipo == b"GRUP":
                p = self._grupo(p, 0)
            else:
                p = self._record(p)
        if p != fin:
            raise PluginInvalido("el recorrido termina en %d, el archivo en %d"
                                 % (p, fin))

    def _record(self, p):
        if p + CABECERA_RECORD > len(self.d):
            raise PluginInvalido(
                "encabezado de record en %d: el archivo termina en %d"
                % (p, len(self.d)))
        tipo = self.d[p:p + 4]
        tam, _fl, fid = struct.unpack_from("<III", self.d, p + 4)
        fin = p + CABECERA_RECORD + tam
        if fin > len(self.d):
            raise PluginInvalido(
                "record %s en %d declara %d bytes y el archivo tiene %d"
                % (tipo.decode("latin-1"), p, tam, len(self.d)))
        self.records.append((tipo.decode("latin-1"), p, tam, fid))
        return fin

    def _grupo(self, p, nivel):
        tam, etiqueta, tipo_grupo = struct.unpack_from("<I4si", self.d, p + 4)
        if tam < CABECERA_GRUPO:
            raise PluginInvalido("grupo en %d con tamano %d" % (p, tam))
        fin = p + tam
        if fin > len(self.d):
            raise PluginInvalido("grupo en %d se pasa del archivo" % p)
        self.grupos.append((etiqueta.decode("latin-1"), p, tam, tipo_grupo))
        q = p + CABECERA_GRUPO
        while q < fin:
            # El hijo tiene que entrar entero en el grupo, no solo en el
            # archivo: con una cola de menos de 24 B, `_record` leia el bloque
            # siguiente (o reventaba con struct.error si el grupo estaba al
            # final) en vez de rechazar el grupo.
            if fin - q < CABECERA_GRUPO:
                raise PluginInvalido(
                    "grupo en %d: cola de %d bytes en %d" % (p, fin - q, q))
            if self.d[q:q + 4] == b"GRUP":
                q = self._grupo(q, nivel + 1)
            else:
                q = self._record(q)
        if q != fin:
            raise PluginInvalido("grupo en %d: recorrido %d != fin %d"
                                 % (p, q, fin))
        return fin

    # --- consultas ----------------------------------------------------------

    def subrecords(self, offset_record):
        """[(tipo, offset_datos, tamano)] de un record, en orden.

        No se descomprimen los records con bandera 0x40000: se informan y se
        saltean, porque inventar su contenido seria peor que no leerlo.

        El escape XXXX lleva el tamano real (> 65535) del subrecord siguiente,
        porque el u16 no alcanza. Se decodifica si aparece: un plugin valido
        con un subrecord grande correria TODOS los offsets siguientes si se
        leyera como un subrecord comun.
        """
        tam, banderas, _fid = struct.unpack_from("<III", self.d, offset_record + 4)
        if banderas & 0x00040000:
            return [("(comprimido)", offset_record + CABECERA_RECORD, tam)]
        fuera = []
        p = offset_record + CABECERA_RECORD
        fin = p + tam
        pendiente = None        # (donde empieza el XXXX, el tamano que promete)
        while p + 6 <= fin:
            crudo = self.d[p:p + 4]
            tipo = crudo.decode("latin-1")
            n, = struct.unpack_from("<H", self.d, p + 4)
            p += 6
            if crudo == ESCAPE_TAMANO:
                if n != 4 or p + 4 > fin:
                    raise PluginInvalido(
                        "XXXX mal formado en %d" % (p - 6))
                pendiente = (p - 6, struct.unpack_from("<I", self.d, p)[0])
                p += 4
                continue
            if pendiente is not None:
                n = pendiente[1]
                pendiente = None
            fuera.append((tipo, p, n))
            p += n
        if pendiente is not None:
            # El XXXX promete el subrecord que describe. Sin el, el record esta
            # truncado y un `p == fin` limpio lo daria por bueno.
            raise PluginInvalido(
                "XXXX en %d sin el subrecord que describe (%d bytes)" % pendiente)
        if p != fin:
            raise PluginInvalido(
                "subrecords de %d: recorrido %d != fin %d" % (offset_record, p, fin))
        return fuera

    def cuenta_tipos(self):
        c = {}
        for tipo, _o, _t, _f in self.records:
            c[tipo] = c.get(tipo, 0) + 1
        return c

    def maestros(self):
        """Los plugins de los que depende, en orden."""
        fuera = []
        for tipo, off, _t, _f in self.records:
            if tipo != "TES4":
                continue
            for st, so, sn in self.subrecords(off):
                if st == "MAST":
                    fuera.append(self.d[so:so + sn].rstrip(b"\x00")
                                 .decode("cp1252", "replace"))
        return fuera


# --- autotest ----------------------------------------------------------------

def autotest(raiz):
    """La identidad de recorrido sobre todos los plugins de una carpeta."""
    print("SUITE DE FALSIFICACION - parser_plugin")
    print("")
    n = ok = malo = 0
    ejemplos = []
    banderas = {}
    for f in sorted(os.listdir(raiz)):
        if not f.lower().endswith((".esm", ".esp", ".esl")):
            continue
        ruta = os.path.join(raiz, f)
        n += 1
        try:
            p = Plugin(ruta)
            ok += 1
            banderas[f] = (p.banderas, p.es_esm, p.es_esl,
                           len(p.records), len(p.grupos))
        except Exception as e:
            malo += 1
            if len(ejemplos) < 4:
                ejemplos.append((f, str(e)[:70]))

    print("  a. el recorrido cae exacto en el fin del archivo")
    print("     %d plugins, %d recorridos enteros, %d fallan" % (n, ok, malo))
    for f, m in ejemplos:
        print("       %s  %s" % (f, m))
    print("")
    print("  b. la bandera ESM, contra la extension")
    coherentes = 0
    for f, (fl, esm, esl, nr, ng) in sorted(banderas.items()):
        esperado = f.lower().endswith(".esm")
        marca = "ok" if esm == esperado else "NO COINCIDE"
        coherentes += 1 if esm == esperado else 0
        print("     %-28s banderas=0x%08X esm=%-5s esl=%-5s records=%-6d grupos=%-4d %s"
              % (f, fl, esm, esl, nr, ng, marca))

    print("")
    if n == 0:
        print("  NO se leyo NINGUN plugin. Revisa la ruta.")
        return False
    if malo:
        print("  El parser NO esta validado.")
        return False
    if coherentes != len(banderas):
        print("  La bandera ESM no coincide con la extension en algun archivo.")
        return False
    print("  Sin fallas.")
    return True


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
    print("%s" % os.path.basename(a[0]))
    print("  %d bytes  banderas=0x%08X  esm=%s  esl=%s"
          % (len(p.d), p.banderas, p.es_esm, p.es_esl))
    print("  maestros: %s" % (p.maestros() or "(ninguno)"))
    print("  records por tipo: %s" % p.cuenta_tipos())
    print("")
    for etiqueta, off, tam, tipo_grupo in p.grupos:
        print("  GRUP %-6s en %-6d %6d B  tipo=%d" % (etiqueta, off, tam, tipo_grupo))
    print("")
    for tipo, off, tam, fid in p.records:
        print("  %-4s en %-6d %6d B  FormID=0x%08X" % (tipo, off, tam, fid))
        for st, so, sn in p.subrecords(off):
            crudo = p.d[so:so + sn]
            texto = ""
            if crudo and all(32 <= c < 127 or c == 0 for c in crudo):
                texto = "  %r" % crudo.rstrip(b"\x00").decode("latin-1")
            print("        %-12s %4d B%s" % (st, sn, texto))


if __name__ == "__main__":
    main()
