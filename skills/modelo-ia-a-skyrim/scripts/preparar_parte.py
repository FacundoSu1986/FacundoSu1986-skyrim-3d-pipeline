# -*- coding: utf-8 -*-
"""Deja una parte de IA lista para montar: soldada, decimada, orientada.

Hace las cuatro cosas que TODA parte generada necesita, en el orden que
importa:

  1. Hornear la matriz del importador. glTF es Y-up; el importador deja esa
     rotacion en la matriz del objeto, no en los vertices. Medir en mundo y
     transformar en local mezcla espacios y la figura termina acostada.
  2. SOLDAR antes de decimar. Los generadores parten los vertices por isla de
     UV, y el decimado por colapso necesita aristas compartidas: sin soldar se
     topa con un piso (2.500 pedidos, 16.453 obtenidos).
  3. Decimar al presupuesto. Preserva la silueta notablemente bien: 447.406 ->
     8.000 triangulos es visualmente indistinguible.
  4. Media vuelta sobre Z, SOLO SI SE PIDE. Muchos generadores devuelven el
     modelo mirando a -Y y Skyrim quiere +Y, pero eso NO es universal y una
     rotacion es destructiva: aplicada sin motivo deja de espaldas un modelo
     que venia bien. Por eso es opt-in. Cuando corresponda, va ACA y no mas
     tarde: girar despues de repartir la geometria en piezas les cambia el lado
     y cada una queda atada al hueso opuesto.

     Para decidir, mira la parte de perfil y fijate hacia donde apuntan la
     cara, el pico o los dedos del pie. La heuristica de masa de
     medir_parte.py es una pista, no una prueba.

Uso:
  blender -b --python preparar_parte.py -- <entrada> <salida.blend> <tris> [--girar-180]

Ejemplo:
  blender -b --python preparar_parte.py -- cabeza.glb partes/cabeza.blend 8000
"""

import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

# Fraccion del alto del modelo que se usa como distancia de soldadura. Lo
# bastante chica para no fusionar detalle real, lo bastante grande para cerrar
# los vertices partidos por isla de UV.
SOLDADURA = 0.0008


def limpiar():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)


def importar(ruta):
    ext = os.path.splitext(ruta)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=ruta)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=ruta)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=ruta)
    else:
        raise SystemExit("extension no soportada: %s" % ext)
    mallas = [o for o in bpy.data.objects if o.type == 'MESH']
    if not mallas:
        raise SystemExit("%s no trae mallas" % ruta)
    for o in mallas:
        o.data.transform(o.matrix_world)
        o.matrix_world = Matrix.Identity(4)
    return mallas


def unir(mallas, nombre):
    if len(mallas) > 1:
        bpy.ops.object.select_all(action='DESELECT')
        for o in mallas:
            o.select_set(True)
        bpy.context.view_layer.objects.active = mallas[0]
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active or mallas[0]
    obj.name = nombre
    obj.data.name = nombre + "_malla"
    return obj


def tris(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def soldar(obj):
    co = [v.co for v in obj.data.vertices]
    alto = max(c.z for c in co) - min(c.z for c in co)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts),
                             dist=max(alto * SOLDADURA, 1e-6))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def decimar(obj, presupuesto):
    actual = tris(obj)
    if actual <= presupuesto:
        return 1.0
    ratio = presupuesto / float(actual)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    mod = obj.modifiers.new("Decimar", 'DECIMATE')
    mod.decimate_type = 'COLLAPSE'
    mod.ratio = ratio
    mod.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return ratio


def media_vuelta(obj):
    obj.data.transform(Matrix.Rotation(3.141592653589793, 4, 'Z'))
    obj.data.update()


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) < 3:
        print(__doc__)
        return
    entrada, salida, presupuesto = args[0], args[1], int(args[2])
    girar = "--girar-180" in args

    limpiar()
    nombre = os.path.splitext(os.path.basename(salida))[0]
    obj = unir(importar(entrada), nombre)

    antes = tris(obj)
    soldar(obj)
    soldado = tris(obj)
    ratio = decimar(obj, presupuesto)
    despues = tris(obj)
    if girar:
        media_vuelta(obj)

    co = [v.co for v in obj.data.vertices]
    x = [min(c.x for c in co), max(c.x for c in co)]
    y = [min(c.y for c in co), max(c.y for c in co)]
    z = [min(c.z for c in co), max(c.z for c in co)]
    h = z[1] - z[0]

    destino = os.path.abspath(salida)
    if os.path.exists(destino) and "--force" not in args:
        raise SystemExit(
            "%s ya existe. Preparar una parte es caro y sobrescribir sin avisar "
            "puede perder trabajo: usa --force si de verdad queres pisarlo."
            % destino)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=destino)

    print("[%s] %d -soldado-> %d -decimado-> %d tris (ratio %.4f)%s"
          % (nombre, antes, soldado, despues, ratio,
             "  + media vuelta" if girar
             else "  (sin girar; usa --girar-180 si mira a -Y)"))
    print("  caja  X %.3f..%.3f  Y %.3f..%.3f  Z %.3f..%.3f"
          % (x[0], x[1], y[0], y[1], z[0], z[1]))
    print("  proporcion  ancho %.2f : fondo %.2f : alto 1.00"
          % ((x[1] - x[0]) / h, (y[1] - y[0]) / h))
    print("  UV: %s" % [u.name for u in obj.data.uv_layers])
    print("[blend] %s" % destino)

    # Si el decimado no llego al presupuesto, la soldadura no alcanzo: hay
    # cascaras sueltas que el colapso no puede reducir. Avisar, no fallar.
    if despues > presupuesto * 1.15:
        print("[aviso] no se llego al presupuesto (%d vs %d pedidos). Quedan "
              "cascaras sueltas: probar una soldadura mas grande que %.5f del "
              "alto." % (despues, presupuesto, SOLDADURA))


main()
