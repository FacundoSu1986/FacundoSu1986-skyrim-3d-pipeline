# -*- coding: utf-8 -*-
"""Pasos 5 y 6: monta las partes de la IA en el lugar de las piezas de un NIF
vanilla --el DONANTE-- y les da sus pesos. Corre en Blender, con PyNifly.

    blender -b --python scripts/montar.py -- <plan.json>
    blender -b --python scripts/montar.py -- --falsificar <donante.nif> [<esqueleto.nif>]

Exit 0 si el NIF escrito pasa los controles, 1 si no, 2 si el plan no sirve.

EL PLAN
-------
Las rutas relativas son relativas al plan. Las piezas que el plan no nombra
quedan como en el vanilla: se puede reemplazar de a una.

    {
      "donante":   "vanilla/steamcenturion.nif",
      "esqueleto": "vanilla/skeleton.nif",            (opcional)
      "salida":    "mod/meshes/.../steamcenturion.nif",
      "piezas": {
        "SteamLThigh": {
          "parte": "partes/muslo.obj",               (.obj .glb .gltf .blend)
          "modo": "segmento",
          "desde": [0, 0, 0.9], "hasta": [0, 0.05, 0.1],  (puntos de la parte)
          "huesos": ["NPC L Thigh [LThg]", "NPC L Calf [LClf]"],
          "escala": "eje",                           (o "uniforme")
          "frente": [0, 1, 0]                        (opcional; o "arriba")
        },
        "SteamRThigh": { ... lo mismo ..., "espejar": true },
        "SteamCenturion": {
          "parte": "partes/cabeza.glb", "modo": "caja",
          "escala": "contener"                       (o "llenar", "ejes")
        }
      }
    }

Los puntos de la parte son coordenadas de Blender despues de importarla (lo
que se ve en el visor). Cada hueso se puede dar por nombre --el crudo del
NIF, con corchetes-- o como un punto [x, y, z] del juego. Las posiciones de
hueso se leen del binario con nif_nodos.py, nunca de PyNifly: importar puede
sustituir el esqueleto (trampa 1). `espejar` refleja la parte en X antes de
montarla, y los puntos del plan son los de la parte SIN espejar.

QUE HACE, POR PIEZA
-------------------
  1. importa la parte y une sus mallas en una;
  2. la monta (montaje_puro.ajuste_segmento o ajuste_caja);
  3. le pone la geometria al objeto de la pieza vanilla, que conserva nombre,
     propiedades de PyNifly, materiales, padre y modificador de armadura;
  4. copia a cada vertice los pesos del vertice vanilla mas cercano,
     particion incluida (montaje_puro.pesos_por_vecino);
  5. controla los pesos (montaje_puro.controles_pesos).

Despues exporta con `target_game='SKYRIMSE', intuit_defaults=False` (trampa
33) y los huesos sin renombrar, y compara el archivo escrito contra el
donante con verificar_export.py. El reporte va a `<salida>_montaje.json`.

LO QUE NO HACE
--------------
  * Solidify: si la medicion dijo cascara, va en el paso 4, antes de las UV
    (trampa 32).
  * Texturas: la pieza queda con el material del donante. Las rutas las pone
    el paso 7.
  * Juzgar el diseno. Que el muslo caiga entre la cadera y la rodilla no dice
    que se vea bien: eso se mira en el render y en el juego.

--falsificar
------------
Saca cada pieza del donante, la corre, la gira y la escala como si viniera de
la IA, arma el plan con los puntos que le corresponden y la monta. Cada
vertice tiene que volver a SU lugar (error < 0,01 unidades), los pesos tienen
que pasar los controles, y el NIF tiene que pasar verificar_export contra el
donante. Un plan con los extremos cruzados tiene que dejar la pieza lejos --a
mas de la mitad de su diagonal--: si no, el control no mide nada.
"""
import json
import math
import os
import random
import shutil
import sys
import tempfile

import bpy
from mathutils import Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from correr_en_blender import correr  # noqa: E402
import montaje_puro as mp  # noqa: E402
import nif_nodos  # noqa: E402
import verificar_export  # noqa: E402

TOLERANCIA_RECONSTRUCCION = 0.01   # unidades del juego


# ---------------------------------------------------------------------------
# Blender
# ---------------------------------------------------------------------------

def preparar_escena():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import addon_utils
    addon_utils.enable("io_scene_nifly", default_set=True)


