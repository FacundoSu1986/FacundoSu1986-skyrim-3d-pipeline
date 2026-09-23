# -*- coding: utf-8 -*-
"""Lee un plugin TERMINADO (.esp/.esl/.esm) y reprueba lo que el juego lee mal
sin avisar.

    python verificar_plugin.py MiMod.esl [...]
    python verificar_plugin.py --autotest
    python verificar_plugin.py --falsificar <carpeta Data>

Exit: 0 pasa, 1 falla (o no se pudo leer), 2 argumentos que no sirven.

POR QUE EXISTE. El `.esl` del hacha de Tencent salio con `formVersion = 0` en
sus tres records. El juego NO dio error: cargo el plugin, el arma aparecio en
el inventario y el VALOR se leyo bien -- pero el PESO y el DANO salieron en
cero. El motor parsea el `DATA` de un `WEAP` con un layout que depende de ese
campo, y el unico sintoma fue un numero mal en una pantalla. Costo una vuelta
entera de "instala y proba". Con 44 el mismo record dio peso 27 y dano 26,
confirmado en el juego.

`census/escritor_plugin.py` ya escribe 44 por defecto. Esto no es para el que
usa el escritor: es para el que arma los bytes a mano, que es lo que habia
pasado, y para cualquier plugin que venga de otra herramienta.

REGLA 1 -- formVersion == 44 en cada record.
    Los 5 plugins que Bethesda AUTORO PARA SE (_ResourcePack.esl y los cuatro de
    Creation Club): 10.273 de 10.273 records en 44. Cero excepciones. Y 44 es el
    maximo de los 1.188.821 records del corpus: no existe un 45.

    EL SUBCONJUNTO ES LA REGLA. Sobre el corpus entero solo el 7,65 % esta en
    44, y el valor mas comun es el 39. Eso no refuta la regla: los masters de
    2011 llevan, record por record, la version de la ultima vez que alguien lo
    toco -- hay records que nadie toco desde la 14. Es historia del archivo, no
    lo que escribe hoy el Creation Kit de SE. Por eso esta herramienta es para
    TU plugin: pasarla sobre Skyrim.esm reprueba 1,1 millones de records que el
    juego carga perfectamente.

REGLA 2 -- el indice de mod de cada FormID <= cantidad de masters.
    El byte alto del FormID dice de que plugin de la lista sale el record. Con
    N masters, el indice N es ESTE plugin y cada indice menor es un master (un
    override). Un indice mayor apunta a un master que no existe.
    Corpus: 1.188.810 de 1.188.811 records. La excepcion tiene nombre: el GMST
    `iDaysToRespawnVendor` (0123C00E) de Skyrim.esm, indice 1 en un archivo sin
    masters -- un record sucio conocido del propio Bethesda.

REGLA 3 -- en cada WEAP: DATA de 10 bytes, DNAM de 100, y el WNAM (el modelo de
    primera persona), si apunta a este mismo plugin, a un STAT que exista.
    Corpus: las 3.359 WEAP de los 10 plugins tienen DATA de 10 y DNAM de 100,
    sin excepcion. De las 472 armas base (sin plantilla CNAM), 463 tienen WNAM
    y las 463 apuntan a un STAT; las 9 sin WNAM son armas conjuradas,
    maniquies de entrenamiento y objetos de mision -- por eso la falta de WNAM
    es una OBSERVACION y no reprueba. Un WNAM que apunta a un master no se
    puede juzgar sin cargarlo, y se dice.

    El DATA es donde el hacha mostro peso y dano en cero (con formVersion 0):
    valor u32, peso f32, dano u16 = 10 bytes, confirmado en el juego con 2750 /
    27 / 26.

Y un requisito previo que no es regla sino lectura: el recorrido tiene que
embaldosar el archivo. Si no cierra, no hay nada que juzgar, y eso es una falla.

El recorrido es el de esl.py (recorrer_records), no uno propio: el mismo que
esl.py cruzo contra census/parser_esm.py en los 10 plugins.
"""
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import esl  # noqa: E402

VERSION_ACTUAL = 44
LIMITE_DETALLE = 10
OFFSET_VERSION = 20

N_SE = 10273          # records de los 5 plugins autorados para SE, todos en 44
N_INDICE = 1188811    # records de los 10 plugins, sin el TES4
N_WEAP = 3359         # WEAP de los 10 plugins: DATA 10 y DNAM 100 en todas
N_WNAM = 463          # armas base con WNAM: todas apuntan a un STAT
COMPRIMIDO = 0x00040000


