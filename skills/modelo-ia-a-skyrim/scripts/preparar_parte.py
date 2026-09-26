# -*- coding: utf-8 -*-
"""Deja una parte de IA lista para montar: soldada, decimada, orientada.

Hace las cuatro cosas que TODA parte generada necesita, en el orden que
importa:

  1. Hornear la matriz del importador. glTF es Y-up; el importador deja esa
     rotacion en la matriz del objeto, no en los vertices. Medir en mundo y
     transformar en local mezcla espacios y la figura termina acostada.
  2. SOLDAR antes de decimar. Los generadores parten los vertices por isla de
     UV, y el decimado por colapso necesita aristas compartidas: sin soldar se
     topa con un piso (2.500 pedidos, 16.453 obtenidos). Soldar DE MAS tambien:
     fusiona detalle, crea aristas no-manifold y el piso vuelve (ver
     SOLDADURA, medido en dos modelos).
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

Opcional, para piezas de PANELES (armas, props, metal): `--planar <grados>`
funde en una sola cara lo que ya es el mismo panel y no mueve un vertice --es
el modo Hardsurface de los addons de retopologia, con lo que ya trae Blender--.
Va DESPUES de soldar y ANTES de colapsar, y el orden es el punto: un panel que
ya es una sola cara no tiene interior que colapsar, asi que el error del
colapso se queda en las zonas curvas en vez de repartirse por los planos y
ondular los filos. Sin esto, el colapso redondea los cantos de una pieza de
metal y la linea del filo zigzaguea.

En una malla de IA los paneles NO son perfectamente planos: con un angulo
generoso quedan caras combadas, que al triangularse se ven como sombras. Empeza
por 5 y subi despacio. **El angulo no esta medido:** lo que decide es el render,
no el conteo de caras. Si el resultado queda en n-gonos, el script triangula
antes de guardar, para que el .blend sea lo que se exporta.

Opcional, para la capa HD (references/hd-texturas.md): `--guardar-alto
<alto.blend>` guarda TAMBIEN la malla soldada SIN decimar. Es la fuente del
bake (`hornear.py`): el detalle que el decimado tira no se recupera
despues. Recibe la misma media vuelta que la baja --la misma transformacion a
las dos, o el horneado sale corrido (trampa 34)--. El bake va justo despues de
desplegar las UV, cuando las dos todavia coinciden; lo que deforme la baja
ANTES (afinar) hay que aplicarselo igual a la alta. Montar va despues del bake
y no toca las UV.

Uso:
  blender -b --python preparar_parte.py -- <entrada> <salida.blend> <tris> [--planar <grados>] [--girar-180] [--guardar-alto <alto.blend>] [--soldadura F] [--force]

  --planar G      fusiona los paneles planos en una sola cara antes de
                  colapsar (grados de tolerancia; probar 5 y subir)
  --soldadura F   distancia de soldadura como fraccion del alto (0.00001 por
                  defecto: junta los duplicados de las costuras de UV)

Ejemplo:
  blender -b --python preparar_parte.py -- cabeza.glb partes/cabeza.blend 8000
  blender -b --python preparar_parte.py -- arma.glb partes/arma.blend 12000 --planar 5
"""

import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from correr_en_blender import correr  # noqa: E402

# Fraccion del alto del modelo que se usa como distancia de soldadura: la
# justa para juntar los vertices DUPLICADOS por las costuras de UV, que en los
# modelos de Tripo coinciden exactamente. Medido sobre dos modelos reales,
# decimando al presupuesto:
#
#                               soldadura   borde   no-manifold   decimado
#   hacha (1,5 M tris) -> 8.000  0,00001       0            0       8.000
#                                0,0008    1.328        1.916      10.034
#   escudo (2 M tris) -> 12.000  0,00001      14           13      11.999
#                                0,0008    9.698       15.616      73.413
#   partes del centurion (~440 k tris) -> 2.500, las dos soldaduras llegan:
#     pie      0,00001: 4 de borde     0,0008: 70
#     pierna   0,00001: 64             0,0008: 15
#     cabeza   0,00001: 138            0,0008: 9
#
# El valor anterior, 0,0008, fusionaba detalle real --el escudo paso de
# 1,98 M a 1,29 M triangulos al soldar--, creaba aristas no-manifold y el
# decimado se trababa lejos del presupuesto. `--soldadura F` la cambia.
SOLDADURA = 0.00001


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
    # Ver medir_parte.importar(): dos objetos que comparten datablock se
    # transforman dos veces y la caja sale bien formada y equivocada.
    for o in mallas:
        if o.data.users > 1:
            o.data = o.data.copy()
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


