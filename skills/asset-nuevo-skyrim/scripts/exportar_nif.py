# -*- coding: utf-8 -*-
"""Paso 5: el NIF de un asset nuevo, con la estructura de un donante vanilla.

    blender -b --python exportar_nif.py -- <plan.json> <asset.blend> [--force]
    blender -b --python exportar_nif.py -- --falsificar

Escribe con la API de PyNifly (el addon io_scene_nifly), no con su
exportador: es el camino de las armas que se vieron en el juego (el hacha de
dos manos, la de una mano), y evita lo que el exportador pierde sin avisar
(trampas 33 y 36 de modelo-ia-a-skyrim).

EL PLAN (JSON; las rutas relativas, desde la carpeta del plan)
--------------------------------------------------------------
    {"donante":  ".../meshes/weapons/glass/glasssword.nif",
     "marcador": ".../meshes/weapons/glass/1stpersonglasssword.nif",
     "salida":   "Data/meshes/weapons/Mia/mia.nif",
     "raiz":     "Mia",
     "piezas": [
       {"objeto": "Metal",  "shape": "Mia:0",
        "receta": {"shape": "GlassSword01:1"},
        "texturas": {"Diffuse": "textures\\weapons\\Mia\\mia.dds",
                     "Normal":  "textures\\weapons\\Mia\\mia_n.dds",
                     "EnvMask": "textures\\weapons\\Mia\\mia_m.dds"}},
       {"objeto": "Brillo", "shape": "Mia:1",
        "receta": {"nif": ".../dawnbreaker.nif", "shape": "..."},
        "texturas": {"Diffuse": "...", "Normal": "...", "Glow": "..._g.dds"}}],
     "colision": {"objetos": ["Metal"]}}

  donante   un NIF vanilla de la MISMA clase (espada, hacha, escudo): de el
            salen `Prn`, `BSXFlags`, el cuerpo rigido (sus 63 campos) y el
            material de la colision.
  marcador  si el donante no trae `BSInvMarker` (el de tercera persona de un
            arma no lo trae; el de primera si), otro NIF de la clase que si.
            Sin marcador no se inventa una orientacion de inventario.
  piezas    cada una, un objeto del .blend y la pieza vanilla cuya RECETA de
            shader copia (tipo, flags, brillo, color especular, cubemap, y su
            NiAlphaProperty si la tiene). Metal y brillo son dos piezas:
            ninguna pieza vanilla combina mapa de entorno y mapa de brillo.
  colision  de que piezas sale la caja (por defecto, de todas).

LO QUE CUIDA
------------
  * De la receta se copian los 84 campos de receta del shader, no los
    identificadores del archivo; y se apagan los bits que dependen de la
    geometria de ESA pieza (skinned, normales en espacio de modelo):
    exportar_puro.conciliar_flags.
  * De la receta NO se copian sus texturas propias (difuso, normal, mascara,
    brillo): el asset llevaria la textura vanilla. Solo el cubemap.
  * La caja de colision sale de la malla (unidades de Havok, 69,99 por
    unidad) con el radio de la REGLA de colision_caja.py; el cuerpo es un
    bhkRigidBodyT (sin la T el motor ignora la traslacion y la caja queda
    centrada en el origen). La inercia es la del donante reescalada:
    HEURISTICA declarada, en exportar_puro.inercia_escalada.
  * Se escribe a un temporal, se RELEE --con PyNifly y con nif_nodos.py, que
    lee los bytes por su cuenta-- y se pasan las REGLAS de colision_caja.py.
    Recien si todo da, reemplaza al definitivo. Si no, deja el temporal
    (.nuevo) para mirarlo.

LAS PIEZAS TRANSPARENTES
------------------------
La NiAlphaProperty se copia de la receta, con su numero: 4333 es blending de
verdad, 4844 es testing y se ve opaco (trampa 14). Hay que elegir una receta
que haga lo mismo que la pieza --el lente del astrolabio dwemer para un
vidrio--. Con blending, el alfa sale de uno de dos lados, segun la receta:

  * con VERTEX_ALPHA, de los colores de vertice: la capa `VERTEX_ALPHA` del
    objeto, con la convencion de PyNifly (el promedio de su RGB, en valores
    lineales). Tiene que existir y VARIAR: sin la capa el alfa vale 0, y
    pareja el panel se ve opaco (trampa 16). El RGB sale de la capa de color
    activa --o la primera que no sea VERTEX_ALPHA--, y si no hay, blanco,
    como en 58 de las 59 piezas vanilla con alfa por vertice (hallazgo 44).
    (El exportador de PyNifly, sin capa base, deja el RGB en negro aunque su
    comentario dice blanco: leido en su export_nif.py, 27.2.)
  * sin VERTEX_ALPHA, del alfa del difuso: ese DDS tiene que llevar alfa
    (DXT5 o sin comprimir), no DXT1. Queda en las notas.

Cuelgan de la raiz, sin BSOrderedNode: `[MEASURED]` en 2.148 NIF vanilla de
armaduras y armas, 262 piezas Lighting con blending, y NINGUNA cuelga de un
BSOrderedNode (234 de la raiz, 28 de un NiNode); el unico BSOrderedNode de
esas carpetas, en el escudo enano de cristal de Dawnguard en primera persona,
no tiene hijos. Por eso no hace falta el parche de la trampa 12.

LO QUE NO HACE, TODAVIA
-----------------------
  Piezas skinneadas (un arco anima la cuerda).

--falsificar arma con PyNifly un donante sintetico y una escena en Blender, y
exporta seis planes. El bueno, con tres piezas --metal con SKINNED y
MODEL_SPACE_NORMALS prendidos en su receta, un vidrio con alfa por vertice y
un panel con el alfa en la textura--, tiene que salir con las recetas
copiadas y conciliadas, sus texturas y no las del donante, y el alfa por
vertice como estaba en la escena. Los otros tienen que reprobar por su
motivo: sin capa VERTEX_ALPHA, con la capa pareja, y un donante sin inercia.
Sin archivos del juego.

Exit 0 si el NIF quedo escrito y confirmado, 1 si reprueba o el plan no
sirve, 2 si los argumentos no sirven.
"""
import json
import os
import shutil
import sys
import tempfile