def importar_donante(ruta):
    """{nombre del shape: objeto}. Los huesos sin renombrar: los nombres
    quedan los crudos del NIF, que es lo que compara verificar_export."""
    antes = set(bpy.data.objects)
    # create_bones=False: sin eso PyNifly agrega a la armadura el esqueleto
    # de referencia entero, y al exportar escribe esos huesos en el NIF.
    # Medido con el centurion: 21 NiNode en el vanilla, 53 en el exportado
    # (los CME, NPC COM, las clavículas...).
    r = bpy.ops.import_scene.pynifly(filepath=ruta, rename_bones=False,
                                     create_bones=False,
                                     import_animations=False,
                                     import_collisions=False)
    if "FINISHED" not in r:
        raise SystemExit("PyNifly no pudo importar %s" % ruta)
    piezas = {}
    for ob in set(bpy.data.objects) - antes:
        if ob.type == "MESH":
            piezas[ob.get("pynNodeName", ob.name)] = ob
    return piezas


def puntos_mundo(ob):
    mw = ob.matrix_world
    return [tuple(mw @ v.co) for v in ob.data.vertices]


def pesos_de(ob):
    nombres = {g.index: g.name for g in ob.vertex_groups}
    return [{nombres[g.group]: g.weight for g in v.groups
             if g.group in nombres} for v in ob.data.vertices]


def importar_parte(ruta, objeto=None):
    """Un objeto de malla con todas las mallas de la parte unidas, con sus
    transformadas aplicadas: sus vertices quedan en coordenadas de mundo."""
    ext = os.path.splitext(ruta)[1].lower()
    antes = set(bpy.data.objects)
    if ext == ".obj":
        bpy.ops.wm.obj_import(filepath=ruta)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=ruta)
    elif ext == ".blend":
        with bpy.data.libraries.load(ruta, link=False) as (origen, destino):
            destino.objects = [n for n in origen.objects
                               if objeto is None or n == objeto]
        for ob in destino.objects:
            if ob is not None:
                bpy.context.scene.collection.objects.link(ob)
    else:
        raise SystemExit("parte %s: extension no soportada" % ruta)
    nuevas = [o for o in set(bpy.data.objects) - antes if o.type == "MESH"
              and (objeto is None or ext != ".blend" or o.name == objeto)]
    if not nuevas:
        raise SystemExit("parte %s: no trajo ninguna malla%s"
                         % (ruta, " llamada %r" % objeto if objeto else ""))
    for o in nuevas:
        o.data = o.data.copy()
        o.data.transform(o.matrix_world)
        o.matrix_world = Matrix.Identity(4)
        o.parent = None
    if len(nuevas) > 1:
        with bpy.context.temp_override(active_object=nuevas[0],
                                       selected_editable_objects=nuevas):
            bpy.ops.object.join()
    parte = nuevas[0]
    for o in set(bpy.data.objects) - antes - {parte}:
        bpy.data.objects.remove(o, do_unlink=True)
    return parte


def posicion_hueso(ref, huesos):
    if isinstance(ref, str):
        if ref not in huesos:
            raise SystemExit("hueso %r: no esta en el donante ni en el "
                             "esqueleto. Algunos que si: %s"
                             % (ref, ", ".join(sorted(huesos)[:8])))
        return tuple(huesos[ref][:3])
    return tuple(float(c) for c in ref)