def soldar(obj, fraccion=SOLDADURA):
    """Suelda y devuelve (aristas de borde, aristas no-manifold): lo que el
    decimado despues no puede colapsar, y por eso lo que fija su piso."""
    co = [v.co for v in obj.data.vertices]
    alto = max(c.z for c in co) - min(c.z for c in co)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts),
                             dist=max(alto * fraccion, 1e-9))
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    borde = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    no_manifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return borde, no_manifold


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


def planar(obj, grados):
    """Funde en una sola cara lo que ya es el mismo panel.

    DISSOLVE --lo que la interfaz llama "Planar"-- no mueve vertices: borra los
    que no cambian la forma. La superficie y los filos quedan donde estaban,
    que es justo lo que el colapso no garantiza. Devuelve (caras antes, caras
    despues).

    OJO: disolver NO es enderezar. Si un filo zigzaguea porque sus vertices
    estan desplazados, esto no lo arregla --para eso esta `enderezar.py`--.
    Lo que hace es dejarle al colapsador menos interior donde repartir el
    error, y por eso ayuda de forma indirecta.

    NO se delimita por UV ni por costura: las UV se rehacen en 4b, y delimitar
    ahi impide juntar el panel, que es el punto entero de este pase.
    """
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    antes = len(obj.data.polygons)
    mod = obj.modifiers.new("Planar", 'DECIMATE')
    # 'DISSOLVE' es lo que la interfaz llama "Planar": el enum es
    # COLLAPSE / UNSUBDIV / DISSOLVE. Escrito 'PLANAR' reventaba en la primera
    # corrida (verificado contra la API de DecimateModifier, defaults
    # documentados: delimit {'NORMAL'}).
    mod.decimate_type = 'DISSOLVE'
    mod.angle_limit = math.radians(grados)
    mod.delimit = {'NORMAL'}
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return antes, len(obj.data.polygons)


