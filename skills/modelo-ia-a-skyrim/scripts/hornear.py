# -*- coding: utf-8 -*-
"""Hornea la malla ALTA de la IA sobre la BAJA de juego: normal, AO, albedo,
rugosidad y metalicidad, con controles medidos.

Es el paso 4c de la capa HD (references/hd-texturas.md). Junta lo que las
trampas ya pagaron:

  * Hornea al DOBLE y reduce 2x2 filtrando cada mapa como lo que es
    (trampa 35, `horneado_puro.py`).
  * Normal en espacio tangente con el verde TAL CUAL, `POS_Y` (trampa 30).
    Incluye el normal/bump del MATERIAL de la alta, no solo su geometria
    (medido con bpy 4.5.14: bump con fuerza 0 sale plano, con fuerza 1 la
    desviacion del canal R es 0,42).
  * Albedo, rugosidad y metalicidad con `EMIT`: cada entrada del Principled
    se conecta a una emision solo durante su bake (trampa 31).
  * PNG propios SIN alfa: el bake escribe alfa = 1 en todo lo horneado, y un
    `_n` convertido con ese alfa es plastico puro.
  * Margen 0 en Blender y margen propio (`horneado_puro.dilatar`): con margen
    > 0 Blender pone alfa 1 en TODA la imagen y el hueco del atlas quedaba en
    RGB 0 -- rugosidad 0, que la fase de texturas vuelve especular al maximo
    (medido: 24,7 % de texeles). Lo que no alcanza el margen toma un valor
    neutro (`horneado_puro.RELLENO`).
  * `max_ray_distance` = 2 x extrusion: sin limite, un rayo que no encuentra
    la superficie cercana sigue hasta el OTRO LADO de la alta y trae su color
    (medido: puntos verdes dentro de islas rojas en una esfera). Con limite,
    ese texel cuenta como fallido y el margen propio lo tapa.

VARIAS PIEZAS, UN ATLAS
-----------------------
La baja puede tener varias mallas que comparten atlas (trampa 17). Se unen en
memoria para hornear de una vez --asi el margen de una pieza no pisa a otra--
y se hornea desde TODAS las altas. Cada baja `X` se empareja con la alta
`X_alto` (el nombre que deja `preparar_parte.py --guardar-alto`); con una sola
de cada lado se emparejan sin mirar nombres. El .blend de la baja NO se
guarda: nada de lo que se hace aca le queda.

CONTROLES
---------
  alineacion   ANTES de hornear, caja de cada baja contra la de su alta. Si no
               coinciden, sale con error: el modo de falla mas comun del bake
               es una alta sin la transformacion de la baja, y no da error.
  UV activa    la capa que se hornea es la activa; si no es tambien la de
               render, sale con error en vez de elegir por vos.
  cobertura    % del atlas que ocupan las islas. Un 2048 con 25 % de
               cobertura es un 1024 lleno que pesa como 2048.
  fallidos     % de texeles de isla donde el rayo no encontro la alta.
               Medido con bpy 4.5.14: un rayo que no pega deja el texel sin
               tocar, igual que uno fuera de isla; por eso se hornean dos
               mascaras (la baja sola y la baja desde la alta). Las dos van
               SIN limpiar sobre una imagen de alfa 0: `use_clear` no sirve
               para esto, porque sin `selected_to_active` llena TODO con
               alfa 1 (medido: daba 100 % de cobertura con 24 % de area UV).
               Un fallido alto casi siempre es extrusion corta: el relieve de
               la alta sale mas afuera que el cage.
  densidad     texeles por unidad de cada pieza; piezas del mismo atlas con
               densidades muy distintas se ven una borrosa al lado de la otra.
  albedo       media de luminancia SOLO sobre texeles cubiertos (trampa 31).
  luz horneada correlacion entre la luminancia del albedo y el AO horneado.
               Alta sugiere sombras pegadas al color (trampa 21). Es
               evidencia, no prueba: la suciedad pintada en los huecos
               tambien correlaciona.

Los umbrales de aviso son criterio `[no medido]`; los numeros se escriben
siempre en `<base>_horneado.json` para poder auditarlos.

Uso:
  blender -b --python hornear.py -- <baja.blend> <carpeta> <res> <alta.blend> [<alta.blend> ...]
          [--extrusion F] [--muestras-ao N] [--force]

  <res>           resolucion FINAL, potencia de 2 (se hornea a 2*res)
  --extrusion     distancia del cage como fraccion de la diagonal de la baja
                  --la MEDIANA de las piezas, no la del conjunto: con varias
                  piezas separadas la del conjunto da rayos que cruzan de una
                  a otra-- (0.01 por defecto `[no medido]`; subila si hay
                  fallidos, bajala si el relieve de una pieza cae en otra).
                  Los rayos llegan hasta 2 x extrusion.
  --muestras-ao   muestras del AO (32 por defecto `[no medido]`). Normal y
                  EMIT usan 1: con una muestra el resultado es deterministico
                  y el aliasing lo resuelve hornear al doble.
  --distancia-ao  hasta donde mira el AO, como fraccion de la diagonal
                  mediana de las piezas (0.1 por defecto `[no medido]`). Sin
                  fijarla, el AO usaba la distancia del World de la escena
                  --10 unidades, sea el asset de 1 o de 100-- y una escena sin
                  World daba AO blanco sin error. La baja NO tapa rayos del
                  AO (medido: un cubo de la baja encima de la alta deja el AO
                  en 1,0; el mismo cubo en la alta lo baja a 0,83).

Salida en <carpeta>, con <base> = nombre del .blend de la baja:
  <base>_albedo.png      RGB sRGB
  <base>_normalgl.png    RGB, verde +Y (OpenGL, el de Skyrim)
  <base>_roughness.png   gris
  <base>_metallic.png    gris
  <base>_ao.png          gris
  <base>_horneado.json   los controles de arriba
Son los nombres de entrada de la fase de texturas del pipeline (PR #51): el
alfa del `_n` sale de la rugosidad y el `_m` de la metalicidad, ahora sobre
las UV NUEVAS.
"""