import bpy
from mathutils import Matrix

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from correr_en_blender import correr  # noqa: E402
import colision_caja  # noqa: E402
import exportar_puro as ep  # noqa: E402
import nif_nodos  # noqa: E402

TOL_MUNDO = 1e-6
CAPA_ALFA = "VERTEX_ALPHA"      # el nombre que usa PyNifly (trampa 16)


class Reprueba(Exception):
    pass


def _mal(texto):
    """Argumentos que no sirven: exit 2, no 1 (1 es "reprueba")."""
    print("[nif] %s" % texto)
    raise SystemExit(2)


def pynifly_del_addon():
    """(pynifly, nifdefs) del addon, y la guarda de que los bits que concilia
    exportar_puro son los de ESTA version de PyNifly."""
    import addon_utils
    addon_utils.enable("io_scene_nifly", default_set=True)
    from io_scene_nifly.pyn import nifdefs, pynifly
    esperados = {"SKINNED": (nifdefs.ShaderFlags1, ep.SF1_SKINNED),
                 "VERTEX_ALPHA": (nifdefs.ShaderFlags1, ep.SF1_VERTEX_ALPHA),
                 "MODEL_SPACE_NORMALS": (nifdefs.ShaderFlags1,
                                         ep.SF1_MODEL_SPACE_NORMALS),
                 "VERTEX_COLORS": (nifdefs.ShaderFlags2, ep.SF2_VERTEX_COLORS)}
    for nombre, (enum, valor) in esperados.items():
        if int(getattr(enum, nombre)) != valor:
            raise SystemExit("PyNifly cambio el bit %s (0x%X, exportar_puro "
                             "tiene 0x%X): no se escribe nada"
                             % (nombre, int(getattr(enum, nombre)), valor))
    return pynifly, nifdefs


# --------------------------------------------------------------------------
# lo que se lee
# --------------------------------------------------------------------------
def _color_de(capa, li, vi):
    """El RGBA lineal de una capa de color en la esquina `li` (vertice
    `vi`), sea la capa por esquina o por punto."""
    return tuple(capa.data[li if capa.domain == "CORNER" else vi].color)


def esquinas_de(obj, con_alfa=False):
    """[(pos, uv, normal)] de cada esquina de cada triangulo, con la capa UV
    de render y las normales por esquina (las aristas duras incluidas). Con
    `con_alfa`, [(pos, uv, normal, rgba)] con el alfa de la capa VERTEX_ALPHA
    (el promedio de su RGB, como PyNifly) y el RGB de la capa base."""
    if obj.type != "MESH":
        raise Reprueba("%s no es una malla" % obj.name)
    if obj.modifiers:
        raise Reprueba("%s tiene modificadores sin aplicar (%s)"
                       % (obj.name, ", ".join(m.name for m in obj.modifiers)))
    mw = obj.matrix_world
    if any(abs(mw[i][j] - (1.0 if i == j else 0.0)) > TOL_MUNDO
           for i in range(4) for j in range(4)):
        raise Reprueba("%s tiene la transformada sin aplicar: la malla tiene "
                       "que estar en el espacio del nodo (al_marco.py de "
                       "modelo-ia-a-skyrim la deja aplicada)" % obj.name)
    me = obj.data
    render = [c for c in me.uv_layers if c.active_render]
    if len(render) != 1:
        raise Reprueba("%s: %d capas UV de render, tiene que haber una"
                       % (obj.name, len(render)))
    uv = render[0].data
    alfa = base = None
    if con_alfa:
        alfa = me.color_attributes.get(CAPA_ALFA)
        if alfa is None:
            raise Reprueba("%s: la receta toma el alfa de los colores de vertice "
                           "(VERTEX_ALPHA) y el objeto no tiene la capa %s: sin "
                           "ella el alfa vale 0 y la pieza es invisible (trampa 16)"
                           % (obj.name, CAPA_ALFA))
        activa = me.color_attributes.active_color
        if activa is not None and activa.name != CAPA_ALFA:
            base = activa
        else:
            base = next((c for c in me.color_attributes if c.name != CAPA_ALFA), None)
    me.calc_loop_triangles()
    normales = me.corner_normals
    fuera = []
    for t in me.loop_triangles:
        for li, vi in zip(t.loops, t.vertices):
            e = (tuple(me.vertices[vi].co), tuple(uv[li].uv),
                 tuple(normales[li].vector))
            if con_alfa:
                a = _color_de(alfa, li, vi)
                rgb = _color_de(base, li, vi)[:3] if base is not None else (1.0, 1.0, 1.0)
                e = e + (tuple(rgb) + ((a[0] + a[1] + a[2]) / 3.0,),)
            fuera.append(e)
    if not fuera:
        raise Reprueba("%s no tiene triangulos" % obj.name)
    return fuera