def montar_pieza(ob, conf, huesos):
    """Monta una parte en el objeto vanilla `ob`. Devuelve el reporte."""
    donante_pts = puntos_mundo(ob)
    donante_pesos = pesos_de(ob)
    # En Blender 4 los nombres de los grupos de vertices viven en la MALLA:
    # al cambiarle la malla al objeto desaparecen. Se guardan antes.
    nombres = [g.name for g in ob.vertex_groups]
    huesos_vanilla = sorted({g for p in donante_pesos for g, w in p.items()
                             if w > 0 and not mp.es_particion(g)})
    caja_vanilla = mp.caja(donante_pts)
    diag = math.dist(caja_vanilla[0], caja_vanilla[1])

    parte = importar_parte(conf["parte"], conf.get("objeto"))
    pts = [tuple(v.co) for v in parte.data.vertices]
    pre = mp.espejo_x() if conf.get("espejar") else mp.identidad()
    pts_pre = mp.aplicar(pre, pts)
    notas = []
    if conf["modo"] == "segmento":
        a, b = mp.aplicar(pre, [conf["desde"], conf["hasta"]])
        giro, destino = None, mp.DIRECCIONES_GIRO["frente"]
        for clave, dir_juego in mp.DIRECCIONES_GIRO.items():
            if clave in conf:
                # una direccion: la parte 3x3 del espejo, sin traslacion
                giro = mp._mat3_vec([fila[:3] for fila in pre[:3]],
                                    conf[clave])
                destino = dir_juego
        A = posicion_hueso(conf["huesos"][0], huesos)
        B = posicion_hueso(conf["huesos"][1], huesos)
        try:
            m, n = mp.ajuste_segmento(a, b, A, B, conf.get("escala", "eje"),
                                      frente=giro, frente_destino=destino)
        except mp.MontajeError as e:
            raise SystemExit("pieza %s: %s" % (ob.name, e))
    else:
        m, n = mp.ajuste_caja(mp.caja(pts_pre), caja_vanilla,
                              conf.get("escala", "contener"))
    notas += n
    total = mp.componer(m, pre)
    nuevos = mp.aplicar(total, pts)

    me = parte.data.copy()
    me.transform(ob.matrix_world.inverted() @ Matrix(total))
    if mp.determinante(total) < 0:
        me.flip_normals()             # un espejo deja las caras del reves
    me.materials.clear()
    for mat in ob.data.materials:
        me.materials.append(mat)
    if not me.uv_layers:
        notas.append("la parte no trae UV: la textura no va a tener donde "
                     "caer")
    if not me.color_attributes:
        # El vanilla lleva colores de vertice (vertexDesc COLORS); sin la capa
        # el exportador los omite y la pieza cambia de formato.
        col = me.color_attributes.new(name="Col", type="BYTE_COLOR",
                                      domain="CORNER")
        col.data.foreach_set("color", [1.0] * (len(col.data) * 4))
    viejo = ob.data
    ob.data = me
    bpy.data.meshes.remove(viejo)
    bpy.data.objects.remove(parte, do_unlink=True)

    pesos, dist = mp.pesos_por_vecino(nuevos, donante_pts, donante_pesos)
    ob.vertex_groups.clear()
    grupos = {nombre: ob.vertex_groups.new(name=nombre) for nombre in nombres}
    por_valor = {}
    for i, p in enumerate(pesos):
        for g, w in p.items():
            por_valor.setdefault((g, w), []).append(i)
    for (g, w), idx in por_valor.items():
        grupos[g].add(idx, w, "REPLACE")

    fallas, obs = mp.controles_pesos(pesos, huesos_vanilla, dist, diag)
    return {
        "parte": conf["parte"], "modo": conf["modo"],
        "espejada": bool(conf.get("espejar")),
        "matriz": [[round(x, 6) for x in fila] for fila in total],
        "vertices": len(nuevos), "vertices_vanilla": len(donante_pts),
        "caja": mp.caja(nuevos), "caja_vanilla": caja_vanilla,
        "huesos_vanilla": huesos_vanilla,
        "fallas": fallas, "notas": notas + obs,
        "distancias": dist,
    }


def exportar(ruta):
    """Exporta todo con PyNifly. El exito se decide por el ARCHIVO: medido
    con PyNifly en Blender 4.4.1, el operador devuelve set() --ni FINISHED ni
    CANCELLED-- aunque escriba bien. Por eso se borra antes lo que hubiera:
    si no, un NIF viejo pasaria por el recien exportado."""
    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    if os.path.exists(ruta):
        os.remove(ruta)
    objetos = [o for o in bpy.data.objects
               if o.type in ("MESH", "ARMATURE", "EMPTY")]
    arm = next((o for o in objetos if o.type == "ARMATURE"), None)
    for o in bpy.data.objects:
        o.select_set(o in objetos)
    if arm is not None:
        bpy.context.view_layer.objects.active = arm
    r = bpy.ops.export_scene.pynifly(
        filepath=ruta, target_game="SKYRIMSE", intuit_defaults=False,
        rename_bones=False, preserve_hierarchy=True, export_modifiers=False,
        export_colors=True, export_animations=False, write_bodytri=False)
    if not os.path.isfile(ruta):
        raise SystemExit("PyNifly no escribio %s (el operador devolvio %r)"
                         % (ruta, r))


