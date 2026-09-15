# -*- coding: utf-8 -*-
"""Renderiza un asset vanilla como referencia para ControlNet.

PARA QUE SIRVE

Los reconstructores imagen->3D infieren la geometria de la imagen: el texto no
es una entrada del modelo. Por eso no se puede pedir "esta forma con este
estilo" en un solo paso. La salida es meter el estilo DENTRO de la imagen antes
del 3D:

    render del asset vanilla (este script)
        |  ControlNet depth/canny + prompt de estilo
    imagen con las proporciones del vanilla y tu estilo
        |  imagen -> 3D
    malla que nace con la silueta del esqueleto correcto

Asi se deja de pelear contra una forma que nunca fue pensada para ese
esqueleto: la silueta la impone el vanilla y el prompt solo decide materiales.

QUE LO DIFERENCIA DE util_render.py

Aquel dibuja una regla de proporciones encima, que sirve para COMPARAR a ojo y
arruina un ControlNet. Este produce imagenes limpias.

TRES PASADAS, PARA TRES USOS DISTINTOS
  profundidad  -- ControlNet depth. La mejor para conservar la forma 3D.
                  Cerca = blanco, lejos = negro (la convencion habitual).
  arcilla      -- gris parejo con luz suave. Para canny/lineart, y para que
                  vos juzgues la silueta.
  silueta      -- blanco puro sobre negro. Para scribble, o como mascara.

ENCUADRE COMPARTIDO

Las dos vistas usan la MISMA escala ortografica. Si cada una se encuadra sola,
el frente y el perfil salen a tamanos distintos y el generador 3D interpreta
mal las proporciones -- que es justo lo que se estaba tratando de fijar.

Uso:
  blender -b --python render_referencia.py -- <archivo.nif> <carpeta_salida>
  blender -b --python render_referencia.py -- <archivo.nif> <salida> --vistas frente,perfil,dorso
"""
import math
import os
import sys

import bpy
from mathutils import Vector

# Azimut 0 pone la camara en -Y mirando a +Y, o sea muestra la cara que apunta
# a -Y. Para un ACTOR de Skyrim el frente es +Y, asi que la vista de frente es
# la de azimut 180, y ese es el default.
#
# PERO NO VALE PARA TODO ARCHIVO. Medido: dwarvensteamcenturion.nif (el estatico
# de las ruinas, no la malla del actor) mira a -Y, o sea su frente es azimut 0.
# Los props estaticos no siguen la convencion de actor.
#
# El script NO puede adivinarlo. Renderiza, mira cual tiene la cara, y si esta
# al reves volve a correr con --frente-az 0. Etiquetar mal un render y despues
# juzgar el modelo sobre esa etiqueta ya paso: es la trampa 19 de trampas.md.
FRENTE_AZ = 180.0
DESFASES = {"frente": 0.0, "perfil": -90.0, "dorso": 180.0, "tresq": 38.0}

RES = (768, 1024)          # relacion 3:4, estandar de difusion y buena para
                           # una figura alta. Cuadrado desperdicia los lados.
MARGEN = 1.12


def limpiar():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for d in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
              bpy.data.cameras):
        for x in list(d):
            d.remove(x)


def importar(ruta):
    ext = os.path.splitext(ruta)[1].lower()
    if ext == ".nif":
        bpy.ops.import_scene.pynifly(filepath=ruta)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=ruta)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=ruta)
    else:
        raise SystemExit("extension no soportada: %s" % ext)
    # PyNifly importa la COLISION como malla mas. Un bhkBoxShape son 8
    # vertices que en pantalla es un rectangulo gigante que tapa el modelo
    # entero -- y no da ningun error: el render "funciona" y sale una lamina
    # gris. Se filtran por prefijo, que es como PyNifly las nombra.
    todas = [o for o in bpy.data.objects if o.type == 'MESH']
    colision = [o for o in todas if o.name.lower().startswith("bhk")]
    mallas = [o for o in todas if o not in colision]
    # BORRARLAS de la escena, no solo excluirlas de la lista. Blender renderiza
    # lo que esta en la escena; filtrar una variable de Python no saca nada del
    # render. Ese error costo tres diagnosticos equivocados: la caja seguia
    # apareciendo como una lamina gris del tamano del modelo y parecia un
    # problema de materiales, de recorte de camara y de encuadre, en ese orden.
    for o in colision:
        bpy.data.objects.remove(o, do_unlink=True)
    if colision:
        print("[colision] %d malla(s) de colision borradas de la escena"
              % len(colision))
    if not mallas:
        raise SystemExit("%s no trae mallas visibles" % ruta)

    # Sacar el modificador Armature y la armature. Sin esto, el render sale con
    # la figura DESARMADA aunque las matrices esten bien, y es facil culpar al
    # encuadre: la caja se calcula con `matrix_world @ v.co`, que ignora
    # modificadores, mientras que el render si los aplica. Si encima PyNifly
    # sustituyo un esqueleto de referencia al importar, ese esqueleto deforma
    # la malla hacia proporciones que no son las del bicho.
    #
    # Para una referencia de ControlNet la pose de bind es justamente la que se
    # quiere: sin deformar, simetrica, con los miembros separados.
    for o in mallas:
        for m in [m for m in o.modifiers if m.type == 'ARMATURE']:
            o.modifiers.remove(m)
    for o in [o for o in bpy.data.objects if o.type == 'ARMATURE']:
        bpy.data.objects.remove(o, do_unlink=True)
    return mallas


