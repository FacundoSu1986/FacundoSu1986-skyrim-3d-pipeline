# -*- coding: utf-8 -*-
"""Mide un modelo recien llegado de una IA 3D. Correlo SIEMPRE antes de tocarlo.

Contesta de una sola pasada las preguntas que deciden si el modelo sirve y que
hay que arreglarle. Cada una corresponde a una trampa conocida:

  * cuantos CUERPOS sueltos trae    -- una lamina de varias vistas pegadas en
                                       una imagen produce varios modelos
                                       sueltos, no un modelo
  * si trae UV y texturas           -- algunas conversiones vienen peladas
  * cuantos triangulos              -- hay que bajar dos ordenes de magnitud
  * la proporcion                   -- es lo unico que no se arregla despues
  * aristas de borde                -- si es cascara abierta, backface culling
                                       la deja invisible de atras
  * hacia donde mira                -- Skyrim quiere +Y

Este script MIDE y no concluye. Donde el dato no alcanza para decidir, lo dice
en vez de adivinar: la orientacion se confirma mirando un render de perfil, y
varios cuerpos sueltos pueden ser varias figuras o pueden ser el detalle suelto
de un solo modelo. Las acciones destructivas (girar, solidificar) se deciden
con el numero delante, no por costumbre.

Uso:
  blender -b --python medir_parte.py -- <archivo> [<archivo> ...]
  blender -b --python medir_parte.py -- <archivo> --json salida.json
"""

import json
import os
import sys

import bpy
from mathutils import Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from correr_en_blender import correr  # noqa: E402


def limpiar():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)
    for i in list(bpy.data.images):
        bpy.data.images.remove(i)
    for m in list(bpy.data.materials):
        bpy.data.materials.remove(m)


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
    # Hornear la matriz del importador ANTES de medir. glTF es Y-up y el
    # importador deja esa rotacion en la matriz del objeto, no en los
    # vertices: medir en mundo y transformar en local mezcla dos espacios.
    for o in bpy.data.objects:
        if o.type == 'MESH':
            # Si dos objetos comparten el mismo datablock de malla --el
            # importador de glTF lo hace con geometria instanciada-- hornear la
            # matriz lo transforma DOS veces. Reproducido: dos cubos, uno en
            # X=0 y otro en X=5, terminan los dos en X 4.5..5.5.
            #
            # Es un fallo silencioso de manual: la caja envolvente sale bien
            # formada y equivocada. Hay que volverlos single-user primero.
            if o.data.users > 1:
                o.data = o.data.copy()
            o.data.transform(o.matrix_world)
            o.matrix_world = Matrix.Identity(4)
    return [o for o in bpy.data.objects if o.type == 'MESH']


def aristas_de_borde(malla, tol=1e-5):
    """Cuantas aristas tienen menos de dos caras. Una malla cerrada da cero.

    SE CANONICALIZA POR POSICION, NO POR INDICE. Los formatos de intercambio
    (glTF, FBX, OBJ) guardan las UV por vertice, asi que al importar cada
    costura de UV parte el vertice en dos indices distintos que ocupan el mismo
    punto. Comparando indices, las aristas de los dos lados de la costura no se
    emparejan y TODA costura cuenta como borde: una malla perfectamente cerrada
    puede reportar decenas de miles de bordes falsos.

    Redondear la posicion a una rejilla y usar eso como clave empareja los
    vertices coincidentes y deja solo los bordes de verdad.
    """
    def clave_pos(i):
        c = malla.vertices[i].co
        return (round(c.x / tol), round(c.y / tol), round(c.z / tol))

    pos = [clave_pos(i) for i in range(len(malla.vertices))]
    cuenta = {}
    for p in malla.polygons:
        vs = list(p.vertices)
        for k in range(len(vs)):
            a, b = pos[vs[k]], pos[vs[(k + 1) % len(vs)]]
            clave = (a, b) if a <= b else (b, a)
            cuenta[clave] = cuenta.get(clave, 0) + 1
    return sum(1 for v in cuenta.values() if v < 2)