def _extra(nif, bloque, nombre=None):
    for ed in nif.root.extra_data():
        if ed is not None and ed.blockname == bloque and \
                (nombre is None or getattr(ed, "name", None) == nombre):
            return ed
    return None


def _vertices_mundo(sh):
    """Los vertices de una pieza con su transformada, si la tiene."""
    vs = [tuple(v) for v in sh.verts]
    tr = getattr(sh, "transform", None)
    if tr is None:
        return vs
    r, t, s = tr.rotation, tr.translation, tr.scale
    return [tuple(s * sum(r[i][k] * v[k] for k in range(3)) + t[i]
                  for i in range(3)) for v in vs]


def leer_donante(pynifly, ruta, ruta_marcador):
    don = pynifly.NifFile(ruta)
    prn = _extra(don, "NiStringExtraData", "Prn")
    if prn is None:
        raise Reprueba("el donante no tiene Prn: no cuelga de ningun nodo, no "
                       "es un equipable")
    bsx = _extra(don, "BSXFlags")
    if bsx is None:
        raise Reprueba("el donante no tiene BSXFlags")
    marcador, de = _extra(don, "BSInvMarker"), ruta
    if marcador is None and ruta_marcador:
        marcador, de = _extra(pynifly.NifFile(ruta_marcador), "BSInvMarker"), ruta_marcador
    if marcador is None:
        raise Reprueba("ni el donante ni el marcador traen BSInvMarker: no se "
                       "inventa una orientacion de inventario (el NIF de "
                       "primera persona de un arma si lo trae)")
    co = don.root.collision_object
    if co is None:
        raise Reprueba("el donante no tiene colision en la raiz")
    material = getattr(co.body.shape.properties, "bhkMaterial", None)
    if material is None:
        raise Reprueba("no se pudo leer el material de la colision del donante")
    # Los lados que la inercia del donante describe: su CAJA de colision si
    # la tiene; si su colision es otra forma (lista, convexa), la malla, con
    # la transformada de cada pieza. Es parte de la heuristica, y se informa.
    forma = co.body.shape
    if forma.blockname == "bhkBoxShape":
        lados = [2.0 * float(forma.properties.bhkDimensions[i]) for i in range(3)]
        lados_de = "la caja de colision del donante"
    else:
        pts = [p for sh in don.shapes for p in _vertices_mundo(sh)]
        lados = [(max(p[i] for p in pts) - min(p[i] for p in pts)) / ep.HAVOK
                 for i in range(3)]
        lados_de = "la malla del donante (su colision es %s)" % forma.blockname
    return {"prn": prn.string_data, "bsx": int(bsx.flags),
            "marcador": (tuple(marcador.rotation), float(marcador.zoom),
                         os.path.basename(de)),
            "flags_colision": int(co.properties.flags), "cuerpo": co.body.properties,
            "material": int(material), "lados": lados, "lados_de": lados_de,
            "_nif": don}   # el cuerpo es de este archivo: que siga vivo


def buscar_receta(pynifly, cache, ruta, shape):
    """(pieza vanilla, (flags, umbral) de su NiAlphaProperty o None)."""
    if ruta not in cache:
        cache[ruta] = pynifly.NifFile(ruta)
    por_nombre = {s.name: s for s in cache[ruta].shapes}
    if shape not in por_nombre:
        raise Reprueba("%s no tiene la pieza %r (tiene %s)"
                       % (os.path.basename(ruta), shape, sorted(por_nombre)))
    sh = por_nombre[shape]
    bloque = sh.shader.blockname
    if bloque != "BSLightingShaderProperty":
        raise Reprueba("la receta %s es %s: solo se copian recetas de "
                       "BSLightingShaderProperty" % (shape, bloque))
    alfa = None
    if sh.has_alpha_property:
        alfa = (int(sh.alpha_property.properties.flags),
                int(sh.alpha_property.properties.threshold))
    return sh, alfa


