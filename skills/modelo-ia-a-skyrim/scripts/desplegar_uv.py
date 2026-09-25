# -*- coding: utf-8 -*-
"""Paso 4b: despliega las UV de la BAJA para hornear, en un solo atlas.

    blender -b --python desplegar_uv.py -- <baja.blend> [--capa UV_Bake] [--angulo 66] [--margen 0.002] [--force]
    blender -b --python desplegar_uv.py -- --falsificar

Va despues de preparar_parte.py --y de lo que agregue caras: Solidify,
afinar-- y antes de hornear.py. Trabaja sobre TODAS las mallas del archivo a
la vez, que es lo que las pone en un mismo atlas:

  1. Una capa nueva (`UV_Bake` por defecto), activa Y de render: hornear.py
     sale con error si no es las dos cosas. Las otras capas NO se borran aca:
     eso lo hace uv_exportacion.conservar_uv sobre una copia, al exportar
     (trampa 40). Si la capa ya existe, pide --force para rehacerla.
  2. smart_project con todas las mallas en edicion a la vez. `[MEASURED]`
     Blender 4.4.1, una esfera y un toro: asi las reparte en UN atlas sin
     pisarlas (solape 0,0000). Desplegadas de a una, cada malla recibe el
     cuadro 0..1 entero y se pisan (trampa 17).
  3. Igualar la densidad de texel (average_islands_scale) y empaquetar
     (pack_islands, margen FRACTION), con las UV seleccionadas a mano por
     bmesh. Sin esa seleccion, en Blender sin interfaz, pack_islands corre
     sin error y no mueve nada (trampa 17; en el experimento de arriba, el
     empaquetado sin seleccion dejo las UV identicas).
  4. Juzga con horneado_puro.juzgar_despliegue: que empaquetar haya MOVIDO
     algo, que todo caiga en el cuadro 0..1, y que el solape no pase el tope
     con el que corta hornear.py. Si reprueba, NO guarda el archivo.

Desplegar en Blender no mueve vertices: las UV son por loop. Por eso aca no se
corre `salud_malla.py --uv`: ese control es para UV hechas en OTRA
herramienta y traidas de vuelta, que si puede reordenar o fusionar vertices.

--falsificar arma dos mallas sinteticas y despliega dos veces: sin
seleccionar las UV, la REGLA empaquetado tiene que reprobar; con la
seleccion, el despliegue tiene que pasar. Sin archivos del juego.

Exit 0 si pasa, 1 si reprueba o no hay mallas, 2 si los argumentos no sirven.
"""
import json
import math
import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from correr_en_blender import correr  # noqa: E402
import horneado_puro as hp  # noqa: E402

CAPA = "UV_Bake"
ANGULO = 66.0      # grados; el del escudo de Tripo
MARGEN = 0.002     # fraccion del atlas: 0,411 de cobertura (trampa 17)
MARGEN_ISLA = 0.001


def mallas():
    return [o for o in bpy.data.objects if o.type == "MESH"]


def preparar_capa(obj, capa, force):
    """Deja `capa` nueva, activa y de render. Cada capa se busca de nuevo por
    nombre despues de tocar la coleccion (trampa 40)."""
    me = obj.data
    if capa in me.uv_layers:
        if not force:
            raise SystemExit("%s ya tiene la capa UV %r: usa --force para "
                             "rehacerla" % (obj.name, capa))
        me.uv_layers.remove(me.uv_layers[capa])
    if me.uv_layers.new(name=capa) is None:
        raise SystemExit("%s: Blender no creo la capa %r (tope de 8 capas UV)"
                         % (obj.name, capa))
    me.uv_layers.active = me.uv_layers[capa]
    me.uv_layers[capa].active_render = True


def triangulos(obj, capa):
    """[((u,v), (u,v), (u,v))] de `capa`, por triangulo."""
    me = obj.data
    me.calc_loop_triangles()
    uv = me.uv_layers[capa].data
    return [tuple(tuple(uv[i].uv) for i in t.loops) for t in me.loop_triangles]


def area_3d(obj):
    """Area en mundo de la malla, sobre sus triangulos."""
    me = obj.data
    me.calc_loop_triangles()
    mw = obj.matrix_world
    total = 0.0
    for t in me.loop_triangles:
        p = [mw @ me.vertices[v].co for v in t.vertices]
        total += (p[1] - p[0]).cross(p[2] - p[0]).length / 2.0
    return total