def triangular(obj):
    """Triangula explicito, antes de guardar.

    Con --planar y sin colapso, el resultado puede quedar en n-gonos. El NIF
    guarda solo triangulos: si se deja al exportador, el .blend deja de ser lo
    que se carga (limites-skyrim.md).
    """
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


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
    fraccion = SOLDADURA
    if "--soldadura" in args:
        i = args.index("--soldadura")
        try:
            fraccion = float(args[i + 1])
        except (IndexError, ValueError):
            raise SystemExit("--soldadura necesita un numero: fraccion del alto")
    planares = None
    if "--planar" in args:
        i = args.index("--planar")
        try:
            grados = float(args[i + 1])
        except (IndexError, ValueError):
            raise SystemExit("--planar necesita un numero: grados de tolerancia")
        if not 0.0 < grados < 180.0:
            raise SystemExit("--planar: los grados van entre 0 y 180")
        planares = grados
    alto_destino = None
    if "--guardar-alto" in args:
        i = args.index("--guardar-alto")
        if i + 1 >= len(args) or args[i + 1].startswith("--"):
            raise SystemExit("--guardar-alto necesita una ruta .blend")
        alto_destino = os.path.abspath(args[i + 1])

    # Comprobar ANTES de trabajar. Estaba al final: la segunda corrida
    # importaba, soldaba y decimaba --lo caro-- y recien entonces avisaba que
    # el destino ya existia.
    destino = os.path.abspath(salida)
    if os.path.exists(destino) and "--force" not in args:
        raise SystemExit(
            "%s ya existe. Preparar una parte es caro y sobrescribir sin avisar "
            "puede perder trabajo: usa --force si de verdad queres pisarlo."
            % destino)
    if alto_destino:
        # normcase: en Windows `Parte.blend` y `parte.blend` son el mismo
        # archivo, y la alta --que se guarda segunda-- pisaba a la baja.
        if (os.path.normcase(os.path.realpath(alto_destino))
                == os.path.normcase(os.path.realpath(destino))):
            raise SystemExit("--guardar-alto no puede ser el mismo archivo "
                             "que la salida: pisaria la malla baja.")
        if os.path.exists(alto_destino) and "--force" not in args:
            raise SystemExit("%s ya existe: usa --force para pisarlo."
                             % alto_destino)

    limpiar()
    nombre = os.path.splitext(os.path.basename(salida))[0]
    obj = unir(importar(entrada), nombre)

    antes = tris(obj)
    borde, no_manifold = soldar(obj, fraccion)
    soldado = tris(obj)
    # Copia de los DATOS, no del objeto: el decimado aplica un modificador al
    # objeto activo y no toca un datablock que no es suyo. Lleva los
    # materiales, que el bake de albedo necesita.
    alto_malla = obj.data.copy() if alto_destino else None
    # El planar va DESPUES de copiar la alta: la alta es la fuente del bake y
    # tiene que llegar densa. Aplicarlo a las dos le sacaria al bake el detalle
    # que este pase justamente borra.
    caras_planas = planar(obj, planares) if planares else None
    ratio = decimar(obj, presupuesto)
    # Solo puede quedar en n-gonos si el planar alcanzo y no hubo colapso; con
    # colapso, use_collapse_triangulate ya devolvio triangulos.
    if caras_planas and any(len(p.vertices) > 3 for p in obj.data.polygons):
        triangular(obj)
    despues = tris(obj)
    if girar:
        media_vuelta(obj)
        if alto_malla is not None:
            alto_malla.transform(Matrix.Rotation(3.141592653589793, 4, 'Z'))
            alto_malla.update()

    co = [v.co for v in obj.data.vertices]
    x = [min(c.x for c in co), max(c.x for c in co)]
    y = [min(c.y for c in co), max(c.y for c in co)]
    z = [min(c.z for c in co), max(c.z for c in co)]
    h = z[1] - z[0]
    # Pieza plana (h ~ 0) puede ser valida. No dividir; no tratarlo como fatal.
    if h > 1e-8:
        prop_ancho = (x[1] - x[0]) / h
        prop_fondo = (y[1] - y[0]) / h
        prop_txt = "ancho %.2f : fondo %.2f : alto 1.00" % (prop_ancho, prop_fondo)
    else:
        prop_txt = "alto ~ 0 (pieza plana); proporcion no aplica"

    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=destino)

    print("[%s] %d -soldado-> %d -decimado-> %d tris (ratio %.4f)%s"
          % (nombre, antes, soldado, despues, ratio,
             "  + media vuelta" if girar
             else "  (sin girar; usa --girar-180 si mira a -Y)"))
    print("  caja  X %.3f..%.3f  Y %.3f..%.3f  Z %.3f..%.3f"
          % (x[0], x[1], y[0], y[1], z[0], z[1]))
    print("  proporcion  %s" % prop_txt)
    print("  soldadura %.6f del alto: %d aristas de borde, %d no-manifold"
          % (fraccion, borde, no_manifold))
    if caras_planas:
        print("  planar %.1f grados: %d caras -> %d caras, sin mover vertices"
              % (planares, caras_planas[0], caras_planas[1]))
    print("  UV: %s" % [u.name for u in obj.data.uv_layers])
    print("[blend] %s" % destino)

    if alto_malla is not None:
        # Despues de guardar la baja: se reemplaza la escena por la alta y se
        # guarda aparte. El nombre lleva "_alto" para que el bake la distinga.
        bpy.data.objects.remove(obj, do_unlink=True)
        alto_obj = bpy.data.objects.new(nombre + "_alto", alto_malla)
        bpy.context.scene.collection.objects.link(alto_obj)
        os.makedirs(os.path.dirname(alto_destino) or ".", exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=alto_destino)
        print("[alto] %d tris sin decimar -> %s" % (soldado, alto_destino))

    # Si el decimado no llego al presupuesto, algo frena el colapso: aristas
    # de borde (cascaras sueltas, costuras sin cerrar) o aristas no-manifold,
    # que una soldadura DEMASIADO grande crea al fusionar detalle. Son dos
    # correcciones opuestas: el aviso dice cual, con el numero. Antes decia
    # siempre "soldadura mas grande", que en los dos modelos medidos era al
    # reves (ver SOLDADURA). Avisar, no fallar.
    if despues > presupuesto * 1.15:
        if no_manifold > borde:
            consejo = ("la soldadura dejo %d aristas no-manifold: probar una "
                       "MAS CHICA que %g (--soldadura)" % (no_manifold,
                                                            fraccion))
        else:
            consejo = ("quedan %d aristas de borde (cascaras sueltas o "
                       "costuras sin cerrar): probar una soldadura MAS GRANDE "
                       "que %g (--soldadura)" % (borde, fraccion))
        print("[aviso] no se llego al presupuesto (%d vs %d pedidos): %s."
              % (despues, presupuesto, consejo))


correr(main)