def puntos_de(mallas):
    return [o.matrix_world @ v.co for o in mallas for v in o.data.vertices]


def material(nombre, color, emision):
    m = bpy.data.materials.new(nombre)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    sal = nt.nodes.new("ShaderNodeOutputMaterial")
    if emision:
        sh = nt.nodes.new("ShaderNodeEmission")
        sh.inputs["Color"].default_value = color
        sh.inputs["Strength"].default_value = 1.0
    else:
        sh = nt.nodes.new("ShaderNodeBsdfDiffuse")
        sh.inputs["Color"].default_value = color
    nt.links.new(sh.outputs[0], sal.inputs["Surface"])
    return m


def aplicar(mallas, mat):
    for o in mallas:
        o.data.materials.clear()
        o.data.materials.append(mat)


def fondo(color):
    w = bpy.data.worlds.get("W") or bpy.data.worlds.new("W")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = color
    w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    bpy.context.scene.world = w


def luces(az):
    """Tres puntos suaves, orientados con la camara: la arcilla tiene que leer
    igual en todas las vistas."""
    a = math.radians(az)
    for dx, dy, energia, alt in ((0.6, -1.0, 4.0, 1.2),
                                 (-1.0, -0.4, 2.0, 0.6),
                                 (0.2, 1.0, 1.5, 0.9)):
        ux = dx * math.cos(a) - dy * math.sin(a)
        uy = dx * math.sin(a) + dy * math.cos(a)
        d = bpy.data.lights.new("L", type='SUN')
        d.energy = energia
        o = bpy.data.objects.new("L", d)
        bpy.context.scene.collection.objects.link(o)
        o.rotation_euler = (math.radians(55 * alt), 0, math.atan2(uy, ux) + math.pi / 2)


def compositor_profundidad(cerca, lejos):
    """Z pass normalizado. Cerca = blanco, lejos = negro."""
    esc = bpy.context.scene
    esc.use_nodes = True
    esc.view_layers[0].use_pass_z = True
    nt = esc.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    rl = nt.nodes.new("CompositorNodeRLayers")
    rango = nt.nodes.new("CompositorNodeMapRange")
    rango.inputs["From Min"].default_value = cerca
    rango.inputs["From Max"].default_value = lejos
    rango.inputs["To Min"].default_value = 1.0     # cerca = blanco
    rango.inputs["To Max"].default_value = 0.0     # lejos = negro
    rango.use_clamp = True
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(rl.outputs["Depth"], rango.inputs["Value"])
    nt.links.new(rango.outputs[0], comp.inputs["Image"])