def desplegar(objs, capa, angulo, margen, seleccionar=True):
    """(antes, despues): los triangulos UV de todas las mallas despues de
    smart_project y despues de igualar y empaquetar."""
    for o in bpy.data.objects:
        o.select_set(o in objs)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(angulo),
                             island_margin=MARGEN_ISLA, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    antes = [t for o in objs for t in triangulos(o, capa)]
    bpy.ops.object.mode_set(mode="EDIT")
    if seleccionar:
        for o in objs:
            bm = bmesh.from_edit_mesh(o.data)
            uvl = bm.loops.layers.uv[capa]
            for f in bm.faces:
                for lz in f.loops:
                    lz[uvl].select = True
                    lz[uvl].select_edge = True
            bmesh.update_edit_mesh(o.data)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION",
                            margin=margen)
    bpy.ops.object.mode_set(mode="OBJECT")
    despues = [t for o in objs for t in triangulos(o, capa)]
    return antes, despues


def informe(objs, capa, fallas, medidas):
    """Las medidas del juicio mas la densidad de texel relativa por malla."""
    densidades = {}
    for o in objs:
        d = hp.densidad_texel(area_3d(o), hp.area_uv(triangulos(o, capa)), 1)
        densidades[o.name] = None if d is None else round(d, 5)
    validas = [d for d in densidades.values() if d]
    out = dict(medidas, capa=capa, mallas=len(objs),
               densidad_por_malla=densidades,
               densidad_max_sobre_min=(round(max(validas) / min(validas), 3)
                                       if validas else None),
               fallas=fallas)
    return out


def falsificar():
    """Sin seleccionar las UV, la REGLA empaquetado tiene que reprobar; con la
    seleccion, el despliegue tiene que pasar. 0 si las dos cosas dan."""
    resultados = {}
    for seleccionar in (False, True):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16)
        bpy.ops.mesh.primitive_torus_add(location=(3.0, 0.0, 0.0))
        objs = mallas()
        for o in objs:
            preparar_capa(o, CAPA, False)
        antes, despues = desplegar(objs, CAPA, ANGULO, MARGEN, seleccionar)
        resultados[seleccionar] = hp.juzgar_despliegue(antes, despues)
    sin, con = resultados[False][0], resultados[True][0]
    atrapo = any("trampa 17" in f for f in sin)
    paso = not con
    print("[falsificar] sin seleccionar las UV: %s"
          % ("reprobo por empaquetado, como tiene que ser" if atrapo
             else "NO reprobo por empaquetado: %r" % sin))
    print("[falsificar] con la seleccion: %s  %s"
          % ("pasa" if paso else "REPRUEBA: %r" % con,
             json.dumps(resultados[True][1])))
    print("falsificar: 2 comprobaciones, %d fallas" % ((not atrapo) + (not paso)))
    return 0 if atrapo and paso else 1


def _mal(texto):
    """Argumentos que no sirven: exit 2, no 1 (1 es "reprueba")."""
    print("[uv] %s" % texto)
    raise SystemExit(2)


def _argumentos(args):
    ruta, capa, angulo, margen, force = None, CAPA, ANGULO, MARGEN, False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--force":
            force = True
        elif a in ("--capa", "--angulo", "--margen"):
            if i + 1 >= len(args):
                _mal("%s necesita un valor" % a)
            v = args[i + 1]
            i += 1
            if a == "--capa":
                capa = v
            else:
                try:
                    num = float(v)
                except ValueError:
                    _mal("%s necesita un numero: %r" % (a, v))
                if a == "--angulo":
                    if not 1.0 <= num <= 89.0:
                        _mal("--angulo entre 1 y 89 grados")
                    angulo = num
                else:
                    if not 0.0 <= num <= 0.1:
                        _mal("--margen entre 0 y 0,1 del atlas")
                    margen = num
        elif a.startswith("--"):
            _mal("opcion desconocida: %s" % a)
        elif ruta is None:
            ruta = a
        else:
            _mal("sobra un argumento: %s" % a)
        i += 1
    if ruta is None:
        print(__doc__)
        raise SystemExit(2)
    if not os.path.isfile(ruta):
        _mal("no existe: %s" % ruta)
    return ruta, capa, angulo, margen, force


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if args == ["--falsificar"]:
        sys.exit(falsificar())
    ruta, capa, angulo, margen, force = _argumentos(args)
    bpy.ops.wm.open_mainfile(filepath=ruta)
    objs = mallas()
    if not objs:
        print("[uv] %s no tiene mallas: nada que desplegar" % ruta)
        sys.exit(1)
    for o in objs:
        preparar_capa(o, capa, force)
    antes, despues = desplegar(objs, capa, angulo, margen)
    fallas, medidas = hp.juzgar_despliegue(antes, despues)
    print("[uv] " + json.dumps(informe(objs, capa, fallas, medidas),
                               ensure_ascii=False))
    for f in fallas:
        print("  FALLA %s" % f)
    if fallas:
        print("[uv] no se guardo %s" % ruta)
        sys.exit(1)
    bpy.ops.wm.save_as_mainfile(filepath=ruta)
    print("[uv] %d mallas en un atlas, capa %r activa y de render -> %s"
          % (len(objs), capa, ruta))


correr(main)