def subrecords(d, off):
    """[(tipo, bytes)] del record en `off`, descomprimido si hace falta.

    Copia del lector de census/parser_esm.py (Plugin.subrecords): este script
    no puede importar census/ porque build_skill.py no lo empaqueta. Los tests
    atan las dos lecturas sobre los mismos bytes, con XXXX y con zlib."""
    tam, flags = struct.unpack_from("<II", d, off + 4)
    crudo = d[off + 24:off + 24 + tam]
    if flags & COMPRIMIDO:
        esperado, = struct.unpack_from("<I", crudo, 0)
        crudo = zlib.decompress(crudo[4:])
        if len(crudo) != esperado:
            raise ValueError("descomprimido da %d y declaraba %d"
                             % (len(crudo), esperado))
    out, p, grande = [], 0, None
    while p + 6 <= len(crudo):
        tipo = crudo[p:p + 4].decode("ascii", "replace")
        n, = struct.unpack_from("<H", crudo, p + 4)
        p += 6
        if tipo == "XXXX":
            grande, = struct.unpack_from("<I", crudo, p)
            p += n
            continue
        if grande is not None:
            n, grande = grande, None
        out.append((tipo, crudo[p:p + n]))
        p += n
    if p != len(crudo):
        raise ValueError("los subrecords no embaldosan el record en +%d" % off)
    return out


def _datos_weap(d, off):
    subs = dict(subrecords(d, off))
    wnam = subs.get("WNAM")
    return {"DATA": len(subs["DATA"]) if "DATA" in subs else None,
            "DNAM": len(subs["DNAM"]) if "DNAM" in subs else None,
            "WNAM": struct.unpack_from("<I", wnam)[0]
            if wnam and len(wnam) == 4 else None}


def leer(ruta):
    """{records: [{tipo, form_id, version}], n_masters, error}."""
    try:
        with open(ruta, "rb") as fh:
            d = fh.read()
    except OSError as e:
        return {"records": [], "n_masters": 0,
                "error": "no se pudo abrir: %s" % e}
    if len(d) < 24 or d[:4] != b"TES4":
        return {"records": [], "n_masters": 0,
                "error": "no empieza con un TES4: no es un plugin"}
    recs, cerro = esl.recorrer_records(d)
    if not cerro:
        return {"records": [], "n_masters": 0,
                "error": "el recorrido no embaldosa el archivo: esta truncado "
                         "o un tamano declarado miente"}
    records = []
    for tag, o in recs:
        r = {"tipo": tag.decode("ascii", "replace"),
             "form_id": struct.unpack_from("<I", d, o + 12)[0],
             "version": struct.unpack_from("<H", d, o + OFFSET_VERSION)[0]}
        if tag == b"WEAP":
            try:
                r["weap"] = _datos_weap(d, o)
            except (ValueError, zlib.error, struct.error) as e:
                return {"records": [], "n_masters": 0,
                        "error": "WEAP %08X ilegible: %s" % (r["form_id"], e)}
        records.append(r)
    return {"records": records, "n_masters": len(esl.masters(d)),
            "error": None}


def _cortar(fallas, total, que):
    """Detalle hasta LIMITE_DETALLE, y el TOTAL verdadero si hay mas."""
    if total <= LIMITE_DETALLE:
        return fallas
    return fallas[:LIMITE_DETALLE] + [
        "... %d records en total con %s (se muestran %d)"
        % (total, que, LIMITE_DETALLE)]


def juzgar(info):
    """(fallas, notas) de UN plugin."""
    if info.get("error"):
        return ["no se pudo leer: %s" % info["error"]], []
    fallas, notas = [], []

    malas = [r for r in info["records"] if r["version"] != VERSION_ACTUAL]
    detalle = [
        "REGLA formVersion: %s %08X tiene formVersion %d y se esperaba %d. "
        "Los 5 plugins autorados para SE: %d de %d records en %d. Con otro "
        "valor el motor lee los campos con un layout viejo -- el hacha salio "
        "con peso y dano 0 y el valor bien."
        % (r["tipo"], r["form_id"], r["version"], VERSION_ACTUAL,
           N_SE, N_SE, VERSION_ACTUAL)
        for r in malas[:LIMITE_DETALLE]]
    fallas += _cortar(detalle, len(malas),
                      "formVersion != %d" % VERSION_ACTUAL)

    n = info["n_masters"]
    fuera = [r for r in info["records"] if (r["form_id"] >> 24) > n]
    detalle = [
        "REGLA indice de mod: %s %08X tiene índice de mod %d y el plugin "
        "tiene %d master(s): apunta a un master que no existe. Vanilla: "
        "%d de %d records dentro."
        % (r["tipo"], r["form_id"], r["form_id"] >> 24, n,
           N_INDICE - 1, N_INDICE)
        for r in fuera[:LIMITE_DETALLE]]
    fallas += _cortar(detalle, len(fuera), "índice de mod > masters")

    fallas += _reglas_weap(info, notas)

    propios = sum(1 for r in info["records"]
                  if r["tipo"] != "TES4" and (r["form_id"] >> 24) == n)
    over = sum(1 for r in info["records"]
               if r["tipo"] != "TES4" and (r["form_id"] >> 24) < n)
    notas.append("OBS %d record(s) propio(s), %d override(s), %d master(s)"
                 % (propios, over, n))
    return fallas, notas


