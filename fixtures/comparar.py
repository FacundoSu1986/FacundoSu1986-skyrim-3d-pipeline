# -*- coding: utf-8 -*-
"""Compara un NIF contra la referencia vanilla.

    python fixtures/comparar.py --contrato <archivo.nif>
    python fixtures/comparar.py --identico <archivo.nif>

--contrato  comprueba las REGLAS que la referencia demuestra y el censo
            respalda. Sirve para un asset nuevo.
--identico  compara campo por campo contra fixtures/roadsignwhiterun01.json.
            Sirve para regresion sobre la referencia misma.

Exit 0 si pasa, 1 si no.

REGLAS Y OBSERVACIONES NO SON LO MISMO
--------------------------------------
Una REGLA reprueba y lleva atras el numero de archivos del censo que la
cumplen. Si no tiene numero, no esta.

Una OBSERVACION se informa y no reprueba. Ahi viven las cosas que la referencia
tiene pero que el censo muestra que NO son universales.

La distincion importa porque el modo de fallar de este repo es al reves del
habitual -- no que falten reglas, sino que sobren inventadas. El ejemplo caro:
"toda ruta de textura empieza con textures\\" parece obvio y reprobaria el
12,2 % del corpus vanilla, porque 24.142 de 198.174 rutas son relativas sin
ese prefijo ("Actors\\Character\\Male\\MaleHead.dds") y el juego las carga
igual.
"""
import hashlib
import json
import os
import struct
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.join(_AQUI, "..", "census"))

import parser_nif  # noqa: E402
import parser_uv  # noqa: E402
import registrar  # noqa: E402

REFERENCIA = os.path.join(_AQUI, "roadsignwhiterun01.json")

# Campos que --identico compara. Se deja afuera la ruta (depende de donde
# extrajo cada uno) y el texto explicativo.
CAMPOS_IDENTIDAD = (
    "sha256", "bytes", "cabecera", "tipo_nodo_raiz", "bloques", "n_bloques",
    "tiene_skin", "bsxflags", "n_shapes", "triangulos_totales", "shapes",
    "geometria", "colision", "texturas_referenciadas",
)


def _rutas_textura(nif, fila):
    fuera = []
    for sh in fila["shapes"]:
        for r in sh.get("rutas_textura") or []:
            if r:
                fuera.append(r)
    return fuera


