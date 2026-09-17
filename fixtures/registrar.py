# -*- coding: utf-8 -*-
"""Registra los metadatos del static de referencia. NO copia el asset.

    python fixtures/registrar.py <carpeta meshes/>
    python fixtures/registrar.py <carpeta meshes/> --verificar

El archivo de referencia es de Bethesda y no se versiona. Lo que se versiona es
la MEDICION: arbol de bloques, shader, rutas de textura, colision, caja
envolvente y el sha256 del archivo original, que es lo que deja comprobar que
dos personas estan mirando exactamente los mismos bytes.

Con --verificar no escribe nada: vuelve a medir y compara contra el JSON ya
registrado. Es la prueba de que la referencia es reproducible y no una foto
que alguien pego una vez.

POR QUE ESTE ARCHIVO Y NO OTRO
------------------------------
Salio de filtrar los 8.644 NIF de clutter/architecture/furniture/dungeons/
landscape con estos criterios, no de elegirlo a ojo:

  raiz BSFadeNode, 1 solo shape, sin skin, 1 solo BSShaderTextureSet,
  con colision, y sin violaciones de identidad de tamano

Quedaron 1.857 candidatos. Entre los mas simples, este es el unico que ademas
tiene EXACTAMENTE el par de texturas canonico (difusa + _n) sin cubemap ni _m
que sumarian una variable, colision de caja (bhkBoxShape, lo mas simple), y
extension real en los tres ejes -- las alfombras, que empataban en tamano, son
planas y no sirven para comprobar dimensiones.
"""
import hashlib
import json
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_AQUI, "..", "census"))

import parser_nif  # noqa: E402
import parser_uv  # noqa: E402

RUTA_RELATIVA = "clutter/signage/roadsigns/roadsignwhiterun01.nif"
SHA256 = "d435f916e43b865107d1dd6af7208250f83cc21626a0dab8f9d4c5b6c0a06574"
SALIDA = os.path.join(_AQUI, "roadsignwhiterun01.json")

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


def medir(raiz_meshes):
    ruta = os.path.join(raiz_meshes, RUTA_RELATIVA.replace("/", os.sep))
    if not os.path.exists(ruta):
        raise SystemExit(
            "no esta el archivo de referencia:\n  %s\n"
            "Ver fixtures/README.md para saber de que BSA sale." % ruta)

    with open(ruta, "rb") as fh:
        crudo = fh.read()
    sha = hashlib.sha256(crudo).hexdigest()

    nif = parser_nif.Nif(ruta)
    fila = nif.fila_censo(raiz_meshes)

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

    return {
        "_que_es_esto": (
            "Medicion de un archivo vanilla de Skyrim SE. Metadatos, no "
            "contenido: el .nif no se versiona. Regenerable con "
            "fixtures/registrar.py."),
        "ruta_relativa": RUTA_RELATIVA,
        "sha256": sha,
        "bytes": len(crudo),
        "cabecera": {
            "version": fila["version"],
            "user_version": fila["user_version"],
            "bs_version": fila["bs_version"],
        },
        "tipo_nodo_raiz": fila["tipo_nodo_raiz"],
        "bloques": dict(sorted(fila["bloques"].items())),
        "n_bloques": sum(fila["bloques"].values()),
        "tiene_skin": fila["tiene_skin"],
        "bsxflags": {"valor": fila["bsxflags_valor"],
                     "bits": fila["bsxflags_bits"]},
        "n_shapes": fila["n_shapes"],
        "triangulos_totales": fila["triangulos_totales"],
        "shapes": fila["shapes"],
        "geometria": geo,
        "colision": fila["colision"],
        "texturas_referenciadas": nif.texturas(),
    }


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        raise SystemExit(2)
    raiz = a[0]
    datos = medir(raiz)

    if datos["sha256"] != SHA256:
        print("AVISO: el sha256 no coincide con el registrado.")
        print("  registrado: %s" % SHA256)
        print("  local     : %s" % datos["sha256"])
        print("  Tu copia no es la misma que produjo fixtures/*.json. Puede ser")
        print("  otra edicion del juego o un archivo parcheado por un mod.")

    if "--verificar" in a:
        if not os.path.exists(SALIDA):
            print("no hay JSON registrado en %s" % SALIDA)
            raise SystemExit(1)
        with open(SALIDA, encoding="utf-8") as fh:
            viejo = json.load(fh)
        if viejo == datos:
            print("La medicion reproduce exactamente el JSON registrado.")
            raise SystemExit(0)
        print("La medicion NO reproduce el JSON registrado. Diferencias:")
        for k in sorted(set(viejo) | set(datos)):
            if viejo.get(k) != datos.get(k):
                print("  %s:\n    registrado: %s\n    ahora     : %s"
                      % (k, json.dumps(viejo.get(k), ensure_ascii=False)[:200],
                         json.dumps(datos.get(k), ensure_ascii=False)[:200]))
        raise SystemExit(1)

    with open(SALIDA, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("escrito: %s" % SALIDA)


if __name__ == "__main__":
    main()