def cuerpos_sueltos(mallas, tol=1e-5):
    """Componentes conexas reales, con su caja y su tamano.

    Se une por POSICION, no por indice, por el mismo motivo que
    aristas_de_borde(): los vertices partidos por isla de UV son el mismo punto
    del solido y no deben contarse como cuerpos distintos.

    Devuelve [(n_vertices, (x0,x1), (y0,y1), (z0,z1)), ...] de mayor a menor.
    NO interpreta el resultado: muchos cuerpos sueltos pueden ser varias
    figuras en un archivo (trampa 9) o el detalle suelto de un solo modelo
    (trampa 7, el piso del decimado). Distinguirlos es mirar las cajas.
    """
    padre = {}

    def raiz(a):
        while padre[a] != a:
            padre[a] = padre[padre[a]]
            a = padre[a]
        return a

    def unir(a, b):
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            padre[rb] = ra

    puntos = {}
    for o in mallas:
        m = o.data
        clave = []
        for v in m.vertices:
            c = v.co
            k = (round(c.x / tol), round(c.y / tol), round(c.z / tol))
            if k not in padre:
                padre[k] = k
                puntos[k] = (c.x, c.y, c.z)
            clave.append(k)
        for poli in m.polygons:
            vs = poli.vertices
            primero = clave[vs[0]]
            for i in range(1, len(vs)):
                unir(primero, clave[vs[i]])

    grupos = {}
    for k in padre:
        grupos.setdefault(raiz(k), []).append(k)

    fuera = []
    for miembros in grupos.values():
        cs = [puntos[k] for k in miembros]
        fuera.append((len(miembros),
                      (min(c[0] for c in cs), max(c[0] for c in cs)),
                      (min(c[1] for c in cs), max(c[1] for c in cs)),
                      (min(c[2] for c in cs), max(c[2] for c in cs))))
    fuera.sort(key=lambda t: -t[0])
    return fuera


def figuras_candidatas(cuerpos, alto_total):
    """Cuerpos que por si solos podrian ser una figura entera.

    Heuristica declarada como tal: un cuerpo que mide mas de la mitad del alto
    total del archivo y esta separado en X de los demas es sospechoso de ser
    otra figura. Un cuerpo chico es detalle, no figura.
    """
    if alto_total <= 0:
        return []
    grandes = [c for c in cuerpos if (c[3][1] - c[3][0]) > alto_total * 0.5]
    grandes.sort(key=lambda c: c[1][0])
    # Separados en X: la caja de uno no pisa la del siguiente.
    fuera, actual = [], None
    for c in grandes:
        if actual is None or c[1][0] > actual[1][1]:
            fuera.append(c)
            actual = c
        elif c[1][1] > actual[1][1]:
            actual = c
    return fuera


def hacia_donde_mira(mallas):
    """Heuristica: en que lado sobresale mas masa respecto del centro de caja.

    Es solo una pista. Lo confiable es renderizar de perfil y mirar la cara,
    el pico o los dedos del pie.
    """
    ys = [v.co.y for o in mallas for v in o.data.vertices]
    if not ys:
        return None
    centro = (min(ys) + max(ys)) / 2.0
    masa = sum(ys) / len(ys)
    sesgo = masa - centro
    rango = max(ys) - min(ys)
    # Umbral alto a proposito. Esta heuristica mira donde hay mas masa
    # respecto del centro de la caja, y eso se equivoca facil: una cresta que
    # barre hacia atras corre la masa al lado contrario de la cara. Solo se
    # pronuncia cuando el sesgo es grande, y aun asi como sospecha. La rotacion
    # es destructiva; no se ejecuta por una pista.
    if rango <= 0 or abs(sesgo) < rango * 0.12:
        return "desconocido -- miralo de perfil antes de girar nada"
    lado = "-Y" if sesgo < 0 else "+Y"
    return ("sospecha: la masa esta hacia %s; confirmalo de perfil "
            "(cara, pico o dedos del pie)" % lado)