def _reglas_weap(info, notas):
    """REGLA 3. Solo mira los records que `leer` marco con sus datos de WEAP:
    un dict armado a mano sin esa clave no se juzga, y la nota dice cuantas
    se comprobaron para que cero no pase por exito."""
    n = info["n_masters"]
    tipo_de = dict((r["form_id"], r["tipo"]) for r in info["records"])
    armas = [r for r in info["records"] if "weap" in r]
    fallas = []
    for r in armas:
        w = r["weap"]
        cual = "WEAP %08X" % r["form_id"]
        if w["DATA"] != 10:
            fallas.append(
                "REGLA WEAP DATA: %s tiene DATA de %s bytes y se esperaban 10 "
                "(valor u32, peso f32, dano u16). Las %d WEAP vanilla miden 10."
                % (cual, w["DATA"], N_WEAP))
        if w["DNAM"] != 100:
            fallas.append(
                "REGLA WEAP DNAM: %s tiene DNAM de %s bytes y se esperaban 100. "
                "Las %d WEAP vanilla miden 100." % (cual, w["DNAM"], N_WEAP))
        destino = w["WNAM"]
        if destino is None:
            notas.append("OBS %s sin WNAM: sin modelo de primera persona. De "
                         "las 472 armas base vanilla, las 9 sin WNAM son "
                         "conjuradas, maniquies o de mision." % cual)
        elif (destino >> 24) == n:
            t = tipo_de.get(destino)
            if t is None:
                fallas.append(
                    "REGLA WEAP WNAM: %s apunta a %08X, que no existe en este "
                    "plugin. El arma no tendria modelo de primera persona."
                    % (cual, destino))
            elif t != "STAT":
                fallas.append(
                    "REGLA WEAP WNAM: %s apunta a %08X, que es un %s y no un "
                    "STAT. Las %d armas base vanilla con WNAM apuntan a un STAT."
                    % (cual, destino, t, N_WNAM))
        else:
            notas.append("OBS %s: su WNAM %08X es de un master y no se puede "
                         "verificar sin cargarlo." % (cual, destino))
    if armas:
        notas.append("OBS %d WEAP comprobada(s)" % len(armas))
    return fallas


def revisar(rutas):
    con_falla = 0
    for ruta in rutas:
        info = leer(ruta)
        fallas, notas = juzgar(info)
        print("== %s   %d records" % (os.path.basename(ruta),
                                      len(info["records"])))
        for x in notas:
            print("   %s" % x)
        for x in fallas:
            print("   FALLA %s" % x)
        if fallas:
            con_falla += 1
        else:
            print("   ok")
    return 1 if con_falla else 0


# --------------------------------------------------------------------------
def _rec(version=VERSION_ACTUAL, form_id=0x800, tipo="STAT"):
    return {"tipo": tipo, "form_id": form_id, "version": version}


def autotest():
    """Enumerante: cada version distinta de la actual reprueba, cada indice
    por encima de los masters reprueba, y lo sano no."""
    fallas = []
    corridos = [0]

    def caso(nombre, info, debe_fallar, marca):
        corridos[0] += 1
        f, _ = juzgar(info)
        dio = any(marca in x for x in f)
        if dio != debe_fallar:
            fallas.append("%s: %s" % (nombre, "no reprobo" if debe_fallar
                                      else "reprobo sin razon: %r" % f))

    base = {"records": [_rec(tipo="TES4", form_id=0), _rec()],
            "n_masters": 0, "error": None}
    caso("sano", base, False, "REGLA")
    for v in list(range(0, VERSION_ACTUAL)) + [VERSION_ACTUAL + 1, 0xFFFF]:
        caso("version %d" % v,
             dict(base, records=[_rec(tipo="TES4", form_id=0),
                                 _rec(version=v)]),
             True, "formVersion")
    for n in range(0, 6):
        caso("propio con %d masters" % n,
             {"records": [_rec(form_id=(n << 24) | 0x800)],
              "n_masters": n, "error": None}, False, "REGLA")
        for i in range(0, n):
            caso("override %d de %d" % (i, n),
                 {"records": [_rec(form_id=(i << 24) | 0x800)],
                  "n_masters": n, "error": None}, False, "REGLA")
        caso("indice %d con %d masters" % (n + 1, n),
             {"records": [_rec(form_id=((n + 1) << 24) | 0x800)],
              "n_masters": n, "error": None}, True, "índice de mod")
    caso("ilegible", {"records": [], "n_masters": 0, "error": "x"},
         True, "no se pudo leer")

    # REGLA 3: un WEAP con sus datos leidos y el STAT de su primera persona
    def arma(data=10, dnam=100, wnam=0x01000801, otros=()):
        recs = [_rec(tipo="TES4", form_id=0),
                _rec(tipo="STAT", form_id=0x01000801),
                dict(_rec(tipo="WEAP", form_id=0x01000800),
                     weap={"DATA": data, "DNAM": dnam, "WNAM": wnam})]
        return {"records": recs + list(otros), "n_masters": 1, "error": None}

    caso("arma sana", arma(), False, "REGLA")
    for n in [None] + [x for x in range(0, 21) if x != 10]:
        caso("DATA %s" % n, arma(data=n), True, "WEAP DATA")
    for n in (None, 0, 96, 99, 101, 104):
        caso("DNAM %s" % n, arma(dnam=n), True, "WEAP DNAM")
    caso("WNAM a un propio inexistente", arma(wnam=0x01000ABC), True,
         "WEAP WNAM")
    caso("WNAM al propio WEAP", arma(wnam=0x01000800), True, "WEAP WNAM")
    caso("WNAM a un master", arma(wnam=0x00012345), False, "REGLA")
    caso("sin WNAM", arma(wnam=None), False, "REGLA")

    print("autotest: %d casos, %d fallas" % (corridos[0], len(fallas)))
    for x in fallas:
        print("  FALLA %s" % x)
    return 1 if fallas else 0