def ejecutar(plan, base):
    """(codigo, reporte). `base` es la carpeta del plan."""
    def ruta(r):
        return r if os.path.isabs(r) else os.path.normpath(
            os.path.join(base, r))

    donante, salida = ruta(plan["donante"]), ruta(plan["salida"])
    preparar_escena()
    piezas = importar_donante(donante)
    faltan = sorted(set(plan["piezas"]) - set(piezas))
    if faltan:
        raise SystemExit("el donante no tiene %s. Tiene: %s"
                         % (", ".join(faltan), ", ".join(sorted(piezas))))
    huesos, _p = nif_nodos.mundo(nif_nodos.leer(donante))
    if plan.get("esqueleto"):
        esq, _p = nif_nodos.mundo(nif_nodos.leer(ruta(plan["esqueleto"])))
        huesos = dict(esq, **huesos)
    reporte = {"blender": bpy.app.version_string, "donante": donante,
               "salida": salida, "piezas": {}}
    for nombre in sorted(plan["piezas"]):
        conf = dict(plan["piezas"][nombre])
        conf["parte"] = ruta(conf["parte"])
        reporte["piezas"][nombre] = montar_pieza(piezas[nombre], conf, huesos)
    exportar(salida)
    fallas, notas, n = verificar_export.comparar(salida, donante)
    reporte["verificar_export"] = {"comparaciones": n,
                                   "fallas": [str(f) for f in fallas],
                                   "notas": [str(x) for x in notas]}
    malas = [(k, f) for k, v in reporte["piezas"].items() for f in v["fallas"]]
    codigo = 1 if (malas or fallas or n == 0) else 0
    for v in reporte["piezas"].values():
        d = v.pop("distancias")
        v["distancia_maxima"] = round(max(d), 4) if d else None
    with open(os.path.splitext(salida)[0] + "_montaje.json", "w",
              encoding="utf-8") as fh:
        json.dump(reporte, fh, indent=2, ensure_ascii=False)
    return codigo, reporte


def imprimir(codigo, reporte):
    for nombre, v in sorted(reporte["piezas"].items()):
        print("[montar] %-18s %-8s %5d vertices  huesos %s"
              % (nombre, v["modo"], v["vertices"],
                 ", ".join(v["huesos_vanilla"])))
        for f in v["fallas"]:
            print("   FALLA %s" % f)
        for x in v["notas"]:
            print("   %s" % x)
    ve = reporte["verificar_export"]
    print("[verificar_export] %d comparaciones, %d fallas"
          % (ve["comparaciones"], len(ve["fallas"])))
    for f in ve["fallas"]:
        print("   %s" % f)
    print("[montar] %s -> %s" % ("PASA" if codigo == 0 else "NO PASA",
                                 reporte["salida"]))


# ---------------------------------------------------------------------------
# falsificacion
# ---------------------------------------------------------------------------

def _rotacion_al_azar(rng):
    eje = mp._unitario((rng.uniform(-1, 1), rng.uniform(-1, 1),
                        rng.uniform(-1, 1)))
    return mp.de_3x3(mp.rotacion_eje(eje, rng.uniform(0.3, 3.0)))


def _extremos(pts):
    """Los dos vertices mas separados a lo largo del eje mas largo de la caja:
    el 'desde' y 'hasta' de una pieza que no tiene huesos a mano."""
    c = mp.caja(pts)
    eje = max(range(3), key=lambda i: c[1][i] - c[0][i])
    return min(pts, key=lambda p: p[eje]), max(pts, key=lambda p: p[eje])


def _error_por_vertice(nombre, esperado):
    """Distancia maxima entre cada vertice montado y EL SUYO del vanilla (no
    el mas cercano: una pieza casi simetrica dada vuelta cae cerca de otros
    vertices y pasaba). El .obj conserva el orden de los vertices."""
    ob = next(o for o in bpy.data.objects if o.type == "MESH"
              and o.get("pynNodeName", o.name) == nombre)
    pts = puntos_mundo(ob)
    if len(pts) != len(esperado):
        return None
    return max(math.dist(p, q) for p, q in zip(pts, esperado))


def _normales_mundo(ob):
    r = ob.matrix_world.to_3x3()
    return [tuple((r @ poly.normal).normalized()) for poly in ob.data.polygons]