# --------------------------------------------------------------------------
# lo que se escribe
# --------------------------------------------------------------------------
def _copiar_campos(origen, destino, saltear=()):
    for nombre, _tipo in origen._fields_:
        if nombre in saltear:
            continue
        valor = getattr(origen, nombre)
        if hasattr(valor, "__len__") and not isinstance(valor, (str, bytes)):
            dst = getattr(destino, nombre)
            for i in range(len(valor)):
                dst[i] = valor[i]
        else:
            setattr(destino, nombre, valor)


def escribir(pynifly, nifdefs, plan, piezas, donante, recetas, tmp):
    """Escribe el NIF en `tmp`. Devuelve lo que se escribio, para releerlo."""
    nif = pynifly.NifFile()
    nif.initialize("SKYRIMSE", tmp, root_type="BSFadeNode", root_name=plan["raiz"])
    escrito = {"piezas": {}, "notas": []}
    for pz in plan["piezas"]:
        receta, alfa, modo = recetas[pz["shape"]]
        esquinas = piezas[pz["objeto"]]
        alfa_rango = None
        if modo == "blending_vertice":
            alfa_rango = ep.validar_alfa_vertice([e[3][3] for e in esquinas])
        verts, uvs, normales, tris, colores = ep.soldar(esquinas)
        sh = nif.createShapeFromData(pz["shape"], verts, tris, uvs, normales,
                                     parent=nif.root)
        if colores:
            sh.set_colors(colores)
        rp = receta.shader._properties
        tipo = int(rp.Shader_Type)
        tx, notas = ep.texturas_pieza(dict(receta.textures), pz["texturas"], tipo)
        for ranura, ruta in tx.items():
            sh.set_texture(ranura, ruta)
        p = sh.shader._properties
        _copiar_campos(rp, p, ep.NO_RECETA)
        f1, f2, cambios = ep.conciliar_flags(int(rp.Shader_Flags_1),
                                             int(rp.Shader_Flags_2),
                                             colores=bool(colores))
        p.Shader_Flags_1, p.Shader_Flags_2 = f1, f2
        sh.save_shader_attributes()
        if alfa:
            sh.has_alpha_property = True
            sh.alpha_property.properties.flags = alfa[0]
            sh.alpha_property.properties.threshold = alfa[1]
            sh.save_alpha_property()
        if modo == "blending_textura":
            notas.append("la transparencia sale del alfa del difuso (%s): ese "
                         "DDS tiene que llevar alfa, DXT5 o sin comprimir; en "
                         "DXT1 el vidrio sale opaco" % tx.get("Diffuse"))
        escrito["piezas"][pz["shape"]] = {
            "tris": len(tris), "vertices": len(verts), "tipo": tipo,
            "flags": [f1, f2], "texturas": tx, "alfa": alfa, "modo_alfa": modo,
            "alfa_vertice": alfa_rango, "colores": bool(colores),
            "uv0": uvs[0], "receta": receta.name,
            "cambios_de_flags": cambios, "notas": notas}
    rot, zoom, _de = donante["marcador"]
    pynifly.BSXFlags.New(nif, "BSX", flags=donante["bsx"], parent=nif.root)
    pynifly.NiStringExtraData.New(nif, "Prn", string_value=donante["prn"],
                                  parent=nif.root)
    pynifly.BSInvMarker.New(nif, "INV", rotation=rot, zoom=zoom, parent=nif.root)

    objetos = (plan.get("colision") or {}).get("objetos") or \
        [pz["objeto"] for pz in plan["piezas"]]
    pts = [e[0] for o in objetos for e in piezas[o]]
    caja = ep.caja_colision(pts)
    lados = [2.0 * s for s in caja["semi"]]
    cuerpo_don = donante["cuerpo"]
    inercia = ep.inercia_escalada(list(cuerpo_don.inertiaMatrix),
                                  float(cuerpo_don.mass), donante["lados"], lados)
    caja_p = nifdefs.bhkBoxShapeProps()
    caja_p.bhkMaterial = donante["material"]
    caja_p.bhkRadius = caja["radio"]
    for i in range(3):
        caja_p.bhkDimensions[i] = caja["semi"][i]
    bloque = nif.add_block("", caja_p, None)
    cuerpo = nifdefs.bhkRigidBodyProps()
    _copiar_campos(cuerpo_don, cuerpo, ("bufSize", "bufType"))
    cuerpo.bufType = nifdefs.PynBufferTypes.bhkRigidBodyTBufType
    cuerpo.shapeID = bloque.id
    for i in range(3):
        cuerpo.translation[i] = caja["centro"][i]
    cuerpo.translation[3] = 0.0
    for i in range(12):
        cuerpo.inertiaMatrix[i] = inercia[i]
    co = nif.root.add_collision(None, flags=donante["flags_colision"])
    co.add_body(cuerpo)
    nif.save()
    escrito.update({"caja": caja, "masa": float(cuerpo_don.mass),
                    "inercia": [inercia[i] for i in (0, 5, 10)],
                    "inercia_escalada_desde": donante["lados_de"],
                    "prn": donante["prn"], "bsx": donante["bsx"],
                    "marcador": [list(rot), zoom, donante["marcador"][2]],
                    "material_colision": donante["material"]})
    return escrito


