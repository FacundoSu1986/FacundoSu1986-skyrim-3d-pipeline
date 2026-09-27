# -*- coding: utf-8 -*-
"""Arma un mod de prueba para mirar en el juego lo que PyNifly le hace a un
estatico vanilla (issue #31): un ESL con DOS STAT por caso, el original y el
que paso ida y vuelta, para ponerlos uno encima del otro con `placeatme`.

    python fixtures/prueba_en_el_juego.py <Skyrim.esm> <meshes vanilla> <ida y vuelta> <salida> <caso.nif> [...]
    python fixtures/prueba_en_el_juego.py --autotest

<ida y vuelta> es la carpeta que deja `fixtures/ida_y_vuelta_pynifly.py`, con
las mismas rutas relativas que <meshes vanilla>. En <salida> quedan el ESL, los
NIF bajo `meshes/prueba31/original/` y `meshes/prueba31/idayvuelta/` --rutas
propias: no pisa ningun archivo vanilla-- y `prueba31.json` con la tabla de
FormIDs.

EL STAT SE COPIA DEL VANILLA
----------------------------
Cada caso usa el STAT de Skyrim.esm cuyo MODL es ese NIF: se copian TODOS sus
subrecords (OBND, MODT, DNAM, lo que traiga, en su orden) y cambian solo el
EDID y el MODL. Los campos que "lleva el vanilla" no se adivinan: se leen.
La version del record (casi siempre 39) va con ellos: el MODT y el DNAM
cambian de layout con ella, y la primera version de este mod, que los
escribia con 44, cerraba el juego en la pantalla de Bethesda (2026-09-27;
las leyes en census/escritor_plugin.py, comprobar_layout). Por eso la REGLA 1
de skills/asset-nuevo-skyrim/scripts/verificar_plugin.py, que pide 44 en todo,
reprueba este ESL: es para records escritos con el layout de 44. El que dice
si version y layout coinciden es SSEEdit ("Check for errors": 0). Un
NIF que en el vanilla no es un STAT (un ACTI, un MISC, un MSTT) no entra: sale
con 2 y dice cual. Si el NIF tiene varios STAT, se usa el primero y el reporte
dice cuantos habia.

LO QUE ESTO NO RESUELVE
-----------------------
Mirarlo. El reporte dice que poner con la consola; lo que se ve es lo unico
que contesta la issue.
"""
import json
import os
import shutil
import struct
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_AQUI, "..", "census"))
import escritor_plugin as E  # noqa: E402
import parser_plugin  # noqa: E402

CARPETA = "prueba31"
VARIANTES = ("original", "idayvuelta")
MAESTRO = "Skyrim.esm"
PRIMER_ID = 0x800
OFFSET_VERSION = 20        # la version del record, en su cabecera


def modl_de(rel):
    """Ruta del MODL de un NIF relativo a meshes/: barras invertidas, en
    minusculas, como las compara el juego."""
    return rel.replace("/", "\\").lower()


def modl_de_prueba(rel, variante):
    return "%s\\%s\\%s" % (CARPETA, variante, modl_de(rel))


def edid_de(rel, variante):
    """Un EDID corto y unico: P31, la variante y el nombre del NIF."""
    base = os.path.splitext(os.path.basename(rel))[0]
    limpio = "".join(ch for ch in base if ch.isalnum())
    return "P31%s%s" % ("Orig" if variante == "original" else "Ida", limpio)


def buscar_stats(plugin, rels):
    """{rel: [(tipo, form_id, [(tipo_sub, datos)], version)]} de cada record
    que tiene ese NIF como MODL, de cualquier tipo: el llamador decide que
    hacer con un NIF que no es STAT."""
    buscados = {modl_de(r): r for r in rels}
    encontrados = {r: [] for r in rels}
    for tipo, off, _tam, fid in plugin.records:
        try:
            subs = plugin.subrecords(off)
        except parser_plugin.PluginInvalido:
            continue
        modl = next((plugin.d[o:o + n] for t, o, n in subs if t in (b"MODL", "MODL")), None)
        if modl is None:
            continue
        rel = buscados.get(modl.rstrip(b"\x00").decode("latin-1").lower())
        if rel is not None:
            t = tipo.decode() if isinstance(tipo, bytes) else tipo
            version, = struct.unpack_from("<H", plugin.d, off + OFFSET_VERSION)
            encontrados[rel].append((t, fid, [((s.decode() if isinstance(s, bytes) else s),
                                               plugin.d[o:o + n]) for s, o, n in subs],
                                     version))
    return encontrados


