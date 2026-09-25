# -*- coding: utf-8 -*-
"""Lleva un asset NUEVO (baja y alta) al espacio de su nodo de anclaje.

    blender -b --python al_marco.py -- <plan.json> <baja.blend> <salida_baja.blend> [<alta.blend> <salida_alta.blend>] [--force]
    blender -b --python al_marco.py -- --falsificar

Es el paso 1 de `asset-nuevo-skyrim` ("modelar en el espacio local del nodo")
cuando el modelo viene de una IA, y el equivalente de `montar.py` para lo que
no es un replacer: un escudo o un arma se dibujan en el espacio local del nodo
del que cuelgan (`Prn`), y ningun nodo de anclaje mira al +Y del mundo. Va
despues de preparar_parte.py y antes de desplegar_uv.py y hornear.py.

EL PLAN (JSON)
--------------
    {"ejes":   {"+Z": "+Y", "+X": "+X"},
     "largo":  {"eje": "+Z", "valor": 55.8},
     "ancla":  {"modelo": [0.0, 0.0, 0.034], "marco": [0, 0, 0]},
     "topes":  {"+Z": 2.2}}

  ejes    dos ejes del modelo y a donde van en el marco: un eje (+Y) o un
          vector ([0.4067, 0.9135, 0]). El tercero sale del producto cruz: la
          rotacion es propia y un espejo no se puede escribir.
  largo   lo que mide la BAJA en ese eje suyo pasa a medir `valor`. O
          `escala` con el factor directo, uno de los dos.
  ancla   un punto del modelo ([x, y, z] o "centro" de su caja) va a ese
          punto del marco; null en un eje que no fija.
  topes   el extremo del modelo en ese sentido del marco queda en ese valor
          ("+Z": 2.2 = el punto mas alto, en Z = 2,2).

Cada eje del marco se fija UNA vez, con el ancla o con un tope. Los numeros
salen de medir los vanilla de la clase --el hacha de una mano: mango en +Y,
pomo en el origen; el escudo: el dorso en Z 2,2, la mediana de 16--, y el
eje del agarre del modelo, de medirlo a el. Validar y calcular es
montaje_puro.validar_marco / matriz_al_marco, que CI prueba.

LO QUE CUIDA
------------
  * La MISMA matriz a todas las mallas de la baja y de la alta (trampa 34: si
    no, el horneado sale corrido). La escala y los topes salen de la baja,
    que es la malla del juego.
  * Hornea la transformada de cada objeto en su malla antes de medir. Rechaza
    una escala negativa (Mesh.transform no da vuelta las caras, trampa 38),
    modificadores sin aplicar (la geometria medida no seria la que se
    exporta) y mallas compartidas por varios objetos.
  * No escribe sobre la entrada: aplicar la matriz dos veces la duplica. Una
    salida que ya existe pide --force.
  * Despues de aplicar, remide la baja en Blender: el largo y los topes
    tienen que dar lo pedido. Si no, no guarda.

--falsificar: una malla sintetica con cuatro puntos conocidos, llevada con un
plan de hacha; cada punto tiene que caer donde se calculo a mano, incluido el
que delata un espejo. Sin archivos del juego.

Exit 0 si pasa, 1 si reprueba o el plan no sirve, 2 si los argumentos no
sirven.
"""
import json
import os
import sys

import bpy
from mathutils import Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from correr_en_blender import correr  # noqa: E402
import montaje_puro as mp  # noqa: E402

TOL = 1e-4


def _mal(texto):
    """Argumentos que no sirven: exit 2, no 1 (1 es "reprueba")."""
    print("[marco] %s" % texto)
    raise SystemExit(2)


def mallas():
    return [o for o in bpy.data.objects if o.type == "MESH"]


def abrir(ruta):
    """Abre `ruta` y hornea la transformada de cada malla en sus vertices.
    [(objeto)] listas para aplicar la matriz del marco."""
    bpy.ops.wm.open_mainfile(filepath=ruta)
    objs = mallas()
    if not objs:
        raise SystemExit("%s no tiene mallas" % ruta)
    for o in objs:
        if o.modifiers:
            raise SystemExit("%s: %s tiene modificadores sin aplicar (%s): lo "
                             "medido no seria lo que se exporta"
                             % (ruta, o.name, ", ".join(m.name for m in o.modifiers)))
        if o.data.users > 1:
            raise SystemExit("%s: la malla de %s la comparten %d objetos"
                             % (ruta, o.name, o.data.users))
        if o.matrix_world.determinant() < 0:
            raise SystemExit("%s: %s tiene escala negativa: Mesh.transform no "
                             "da vuelta las caras (trampa 38). Aplicala y "
                             "revisa las normales antes" % (ruta, o.name))
        o.data.transform(o.matrix_world, shape_keys=True)
        o.matrix_world = Matrix.Identity(4)
    return objs


def vertices(objs):
    return [tuple(v.co) for o in objs for v in o.data.vertices]


def aplicar(objs, m):
    mm = Matrix(m)
    for o in objs:
        o.data.transform(mm, shape_keys=True)
        o.data.update()


