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

Y un requisito previo que no es regla sino lectura: el recorrido tiene que
embaldosar el archivo. Si no cierra, no hay nada que juzgar, y eso es una falla.

El recorrido es el de esl.py (recorrer_records), no uno propio: el mismo que
esl.py cruzo contra census/parser_esm.py en los 10 plugins.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import esl  # noqa: E402

VERSION_ACTUAL = 44
LIMITE_DETALLE = 10
OFFSET_VERSION = 20

N_SE = 10273          # records de los 5 plugins autorados para SE, todos en 44
N_INDICE = 1188811    # records de los 10 plugins, sin el TES4


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
    records = [{"tipo": tag.decode("ascii", "replace"),
                "form_id": struct.unpack_from("<I", d, o + 12)[0],
                "version": struct.unpack_from("<H", d, o + OFFSET_VERSION)[0]}
               for tag, o in recs]
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

    propios = sum(1 for r in info["records"]
                  if r["tipo"] != "TES4" and (r["form_id"] >> 24) == n)
    over = sum(1 for r in info["records"]
               if r["tipo"] != "TES4" and (r["form_id"] >> 24) < n)
    notas.append("OBS %d record(s) propio(s), %d override(s), %d master(s)"
                 % (propios, over, n))
    return fallas, notas


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
        for que, i, mut in mutaciones:
            roturas += 1
            torcido = dict(info, records=recs[:i] + [mut] + recs[i + 1:])
            f, _ = juzgar(torcido)
            if not f:
                fallas.append("%s / %s: no reprobo" % (nombre, que))
        print("   %-34s patron: %d records, %d masters, 4 roturas"
              % (nombre, len(recs), n))
    print("falsificar: %d plugins x 4 roturas = %d comprobaciones, %d fallas"
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