# --------------------------------------------------------------------------
# la relectura
# --------------------------------------------------------------------------
def releer(pynifly, plan, tmp, escrito):
    """Fallas de la relectura: con PyNifly, y con nif_nodos.py, que lee los
    bytes por su cuenta; y las REGLAS de colision_caja.py."""
    fallas = []
    rel = pynifly.NifFile(tmp)
    if rel.rootName != plan["raiz"]:
        fallas.append("la raiz se llama %r" % rel.rootName)
    por_nombre = {s.name: s for s in rel.shapes}
    if set(por_nombre) != set(escrito["piezas"]):
        fallas.append("las piezas son %s" % sorted(por_nombre))
    for nombre, w in escrito["piezas"].items():
        s = por_nombre.get(nombre)
        if s is None:
            continue
        p = s.shader._properties
        if len(s.tris) != w["tris"]:
            fallas.append("%s: %d triangulos, se escribieron %d"
                          % (nombre, len(s.tris), w["tris"]))
        if int(p.Shader_Type) != w["tipo"] or \
                [int(p.Shader_Flags_1), int(p.Shader_Flags_2)] != w["flags"]:
            fallas.append("%s: shader tipo %s flags 0x%08X/0x%08X, se escribio "
                          "%s 0x%08X/0x%08X" % (nombre, p.Shader_Type,
                                                p.Shader_Flags_1, p.Shader_Flags_2,
                                                w["tipo"], w["flags"][0], w["flags"][1]))
        tex = {k: v for k, v in dict(s.textures).items() if v}
        if tex != w["texturas"]:
            fallas.append("%s: texturas %s, se escribieron %s"
                          % (nombre, tex, w["texturas"]))
        # media precision en el BSTriShape: el ultimo bit vale ~6e-5 a V=0,13
        uv0 = s.uvs[0] if len(s.uvs) else None
        if uv0 is None or abs(uv0[0] - w["uv0"][0]) > 1e-3 or \
                abs(uv0[1] - w["uv0"][1]) > 1e-3:
            fallas.append("%s: la UV del primer vertice quedo en %s y se "
                          "escribio %s" % (nombre, uv0, w["uv0"]))
        leido = ((int(s.alpha_property.properties.flags),
                  int(s.alpha_property.properties.threshold))
                 if s.has_alpha_property else None)
        if leido != (tuple(w["alfa"]) if w["alfa"] else None):
            fallas.append("%s: NiAlphaProperty %s, se escribio %s"
                          % (nombre, leido, w["alfa"]))
        if bool(s.properties.hasVertexColors) != w["colores"]:
            fallas.append("%s: colores de vertice %s, se esperaba %s"
                          % (nombre, bool(s.properties.hasVertexColors), w["colores"]))
        elif w["alfa_vertice"]:
            alfas = [c[3] for c in s.colors]
            lo, hi = w["alfa_vertice"]
            # el alfa del color va en 8 bits: 1/255 de tolerancia
            if abs(min(alfas) - lo) > 0.005 or abs(max(alfas) - hi) > 0.005:
                fallas.append("%s: el alfa por vertice quedo en %.3f..%.3f y se "
                              "escribio %.3f..%.3f" % (nombre, min(alfas),
                                                       max(alfas), lo, hi))
    crudo = nif_nodos.leer(tmp)
    if nif_nodos.cadena_extra(crudo, "Prn") != escrito["prn"]:
        fallas.append("el Prn quedo en %r" % nif_nodos.cadena_extra(crudo, "Prn"))
    bloques = {t for t, _o, _s in crudo["bloques"]}
    for nombre in ("BSXFlags", "BSInvMarker", "NiStringExtraData",
                   "bhkCollisionObject", "bhkRigidBodyT", "bhkBoxShape"):
        if nombre not in bloques:
            fallas.append("falta el bloque %s" % nombre)
    cajas = colision_caja.cajas(crudo)
    if len(cajas) != 1:
        fallas.append("%d cajas de colision, se escribio 1" % len(cajas))
    for c in cajas:
        f, _notas = colision_caja.juzgar(c)
        fallas.extend("colision: %s" % x for x in f)
        if not c.get("error") and any(
                abs(c["dims"][i] - escrito["caja"]["semi"][i]) > 1e-4 for i in range(3)):
            fallas.append("la caja quedo en %s y se pidio %s"
                          % ([round(x, 5) for x in c["dims"]],
                             [round(x, 5) for x in escrito["caja"]["semi"]]))
    return fallas


