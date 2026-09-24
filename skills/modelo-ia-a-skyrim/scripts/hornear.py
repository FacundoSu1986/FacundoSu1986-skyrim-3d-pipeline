# -*- coding: utf-8 -*-
"""Hornea normal, AO y albedo de la malla ALTA de la IA sobre la BAJA de juego.

Es el paso 7a de la capa HD (references/hd-texturas.md). Junta en un script lo
que las trampas ya pagaron:

  * Hornea al DOBLE y reduce 2x2 filtrando cada mapa como lo que es
    (trampa 35, `reducir_horneado.py`).
  * Normal en espacio tangente con el verde TAL CUAL, `POS_Y` (trampa 30).
  * Albedo con `EMIT` y no con `DIFFUSE`: `DIFFUSE` deja negro lo metalico y
    con la configuracion por defecto hornea color x luz (trampa 31).
  * El color space de cada imagen se fija AL CREARLA, antes de escribir
    pixeles (trampa 16).

Lo que NO hace, a proposito:
  * No hace UV. La baja tiene que llegar desplegada, y desplegada DESPUES de
    todo modificador que agregue caras (trampa 32).
  * No arregla la luz horneada del generador (trampa 21): el albedo sale con
    la que traiga. Eso se corrige despues, mirando el mapa plano.
  * No escribe DDS ni empaqueta la mascara especular en el alfa del `_n`:
    deja PNG. La conversion va con texconv/NVTT o con el camino de texturas
    del pipeline.

Uso:
  blender -b --python hornear.py -- <baja.blend> <alta.blend> <carpeta> <res> [--extrusion F] [--force]

  <baja.blend>  UNA malla de juego con UV (la que dejo preparar_parte/montar/rig)
  <alta.blend>  la de `preparar_parte.py --guardar-alto`, con la MISMA
                transformacion que la baja (trampa 34)
  <res>         resolucion FINAL, potencia de 2 (se hornea a 2*res)
  --extrusion   distancia del cage como fraccion de la diagonal de la baja
                (por defecto 0.01; [no medido]: subila si aparecen huecos
                negros, bajala si el relieve de una pieza cae en otra)

Salida: <carpeta>/<nombre>_albedo.png, <nombre>_n.png (RGB, sin alfa todavia),
<nombre>_ao.png.

VERIFICACION: este script no tiene autotest --necesita Blender--. Controles
despues de correrlo: el albedo no puede salir casi negro (el script avisa),
y el normal se juzga con luz rasante y sin albedo (trampa 30): los remaches
salen, las incisiones se hunden.
"""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reducir_horneado import reducir  # noqa: E402

MARGEN_FINAL = 8          # texeles de sangrado alrededor de cada isla


def potencia_de_2(n):
    return n >= 4 and (n & (n - 1)) == 0


def args_cli():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(args) < 4:
        print(__doc__)
        raise SystemExit(2)
    baja, alta, carpeta, res = args[0], args[1], args[2], int(args[3])
    if not potencia_de_2(res):
        raise SystemExit("res %d: tiene que ser potencia de 2 (0 excepciones "
                         "en 32.241 texturas vanilla)" % res)
    extrusion = 0.01
    if "--extrusion" in args:
        extrusion = float(args[args.index("--extrusion") + 1])
    return baja, alta, carpeta, res, extrusion, "--force" in args


def una_malla(objetos, de_donde):
    mallas = [o for o in objetos if o.type == 'MESH']
    if len(mallas) != 1:
        raise SystemExit("%s: se esperaba UNA malla, hay %d (%s). Unilas o "
                         "horneá pieza por pieza."
                         % (de_donde, len(mallas), [o.name for o in mallas]))
    return mallas[0]


def cargar_alta(ruta):
    with bpy.data.libraries.load(ruta, link=False) as (origen, destino):
        destino.objects = list(origen.objects)
    nuevos = [o for o in destino.objects if o is not None]
    for o in nuevos:
        bpy.context.scene.collection.objects.link(o)
    return una_malla(nuevos, ruta)


def diagonal(obj):
    co = [obj.matrix_world @ v.co for v in obj.data.vertices]
    lo = [min(c[i] for c in co) for i in range(3)]
    hi = [max(c[i] for c in co) for i in range(3)]
    return sum((hi[i] - lo[i]) ** 2 for i in range(3)) ** 0.5


def imagen(nombre, lado, espacio):
    img = bpy.data.images.new(nombre, lado, lado, alpha=True)
    # ANTES de que nadie escriba pixeles (trampa 16).
    img.colorspace_settings.name = espacio
    return img


def destino_en_baja(baja, img):
    """Nodo de imagen activo en cada material de la baja: ahi escribe el bake."""
    if not baja.data.materials:
        baja.data.materials.append(bpy.data.materials.new(baja.name + "_bake"))
    nodos = []
    for mat in baja.data.materials:
        mat.use_nodes = True
        n = mat.node_tree.nodes.new("ShaderNodeTexImage")
        n.image = img
        mat.node_tree.nodes.active = n
        nodos.append((mat, n))
    return nodos


