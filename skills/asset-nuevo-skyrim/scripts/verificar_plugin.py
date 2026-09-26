# -*- coding: utf-8 -*-
"""Lee un plugin TERMINADO (.esp/.esl/.esm) y reprueba lo que el juego lee mal
sin avisar.

    python verificar_plugin.py MiMod.esl [...]
    python verificar_plugin.py --autotest
    python verificar_plugin.py --falsificar <carpeta Data>
    python verificar_plugin.py --falsificar-prn <carpeta Data> <carpeta meshes>

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

REGLA 4 -- el Prn del NIF de cada WEAP corresponde a su tipo de animacion
    (DNAM[0]): WeaponSword, WeaponDagger, WeaponAxe, WeaponMace, WeaponBack
    para las de dos manos, WeaponBow para arcos y ballestas. Es el nodo del que
    cuelga el arma envainada. 305 de 306 armas vanilla del jugador; la
    excepcion es NordicGreatSword.nif. Los bastones no tienen regla
    (WeaponStaff en 21, SHIELD en 18) y salen como OBSERVACION.
    El NIF se busca en meshes/ al lado del plugin, sin distinguir mayusculas;
    si no esta, se dice y no se juzga.

REGLA 5 -- una referencia colocada (REFR, ACHR, PGRE, PMIS, PHZD, PARW, PBAR,
    PBEA, PCON, PFLA) en un GRUP de tipo 8 (Cell Persistent Children) lleva
    la bandera 0x400 (Persistent); en uno de tipo 9 (Temporary Children) no;
    y en ningun otro grupo hay referencias. Medido el 2026-09-25 sobre los 10
    plugins oficiales: 879.753 referencias, las 59.240 de grupos 8 con 0x400
    (24.838 del mundo + 34.402 de interiores), ninguna de las 820.513 de
    grupos 9 (483.178 interiores + 337.335 exteriores), cero en otro grupo.
    Las celdas exteriores no tienen grupo 8: las referencias persistentes del
    mundo viven en la celda persistente (la CELL directamente bajo el World
    Children, p. ej. 0001A270 de WhiterunWorld).
    El REFR de RetreteVIP v1.1 estaba en ese grupo 8 con banderas 0 -- la
    unica referencia de la instalacion con esa combinacion -- y el objeto no
    aparecio en el juego.

REGLA 6 -- cada entrada no nula del OFST de un WRLD cae dentro del archivo.
    OFST es una tabla de offsets de las celdas del mundo en ESE archivo. Los
    94 WRLD de los 10 plugins la llevan, overrides incluidos, asi que llevarla
    no es el defecto: 76.250 entradas y 0 fuera de su archivo. El WRLD del
    v1.1, copiado crudo de Skyrim.esm, traia 113 entradas y las 113 se salian
    de un archivo de 11.289 bytes: apuntaban a Skyrim.esm. Un OFST que cae
    adentro sale como OBSERVACION: xEdit lo quita por defecto ("Remove OFST
    Data", whatsnew.md de SSEEdit 4.1.5f).
    OBSERVACION, no regla: un override de WRLD con RNAM (referencias grandes).
    10 de los 45 overrides oficiales de WRLD lo llevan. Pero copiado de un
    master pisa el de los DLC: el v1.1 traia las 40 RNAM de WhiterunWorld de
    Skyrim.esm y los overrides que ganan (Dawnguard, HearthFires, Fish) no
    tienen ninguna.

REGLA 7 -- en un plugin NO localizado (bandera 0x80 del TES4 apagada), cada
    FULL es texto: termina en un NUL y no tiene otro antes. En uno localizado
    FULL es un ID de 4 bytes a los .STRINGS: las 34.956 FULL de los 10
    plugins (localizados los 10) miden 4. Copiado crudo a un plugin no
    localizado, el juego lee el ID como texto: la FULL de WhiterunWorld es el
    ID 0x4C20, bytes 20 4C 00 00, que se lee " L". Lo que la regla NO ve: 4.775
    de esos 34.956 IDs (13,7 %) tienen sus bytes con forma de texto de 3
    caracteres; por eso una FULL de 4 bytes en un override de un plugin no
    localizado deja ademas una OBSERVACION.

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
import nif_nodos  # noqa: E402

VERSION_ACTUAL = 44
LIMITE_DETALLE = 10
OFFSET_VERSION = 20

N_SE = 10273          # records de los 5 plugins autorados para SE, todos en 44
N_INDICE = 1188811    # records de los 10 plugins, sin el TES4
N_WEAP = 3359         # WEAP de los 10 plugins: DATA 10 y DNAM 100 en todas
N_WNAM = 463          # armas base con WNAM: todas apuntan a un STAT
COMPRIMIDO = 0x00040000

# REGLA 4: el Prn del NIF segun DNAM[0]. 305 de 306 armas del jugador; la
# excepcion es NordicGreatSword.nif. El 8 (baston) no tiene regla: WeaponStaff
# en 21, SHIELD en 18. census/hallazgos_plugins.md, entrada 17.
PRN_POR_TIPO = {1: "WeaponSword", 2: "WeaponDagger", 3: "WeaponAxe",
                4: "WeaponMace", 5: "WeaponBack", 6: "WeaponBack",
                7: "WeaponBow", 9: "WeaponBow"}
TIPO_BASTON = 8
N_PRN = 306

# REGLA 5: referencias colocadas y su grupo. Medido el 2026-09-25, 10 plugins.
REFERENCIAS = ("REFR", "ACHR", "PGRE", "PMIS", "PHZD", "PARW", "PBAR",
               "PBEA", "PCON", "PFLA")
PERSISTENTE = 0x400
GRUPO_PERSISTENTE = 8
GRUPO_TEMPORAL = 9
N_REF = 879753
N_REF_G8 = 59240
N_REF_G9 = 820513

# REGLA 6 y su observacion
N_WRLD_OFST = 94          # WRLD oficiales, todos con OFST
N_OFST_ENTRADAS = 76250   # entradas no nulas, 0 fuera de su archivo
N_WRLD_OVERRIDE = 45
N_OVERRIDE_RNAM = 10

# REGLA 7
LOCALIZADO = 0x80
N_FULL_LOC = 34956        # FULL de los 10 plugins, todas de 4 bytes
N_FULL_PARECE_TEXTO = 4775


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
    modl = subs.get("MODL")
    return {"DATA": len(subs["DATA"]) if "DATA" in subs else None,
            "DNAM": len(subs["DNAM"]) if "DNAM" in subs else None,
            "WNAM": struct.unpack_from("<I", wnam)[0]
            if wnam and len(wnam) == 4 else None,
            "anim": subs["DNAM"][0] if subs.get("DNAM") else None,
            "MODL": modl.split(b"\x00")[0].decode("cp1252", "replace")
            if modl else None,
            "plantilla": "CNAM" in subs}


def _resolver(base, ruta_modl):
    """La ruta del NIF bajo `base`, sin distinguir mayusculas -- como el
    sistema de archivos del juego --, o None. Los MODL van relativos a meshes/
    y sin ese prefijo (12.618 de 12.618, hallazgo 4)."""
    p = base
    for parte in [x for x in ruta_modl.replace("/", "\\").split("\\") if x]:
        if not os.path.isdir(p):
            return None
        n = dict((x.lower(), x) for x in os.listdir(p)).get(parte.lower())
        if n is None:
            return None
        p = os.path.join(p, n)
    return p if os.path.isfile(p) else None


def _prn(meshes, w):
    """Pone en `w` lo que se sabe del Prn de su NIF bajo `meshes`."""
    w["nif"] = _resolver(meshes, w["MODL"]) if w.get("MODL") else None
    w["prn"] = None
    w["nif_error"] = None
    if w["nif"]:
        try:
            w["prn"] = nif_nodos.cadena_extra(nif_nodos.leer(w["nif"]), "Prn")
        except (ValueError, IndexError, struct.error, OSError) as e:
            w["nif_error"] = "%s: %s" % (type(e).__name__, e)


def leer(ruta, meshes=None):
    """{records: [{tipo, form_id, version}], n_masters, error}.

    El NIF de cada WEAP se busca en `meshes` -- por defecto la carpeta meshes/
    al lado del plugin, que es como viene un mod."""
    try:
        with open(ruta, "rb") as fh:
            d = fh.read()
    except OSError as e:
        return {"records": [], "n_masters": 0,
                "error": "no se pudo abrir: %s" % e}
    if len(d) < 24 or d[:4] != b"TES4":
        return {"records": [], "n_masters": 0,
                "error": "no empieza con un TES4: no es un plugin"}
    recs, cerro = esl.recorrer_con_grupos(d)
    if not cerro:
        return {"records": [], "n_masters": 0,
                "error": "el recorrido no embaldosa el archivo: esta truncado "
                         "o un tamano declarado miente"}
    records = []
    for tag, o, grupo in recs:
        r = {"tipo": tag.decode("ascii", "replace"),
             "form_id": struct.unpack_from("<I", d, o + 12)[0],
             "version": struct.unpack_from("<H", d, o + OFFSET_VERSION)[0],
             "banderas": struct.unpack_from("<I", d, o + 8)[0],
             "grupo": grupo}
        if tag != b"TES4" and (tag == b"WRLD" or b"FULL" in d[
                o + 24:o + 24 + struct.unpack_from("<I", d, o + 4)[0]]
                or r["banderas"] & COMPRIMIDO):
            try:
                subs = subrecords(d, o)
            except (ValueError, zlib.error, struct.error) as e:
                return {"records": [], "n_masters": 0,
                        "error": "%s %08X ilegible: %s"
                                 % (r["tipo"], r["form_id"], e)}
            full = [b for t, b in subs if t == "FULL"]
            if full:
                r["full"] = full[0]
            if tag == b"WRLD":
                # Los 94 OFST oficiales miden multiplo de 4. Con 1-3 bytes
                # de sobra, `len // 4` los tiraba y el OFST pasaba entero
                # "adentro": no se lee lo que no se puede leer completo.
                for t, b in subs:
                    if t == "OFST" and len(b) % 4:
                        return {"records": [], "n_masters": 0,
                                "error": "WRLD %08X ilegible: OFST de %d "
                                         "bytes, no es multiplo de 4 (los "
                                         "%d oficiales lo son)"
                                         % (r["form_id"], len(b),
                                            N_WRLD_OFST)}
                r["wrld"] = {
                    "rnam": sum(1 for t, _b in subs if t == "RNAM"),
                    "ofst": [x for t, b in subs if t == "OFST"
                             for x in struct.unpack_from(
                                 "<%dI" % (len(b) // 4), b) if x]
                    if any(t == "OFST" for t, _b in subs) else None}
        if tag == b"WEAP":
            try:
                r["weap"] = _datos_weap(d, o)
            except (ValueError, zlib.error, struct.error) as e:
                return {"records": [], "n_masters": 0,
                        "error": "WEAP %08X ilegible: %s" % (r["form_id"], e)}
            _prn(meshes or os.path.join(os.path.dirname(
                os.path.abspath(ruta)), "meshes"), r["weap"])
        records.append(r)
    return {"records": records, "n_masters": len(esl.masters(d)),
            "error": None, "tam": len(d),
            "localizado": bool(struct.unpack_from("<I", d, 8)[0]
                               & LOCALIZADO)}


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
    fallas += regla_referencias(info["records"], notas)
    fallas += _reglas_wrld(info, notas)
    fallas += _regla_full(info, notas)

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
        fallas += _regla_prn(cual, w, notas)
    if armas:
        notas.append("OBS %d WEAP comprobada(s)" % len(armas))
    return fallas


def regla_referencias(records, notas):
    """REGLA 5. Solo mira los records que `leer` marco con su grupo y sus
    banderas: un dict armado a mano sin esas claves no se juzga, y la nota
    dice cuantas se comprobaron para que cero no pase por exito."""
    refs = [r for r in records
            if r["tipo"] in REFERENCIAS and "grupo" in r and "banderas" in r]
    malas = []
    for r in refs:
        persistente = bool(r["banderas"] & PERSISTENTE)
        g = r["grupo"]
        if g == GRUPO_PERSISTENTE and not persistente:
            que = ("esta en un grupo 8 (Persistent Children) sin la bandera "
                   "0x400 (banderas 0x%08X). Las %d referencias oficiales de "
                   "grupos 8 la tienen, sin excepcion; asi salio el REFR de "
                   "RetreteVIP v1.1, que no aparecio en el juego. Con "
                   "census/escritor_plugin.py: record(..., banderas=0x400)"
                   % (r["banderas"], N_REF_G8))
        elif g == GRUPO_TEMPORAL and persistente:
            que = ("esta en un grupo 9 (Temporary Children) con la bandera "
                   "0x400. Ninguna de las %d referencias oficiales de grupos "
                   "9 la tiene: o va sin la bandera, o va en el grupo 8 de "
                   "la celda persistente" % N_REF_G9)
        elif g not in (GRUPO_PERSISTENTE, GRUPO_TEMPORAL):
            que = ("esta en un grupo de tipo %s. Las %d referencias "
                   "oficiales estan en grupos 8 o 9" % (g, N_REF))
        else:
            continue
        malas.append("REGLA referencia persistente: %s %08X %s."
                     % (r["tipo"], r["form_id"], que))
    if refs:
        notas.append("OBS %d referencia(s) colocada(s) comprobada(s)"
                     % len(refs))
    return _cortar(malas[:LIMITE_DETALLE], len(malas),
                   "referencia en el grupo equivocado")


def _reglas_wrld(info, notas):
    """REGLA 6 y la observacion de RNAM. `tam` es el largo del archivo."""
    fallas = []
    n = info["n_masters"]
    for r in info["records"]:
        w = r.get("wrld")
        if not w:
            continue
        cual = "WRLD %08X" % r["form_id"]
        ofst = w["ofst"]
        if ofst is not None and "tam" in info:
            fuera = [x for x in ofst if x >= info["tam"]]
            if fuera:
                fallas.append(
                    "REGLA WRLD OFST: %s lleva un OFST con %d de %d entradas "
                    "fuera del archivo (%d bytes; la mayor, %d): es la tabla "
                    "de offsets de OTRO archivo, copiada cruda. En los %d WRLD "
                    "oficiales, 0 de %d entradas caen fuera del suyo. Borra el "
                    "OFST (xEdit lo hace por defecto)."
                    % (cual, len(fuera), len(ofst), info["tam"], max(fuera),
                       N_WRLD_OFST, N_OFST_ENTRADAS))
            else:
                notas.append("OBS %s lleva OFST (%d entradas, todas dentro "
                             "del archivo). xEdit lo quita por defecto."
                             % (cual, len(ofst)))
        if w["rnam"] and (r["form_id"] >> 24) < n:
            notas.append(
                "OBS %s es un override con %d RNAM (referencias grandes). %d "
                "de los %d overrides oficiales de WRLD llevan RNAM; si los "
                "copiaste del master, pisan los de los DLC (el v1.1 traia "
                "las 40 de Skyrim.esm y los overrides que ganan no tienen "
                "ninguna)." % (cual, w["rnam"], N_OVERRIDE_RNAM,
                               N_WRLD_OVERRIDE))
    return fallas


def es_texto(b):
    """Un zstring: termina en NUL y no tiene otro antes."""
    return len(b) > 0 and b.find(b"\x00") == len(b) - 1


def _regla_full(info, notas):
    """REGLA 7. Solo en un plugin que `leer` marco como NO localizado."""
    if info.get("localizado") is not False:
        return []
    malas = []
    for r in info["records"]:
        b = r.get("full")
        if b is None:
            continue
        cual = "%s %08X" % (r["tipo"], r["form_id"])
        if not es_texto(b):
            malas.append(
                "REGLA FULL: %s tiene FULL %s (%d bytes) y el plugin no es "
                "localizado (bandera 0x80 del TES4 apagada): no es texto. "
                "Es un ID de .STRINGS copiado de un master localizado -- las "
                "%d FULL oficiales miden 4 -- y el juego lo lee como texto "
                "(la de WhiterunWorld sale \" L\"). Escribi el nombre."
                % (cual, b.hex(" ").upper(), len(b), N_FULL_LOC))
        elif len(b) == 4 and (r["form_id"] >> 24) < info["n_masters"]:
            notas.append(
                "OBS %s es un override con FULL de 4 bytes (%r): puede ser un "
                "ID de .STRINGS con forma de texto, como %d de los %d IDs "
                "oficiales." % (cual, b[:-1].decode("cp1252", "replace"),
                                N_FULL_PARECE_TEXTO, N_FULL_LOC))
    return _cortar(malas[:LIMITE_DETALLE], len(malas), "FULL que no es texto")


def _regla_prn(cual, w, notas):
    """REGLA 4: el Prn del NIF corresponde al tipo de animacion. Solo corre
    si `leer` busco el NIF (clave "nif"); si no lo encontro, lo dice."""
    if "nif" not in w or w.get("anim") in (None, 0):
        return []
    if not w["nif"]:
        notas.append("OBS %s: no se encontro el NIF %r junto al plugin: Prn "
                     "no verificado." % (cual, w.get("MODL")))
        return []
    if w["nif_error"]:
        return ["REGLA WEAP Prn: %s: el NIF %s no se pudo leer (%s)."
                % (cual, w["MODL"], w["nif_error"])]
    if w["anim"] == TIPO_BASTON:
        notas.append("OBS %s es un baston: Prn %s. Los bastones vanilla no "
                     "tienen regla (WeaponStaff en 21, SHIELD en 18)."
                     % (cual, w["prn"]))
        return []
    esperado = PRN_POR_TIPO.get(w["anim"])
    if esperado is None:
        return []
    if w["prn"] == esperado:
        # Un control que pasa en silencio no se distingue de uno que no corrio
        notas.append("OBS %s: Prn %s, el de su tipo (%d)"
                     % (cual, w["prn"], w["anim"]))
        return []
    tiene = "sin Prn" if w["prn"] is None else "con Prn %s" % w["prn"]
    return ["REGLA WEAP Prn: %s es de tipo %d y su NIF esta %s; se esperaba "
            "%s. El Prn es el nodo del que cuelga el arma envainada, y sigue "
            "al tipo en %d de %d armas vanilla del jugador."
            % (cual, w["anim"], tiene, esperado, N_PRN - 1, N_PRN)]


def falsificar_prn(data, meshes):
    """Sobre las armas base REALES de los 10 plugins, con sus NIF: las que
    pasan tal cual sirven de patron, y ponerles cualquier otro Prn tiene que
    reprobar. Los plugins no se juzgan enteros -- los masters de 2011 no pasan
    la REGLA 1 --: solo la REGLA 4, arma por arma."""
    patrones = roturas = 0
    no_patron = []
    fallas = []
    nombres = []
    if os.path.isdir(data):
        nombres = sorted(n for n in os.listdir(data)
                         if n.lower().endswith((".esm", ".esl", ".esp")))
    valores = sorted(set(PRN_POR_TIPO.values()))
    for nombre in nombres:
        info = leer(os.path.join(data, nombre), meshes=meshes)
        if info["error"]:
            continue
        for r in info["records"]:
            w = r.get("weap")
            if (not w or w["plantilla"] or not w["nif"]
                    or w["anim"] not in PRN_POR_TIPO):
                continue
            cual = "%s %08X" % (nombre, r["form_id"])
            if _regla_prn(cual, w, []):
                no_patron.append("%s  Prn=%s" % (w["MODL"], w["prn"]))
                continue
            patrones += 1
            for otro in [v for v in valores if v != w["prn"]] + [None]:
                roturas += 1
                if not _regla_prn(cual, dict(w, prn=otro), []):
                    fallas.append("%s con Prn %s: no reprobo" % (cual, otro))
    # Las que no pasan tal cual se MUESTRAN, no se describen: sobre el Data
    # vanilla son maniquies de Clutter\DummyItems, el arco de la esfera
    # dwemer, picos decorativos, un emblema y NordicGreatSword (hallazgo 17),
    # pero sobre otro Data serian otras.
    distintas = sorted(set(no_patron))
    print("falsificar-prn: %d armas de patron, %d roturas, %d fallas. "
          "No pasan tal cual: %d (%d NIF distintos)"
          % (patrones, roturas, len(fallas), len(no_patron), len(distintas)))
    for x in distintas[:LIMITE_DETALLE]:
        print("   no es patron: %s" % x)
    if len(distintas) > LIMITE_DETALLE:
        print("   ... y %d mas" % (len(distintas) - LIMITE_DETALLE))
    for x in fallas[:LIMITE_DETALLE]:
        print("  FALLA %s" % x)
    if patrones == 0:
        print("FALLA: cero armas utilizables -- no comprobar nada no es "
              "exito")
        return 1
    return 1 if fallas else 0


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

    # REGLA 4: cada tipo con su Prn pasa, y con cualquier otro (o sin Prn) no
    def con_prn(anim, prn, nif="x.nif"):
        info = arma()
        info["records"][2]["weap"].update(
            anim=anim, MODL="x.nif", nif=nif, prn=prn, nif_error=None)
        return info

    valores = sorted(set(PRN_POR_TIPO.values()))
    for anim, bueno in sorted(PRN_POR_TIPO.items()):
        caso("tipo %d con %s" % (anim, bueno), con_prn(anim, bueno), False,
             "REGLA")
        for otro in [v for v in valores if v != bueno] + [None]:
            caso("tipo %d con %s" % (anim, otro), con_prn(anim, otro), True,
                 "WEAP Prn")
    for prn in ("WeaponStaff", "SHIELD"):
        caso("baston con %s" % prn, con_prn(TIPO_BASTON, prn), False, "REGLA")
    caso("NIF no encontrado", con_prn(6, None, nif=None), False, "REGLA")

    # REGLA 5: cada tipo de referencia, en cada grupo, con y sin 0x400
    def ref(tipo, grupo, banderas):
        return {"records": [_rec(tipo="TES4", form_id=0),
                            dict(_rec(tipo=tipo, form_id=0x01000801),
                                 grupo=grupo, banderas=banderas)],
                "n_masters": 1, "error": None}

    for t in REFERENCIAS:
        caso("%s en grupo 8 con 0x400" % t, ref(t, 8, 0x400), False, "REGLA")
        caso("%s en grupo 8 con banderas 0 (el v1.1)" % t, ref(t, 8, 0),
             True, "referencia persistente")
        caso("%s en grupo 8 con otras banderas" % t, ref(t, 8, 0x800),
             True, "referencia persistente")
        caso("%s en grupo 9 sin 0x400" % t, ref(t, 9, 0), False, "REGLA")
        caso("%s en grupo 9 con 0x400" % t, ref(t, 9, 0x400), True,
             "referencia persistente")
        for g in (None, 0, 1, 6, 10):
            caso("%s en grupo %s" % (t, g), ref(t, g, 0x400), True,
                 "referencia persistente")
    caso("un STAT en grupo 8 no es referencia", ref("STAT", 8, 0), False,
         "REGLA")

    # REGLA 6: el OFST, contra el largo del archivo
    def mundo(ofst=None, rnam=0, full=b"Carrera Blanca\x00", tam=11289,
              localizado=False, grupo_ref=8, banderas_ref=0x400):
        w = {"rnam": rnam, "ofst": ofst}
        return {"records": [
            _rec(tipo="TES4", form_id=0),
            dict(_rec(tipo="WRLD", form_id=0x0001A26F), wrld=w, full=full,
                 grupo=0, banderas=0),
            dict(_rec(tipo="CELL", form_id=0x0001A270), grupo=1,
                 banderas=0x400),
            dict(_rec(tipo="REFR", form_id=0x01000801), grupo=grupo_ref,
                 banderas=banderas_ref)],
            "n_masters": 1, "error": None, "tam": tam,
            "localizado": localizado}

    caso("el v1.2: sin OFST, sin RNAM, FULL de texto, REFR con 0x400",
         mundo(), False, "REGLA")
    # Cada una de las tres razones, por separado: con "REGLA" a secas, una
    # sola alcanzaba para que el caso pasara.
    for marca in ("referencia persistente", "WRLD OFST", "REGLA FULL"):
        caso("el v1.1 reprueba por %s" % marca,
             mundo(ofst=[57966, 393059], rnam=40, full=b" L\x00\x00",
                   banderas_ref=0), True, marca)
    for ofst in ([11289], [1, 11289], [0xFFFFFFFF]):
        caso("OFST %r en 11289 bytes" % ofst, mundo(ofst=ofst), True,
             "WRLD OFST")
    caso("OFST dentro del archivo", mundo(ofst=[24, 11288]), False, "REGLA")
    caso("OFST vacio", mundo(ofst=[]), False, "REGLA")
    caso("RNAM en un override es observacion", mundo(rnam=40), False,
         "REGLA")

    # REGLA 7: FULL en un plugin no localizado
    for full in (b"\x20\x4C\x01\x02", b"ABCD", b" L\x00\x00",
                 b"\x00\x00\x00\x00", b"", b"Carrera\x00Blanca\x00",
                 b"sin nul"):
        caso("FULL %r sin localizar" % full, mundo(full=full), True,
             "REGLA FULL")
        if len(full) == 4:
            caso("FULL %r localizado" % full,
                 mundo(full=full, localizado=True), False, "REGLA")
    # b"\x00" es un nombre vacio, texto valido: no es un ID
    for full in (b"Axe\x00", b"A\x00", b"\x00", b"Retrete VIP\x00"):
        caso("FULL %r sin localizar" % full, mundo(full=full), False, "REGLA")

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
    u2, r2, f2 = _falsificar_mundo(raiz, nombres)
    roturas += r2
    fallas += f2
    print("falsificar: %d plugins, %d comprobaciones, %d fallas"
          % (usados, roturas, len(fallas)))
    if u2 == 0:
        print("FALLA: ninguna referencia real se pudo torcer -- no comprobar "
              "nada no es exito")
        return 1
    for x in fallas:
        print("  FALLA %s" % x)
    if usados == 0:
        print("FALLA: cero plugins utilizables -- no comprobar nada no es "
              "exito")
        return 1
    return 1 if fallas else 0


def _falsificar_mundo(raiz, nombres):
    """REGLAS 5, 6 y 7 sobre TODOS los plugins, masters de 2011 incluidos:
    se juzgan solas, como la REGLA 4 en falsificar_prn, porque la REGLA 1 no
    vale para los masters. Primero se mide (tiene que dar cero excepciones
    tal cual) y despues se tuerce: una referencia real del grupo 8 pierde la
    bandera, una del grupo 9 la gana, un OFST real recibe una entrada fuera
    del archivo, y una FULL real de un plugin localizado se juzga como si el
    plugin no lo fuera -- que es lo que hizo el v1.1 al copiar el WRLD.
    Devuelve (plugins con referencias torcidas, roturas, fallas)."""
    usados, roturas, fallas = 0, 0, []
    total = {"g8": 0, "g9": 0, "otro": 0, "excepciones": 0}
    for nombre in nombres:
        info = leer(os.path.join(raiz, nombre))
        if info["error"]:
            print("   %-34s ilegible: %s" % (nombre, info["error"]))
            continue
        recs = info["records"]
        refs = [j for j, r in enumerate(recs) if r["tipo"] in REFERENCIAS]
        g8 = [j for j in refs if recs[j]["grupo"] == GRUPO_PERSISTENTE]
        g9 = [j for j in refs if recs[j]["grupo"] == GRUPO_TEMPORAL]
        exc = len(regla_referencias(recs, []))
        total["g8"] += len(g8)
        total["g9"] += len(g9)
        total["otro"] += len(refs) - len(g8) - len(g9)
        total["excepciones"] += exc
        mutaciones = []
        if exc:
            fallas.append("%s: %d referencias reprueban tal cual" % (nombre,
                                                                     exc))
        else:
            if g8:
                j = g8[len(g8) // 2]
                mutaciones.append((
                    "ref del grupo 8 sin 0x400", "referencia",
                    recs[:j] + [dict(recs[j], banderas=recs[j]["banderas"]
                                     & ~PERSISTENTE)] + recs[j + 1:]))
            if g9:
                j = g9[len(g9) // 2]
                mutaciones.append((
                    "ref del grupo 9 con 0x400", "referencia",
                    recs[:j] + [dict(recs[j], banderas=recs[j]["banderas"]
                                     | PERSISTENTE)] + recs[j + 1:]))
            if mutaciones:
                usados += 1
        mundos = [j for j, r in enumerate(recs)
                  if r.get("wrld") and r["wrld"]["ofst"]]
        if mundos and not _reglas_wrld(info, []):
            j = mundos[len(mundos) // 2]
            w = recs[j]["wrld"]
            mutaciones.append((
                "OFST con una entrada fuera", "wrld",
                recs[:j] + [dict(recs[j], wrld=dict(
                    w, ofst=w["ofst"] + [info["tam"]]))] + recs[j + 1:]))
        ids = [j for j, r in enumerate(recs)
               if "full" in r and not es_texto(r["full"])]
        if info["localizado"] and ids:
            j = ids[len(ids) // 2]
            mutaciones.append(("FULL de %s en un plugin no localizado"
                               % recs[j]["tipo"], "full", recs))
        for que, regla, torcidos in mutaciones:
            roturas += 1
            t = dict(info, records=torcidos)
            if regla == "referencia":
                f = regla_referencias(torcidos, [])
            elif regla == "wrld":
                f = _reglas_wrld(t, [])
            else:
                f = _regla_full(dict(t, localizado=False), [])
            if not f:
                fallas.append("%s / %s: no reprobo" % (nombre, que))
        print("   %-34s %d refs (%d en grupo 8, %d en grupo 9), %d "
              "excepciones, %d roturas de REGLAS 5-7"
              % (nombre, len(refs), len(g8), len(g9), exc, len(mutaciones)))
    print("   referencias: %d en grupo 8, %d en grupo 9, %d en otro grupo, "
          "%d excepciones (medido el 2026-09-25: %d, %d, 0, 0)"
          % (total["g8"], total["g9"], total["otro"], total["excepciones"],
             N_REF_G8, N_REF_G9))
    return usados, roturas, fallas


def main(argv):
    if len(argv) == 1 and argv[0] == "--autotest":
        return autotest()
    if len(argv) == 2 and argv[0] == "--falsificar":
        return falsificar(argv[1])
    if len(argv) == 3 and argv[0] == "--falsificar-prn":
        return falsificar_prn(argv[1], argv[2])
    if argv and not any(a.startswith("--") for a in argv):
        return revisar(argv)
    print("uso: verificar_plugin.py <plugin> [...] | --autotest | "
          "--falsificar <carpeta Data> | --falsificar-prn <carpeta Data> "
          "<carpeta meshes>")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