def reglas(ruta):
    """[(ok, clave, detalle, evidencia)]. Cada regla dice que la sostiene."""
    salida = []

    try:
        nif = parser_nif.Nif(ruta)
    except Exception as e:
        return [(False, "parsea",
                 "%s: %s" % (type(e).__name__, e),
                 "22.394 de 22.394 archivos del censo parsean sin violar "
                 "ninguna identidad de tamano")]

    fila = nif.fila_censo()
    ver = fila["version"]

    salida.append((
        (ver, fila["user_version"]) == ("20.2.0.7", 12),
        "cabecera_sse",
        "version=%s user=%s" % (ver, fila["user_version"]),
        "22.394 de 22.394 comparten 20.2.0.7 / user 12"))

    salida.append((
        fila["bs_version"] == 100,
        "bs_version",
        "bs=%s" % fila["bs_version"],
        "22.393 de 22.394 son BS 100; la unica excepcion vanilla es "
        "artrigpressureplate01.nif (BS 83)"))

    salida.append((
        fila["tipo_nodo_raiz"] in parser_nif.TIPOS_NODO,
        "nodo_raiz_conocido",
        "raiz=%s" % fila["tipo_nodo_raiz"],
        "los tipos de nodo raiz observados en el censo (hallazgo 5)"))

    salida.append((
        fila["n_shapes"] >= 1,
        "tiene_geometria",
        "%d shapes" % fila["n_shapes"],
        "463 de 22.394 archivos vanilla no tienen shapes, pero son nodos "
        "auxiliares, no assets entregables"))

    geos = parser_uv.geometria(nif)
    malos_geo = [g for g in geos if "error" in g]
    salida.append((
        not malos_geo,
        "geometria_legible",
        "%d de %d shapes con geometria ilegible%s"
        % (len(malos_geo), len(geos),
           (": " + ", ".join(str(g.get("error", "error"))[:60] for g in malos_geo[:3]))
           if malos_geo else ""),
        "82.694 de 82.694 shapes del censo tienen geometria legible "
        "(0 violaciones de identidad de bloque, hallazgo 3)"))

    rutas = _rutas_textura(nif, fila)
    malas_ext = [r for r in rutas if not r.lower().endswith(".dds")]
    salida.append((
        not malas_ext,
        "texturas_dds",
        "%d de %d rutas no terminan en .dds%s"
        % (len(malas_ext), len(rutas),
           (": " + ", ".join(malas_ext[:3])) if malas_ext else ""),
        "198.087 de 198.174 rutas del censo terminan en .dds; las 87 "
        "excepciones son placeholders de Bethesda (NOR, .tga, .bmp)"))

    malas_sep = [r for r in rutas if "\\" not in r]
    salida.append((
        not malas_sep,
        "texturas_separador",
        "%d de %d rutas sin separador '\\'%s"
        % (len(malas_sep), len(rutas),
           (": " + ", ".join(malas_sep[:3])) if malas_sep else ""),
        "198.091 de 198.174 rutas del censo usan '\\'"))

    rbs = nif.de_tipo("bhkRigidBody", "bhkRigidBodyT")
    if rbs:
        malos = []
        for _i, o, s in rbs:
            if s < 250:
                malos.append("size=%d (corto)" % s)
                continue
            c, = struct.unpack_from("<I", nif.d, o + 244)
            if s != 250 + 4 * c:
                malos.append("size=%d c=%d" % (s, c))
        salida.append((
            not malos,
            "rigidbody_identidad",
            "%d de %d bloques fuera de la identidad%s"
            % (len(malos), len(rbs), (": " + ", ".join(malos[:3])) if malos else ""),
            "size == 250 + 4*numConstraints se cumple en 14.586 de 14.586 "
            "bloques del censo"))

    return salida


def observaciones(ruta):
    """Se informan, no reprueban. Cada una con por que NO es una regla."""
    fuera = []
    nif = parser_nif.Nif(ruta)
    fila = nif.fila_censo()

    rutas = _rutas_textura(nif, fila)
    con_pref = [r for r in rutas if r.lower().startswith("textures\\")]
    fuera.append((
        "prefijo_textures",
        "%d de %d rutas empiezan con 'textures\\'" % (len(con_pref), len(rutas)),
        "NO es regla: 24.142 de 198.174 rutas vanilla (12,2 %) son relativas "
        "sin ese prefijo y el juego las carga igual"))

    fuera.append((
        "skin",
        "tiene_skin=%s (raiz %s)" % (fila["tiene_skin"], fila["tipo_nodo_raiz"]),
        "NO es regla: 3.641 de 18.526 archivos con raiz BSFadeNode (19,65 %) "
        "tienen skin; la raiz no decide"))

    sin_uv = fuera_01 = total = 0
    errores_geo = 0
    for sh in parser_uv.geometria(nif):
        if "error" in sh:
            errores_geo += 1
            continue
        total += 1
        if not sh.get("con_uv"):
            sin_uv += 1
        elif sh.get("uv") and any(not (0.0 <= u <= 1.0) or not (0.0 <= v <= 1.0)
                                  for u, v in sh["uv"]):
            fuera_01 += 1
    fuera.append((
        "uv",
        "%d de %d shapes sin UV; %d con UV fuera de [0,1]%s"
        % (sin_uv, total, fuera_01,
           (" (%d no legibles descartados)" % errores_geo) if errores_geo else ""),
        "salir de [0,1] NO es defecto: es tiling, y pasa en el 49,2 % de los "
        "shapes vanilla medidos"))

    fuera.append((
        "colision",
        "tipos_bhk=%s layer=%s"
        % (fila["colision"]["tipos_bhk"] or "(ninguno)",
           fila["colision"]["layer"]),
        "informativo: 11.200 de 22.394 archivos vanilla tienen colision, "
        "o sea que no tenerla tampoco es un defecto"))

    return fuera