def stat_de_prueba(subs_vanilla, form_id, edid, modl, version):
    """El record STAT: los subrecords del vanilla en su orden, con el EDID y
    el MODL cambiados, y la `version` del vanilla, que es la que dice como se
    leen sus bytes. Sin EDID o sin MODL en el vanilla no hay de donde copiar
    la forma del record: ValueError."""
    tipos = [t for t, _ in subs_vanilla]
    if "EDID" not in tipos or "MODL" not in tipos:
        raise ValueError("el STAT vanilla no trae EDID y MODL: %s" % tipos)
    subs = []
    for t, datos in subs_vanilla:
        if t == "EDID":
            datos = E.zstr(edid)
        elif t == "MODL":
            datos = E.zstr(modl)
        subs.append(E.sub(t, datos))
    return E.record("STAT", form_id, subs, version=version)


def plan(encontrados):
    """[(form_id, edid, modl, rel, variante, form_id_vanilla, n_stats)] y los
    rels que no son STAT en el vanilla. Dos FormIDs por caso, en orden."""
    filas, fuera = [], []
    fid = PRIMER_ID
    for rel, recs in encontrados.items():
        stats = [r for r in recs if r[0] == "STAT"]
        if not stats:
            fuera.append((rel, sorted({r[0] for r in recs}) or ["ninguno"]))
            continue
        for variante in VARIANTES:
            filas.append((0x01000000 | fid, edid_de(rel, variante),
                          modl_de_prueba(rel, variante), rel, variante,
                          stats[0][1], len(stats)))
            fid += 1
    return filas, fuera


def armar(esm, meshes, ida, salida, rels):
    """Escribe el mod. Devuelve el reporte; SystemExit(2) si un caso no es
    STAT o falta un NIF."""
    encontrados = buscar_stats(parser_plugin.Plugin(esm), rels)
    filas, fuera = plan(encontrados)
    if fuera:
        raise SystemExit("no son STAT en %s: %s" % (os.path.basename(esm), fuera))
    if not filas:
        raise SystemExit("cero casos: nada que armar no es exito")
    for rel in rels:
        for base in (meshes, ida):
            if not os.path.isfile(os.path.join(base, rel)):
                raise SystemExit("falta %s" % os.path.join(base, rel))
    records = []
    for fid, edid, modl, rel, _variante, _fv, _n in filas:
        _t, _f, subs, version = next(r for r in encontrados[rel] if r[0] == "STAT")
        records.append(stat_de_prueba(subs, fid, edid, modl, version))
    os.makedirs(salida, exist_ok=True)
    esl = os.path.join(salida, "%s.esl" % CARPETA)
    E.escribir(esl, [MAESTRO], [E.grupo("STAT", records)], [f for f, *_ in filas],
               autor="skyrim-3d-pipeline, issue #31",
               descripcion="PyNifly ida y vuelta: original contra exportado")
    for rel in rels:
        for variante, base in zip(VARIANTES, (meshes, ida)):
            destino = os.path.join(salida, "meshes", CARPETA, variante, rel)
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.copyfile(os.path.join(base, rel), destino)
    reporte = {"esl": esl, "maestro": MAESTRO, "casos": [
        {"form_id_local": "%03X" % (fid & 0xFFF), "edid": edid, "modl": modl,
         "nif": rel, "variante": variante, "stat_vanilla": "%08X" % fv,
         "stats_vanilla_con_ese_nif": n}
        for fid, edid, modl, rel, variante, fv, n in filas]}
    with open(os.path.join(salida, "%s.json" % CARPETA), "w", encoding="utf-8") as fh:
        json.dump(reporte, fh, indent=1)
    return reporte


# --- autotest ----------------------------------------------------------------