def quitar(nodos):
    for mat, n in nodos:
        mat.node_tree.nodes.remove(n)


def albedo_como_emision(alta):
    """Base Color -> Emission -> salida, solo durante el bake (trampa 31).
    Devuelve con que restaurar."""
    restaurar = []
    for mat in alta.data.materials:
        if mat is None or not mat.use_nodes:
            continue
        arbol = mat.node_tree
        salida = next((n for n in arbol.nodes
                       if n.type == 'OUTPUT_MATERIAL' and n.is_active_output),
                      None)
        bsdf = next((n for n in arbol.nodes if n.type == 'BSDF_PRINCIPLED'),
                    None)
        if salida is None or bsdf is None:
            print("[aviso] %s: sin Principled/salida, su albedo sale negro"
                  % mat.name)
            continue
        base = bsdf.inputs["Base Color"]
        previo = [l.from_socket for l in salida.inputs["Surface"].links]
        emi = arbol.nodes.new("ShaderNodeEmission")
        if base.links:
            arbol.links.new(base.links[0].from_socket, emi.inputs["Color"])
        else:
            emi.inputs["Color"].default_value = base.default_value
        arbol.links.new(emi.outputs["Emission"], salida.inputs["Surface"])
        restaurar.append((arbol, salida, emi, previo))
    return restaurar


def restaurar_materiales(restaurar):
    for arbol, salida, emi, previo in restaurar:
        arbol.nodes.remove(emi)
        for s in previo:
            arbol.links.new(s, salida.inputs["Surface"])


def hornear(tipo, alta, baja, img, extrusion, **extra):
    nodos = destino_en_baja(baja, img)
    try:
        bpy.ops.object.select_all(action='DESELECT')
        alta.select_set(True)
        baja.select_set(True)
        bpy.context.view_layer.objects.active = baja
        bpy.ops.object.bake(type=tipo, use_selected_to_active=True,
                            cage_extrusion=extrusion,
                            margin=MARGEN_FINAL * 2, **extra)
    finally:
        quitar(nodos)


def reducir_y_guardar(img, modo, espacio, ruta):
    lado = img.size[0]
    pix, w, h = reducir(list(img.pixels[:]), lado, lado, modo)
    final = imagen(os.path.basename(ruta), w, espacio)
    final.pixels[:] = pix
    final.filepath_raw = ruta
    final.file_format = 'PNG'
    final.save()
    return pix


def main():
    ruta_baja, ruta_alta, carpeta, res, frac, forzar = args_cli()

    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(ruta_baja))
    baja = una_malla(bpy.context.scene.objects, ruta_baja)
    if not baja.data.uv_layers:
        raise SystemExit("%s no tiene UV: desplegala antes de hornear "
                         "(y despues de todo modificador, trampa 32)"
                         % baja.name)
    alta = cargar_alta(os.path.abspath(ruta_alta))

    nombre = baja.name
    carpeta = os.path.abspath(carpeta)
    rutas = {m: os.path.join(carpeta, "%s_%s.png" % (nombre, m))
             for m in ("albedo", "n", "ao")}
    existentes = [r for r in rutas.values() if os.path.exists(r)]
    if existentes and not forzar:
        raise SystemExit("ya existen %s: usa --force para pisarlos"
                         % existentes)
    os.makedirs(carpeta, exist_ok=True)

    escena = bpy.context.scene
    escena.render.engine = 'CYCLES'
    escena.cycles.samples = 1
    extrusion = frac * diagonal(baja)
    lado = res * 2

    img = imagen("normal_x2", lado, "Non-Color")
    hornear('NORMAL', alta, baja, img, extrusion, normal_space='TANGENT',
            normal_r='POS_X', normal_g='POS_Y', normal_b='POS_Z')
    reducir_y_guardar(img, "normal", "Non-Color", rutas["n"])

    img = imagen("ao_x2", lado, "Non-Color")
    hornear('AO', alta, baja, img, extrusion)
    reducir_y_guardar(img, "lineal", "Non-Color", rutas["ao"])

    img = imagen("albedo_x2", lado, "sRGB")
    restaurar = albedo_como_emision(alta)
    try:
        hornear('EMIT', alta, baja, img, extrusion)
    finally:
        restaurar_materiales(restaurar)
    pix = reducir_y_guardar(img, "color", "sRGB", rutas["albedo"])

    # Control de la trampa 31: un albedo casi negro es el sintoma, sin error.
    n = len(pix) // 4
    media = sum(pix[i * 4] + pix[i * 4 + 1] + pix[i * 4 + 2]
                for i in range(n)) / (3.0 * n)
    if media < 0.02:
        print("[aviso] albedo casi negro (media %.4f): revisar materiales de "
              "la alta (trampa 31)" % media)

    print("[bake] %s: %dx%d (horneado a %d), extrusion %.4f"
          % (nombre, res, res, lado, extrusion))
    for m, r in rutas.items():
        print("  %-6s %s" % (m, r))


main()