import json
import os
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import horneado_puro as hp  # noqa: E402

MARGEN_FINAL = 8          # texeles de sangrado alrededor de cada isla
VACIO = (0.0, 0.0, 0.0, 0.0)
UV_BAKE = "_uv_bake"      # nombre comun de la capa UV al unir las bajas
MUESTRAS_ESTADISTICA = 65536
AVISO_FALLIDOS = 0.01     # criterio [no medido]
AVISO_DENSIDAD = 2.0      # max/min entre piezas, criterio [no medido]
AVISO_CORRELACION = 0.5   # criterio [no medido]


def potencia_de_2(n):
    return n >= 4 and (n & (n - 1)) == 0


def args_cli():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opciones = {"--extrusion": 0.01, "--muestras-ao": 32,
                "--distancia-ao": 0.1}
    posicionales, i = [], 0
    while i < len(args):
        a = args[i]
        if a in opciones:
            if i + 1 >= len(args):
                raise SystemExit("%s necesita un valor" % a)
            opciones[a] = type(opciones[a])(args[i + 1])
            i += 2
            continue
        if a != "--force":
            posicionales.append(a)
        i += 1
    if len(posicionales) < 4:
        print(__doc__)
        raise SystemExit(2)
    baja, carpeta, res = posicionales[0], posicionales[1], int(posicionales[2])
    if not potencia_de_2(res):
        raise SystemExit("res %d: tiene que ser potencia de 2 (0 excepciones "
                         "en 32.241 texturas vanilla)" % res)
    return (baja, carpeta, res, posicionales[3:], opciones["--extrusion"],
            opciones["--muestras-ao"], opciones["--distancia-ao"],
            "--force" in args)


def mallas(objetos):
    return [o for o in objetos if o is not None and o.type == 'MESH']


def cargar_altas(rutas):
    altas = []
    for ruta in rutas:
        with bpy.data.libraries.load(os.path.abspath(ruta),
                                     link=False) as (origen, destino):
            destino.objects = list(origen.objects)
        nuevas = mallas(destino.objects)
        if not nuevas:
            raise SystemExit("%s no trae mallas" % ruta)
        for o in nuevas:
            bpy.context.scene.collection.objects.link(o)
        altas.extend(nuevas)
    return altas


def emparejar(bajas, altas):
    if len(bajas) == 1 and len(altas) == 1:
        return [(bajas[0], altas[0])]
    por_nombre = {a.name: a for a in altas}
    pares, faltan = [], []
    for b in bajas:
        a = por_nombre.get(b.name + "_alto")
        if a is None:
            faltan.append(b.name)
        else:
            pares.append((b, a))
    if faltan:
        raise SystemExit("sin alta para %s: se busca '<nombre>_alto' (lo deja "
                         "preparar_parte.py --guardar-alto). Altas cargadas: "
                         "%s" % (faltan, sorted(por_nombre)))
    return pares