def autotest():
    """Sobre un maestro sintetico escrito con escritor_plugin. Cero casos NO
    es exito."""
    import tempfile
    tmp = tempfile.mkdtemp()
    fallas, n = [], [0]

    def exigir(cond, texto):
        n[0] += 1
        if not cond:
            fallas.append(texto)

    # como casi todos los STAT de Skyrim.esm: version 39, MODT en triples sin
    # encabezado y DNAM de 8 bytes
    obnd = struct.pack("<6h", -10, -20, 0, 10, 20, 30)
    dnam = struct.pack("<fI", 90.0, 0)
    modt = struct.pack("<I4sI", 0x235EFA34, b"dds\x00", 0x0D8AC7C5)

    def stat(fid, edid, modl):
        return E.record("STAT", fid, [E.sub("EDID", E.zstr(edid)), E.sub("OBND", obnd),
                                      E.sub("MODL", E.zstr(modl)), E.sub("MODT", modt),
                                      E.sub("DNAM", dnam)], version=39)
    maestro = os.path.join(tmp, "Maestro.esm")
    recs = [stat(0x00012345, "EstanteVanilla", "Architecture\\Solitude\\Clutter\\SMDShelf01.nif"),
            stat(0x00012346, "OtroEstante", "architecture\\solitude\\clutter\\smdshelf01.nif"),
            E.record("MISC", 0x00012347, [E.sub("EDID", E.zstr("Jarra")),
                                          E.sub("MODL", E.zstr("clutter\\jarra.nif"))])]
    E.escribir(maestro, [], [E.grupo("STAT", recs[:2]), E.grupo("MISC", recs[2:])],
               [0x00012345, 0x00012346, 0x00012347], esl=False)
    p = parser_plugin.Plugin(maestro)
    enc = buscar_stats(p, ["architecture/solitude/clutter/smdshelf01.nif", "clutter/jarra.nif"])
    exigir(len(enc["architecture/solitude/clutter/smdshelf01.nif"]) == 2,
           "el MODL se compara sin mayusculas: los dos STAT del estante")
    exigir([r[0] for r in enc["clutter/jarra.nif"]] == ["MISC"], "la jarra es un MISC")
    filas, fuera = plan(enc)
    exigir(fuera == [("clutter/jarra.nif", ["MISC"])], "un NIF que no es STAT queda afuera: %r" % (fuera,))
    exigir([f[0] for f in filas] == [0x01000800, 0x01000801],
           "dos FormIDs por caso, desde 0x800, con el maestro en el byte alto: %r" % ([hex(f[0]) for f in filas],))
    exigir([f[4] for f in filas] == list(VARIANTES), "original primero, ida y vuelta despues")
    exigir(filas[0][6] == 2 and filas[0][5] == 0x00012345, "se usa el primer STAT y se cuentan los dos")
    exigir(filas[0][2] == "prueba31\\original\\architecture\\solitude\\clutter\\smdshelf01.nif",
           "MODL propio, bajo prueba31: %r" % filas[0][2])
    exigir(edid_de("a/b/SMD-Shelf_01.nif", "idayvuelta") == "P31IdaSMDShelf01", "EDID limpio")

    # el record: los subrecords del vanilla, en su orden, con EDID y MODL nuevos
    _t, _f, subs, version = enc["architecture/solitude/clutter/smdshelf01.nif"][0]
    exigir(version == 39, "la version del vanilla se lee de su cabecera: %r" % version)
    rec = stat_de_prueba(subs, 0x01000800, "P31OrigSMDShelf01", filas[0][2], version)
    esl = os.path.join(tmp, "prueba31.esl")
    E.escribir(esl, ["Maestro.esm"], [E.grupo("STAT", [rec])], [0x01000800])
    q = parser_plugin.Plugin(esl)
    exigir(q.es_esl and q.maestros() == ["Maestro.esm"], "ESL con su maestro")
    stats = [r for r in q.records if r[0] in (b"STAT", "STAT")]
    exigir(len(stats) == 1 and stats[0][3] == 0x01000800, "un STAT con el FormID pedido")
    exigir(stats and struct.unpack_from("<H", q.d, stats[0][1] + OFFSET_VERSION)[0] == 39,
           "el STAT copiado lleva la version del vanilla, no 44")
    leidos = [((t.decode() if isinstance(t, bytes) else t), q.d[o:o + m])
              for t, o, m in q.subrecords(stats[0][1])]
    exigir([t for t, _ in leidos] == ["EDID", "OBND", "MODL", "MODT", "DNAM"],
           "el orden del vanilla: %r" % [t for t, _ in leidos])
    d = dict(leidos)
    exigir(d["OBND"] == obnd and d["MODT"] == modt and d["DNAM"] == dnam,
           "OBND, MODT y DNAM copiados byte a byte")
    exigir(d["EDID"] == E.zstr("P31OrigSMDShelf01") and d["MODL"] == E.zstr(filas[0][2]),
           "EDID y MODL cambiados")
    try:
        stat_de_prueba([("OBND", obnd)], 0x01000800, "X", "y", 39)
        exigir(False, "un STAT sin EDID ni MODL tenia que rechazarse")
    except ValueError:
        exigir(True, "")
    try:
        stat_de_prueba(subs, 0x01000800, "X", "y", 44)
        exigir(False, "los bytes de un 39 con version 44 tenian que rechazarse: "
                      "cerraban el juego en la pantalla de Bethesda")
    except E.ErrorPlugin:
        exigir(True, "")
    exigir(plan({}) == ([], []), "sin casos, plan vacio")
    shutil.rmtree(tmp, ignore_errors=True)
    for f in fallas:
        print("[FALLA] %s" % f)
    print("autotest: %d comprobaciones, %d fallas" % (n[0], len(fallas)))
    return 1 if fallas or n[0] == 0 else 0


def main(argv):
    if argv == ["--autotest"]:
        return autotest()
    if len(argv) < 5 or any(a.startswith("--") for a in argv):
        print(__doc__)
        return 2
    esm, meshes, ida, salida = argv[:4]
    rels = [r.replace("\\", "/") for r in argv[4:]]
    reporte = armar(esm, meshes, ida, salida, rels)
    for c in reporte["casos"]:
        print("  %s  %-34s %s" % (c["form_id_local"], c["edid"], c["nif"]))
    print("[prueba31] %d STAT en %s" % (len(reporte["casos"]), reporte["esl"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