def medir(ruta):
    limpiar()
    mallas = importar(ruta)
    if not mallas:
        return {"archivo": os.path.basename(ruta), "error": "sin mallas"}

    co = [v.co.copy() for o in mallas for v in o.data.vertices]
    x = [min(c.x for c in co), max(c.x for c in co)]
    y = [min(c.y for c in co), max(c.y for c in co)]
    z = [min(c.z for c in co), max(c.z for c in co)]
    w, d, h = x[1] - x[0], y[1] - y[0], z[1] - z[0]

    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in mallas)
    bordes = sum(aristas_de_borde(o.data) for o in mallas)
    uv = sorted({u.name for o in mallas for u in o.data.uv_layers})
    imgs = [[i.name, list(i.size)] for i in bpy.data.images if i.size[0]]
    cuerpos = cuerpos_sueltos(mallas)
    candidatas = figuras_candidatas(cuerpos, h)

    e = {
        "archivo": os.path.basename(ruta),
        "bytes": os.path.getsize(ruta),
        "mallas": len(mallas),
        "triangulos": tris,
        "vertices": len(co),
        "uv": uv,
        "texturas": imgs,
        "caja": {"x": [round(v, 4) for v in x], "y": [round(v, 4) for v in y],
                 "z": [round(v, 4) for v in z]},
        "proporcion": {"ancho": round(w / h, 3) if h else None,
                       "fondo": round(d / h, 3) if h else None, "alto": 1.0},
        "aristas_de_borde": bordes,
        "cerrado": bordes == 0,
        "cuerpos_sueltos": len(cuerpos),
        "cuerpos_mayores": [
            {"vertices": c[0],
             "caja": {"x": [round(c[1][0], 4), round(c[1][1], 4)],
                      "y": [round(c[2][0], 4), round(c[2][1], 4)],
                      "z": [round(c[3][0], 4), round(c[3][1], 4)]}}
            for c in cuerpos[:8]],
        "posibles_figuras": len(candidatas),
        "mira_hacia": hacia_donde_mira(mallas),
    }

    # --- avisos accionables ---
    avisos = []
    if not uv:
        avisos.append("SIN UV: es el FBX 'convertido'. Bajar el GLB de la "
                      "misma generacion (no gasta creditos).")
    if not imgs:
        avisos.append("SIN TEXTURAS: mismo motivo que arriba.")
    if len(candidatas) > 1:
        avisos.append("POSIBLES %d FIGURAS en un archivo: hay %d cuerpos "
                      "sueltos que miden mas de medio alto y no se pisan en X. "
                      "Miralo renderizado: si son varias vistas del mismo "
                      "modelo, quedate con una sola." % (len(candidatas),
                                                         len(candidatas)))
    if w > h:
        avisos.append("Mas ancho que alto: puede ser normal (un pie, un arma "
                      "acostada) o sintoma de varias figuras. Confirmalo con "
                      "un render, no con este numero solo.")
    if len(cuerpos) > 50:
        avisos.append("%d cuerpos sueltos: el decimado por colapso se va a "
                      "topar con un piso. Soldar ANTES de decimar." % len(cuerpos))
    if bordes == 0:
        avisos.append("Volumen cerrado: NO le apliques Solidify, duplica los "
                      "triangulos sin necesidad.")
    elif bordes > max(50, tris * 0.02):
        avisos.append("CASCARA ABIERTA (%d aristas de borde sobre %d "
                      "triangulos): con backface culling se va a ver invisible "
                      "desde atras. Ahi si conviene Solidify." % (bordes, tris))
    else:
        avisos.append("%d aristas de borde: son agujeritos sueltos, no una "
                      "cascara. Taparlos (holes_fill) sale mas barato que "
                      "solidificar." % bordes)
    if tris > 100000:
        avisos.append("%d triangulos: hay que decimar. Soldar los vertices "
                      "ANTES o el decimado se topa con un piso." % tris)
    if imgs and max(max(i[1]) for i in imgs) < 1024:
        avisos.append("Texturas de baja resolucion (%d): si el generador "
                      "ofrece 4096, bajar esa." % max(max(i[1]) for i in imgs))
    e["avisos"] = avisos
    return e


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not args:
        print(__doc__)
        return
    salida_json = None
    if "--json" in args:
        i = args.index("--json")
        salida_json = args[i + 1]
        args = args[:i] + args[i + 2:]

    todo = []
    for ruta in args:
        e = medir(ruta)
        todo.append(e)
        print("=" * 70)
        print("%s  (%.1f MB)" % (e["archivo"], e.get("bytes", 0) / 1e6))
        if "error" in e:
            print("  ERROR: %s" % e["error"])
            continue
        print("  %d triangulos, %d vertices, %d malla(s)"
              % (e["triangulos"], e["vertices"], e["mallas"]))
        print("  proporcion  ancho %.2f : fondo %.2f : alto 1.00"
              % (e["proporcion"]["ancho"], e["proporcion"]["fondo"]))
        print("  UV: %s" % (", ".join(e["uv"]) if e["uv"] else "NINGUNA"))
        print("  texturas: %s"
              % (", ".join("%s %dx%d" % (n, s[0], s[1]) for n, s in e["texturas"])
                 if e["texturas"] else "NINGUNA"))
        print("  aristas de borde: %d (%s)"
              % (e["aristas_de_borde"], "cerrado" if e["cerrado"] else "abierto"))
        print("  cuerpos sueltos: %d  (posibles figuras enteras: %d)"
              % (e["cuerpos_sueltos"], e["posibles_figuras"]))
        for c in e["cuerpos_mayores"][:4]:
            b = c["caja"]
            print("    %8d verts   X %.3f..%.3f  Z %.3f..%.3f"
                  % (c["vertices"], b["x"][0], b["x"][1], b["z"][0], b["z"][1]))
        print("  mira hacia: %s" % e["mira_hacia"])
        if e["avisos"]:
            print("  --- avisos ---")
            for a in e["avisos"]:
                print("   * %s" % a)

    if salida_json:
        with open(salida_json, "w", encoding="utf-8") as fh:
            json.dump(todo, fh, indent=1, ensure_ascii=False)
        print("[json] %s" % salida_json)


correr(main)
