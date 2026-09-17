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
sys.path.insert(0, os.path.join(_AQUI, "..", "census"))

import parser_nif  # noqa: E402
import parser_uv  # noqa: E402

REFERENCIA = os.path.join(_AQUI, "roadsignwhiterun01.json")

# Campos que --identico compara. Se deja afuera la ruta (depende de donde
# extrajo cada uno) y el texto explicativo.
CAMPOS_IDENTIDAD = (
    "sha256", "bytes", "cabecera", "tipo_nodo_raiz", "bloques", "n_bloques",
    "tiene_skin", "bsxflags", "n_shapes", "triangulos_totales", "shapes",
    "geometria", "colision", "texturas_referenciadas",
)

UNIDADES_POR_METRO = 70.0


def _caja(posiciones):
    """AABB en unidades de Skyrim. None si el shape no trae posiciones."""
    if not posiciones:
        return None
    ejes = []
    for i in range(3):
        vals = [p[i] for p in posiciones]
        ejes.append((min(vals), max(vals)))
    return {
        "min": [round(a, 4) for a, _ in ejes],
        "max": [round(b, 4) for _, b in ejes],
        "tamano_unidades": [round(b - a, 4) for a, b in ejes],
        "tamano_metros": [round((b - a) / UNIDADES_POR_METRO, 4) for a, b in ejes],
    }


def _geometria_resumen(nif):
    """Construye el mismo resumen que registrar.medir() para --identico.

    Si un shape no es legible, se guarda el error en vez de inventar numeros.
    Asi --identico detecta regresiones de geometria y --contrato puede
    reprobar geometria rota.
    """
    geo = []
    for sh in parser_uv.geometria(nif):
        if "error" in sh:
            geo.append({"nombre": sh.get("nombre"), "error": sh["error"]})
            continue
        geo.append({
            "nombre": sh["nombre"],
            "tipo_bloque": sh["tipo"],
            "skin": sh["skin"],
            "con_uv": sh["con_uv"],
            "vertices": len(sh["pos"]),
            "triangulos": len(sh["tris"]),
            "caja": _caja(sh["pos"]),
        })
    return geo


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

    # P1 FIX: geometria legible — antes un shape con data_size inconsistente
    # (inline) o con particion que no cierra pasaba tiene_geometria pero no era
    # decodificable. parser_uv.geometria() devuelve {"error": ...} en esos casos.
    try:
        geos = parser_uv.geometria(nif)
        errores_geo = [g for g in geos if "error" in g]
    except Exception as e:
        # Si el recorrido mismo revienta, se trata como error de geometria
        errores_geo = [{"error": "%s: %s" % (type(e).__name__, e)}]
        geos = []

    # Detalle corto para el log, sin volcar bytes
    if errores_geo:
        ejemplos = ", ".join(
            "%s: %s" % (g.get("nombre", "?"), g.get("error", "")[:60])
            for g in errores_geo[:2]
        )
        detalle_geo = "%d de %d shapes con error: %s" % (
            len(errores_geo), len(geos) if geos else fila["n_shapes"], ejemplos)
    else:
        detalle_geo = "%d shapes legibles" % len(geos)

    salida.append((
        not errores_geo,
        "geometria_legible",
        detalle_geo,
        "82.694 de 82.694 shapes del censo tienen geometria legible "
        "(0 violaciones de identidad data_size == n_ver*stride + n_tri*6 y "
        "cierre de particiones, hallazgo 3)"))

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

    # P1 FIX (parte 2): antes se hacia `if "error" in sh: continue` y se
    # perdia el conteo. Ahora se cuentan los errores y se informan, pero no
    # reprueban aca — reprueban en la regla geometria_legible.
    sin_uv = fuera_01 = total = errores_geo = 0
    ejemplos_error = []
    for sh in parser_uv.geometria(nif):
        if "error" in sh:
            errores_geo += 1
            if len(ejemplos_error) < 2:
                ejemplos_error.append("%s: %s" % (
                    sh.get("nombre", "?"), sh.get("error", "")[:60]))
            continue
        total += 1
        if not sh.get("con_uv"):
            sin_uv += 1
        elif sh.get("uv") and any(not (0.0 <= u <= 1.0) or not (0.0 <= v <= 1.0)
                                  for u, v in sh["uv"]):
            fuera_01 += 1

    if errores_geo:
        fuera.append((
            "geometria_errores",
            "%d de %d shapes con error de geometria%s" % (
                errores_geo, errores_geo + total,
                (": " + ", ".join(ejemplos_error)) if ejemplos_error else ""),
            "informativo: 0 de 82.694 shapes vanilla tienen error de geometria "
            "(hallazgo 3); si hay errores, la regla geometria_legible reprueba"))

    fuera.append((
        "uv",
        "%d de %d shapes sin UV; %d con UV fuera de [0,1]%s" % (
            sin_uv, total, fuera_01,
            ("; %d con error de geometria (ver geometria_errores)" % errores_geo)
            if errores_geo else ""),
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

    # P2 FIX: antes geometria no se recalculaba y se saltaba con
    # `if campo not in ahora: continue`, asi que nunca se comparaba.
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
        "geometria": _geometria_resumen(nif),
        "colision": fila["colision"],
        "texturas_referenciadas": nif.texturas(),
    }

    print("IDENTIDAD contra %s" % os.path.basename(REFERENCIA))
    print("")
    difs = []
    for campo in CAMPOS_IDENTIDAD:
        # Todos los campos de identidad deben estar en ahora despues del fix.
        # Si falta alguno, es un bug del comparador, no un skip silencioso.
        if campo not in ahora:
            print("  [??] %s no calculado por el comparador (bug)" % campo)
            difs.append(campo)
            continue
        if ref.get(campo) != ahora.get(campo):
            difs.append(campo)
            print("  [NO] %s" % campo)
            print("       referencia: %s"
                  % json.dumps(ref.get(campo), ensure_ascii=False)[:200])
            print("       archivo   : %s"
                  % json.dumps(ahora.get(campo), ensure_ascii=False)[:200])
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