def comprobar(plan, objs, m):
    """Remide en Blender lo que el plan pidio. Lista de fallas."""
    pts = vertices(objs)
    fallas = []
    if "largo" in plan:
        eje = plan["largo"]["eje"]
        r = mp.rotacion_por_ejes(plan["ejes"])
        d = mp._mat3_vec(r, mp.EJES[eje])
        proy = [sum(p[i] * d[i] for i in range(3)) for p in pts]
        largo = max(proy) - min(proy)
        if abs(largo - plan["largo"]["valor"]) > TOL * max(1.0, largo):
            fallas.append("el largo quedo en %.6f y no en %.6f"
                          % (largo, plan["largo"]["valor"]))
    for eje, v in (plan.get("topes") or {}).items():
        i = "XYZ".index(eje[1])
        ext = max(p[i] for p in pts) if eje[0] == "+" else min(p[i] for p in pts)
        if abs(ext - v) > TOL * max(1.0, abs(v)):
            fallas.append("el tope %s quedo en %.6f y no en %.6f" % (eje, ext, v))
    if mp.determinante(m) <= 0:
        fallas.append("la matriz espeja (determinante %.6f)" % mp.determinante(m))
    return fallas


def caja_de(objs):
    lo, hi = mp.caja(vertices(objs))
    return [[round(c, 4) for c in lo], [round(c, 4) for c in hi]]


def falsificar():
    """Cuatro puntos conocidos con un plan de hacha: cada uno a su lugar."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("puntos")
    me.from_pydata([(0, 0, 0), (0, 0, 1), (1, 0, 0), (0, 1, 0)], [],
                   [(0, 1, 2), (0, 2, 3), (0, 3, 1)])
    ob = bpy.data.objects.new("puntos", me)
    bpy.context.collection.objects.link(ob)
    plan = {"ejes": {"+Z": "+Y", "+X": "+X"},
            "largo": {"eje": "+Z", "valor": 10.0},
            "ancla": {"modelo": [0, 0, 0], "marco": [0, 0, 0]}}
    m, _inf = mp.matriz_al_marco(plan, vertices([ob]))
    aplicar([ob], m)
    fin = [tuple(round(c, 6) for c in v.co) for v in me.vertices]
    esperado = [(0, 0, 0), (0, 10, 0), (10, 0, 0), (0, 0, -10)]
    bien = all(all(abs(a - b) < 1e-5 for a, b in zip(f, e))
               for f, e in zip(fin, esperado))
    fallas = comprobar(plan, [ob], m)
    print("[falsificar] los cuatro puntos: %s" % ("donde tienen que ir" if bien
          else "MAL: %r en vez de %r" % (fin, esperado)))
    print("[falsificar] el remedido: %s" % ("da lo pedido" if not fallas
                                            else "; ".join(fallas)))
    print("falsificar: 2 comprobaciones, %d fallas" % ((not bien) + bool(fallas)))
    return 0 if bien and not fallas else 1


def _argumentos(args):
    force = "--force" in args
    resto = [a for a in args if a != "--force"]
    for a in resto:
        if a.startswith("--"):
            _mal("opcion desconocida: %s" % a)
    if len(resto) not in (3, 5):
        print(__doc__)
        raise SystemExit(2)
    plan_ruta, baja, salida_baja = resto[:3]
    pares = [(baja, salida_baja)]
    if len(resto) == 5:
        pares.append((resto[3], resto[4]))
    if not os.path.isfile(plan_ruta):
        _mal("no existe el plan: %s" % plan_ruta)
    for entrada, salida in pares:
        if not os.path.isfile(entrada):
            _mal("no existe: %s" % entrada)
        if os.path.abspath(entrada) == os.path.abspath(salida):
            _mal("%s: la salida no puede ser la entrada (la matriz se "
                 "aplicaria dos veces al reejecutar)" % entrada)
        if os.path.exists(salida) and not force:
            _mal("%s ya existe: usa --force para pisarlo" % salida)
    return plan_ruta, pares


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if args == ["--falsificar"]:
        sys.exit(falsificar())
    plan_ruta, pares = _argumentos(args)
    with open(plan_ruta, encoding="utf-8") as fh:
        try:
            plan = json.load(fh)
        except ValueError as e:
            raise SystemExit("el plan no es JSON: %s" % e)
    problemas = mp.validar_marco(plan)
    if problemas:
        for x in problemas:
            print("  PLAN %s" % x)
        raise SystemExit("el plan no sirve (%d problemas)" % len(problemas))

    (baja, salida_baja) = pares[0]
    objs = abrir(baja)
    m, inf = mp.matriz_al_marco(plan, vertices(objs))
    informe = {"plan": plan, "matriz": [[round(c, 6) for c in f] for f in m],
               "escala": round(inf["escala"], 6),
               "determinante": round(inf["determinante"], 6)}
    for i, (entrada, salida) in enumerate(pares):
        if i:
            objs = abrir(entrada)
        aplicar(objs, m)
        nombre = "baja" if i == 0 else "alta"
        informe[nombre] = {"mallas": len(objs), "caja": caja_de(objs)}
        if i == 0:
            fallas = comprobar(plan, objs, m)
            if fallas:
                print("[marco] " + json.dumps(informe, ensure_ascii=False))
                for f in fallas:
                    print("  FALLA %s" % f)
                raise SystemExit("no se guardo nada")
        bpy.ops.wm.save_as_mainfile(filepath=salida)
    with open(os.path.splitext(pares[0][1])[0] + "_marco.json", "w",
              encoding="utf-8") as fh:
        json.dump(informe, fh, indent=1, ensure_ascii=False)
    print("[marco] " + json.dumps(informe, ensure_ascii=False))
    print("[marco] escala %.4f, la misma matriz a %s"
          % (inf["escala"], " y ".join(s for _e, s in pares)))


correr(main)