def compositor_directo():
    esc = bpy.context.scene
    esc.use_nodes = True
    nt = esc.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    rl = nt.nodes.new("CompositorNodeRLayers")
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(rl.outputs["Image"], comp.inputs["Image"])


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) < 2:
        print(__doc__)
        return
    entrada, salida = args[0], args[1]
    nombres = ["frente", "perfil"]
    if "--vistas" in args:
        nombres = args[args.index("--vistas") + 1].split(",")
    frente_az = FRENTE_AZ
    if "--frente-az" in args:
        frente_az = float(args[args.index("--frente-az") + 1])
    vistas = {k: (frente_az + d) % 360.0 for k, d in DESFASES.items()}
    for n in nombres:
        if n not in vistas:
            raise SystemExit("vista desconocida: %s (hay %s)"
                             % (n, ", ".join(sorted(vistas))))

    limpiar()
    mallas = importar(entrada)
    pts = puntos_de(mallas)
    z0 = min(p.z for p in pts)
    z1 = max(p.z for p in pts)
    alto = z1 - z0

    # --- encuadre COMPARTIDO: el mayor de todas las vistas ---
    escala = 0.0
    centros = {}
    for nom in nombres:
        a = math.radians(vistas[nom])
        us = [p.x * math.cos(a) + p.y * math.sin(a) for p in pts]
        vs = [p.z for p in pts]
        cu = (min(us) + max(us)) / 2.0
        cv = (min(vs) + max(vs)) / 2.0
        centros[nom] = (cu, cv)
        escala = max(escala,
                     (max(us) - min(us)) * RES[1] / float(RES[0]),
                     max(vs) - min(vs))
    escala *= MARGEN

    esc = bpy.context.scene
    esc.render.engine = 'BLENDER_EEVEE_NEXT'
    esc.render.resolution_x, esc.render.resolution_y = RES
    esc.render.film_transparent = False
    esc.render.image_settings.file_format = 'PNG'
    esc.render.image_settings.color_mode = 'RGB'

    cam_d = bpy.data.cameras.new("cam")
    cam_d.type = 'ORTHO'
    cam_d.ortho_scale = escala
    # Planos de recorte. El default de Blender es clip_end = 100, y la camara
    # se aleja ~3x el alto del modelo: para un bicho de 300 unidades quedan
    # ~900, o sea TODO el modelo detras del plano lejano. El sintoma no es una
    # imagen vacia sino una lamina gris que parece un bug de materiales.
    cam_d.clip_start = 0.1
    cam_d.clip_end = 0.0
    cam = bpy.data.objects.new("cam", cam_d)
    esc.collection.objects.link(cam)
    esc.camera = cam

    dist = max(alto, escala) * 3.0
    cam_d.clip_end = dist * 2.5
    os.makedirs(salida, exist_ok=True)
    base = os.path.splitext(os.path.basename(entrada))[0]
    hechos = []

    mat_arcilla = material("arcilla", (0.62, 0.60, 0.58, 1.0), False)
    mat_blanco = material("blanco", (1.0, 1.0, 1.0, 1.0), True)

    for nom in nombres:
        a = math.radians(vistas[nom])
        cu, cv = centros[nom]
        centro = Vector((cu * math.cos(a), cu * math.sin(a), cv))
        cam.location = (centro.x + dist * math.sin(a),
                        centro.y - dist * math.cos(a),
                        centro.z)
        cam.rotation_euler = (math.pi / 2, 0, a)

        # profundidad real de la figura vista desde esta camara
        vista = Vector((-math.sin(a), math.cos(a), 0.0))
        prof = [(p - cam.location) @ vista for p in pts]
        cerca, lejos = min(prof), max(prof)

        for pasada in ("profundidad", "arcilla", "silueta"):
            for l in [o for o in bpy.data.objects if o.type == 'LIGHT']:
                bpy.data.objects.remove(l, do_unlink=True)
            if pasada == "profundidad":
                aplicar(mallas, mat_arcilla)
                fondo((0, 0, 0, 1))
                compositor_profundidad(cerca, lejos)
            elif pasada == "arcilla":
                aplicar(mallas, mat_arcilla)
                fondo((0.05, 0.05, 0.06, 1))
                luces(vistas[nom])
                compositor_directo()
            else:
                aplicar(mallas, mat_blanco)
                fondo((0, 0, 0, 1))
                compositor_directo()

            ruta = os.path.join(salida, "%s_%s_%s.png" % (base, nom, pasada))
            esc.render.filepath = ruta
            bpy.ops.render.render(write_still=True)
            hechos.append(ruta)
            print("[%s] %s" % (pasada, ruta))

    print("")
    print("[alto] %.1f unidades = %.2f m   [escala ortografica compartida] %.1f"
          % (alto, alto / 70.0, escala))
    print("[frente] azimut %.0f. Si el render 'frente' muestra la espalda, "
          "volve a correr con --frente-az %.0f" % (frente_az,
                                                   (frente_az + 180) % 360))
    print("[listo] %d imagenes en %s" % (len(hechos), salida))


main()