def _pares_izquierda_derecha(nombres):
    """[(izquierda, derecha)] de piezas cuyo nombre cambia en una L por R."""
    pares = []
    for n in sorted(nombres):
        for i, c in enumerate(n):
            if c == "L" and n[:i] + "R" + n[i + 1:] in nombres:
                pares.append((n, n[:i] + "R" + n[i + 1:]))
                break
    return pares


def falsificar(donante, esqueleto=None):
    rng = random.Random(57)
    tmp = tempfile.mkdtemp(prefix="montar_falsificar_")
    try:
        preparar_escena()
        piezas = importar_donante(donante)
        plan = {"donante": donante, "salida": os.path.join(tmp, "nuevo.nif"),
                "piezas": {}}
        if esqueleto:
            plan["esqueleto"] = esqueleto
        huesos, _p = nif_nodos.mundo(nif_nodos.leer(donante))
        esperado = {}
        for i, (nombre, ob) in enumerate(sorted(piezas.items())):
            pts = puntos_mundo(ob)
            esperado[nombre] = pts
            s = rng.uniform(0.005, 0.05)          # de unidades del juego a "metros"
            t = mp.traslacion((rng.uniform(-3, 3), rng.uniform(-3, 3),
                               rng.uniform(-3, 3)))
            if i % 2 == 0:
                r = _rotacion_al_azar(rng)
                a, b = _extremos(pts)
                conf = {"modo": "segmento", "escala": "uniforme",
                        "huesos": [list(a), list(b)]}
            else:
                r = mp.identidad()                 # la caja no sabe de giros
                conf = {"modo": "caja", "escala": "contener"}
            m = mp.componer(t, r, mp.de_3x3([[s, 0, 0], [0, s, 0], [0, 0, s]]))
            if conf["modo"] == "segmento":
                pa, pb = mp.aplicar(m, [a, b])
                conf["desde"], conf["hasta"] = list(pa), list(pb)
                # La direccion del juego mas perpendicular al eje de la
                # pieza: +Y para casi todas, +Z para el pie, que es largo en Y.
                eje = mp._unitario(mp._resta(b, a))
                clave = min(mp.DIRECCIONES_GIRO, key=lambda k: abs(
                    mp._punto(eje, mp.DIRECCIONES_GIRO[k])))
                conf[clave] = list(mp._mat3_vec([fila[:3] for fila in r[:3]],
                                                mp.DIRECCIONES_GIRO[clave]))
            me = ob.data.copy()
            me.transform(Matrix(m) @ ob.matrix_world)
            tmp_ob = bpy.data.objects.new("parte_" + nombre, me)
            bpy.context.scene.collection.objects.link(tmp_ob)
            for o in bpy.data.objects:
                o.select_set(o is tmp_ob)
            ruta = os.path.join(tmp, "parte_%s.obj" % nombre)
            bpy.ops.wm.obj_export(filepath=ruta, export_selected_objects=True,
                                  apply_modifiers=False,
                                  export_materials=False)
            bpy.data.objects.remove(tmp_ob, do_unlink=True)
            conf["parte"] = ruta
            plan["piezas"][nombre] = conf
        with open(os.path.join(tmp, "plan.json"), "w") as fh:
            json.dump(plan, fh)

        fallas = []
        codigo, rep = ejecutar(plan, tmp)
        errores = {}
        for nombre, v in rep["piezas"].items():
            errores[nombre] = _error_por_vertice(nombre, esperado[nombre])
            if errores[nombre] is None or \
                    errores[nombre] > TOLERANCIA_RECONSTRUCCION:
                fallas.append("%s: no volvio a su lugar (%s unidades)"
                              % (nombre, errores[nombre]))
            fallas += ["%s: %s" % (nombre, f) for f in v["fallas"]]
        fallas += rep["verificar_export"]["fallas"]
        # El plan con los extremos cruzados, en la pieza de segmento mas
        # largo: tiene que terminar dada vuelta y lejos. Con la primera por
        # orden alfabetico (la cabeza, casi simetrica) quedaba a solo el 13 %
        # de su diagonal.
        segmentadas = [k for k, v in plan["piezas"].items()
                       if v["modo"] == "segmento"]
        victima = max(segmentadas, key=lambda k: math.dist(
            *plan["piezas"][k]["huesos"]))       # el largo en el juego
        cruzado = json.loads(json.dumps(plan))
        pz = cruzado["piezas"][victima]
        pz["desde"], pz["hasta"] = pz["hasta"], pz["desde"]
        cruzado["piezas"] = {victima: pz}
        cruzado["salida"] = os.path.join(tmp, "cruzado.nif")
        _c, rep2 = ejecutar(cruzado, tmp)
        lejos = _error_por_vertice(victima, esperado[victima])
        diag = math.dist(*rep2["piezas"][victima]["caja_vanilla"])
        if lejos is None or lejos < 0.5 * diag:
            fallas.append("plan cruzado en %s: la pieza quedo a %s, el "
                          "control no distingue un montaje dado vuelta"
                          % (victima, lejos))
        # Espejar: la pieza izquierda, montada espejada en el lugar de la
        # derecha, tiene que dar EXACTAMENTE su espejo, con las caras hacia
        # afuera. Sin invertir las caras el espejo deja las normales hacia
        # adentro, y con backface culling la pieza sale invisible.
        pares = _pares_izquierda_derecha(set(plan["piezas"]))
        espejo_txt = "sin pares izquierda/derecha en el donante"
        if pares:
            izq, der = pares[0]
            preparar_escena()
            fuente = importar_donante(donante)[izq]
            pts_izq = puntos_mundo(fuente)
            normales_izq = _normales_mundo(fuente)
            for o in bpy.data.objects:
                o.select_set(o is fuente)
            ruta = os.path.join(tmp, "izquierda.obj")
            bpy.ops.wm.obj_export(filepath=ruta, export_selected_objects=True,
                                  apply_modifiers=False,
                                  export_materials=False)
            a, b = _extremos(pts_izq)
            espejado = {"donante": donante,
                        "salida": os.path.join(tmp, "espejo.nif"),
                        "piezas": {der: {
                            "parte": ruta, "modo": "segmento",
                            "escala": "uniforme", "espejar": True,
                            "desde": list(a), "hasta": list(b),
                            "huesos": [[-a[0], a[1], a[2]],
                                       [-b[0], b[1], b[2]]]}}}
            ejecutar(espejado, tmp)
            esperado_der = [(-x, y, z) for x, y, z in pts_izq]
            err = _error_por_vertice(der, esperado_der)
            ob = next(o for o in bpy.data.objects if o.type == "MESH"
                      and o.get("pynNodeName", o.name) == der)
            nm = _normales_mundo(ob)
            coinciden = sum(
                1 for n, m in zip(nm, normales_izq)
                if n[0] * -m[0] + n[1] * m[1] + n[2] * m[2] > 0.99)
            if err is None or err > TOLERANCIA_RECONSTRUCCION:
                fallas.append("espejo %s -> %s: no dio el espejo exacto (%s)"
                              % (izq, der, err))
            if len(nm) != len(normales_izq) or coinciden != len(nm):
                fallas.append("espejo %s -> %s: %d de %d caras con la normal "
                              "hacia afuera" % (izq, der, coinciden, len(nm)))
            espejo_txt = ("espejo %s -> %s: error %.5f, %d de %d caras hacia "
                          "afuera" % (izq, der, err if err is not None else -1,
                                      coinciden, len(nm)))
        print("[falsificar] %d piezas (%d por segmento, %d por caja); "
              "peor error %.5f; verificar_export %d comparaciones; plan "
              "cruzado en %s: %.2f unidades (%.0f %% de su diagonal)"
              % (len(plan["piezas"]), len(segmentadas),
                 len(plan["piezas"]) - len(segmentadas),
                 max(e for e in errores.values() if e is not None),
                 rep["verificar_export"]["comparaciones"], victima, lejos,
                 100.0 * lejos / diag))
        print("[falsificar] %s" % espejo_txt)
        for f in fallas:
            print("   FALLA %s" % f)
        print("[falsificar] %s" % ("PASA" if not fallas else "NO PASA"))
        return 1 if fallas else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------

def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if args and args[0] == "--falsificar" and len(args) in (2, 3):
        raise SystemExit(falsificar(*args[1:]))
    if len(args) != 1 or args[0].startswith("--"):
        print(__doc__)
        raise SystemExit(2)
    with open(args[0], encoding="utf-8") as fh:
        plan = json.load(fh)
    problemas = mp.validar_plan(plan)
    if problemas:
        print("el plan no sirve:")
        for x in problemas:
            print("  - %s" % x)
        raise SystemExit(2)
    codigo, reporte = ejecutar(plan, os.path.dirname(os.path.abspath(args[0])))
    imprimir(codigo, reporte)
    raise SystemExit(codigo)


correr(main)