def falsificar(raiz):
    """Sobre plugins REALES: los que pasan tal cual sirven de patron, y
    torcer cada campo tiene que reprobar. Los masters de 2011 no pasan la
    REGLA 1 (records viejos) y quedan afuera como patron, a proposito."""
    usados, roturas, fallas = 0, 0, []
    nombres = []
    if os.path.isdir(raiz):
        nombres = sorted(n for n in os.listdir(raiz)
                         if n.lower().endswith((".esm", ".esl", ".esp")))
    for nombre in nombres:
        info = leer(os.path.join(raiz, nombre))
        base, _ = juzgar(info)
        if base:
            print("   %-34s no sirve de patron (%d fallas tal cual)"
                  % (nombre, len(base)))
            continue
        usados += 1
        recs = info["records"]
        n = info["n_masters"]
        # Se tuerce UN record en el medio del archivo, no el primero: un
        # verificador que solo mirara el TES4 pasaria esto.
        k = len(recs) // 2
        mutaciones = [
            ("formVersion 0 (el hacha)", k, dict(recs[k], version=0)),
            ("formVersion 39 (la mas comun)", k, dict(recs[k], version=39)),
            ("formVersion 45", k, dict(recs[k], version=45)),
            ("indice de mod N+1", k,
             dict(recs[k], form_id=((n + 1) << 24)
                  | (recs[k]["form_id"] & 0xFFFFFF))),
        ]
        # REGLA 3 sobre un WEAP real, si el plugin tiene alguno
        armas = [j for j, r in enumerate(recs) if "weap" in r]
        if armas:
            j = armas[len(armas) // 2]
            w = recs[j]["weap"]
            mutaciones += [
                ("WEAP DATA de 12", j, dict(recs[j], weap=dict(w, DATA=12))),
                ("WEAP DNAM de 96", j, dict(recs[j], weap=dict(w, DNAM=96))),
                ("WEAP WNAM a un propio inexistente", j,
                 dict(recs[j], weap=dict(w, WNAM=(n << 24) | 0xFFFFFE))),
            ]
        for que, i, mut in mutaciones:
            roturas += 1
            torcido = dict(info, records=recs[:i] + [mut] + recs[i + 1:])
            f, _ = juzgar(torcido)
            if not f:
                fallas.append("%s / %s: no reprobo" % (nombre, que))
        print("   %-34s patron: %d records (%d WEAP), %d masters, %d roturas"
              % (nombre, len(recs), len(armas), n, len(mutaciones)))
    print("falsificar: %d plugins, %d comprobaciones, %d fallas"
          % (usados, roturas, len(fallas)))
    for x in fallas:
        print("  FALLA %s" % x)
    if usados == 0:
        print("FALLA: cero plugins utilizables -- no comprobar nada no es "
              "exito")
        return 1
    return 1 if fallas else 0


def main(argv):
    if len(argv) == 1 and argv[0] == "--autotest":
        return autotest()
    if len(argv) == 2 and argv[0] == "--falsificar":
        return falsificar(argv[1])
    if argv and not any(a.startswith("--") for a in argv):
        return revisar(argv)
    print("uso: verificar_plugin.py <plugin> [...] | --autotest | "
          "--falsificar <carpeta Data>")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