# --------------------------------------------------------------------------
# el camino entero
# --------------------------------------------------------------------------
def exportar(pynifly, nifdefs, plan, base, blend, force):
    """(salida, informe). Reprueba con Reprueba o ep.ExportError."""
    problemas = ep.validar_plan(plan)
    if problemas:
        raise Reprueba("el plan no sirve: " + "; ".join(problemas))
    ruta = lambda r: r if os.path.isabs(r) else os.path.normpath(os.path.join(base, r))  # noqa: E731
    donante_ruta, salida = ruta(plan["donante"]), ruta(plan["salida"])
    if os.path.exists(salida) and not force:
        raise Reprueba("%s ya existe: usa --force para pisarlo" % salida)
    donante = leer_donante(pynifly, donante_ruta,
                           ruta(plan["marcador"]) if plan.get("marcador") else None)
    # Las recetas antes que las piezas: la receta dice si la pieza necesita
    # alfa por vertice.
    cache, recetas = {}, {}
    for pz in plan["piezas"]:
        rc = pz["receta"]
        sh, alfa = buscar_receta(
            pynifly, cache, ruta(rc["nif"]) if rc.get("nif") else donante_ruta,
            rc["shape"])
        recetas[pz["shape"]] = (sh, alfa, ep.modo_alfa(
            alfa, int(sh.shader._properties.Shader_Flags_1)))
    bpy.ops.wm.open_mainfile(filepath=blend)
    piezas = {}
    for pz in plan["piezas"]:
        obj = bpy.data.objects.get(pz["objeto"])
        if obj is None:
            raise Reprueba("el .blend no tiene el objeto %r" % pz["objeto"])
        piezas[pz["objeto"]] = esquinas_de(
            obj, con_alfa=recetas[pz["shape"]][2] == "blending_vertice")
    os.makedirs(os.path.dirname(salida) or ".", exist_ok=True)
    tmp = salida + ".nuevo"
    if os.path.exists(tmp):
        os.unlink(tmp)
    escrito = escribir(pynifly, nifdefs, plan, piezas, donante, recetas, tmp)
    fallas = releer(pynifly, plan, tmp, escrito)
    if fallas:
        raise Reprueba("la relectura no confirma el archivo (queda %s): %s"
                       % (tmp, "; ".join(fallas)))
    os.replace(tmp, salida)
    return salida, escrito