def _cargar_referencia():
    if not os.path.exists(REFERENCIA):
        raise SystemExit("falta %s; correr fixtures/registrar.py" % REFERENCIA)
    with open(REFERENCIA, encoding="utf-8") as fh:
        return json.load(fh)


def modo_contrato(ruta):
    print("CONTRATO  %s" % ruta)
    print("")
    rs = reglas(ruta)
    fallan = [r for r in rs if not r[0]]
    for ok, clave, detalle, ev in rs:
        print("  [%s] %-22s %s" % ("ok" if ok else "NO", clave, detalle))
        if not ok:
            print("       evidencia: %s" % ev)
    print("")
    print("  %d reglas, %d sin cumplir" % (len(rs), len(fallan)))

    if not fallan:
        print("")
        print("  observaciones (no reprueban):")
        try:
            for clave, detalle, por_que in observaciones(ruta):
                print("    %-20s %s" % (clave, detalle))
                print("       %s" % por_que)
        except Exception as e:
            print("    (no se pudieron leer: %s)" % e)
    return 1 if fallan else 0


def modo_identico(ruta):
    ref = _cargar_referencia()
    # Se mide el archivo dado directamente, sin asumir donde vive: el usuario
    # lo extrajo a su carpeta, no necesariamente dentro de un arbol meshes/.
    nif = parser_nif.Nif(ruta)
    fila = nif.fila_censo()
    with open(ruta, "rb") as fh:
        crudo = fh.read()
    ahora = {
        "sha256": hashlib.sha256(crudo).hexdigest(),
        "bytes": len(crudo),
        "cabecera": {"version": fila["version"],
                     "user_version": fila["user_version"],
                     "bs_version": fila["bs_version"]},
        "tipo_nodo_raiz": fila["tipo_nodo_raiz"],
        "bloques": dict(sorted(fila["bloques"].items())),
        "n_bloques": sum(fila["bloques"].values()),
        "tiene_skin": fila["tiene_skin"],
        "bsxflags": {"valor": fila["bsxflags_valor"],
                     "bits": fila["bsxflags_bits"]},
        "n_shapes": fila["n_shapes"],
        "triangulos_totales": fila["triangulos_totales"],
        "shapes": fila["shapes"],
        "geometria": registrar.resumen_geometria(nif),
        "colision": fila["colision"],
        "texturas_referenciadas": nif.texturas(),
    }

    print("IDENTIDAD contra %s" % os.path.basename(REFERENCIA))
    print("")
    difs = []
    for campo in CAMPOS_IDENTIDAD:
        if campo not in ahora:
            difs.append(campo)
            print("  [NO] %s (campo ausente en medicion)" % campo)
            continue
        if ref.get(campo) != ahora[campo]:
            difs.append(campo)
            print("  [NO] %s" % campo)
            print("       referencia: %s"
                  % json.dumps(ref.get(campo), ensure_ascii=False)[:160])
            print("       archivo   : %s"
                  % json.dumps(ahora[campo], ensure_ascii=False)[:160])
        else:
            print("  [ok] %s" % campo)
    print("")
    print("  %d campos comparados, %d distintos" % (len(CAMPOS_IDENTIDAD), len(difs)))
    return 1 if difs else 0


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in ("--contrato", "--identico"):
        print(__doc__)
        raise SystemExit(2)
    if not os.path.exists(a[1]):
        raise SystemExit("no existe: %s" % a[1])
    raise SystemExit(modo_contrato(a[1]) if a[0] == "--contrato"
                     else modo_identico(a[1]))


if __name__ == "__main__":
    main()
