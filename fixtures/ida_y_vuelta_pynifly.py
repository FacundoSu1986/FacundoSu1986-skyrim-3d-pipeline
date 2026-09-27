# -*- coding: utf-8 -*-
"""Ida y vuelta de estaticos vanilla por PyNifly, como en fixtures/pynifly.md,
y lo que cambio. Corre en Blender.

    blender -b --python fixtures/ida_y_vuelta_pynifly.py -- <meshes vanilla> <salida> <lista.txt> <resultado.json>

<lista.txt>: una ruta relativa a <meshes vanilla> por linea. Cada NIF se
importa con PyNifly, se exporta tal cual a <salida>/<ruta> con
`target_game=SKYRIMSE` (el default del exportador es SKYRIM), y se vuelve a
importar. Por archivo, en <resultado.json>:

  malla_orig / malla_ida   caja de la malla en espacio de MUNDO, importada
  col_orig / col_ida       caja de los objetos de colision (bhk*), idem
  malla_se_mueve / col_se_mueve   si alguna cara de la caja se corre > 0,05
  material_orig / material_ida    material Havok con census/parser_nif, que
                                  no es el addon (un defecto simetrico de
                                  lectura y escritura no se cancela)

Es la medicion de la seccion 3 y 5 de pynifly.md; el mod de prueba de la issue
#31 (`prueba_en_el_juego.py`) toma los NIF que deja en <salida>.

Correr SIN --factory-startup: PyNifly resuelve texturas contra SUS preferencias
(pynifly.md, seccion 4), y asi se midio. Una excepcion fuera de un archivo
sale con 1 (trampa 37: Blender sin interfaz sale con 0 aunque el script
reviente); un archivo que falla queda en el resultado con su error, y cero
archivos medidos tambien sale con 1.
"""
import json
import os
import sys
import traceback

import bpy
from mathutils import Vector

TOL = 0.05


def es_colision(o):
    return o.name.startswith("bhk") or str(o.get("pynBlockName", "")).startswith("bhk")


def cajas():
    malla, col = [], []
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
        (col if es_colision(o) else malla).extend(pts)

    def caja(pts):
        if not pts:
            return None
        return [[round(min(p[i] for p in pts), 3) for i in range(3)],
                [round(max(p[i] for p in pts), 3) for i in range(3)]]
    return caja(malla), caja(col)


def importar(ruta):
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.import_scene.pynifly(filepath=ruta)


def distinta(a, b):
    if a is None or b is None:
        return a != b
    return any(abs(x - y) > TOL for u, v in zip(a, b) for x, y in zip(u, v))


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    if len(args) != 4:
        print(__doc__)
        return 2
    meshes, salida, lista, resultado = args
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "census"))
    import parser_nif

    def material(ruta):
        try:
            return parser_nif.Nif(ruta).colision_info().get("material_havok")
        except Exception as e:
            return "ERROR %s" % e

    import addon_utils
    addon_utils.enable("io_scene_nifly", default_set=True)
    filas = []
    for rel in [l.strip() for l in open(lista, encoding="utf-8") if l.strip()]:
        orig, ida = os.path.join(meshes, rel), os.path.join(salida, rel)
        fila = {"ruta": rel}
        try:
            importar(orig)
            fila["malla_orig"], fila["col_orig"] = cajas()
            for o in bpy.data.objects:
                o.select_set(True)
            bpy.context.view_layer.objects.active = next(
                (o for o in bpy.data.objects if o.parent is None), bpy.data.objects[0])
            os.makedirs(os.path.dirname(ida), exist_ok=True)
            bpy.ops.export_scene.pynifly(filepath=ida, target_game="SKYRIMSE")
            importar(ida)
            fila["malla_ida"], fila["col_ida"] = cajas()
            fila["malla_se_mueve"] = distinta(fila["malla_orig"], fila["malla_ida"])
            fila["col_se_mueve"] = distinta(fila["col_orig"], fila["col_ida"])
            fila["material_orig"], fila["material_ida"] = material(orig), material(ida)
        except Exception:
            fila["error"] = traceback.format_exc()[-400:]
        filas.append(fila)
        print("[ida_y_vuelta] %s malla %s col %s material %s -> %s%s"
              % (rel, fila.get("malla_se_mueve"), fila.get("col_se_mueve"),
                 fila.get("material_orig"), fila.get("material_ida"),
                 "  ERROR" if "error" in fila else ""))
    with open(resultado, "w", encoding="utf-8") as fh:
        json.dump(filas, fh, indent=1)
    medidos = sum(1 for f in filas if "error" not in f)
    print("[ida_y_vuelta] %d archivos, %d medidos -> %s" % (len(filas), medidos, resultado))
    return 0 if medidos else 1


if __name__ == "__main__":
    try:
        codigo = main()
    except BaseException:
        traceback.print_exc()
        codigo = 1
    sys.stdout.flush()
    os._exit(codigo)