# --------------------------------------------------------------------------
# la falsificacion
# --------------------------------------------------------------------------
_CAJA_V = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
           (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
_CAJA_T = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
           (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]


def _donante_sintetico(pynifly, nifdefs, ruta, inercia):
    """Un donante hecho con PyNifly: una receta de metal con SKINNED y
    MODEL_SPACE_NORMALS prendidos (se tienen que apagar), una de vidrio con
    alfa por vertice (4333 + VERTEX_ALPHA) y una de panel con el alfa en la
    textura (4333 sin VERTEX_ALPHA)."""
    uv = [(0.1 * i, 0.05 * i) for i in range(8)]
    n = [(0.0, 0.0, 1.0)] * 8
    nif = pynifly.NifFile()
    nif.initialize("SKYRIMSE", ruta, root_type="BSFadeNode", root_name="Donante")

    def pieza(nombre, f1, f2, texturas, alfa=None):
        sh = nif.createShapeFromData(nombre, _CAJA_V, _CAJA_T, uv, n, parent=nif.root)
        for r, v in texturas.items():
            sh.set_texture(r, v)
        p = sh.shader._properties
        p.Shader_Type = 1
        p.Shader_Flags_1, p.Shader_Flags_2 = f1, f2
        p.Glossiness = 77.0
        p.Env_Map_Scale = 0.55
        sh.save_shader_attributes()
        if alfa:
            sh.has_alpha_property = True
            sh.alpha_property.properties.flags = alfa
            sh.alpha_property.properties.threshold = 128
            sh.save_alpha_property()

    pieza("Donante:0", 0x82400381 | ep.SF1_SKINNED | ep.SF1_MODEL_SPACE_NORMALS,
          0x00008011, {"Diffuse": r"textures\donante\donante.dds",
                       "Normal": r"textures\donante\donante_n.dds",
                       "EnvMap": r"textures\cubemaps\prueba_e.dds",
                       "EnvMask": r"textures\donante\donante_m.dds"})
    pieza("Donante:1", 0x82400389, 0x00008021,
          {"Diffuse": r"textures\donante\lente.dds",
           "EnvMap": r"textures\cubemaps\hielo_e.dds"}, alfa=4333)
    pieza("Donante:2", 0x82400381, 0x00008001,
          {"Diffuse": r"textures\donante\panel.dds"}, alfa=4333)
    pynifly.BSXFlags.New(nif, "BSX", flags=194, parent=nif.root)
    pynifly.NiStringExtraData.New(nif, "Prn", string_value="WeaponSword",
                                  parent=nif.root)
    pynifly.BSInvMarker.New(nif, "INV", rotation=(4712, 0, 0), zoom=1.05,
                            parent=nif.root)
    cp = nifdefs.bhkBoxShapeProps()
    cp.bhkMaterial = 1060167844
    cp.bhkRadius = 0.0143
    for i in range(3):
        cp.bhkDimensions[i] = 1.0 / ep.HAVOK
    blk = nif.add_block("", cp, None)
    cuerpo = nifdefs.bhkRigidBodyProps()
    cuerpo.bufType = nifdefs.PynBufferTypes.bhkRigidBodyTBufType
    cuerpo.shapeID = blk.id
    cuerpo.mass = 10.0
    cuerpo.collisionFilter_layer = 5
    cuerpo.motionSystem = 3
    for k, v in zip((0, 5, 10), inercia):
        cuerpo.inertiaMatrix[k] = v
    co = nif.root.add_collision(None, flags=129)
    co.add_body(cuerpo)
    nif.save()
    return ruta


def _escena(ruta):
    """Tres objetos: Metal sin capas de color; Vidrio con VERTEX_ALPHA que
    varia (0,30 a 0,96) y una capa base roja; Parejo con VERTEX_ALPHA en 1."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for nombre, x in (("Metal", 0.0), ("Vidrio", 3.0), ("Parejo", 6.0), ("Panel", 9.0)):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
        o = bpy.context.object
        o.name = nombre
        o.data.transform(Matrix.Translation((x, 0.0, 0.0)) @
                         Matrix.Diagonal((2.0, 30.0, 0.5, 1.0)))
    for nombre, alfas in (("Vidrio", None), ("Parejo", 1.0)):
        me = bpy.data.objects[nombre].data
        base = me.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
        capa = me.color_attributes.new(CAPA_ALFA, "FLOAT_COLOR", "CORNER")
        for i, d in enumerate(capa.data):
            a = alfas if alfas is not None else 0.30 + 0.66 * (i % 7) / 6.0
            d.color = (a, a, a, 1.0)
            base.data[i].color = (1.0, 0.5, 0.25, 1.0)
        me.color_attributes.active_color = me.color_attributes[CAPA_ALFA]
    bpy.ops.wm.save_as_mainfile(filepath=ruta)
    return ruta


def falsificar():
    """Un donante sintetico y seis planes: el bueno tiene que salir bien, y
    los otros tienen que reprobar por su motivo."""
    pynifly, nifdefs = pynifly_del_addon()
    d = tempfile.mkdtemp(prefix="exportar_nif_")
    hechas, fallas = [0], []

    def exigir(cond, texto):
        hechas[0] += 1
        if not cond:
            fallas.append(texto)

    def pieza(objeto, receta, extra=None):
        tx = {"Diffuse": r"textures\prueba\%s.dds" % objeto.lower(),
              "Normal": r"textures\prueba\%s_n.dds" % objeto.lower()}
        return {"objeto": objeto, "shape": "Prueba:%s" % objeto,
                "receta": {"shape": receta}, "texturas": dict(tx, **(extra or {}))}

    def plan(don, piezas):
        return {"donante": don, "salida": "salida/prueba.nif", "raiz": "Prueba",
                "piezas": piezas, "colision": {"objetos": ["Metal"]}}

    try:
        bueno_d = _donante_sintetico(pynifly, nifdefs, os.path.join(d, "donante.nif"),
                                     (2.0, 0.4, 2.3))
        sin_inercia = _donante_sintetico(pynifly, nifdefs,
                                         os.path.join(d, "sin_inercia.nif"), (0, 0, 0))
        blend = _escena(os.path.join(d, "asset.blend"))

        salida, w = exportar(pynifly, nifdefs, plan(bueno_d, [
            pieza("Metal", "Donante:0"), pieza("Vidrio", "Donante:1"),
            pieza("Panel", "Donante:2")]), d, blend, True)
        rel = {x.name: x for x in pynifly.NifFile(salida).shapes}
        m, v, pn = rel.get("Prueba:Metal"), rel.get("Prueba:Vidrio"), rel.get("Prueba:Panel")
        exigir(None not in (m, v, pn), "el bueno: faltan piezas: %s" % sorted(rel))
        if m is not None:
            p = m.shader._properties
            tex = {k: x for k, x in dict(m.textures).items() if x}
            exigir(abs(p.Glossiness - 77.0) < 1e-4 and int(p.Shader_Type) == 1
                   and abs(p.Env_Map_Scale - 0.55) < 1e-4,
                   "metal: la receta no se copio (glossiness %s)" % p.Glossiness)
            exigir(int(p.Shader_Flags_1) == 0x82400381 and int(p.Shader_Flags_2) == 0x8011,
                   "metal: flags 0x%08X/0x%08X, se esperaba SKINNED y "
                   "MODEL_SPACE_NORMALS apagados" % (p.Shader_Flags_1, p.Shader_Flags_2))
            exigir(tex == {"Diffuse": r"textures\prueba\metal.dds",
                           "Normal": r"textures\prueba\metal_n.dds",
                           "EnvMap": r"textures\cubemaps\prueba_e.dds"},
                   "metal: texturas %s (el EnvMask del donante no se copia; el "
                   "cubemap si)" % tex)
            exigir(not m.has_alpha_property and not m.properties.hasVertexColors,
                   "metal: quedo con alfa o colores")
        if v is not None:
            p = v.shader._properties
            alfas = [c[3] for c in v.colors] if v.properties.hasVertexColors else []
            exigir(v.has_alpha_property and
                   int(v.alpha_property.properties.flags) == 4333,
                   "vidrio: la NiAlphaProperty no es la 4333 de la receta")
            exigir(int(p.Shader_Flags_1) & ep.SF1_VERTEX_ALPHA and
                   int(p.Shader_Flags_2) & ep.SF2_VERTEX_COLORS,
                   "vidrio: flags 0x%08X/0x%08X sin VERTEX_ALPHA o VERTEX_COLORS"
                   % (p.Shader_Flags_1, p.Shader_Flags_2))
            exigir(bool(alfas) and abs(min(alfas) - 0.30) < 0.005
                   and abs(max(alfas) - 0.96) < 0.005,
                   "vidrio: el alfa por vertice quedo en %s, se pinto 0,30..0,96"
                   % (((min(alfas), max(alfas)) if alfas else None),))
            exigir(bool(alfas) and all(abs(c[0] - 1.0) < 0.01 and abs(c[1] - 0.5) < 0.01
                                      and abs(c[2] - 0.25) < 0.01 for c in v.colors),
                   "vidrio: el RGB no salio de la capa base (rojo 1, 0,5, 0,25)")
        if pn is not None:
            p = pn.shader._properties
            exigir(pn.has_alpha_property and not pn.properties.hasVertexColors
                   and not int(p.Shader_Flags_1) & ep.SF1_VERTEX_ALPHA,
                   "panel: el alfa de textura no tiene que llevar colores")
            exigir(any("DXT1" in x for x in w["piezas"]["Prueba:Panel"]["notas"]),
                   "panel: falta la nota del DDS con alfa")
        crudo = nif_nodos.leer(salida)
        exigir(nif_nodos.cadena_extra(crudo, "Prn") == "WeaponSword",
               "el bueno: el Prn no se copio")
        exigir("BSOrderedNode" not in {t for t, _o, _s in crudo["bloques"]},
               "el bueno: aparecio un BSOrderedNode")
        c = colision_caja.cajas(crudo)
        exigir(len(c) == 1 and not colision_caja.juzgar(c[0])[0]
               and max(c[0]["inercia"]) > 0, "el bueno: la colision %r" % c)

        for nombre, pl, trozo in (
                ("un vidrio sin capa VERTEX_ALPHA",
                 plan(bueno_d, [pieza("Metal", "Donante:1")]), "no tiene la capa"),
                ("un vidrio con la capa pareja",
                 plan(bueno_d, [pieza("Metal", "Donante:0"),
                                pieza("Parejo", "Donante:1")]), "uniforme"),
                ("el donante sin inercia",
                 plan(sin_inercia, [pieza("Metal", "Donante:0")]), "REGLA inercia")):
            try:
                exportar(pynifly, nifdefs, pl, d, blend, True)
                exigir(False, "%s no reprobo" % nombre)
            except (Reprueba, ep.ExportError) as e:
                exigir(trozo in str(e), "%s reprobo por otra cosa: %s" % (nombre, e))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    for f in fallas:
        print("  FALLA %s" % f)
    print("falsificar: %d comprobaciones, %d fallas" % (hechas[0], len(fallas)))
    return 1 if fallas or not hechas[0] else 0


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if args == ["--falsificar"]:
        sys.exit(falsificar())
    force = "--force" in args
    resto = [a for a in args if a != "--force"]
    for a in resto:
        if a.startswith("--"):
            _mal("opcion desconocida: %s" % a)
    if len(resto) != 2:
        print(__doc__)
        raise SystemExit(2)
    plan_ruta, blend = resto
    for r in (plan_ruta, blend):
        if not os.path.isfile(r):
            _mal("no existe: %s" % r)
    with open(plan_ruta, encoding="utf-8") as fh:
        try:
            plan = json.load(fh)
        except ValueError as e:
            raise SystemExit("el plan no es JSON: %s" % e)
    pynifly, nifdefs = pynifly_del_addon()
    try:
        salida, escrito = exportar(pynifly, nifdefs, plan,
                                   os.path.dirname(os.path.abspath(plan_ruta)),
                                   blend, force)
    except (Reprueba, ep.ExportError) as e:
        print("[nif] REPRUEBA %s" % e)
        raise SystemExit(1)
    informe = os.path.splitext(plan_ruta)[0] + "_informe.json"
    with open(informe, "w", encoding="utf-8") as fh:
        json.dump(escrito, fh, indent=1, ensure_ascii=False, default=str)
    print("[nif] %s escrito y releido: %d piezas, caja %s, Prn %s -> informe %s"
          % (salida, len(escrito["piezas"]),
             [round(x, 4) for x in escrito["caja"]["semi"]], escrito["prn"], informe))


correr(main)