def capa_uv(baja):
    capas = baja.data.uv_layers
    if not len(capas):
        raise SystemExit("%s no tiene UV: desplegala antes de hornear "
                         "(y despues de todo modificador que agregue caras, "
                         "trampa 32)" % baja.name)
    activa = capas.active
    render = next((c for c in capas if c.active_render), activa)
    if activa.name != render.name:
        raise SystemExit("%s: la UV activa (%s) no es la de render (%s). "
                         "Elegi cual se hornea y marcala en las dos."
                         % (baja.name, activa.name, render.name))
    return activa


def caja_mundo(obj):
    co = [obj.matrix_world @ v.co for v in obj.data.vertices]
    return (tuple(min(c[i] for c in co) for i in range(3)),
            tuple(max(c[i] for c in co) for i in range(3)))


def areas(obj):
    """(area 3D en mundo, area UV) de la malla, sobre sus triangulos."""
    me = obj.data
    me.calc_loop_triangles()
    uv = me.uv_layers.active.data
    mw = obj.matrix_world
    a3 = auv = 0.0
    for t in me.loop_triangles:
        p = [mw @ me.vertices[v].co for v in t.vertices]
        a3 += (p[1] - p[0]).cross(p[2] - p[0]).length / 2.0
        u = [uv[i].uv for i in t.loops]
        auv += abs((u[1][0] - u[0][0]) * (u[2][1] - u[0][1])
                   - (u[2][0] - u[0][0]) * (u[1][1] - u[0][1])) / 2.0
    return a3, auv


def unir_bajas(bajas):
    for b in bajas:
        b.data.uv_layers.active.name = UV_BAKE
    bpy.ops.object.select_all(action='DESELECT')
    for b in bajas:
        b.select_set(True)
    bpy.context.view_layer.objects.active = bajas[0]
    if len(bajas) > 1:
        bpy.ops.object.join()
    baja = bpy.context.view_layer.objects.active
    capa = baja.data.uv_layers[UV_BAKE]
    baja.data.uv_layers.active = capa
    capa.active_render = True
    return baja


def diagonal(obj):
    lo, hi = caja_mundo(obj)
    return sum((hi[i] - lo[i]) ** 2 for i in range(3)) ** 0.5


def imagen(nombre, lado, espacio, fondo=None):
    img = bpy.data.images.new(nombre, lado, lado, alpha=True)
    # ANTES de que nadie escriba pixeles (trampa 16).
    img.colorspace_settings.name = espacio
    if fondo is not None:
        img.generated_color = fondo
    return img


def mascara(altas, baja, res, extrusion, desde_alta):
    """Texeles que el bake toca: alfa 1 sobre un fondo de alfa 0."""
    img = imagen("mascara", res, "Non-Color", fondo=VACIO)
    return hornear('NORMAL', altas, baja, img, extrusion,
                   desde_alta=desde_alta)[..., 3] > 0.5


def leer(img):
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, 4)


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


def materiales(objetos):
    vistos = {}
    for o in objetos:
        for m in o.data.materials:
            if m is not None:
                vistos[m.name] = m
    return list(vistos.values())


def entrada_como_emision(altas, entrada):
    """La entrada `entrada` del Principled -> Emission -> salida, solo durante
    el bake (trampa 31). Devuelve con que restaurar y los materiales sin
    Principled."""
    restaurar, sin_principled = [], []
    for mat in materiales(altas):
        if not mat.use_nodes:
            sin_principled.append(mat.name)
            continue
        arbol = mat.node_tree
        salida = next((n for n in arbol.nodes
                       if n.type == 'OUTPUT_MATERIAL' and n.is_active_output),
                      None)
        bsdf = next((n for n in arbol.nodes if n.type == 'BSDF_PRINCIPLED'),
                    None)
        if salida is None or bsdf is None:
            sin_principled.append(mat.name)
            continue
        socket = bsdf.inputs[entrada]
        previo = [l.from_socket for l in salida.inputs["Surface"].links]
        emi = arbol.nodes.new("ShaderNodeEmission")
        if socket.links:
            arbol.links.new(socket.links[0].from_socket, emi.inputs["Color"])
        else:
            v = socket.default_value
            emi.inputs["Color"].default_value = (
                tuple(v) if hasattr(v, "__len__") else (v, v, v, 1.0))
        arbol.links.new(emi.outputs["Emission"], salida.inputs["Surface"])
        restaurar.append((arbol, salida, emi, previo))
    return restaurar, sin_principled


def restaurar_materiales(restaurar):
    for arbol, salida, emi, previo in restaurar:
        arbol.nodes.remove(emi)
        for s in previo:
            arbol.links.new(s, salida.inputs["Surface"])


def hornear(tipo, altas, baja, img, extrusion, desde_alta=True, **extra):
    """Margen 0 y sin limpiar sobre una imagen de alfa 0: el alfa queda en 1
    exactamente en lo horneado (ver `horneado_puro.dilatar`)."""
    nodos = destino_en_baja(baja, img)
    try:
        bpy.ops.object.select_all(action='DESELECT')
        if desde_alta:
            for a in altas:
                a.select_set(True)
        baja.select_set(True)
        bpy.context.view_layer.objects.active = baja
        bpy.ops.object.bake(type=tipo, use_selected_to_active=desde_alta,
                            cage_extrusion=extrusion,
                            max_ray_distance=2.0 * extrusion, margin=0,
                            use_clear=False, **extra)
    finally:
        for mat, n in nodos:
            mat.node_tree.nodes.remove(n)
    return leer(img)


def muestrear(*arrays):
    """Submuestreo regular para estadisticas en Python puro."""
    n = arrays[0].size
    paso = max(1, n // MUESTRAS_ESTADISTICA)
    return [a.ravel()[::paso].tolist() for a in arrays]


def main():
    (ruta_baja, carpeta, res, rutas_altas, frac, muestras_ao, frac_ao,
     forzar) = args_cli()

    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(ruta_baja))
    bajas = mallas(bpy.context.scene.objects)
    if not bajas:
        raise SystemExit("%s no trae mallas" % ruta_baja)
    for b in bajas:
        print("[uv] %s: se hornea la capa '%s'" % (b.name, capa_uv(b).name))
    altas = cargar_altas(rutas_altas)
    pares = emparejar(bajas, altas)

    motivos = []
    for b, a in pares:
        for m in hp.alineacion(caja_mundo(b), caja_mundo(a)):
            motivos.append("%s <- %s: %s" % (b.name, a.name, m))
    if motivos:
        raise SystemExit("la alta no esta donde esta la baja (aplicale la "
                         "misma transformacion, trampa 34):\n  "
                         + "\n  ".join(motivos))

    densidades = {}
    for b in bajas:
        a3, auv = areas(b)
        densidades[b.name] = hp.densidad_texel(a3, auv, res)
    validas = [d for d in densidades.values() if d]
    dispersion = max(validas) / min(validas) if validas else None

    base = os.path.splitext(os.path.basename(ruta_baja))[0]
    carpeta = os.path.abspath(carpeta)
    mapas = {"albedo": ("color", "sRGB", 3), "normalgl": ("normal",
             "Non-Color", 3), "roughness": ("lineal", "Non-Color", 1),
             "metallic": ("lineal", "Non-Color", 1),
             "ao": ("lineal", "Non-Color", 1)}
    rutas = {m: os.path.join(carpeta, "%s_%s.png" % (base, m)) for m in mapas}
    rutas["json"] = os.path.join(carpeta, base + "_horneado.json")
    existentes = [r for r in rutas.values() if os.path.exists(r)]
    if existentes and not forzar:
        raise SystemExit("ya existen %s: usa --force para pisarlos"
                         % existentes)
    os.makedirs(carpeta, exist_ok=True)

    # Los nombres ANTES de unir: el join borra los objetos que no son el
    # activo, y cualquier referencia a ellos revienta despues.
    piezas = [{"baja": b.name, "alta": a.name} for b, a in pares]
    diagonales = sorted(diagonal(b) for b in bajas)
    extrusion = frac * diagonales[len(diagonales) // 2]
    distancia_ao = frac_ao * diagonales[len(diagonales) // 2]
    baja = unir_bajas(bajas)
    escena = bpy.context.scene
    escena.render.engine = 'CYCLES'
    escena.cycles.samples = 1
    if escena.world is None:
        escena.world = bpy.data.worlds.new("hornear")
    escena.world.light_settings.distance = distancia_ao
    lado = res * 2

    # Mascaras a resolucion final, sin margen.
    cubierto = mascara(altas, baja, res, extrusion, desde_alta=False)
    acierto = mascara(altas, baja, res, extrusion, desde_alta=True)
    n_cub = int(cubierto.sum())
    cobertura = n_cub / float(cubierto.size)
    fallidos = (int((cubierto & ~acierto).sum()) / float(n_cub)
                if n_cub else None)

    finales = {}

    def guardar(mapa, arr):
        modo, _, canales = mapas[mapa]
        hp.dilatar(arr, MARGEN_FINAL * 2)
        hp.rellenar_vacios(arr, hp.RELLENO[mapa])
        red = hp.reducir_np(arr, modo)
        hp.escribir_png(rutas[mapa], res, res, canales,
                        hp.a_bytes(red, res, res, canales))
        finales[mapa] = red

    guardar("normalgl", hornear(
        'NORMAL', altas, baja, imagen("n2", lado, "Non-Color", VACIO),
        extrusion, normal_space='TANGENT', normal_r='POS_X',
        normal_g='POS_Y', normal_b='POS_Z'))

    escena.cycles.samples = muestras_ao
    guardar("ao", hornear('AO', altas, baja,
                          imagen("ao2", lado, "Non-Color", VACIO), extrusion))
    escena.cycles.samples = 1

    sin_principled = set()
    for mapa, entrada in (("albedo", "Base Color"), ("roughness", "Roughness"),
                          ("metallic", "Metallic")):
        restaurar, sin = entrada_como_emision(altas, entrada)
        sin_principled.update(sin)
        try:
            arr = hornear('EMIT', altas, baja,
                          imagen(mapa + "2", lado, mapas[mapa][1], VACIO),
                          extrusion)
        finally:
            restaurar_materiales(restaurar)
        guardar(mapa, arr)

    alb, ao = finales["albedo"], finales["ao"]
    lum = alb[..., 0] * 0.2126 + alb[..., 1] * 0.7152 + alb[..., 2] * 0.0722
    m_lum, m_ao, m_cub = muestrear(lum, ao[..., 0], cubierto)
    media_albedo = hp.media(m_lum, m_cub)
    corr = hp.correlacion(m_lum, m_ao, m_cub)

    reporte = {
        "blender": bpy.app.version_string, "res": res, "horneado_a": lado,
        "extrusion": extrusion, "muestras_ao": muestras_ao,
        "distancia_ao": distancia_ao,
        "piezas": piezas,
        "cobertura": round(cobertura, 4),
        "fallidos": None if fallidos is None else round(fallidos, 4),
        "densidad_texel": {k: None if v is None else round(v, 2)
                           for k, v in densidades.items()},
        "densidad_max_sobre_min": (None if dispersion is None
                                   else round(dispersion, 2)),
        "albedo_media_cubierta": (None if media_albedo is None
                                  else round(media_albedo, 4)),
        "correlacion_albedo_ao": None if corr is None else round(corr, 3),
        "materiales_sin_principled": sorted(sin_principled),
        "salidas": {m: rutas[m] for m in mapas},
    }
    with open(rutas["json"], "w", encoding="utf-8") as f:
        json.dump(reporte, f, indent=2, ensure_ascii=False)

    print("[bake] %s: %d piezas, %dx%d (horneado a %d), extrusion %.4f"
          % (base, len(piezas), res, res, lado, extrusion))
    print("  cobertura %.1f %% del atlas (equivale a un %d lleno)"
          % (cobertura * 100, int(res * cobertura ** 0.5)))
    for m in mapas:
        print("  %-9s %s" % (m, rutas[m]))
    print("  reporte   %s" % rutas["json"])

    avisos = []
    if n_cub == 0:
        avisos.append("la baja no cubre ningun texel: UV vacias o colapsadas")
    if fallidos is not None and fallidos > AVISO_FALLIDOS:
        avisos.append("%.1f %% de los texeles de isla no encontro la alta: "
                      "subi --extrusion o revisa la alineacion"
                      % (fallidos * 100))
    if dispersion is not None and dispersion > AVISO_DENSIDAD:
        avisos.append("densidad de texel dispareja entre piezas (max/min "
                      "%.2f): %s" % (dispersion, reporte["densidad_texel"]))
    if media_albedo is not None and media_albedo < 0.02:
        avisos.append("albedo casi negro sobre lo cubierto (media %.4f): "
                      "revisa los materiales de la alta (trampa 31)"
                      % media_albedo)
    if corr is not None and corr > AVISO_CORRELACION:
        avisos.append("el albedo correlaciona con el AO (r=%.2f): posible luz "
                      "horneada del generador (trampa 21)" % corr)
    if sin_principled:
        avisos.append("materiales sin Principled, salen negros en albedo/"
                      "rugosidad/metalicidad: %s" % sorted(sin_principled))
    for a in avisos:
        print("[aviso] %s" % a)


main()
