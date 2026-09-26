# -*- coding: utf-8 -*-
"""Endereza las lineas duras de una pieza: la ondulacion, no la curva.

POR QUE NO ALCANZA CON `preparar_parte.py --planar`. El pase planar DISUELVE
geometria redundante: junta en una cara lo que ya es el mismo panel. Lo que no
hace es mover un vertice. Si la linea de un filo zigzaguea porque sus vertices
estan fisicamente desplazados, disolver no la endereza --y con menos vertices
encima, a veces se ve peor--. Este script hace la otra operacion: ajusta la
cuerda de cada cadena y PROYECTA los vertices interiores sobre ella.

Que endereza: los CAMINOS de aristas duras de 3 vertices o mas. Los caminos
salen de partir el grafo de aristas duras en los cruces: un vertice donde las
lineas se cruzan es EXTREMO de los caminos que salen de el, nunca un punto
interior, asi que un cruce no lo mueven dos cuerdas a la vez. Los caminos de
dos vertices --los que salen de un cruce-- no se tocan. Los ciclos cerrados se
rechazan: sin extremos que fijar, una cuerda los convertiria en una recta.

DE DONDE SALEN LAS ARISTAS DURAS. Por defecto, automatico: las aristas que
doblan mas de `--angulo` mas los bordes abiertos. En una malla de IA eso sale
RUIDOSO --la superficie es densa y una cresta de 60 grados aparece y desaparece
a lo largo de la misma linea--, y los caminos salen cortos. Por eso existe
`--marcadas`: con el las aristas son SOLO las que marcaste como *sharp* en
Blender. Es la via confiable, porque la linea la eligio una persona mirando la
pieza y no un umbral de grados. En un arma Dwemer generada por IA, marcar las
lineas estructurales antes de correr esto es la diferencia entre enderezar
algo y enderezar nada.

El tope es la parte importante: `--tope F` es la fraccion del alto de la pieza
que una cadena puede apartarse de su cuerda y seguir siendo "una linea
ondulada". Si se aparta mas, se la deja como esta y se informa: es una curva de
diseno. En una pieza Dwemer conviven las dos cosas --una barra mecanica y un
arco decorativo--, y confundirlas no tira ningun error: la malla sigue sana y
el destrozo solo se ve en el render.

**El tope NO esta medido.** 0,002 (0,2 % del alto) es un punto de partida
prudente, no un valor del censo. Para elegirlo con datos en vez de a ojo, el
informe trae la CALIBRACION: los percentiles de desvio/alto de todas las
cadenas candidatas --tambien las que el tope rechazo-- y cuantas calificarian
con cada tope de una grilla. Si las cadenas se parten en dos grupos, el tope
que los separa se lee ahi.

Sin `--aplicar` no escribe nada: informa que cadenas encontraria, cuanto se
aparta cada una y cual enderezaria. Con `--aplicar`, si ninguna cadena califica
no guarda y sale con 1 --como `desplegar_uv.py`: no comprobar nada no es
exito--.

ORDEN: despues de `preparar_parte.py` (que solda y decima) y ANTES de
`desplegar_uv.py`. Rehace geometria, asi que despues del bake o del despliegue
de UV tira trabajo.

LO QUE NO ESTA RESUELTO, Y ES CARO: esto mueve la BAJA y no la ALTA. La regla
del repo para lo que deforma es aplicarselo tambien a la alta (trampa 34), y
aca no se puede vertice a vertice: son topologias distintas. El movimiento es
chico --el que dice el informe, del orden del tope-- pero cuanto de eso llega
al normal horneado no se midio (`[no medido]`). Consecuencia practica: mirar
los avisos de alineacion de `hornear.py` y el render, y no encadenar este paso
con un tope grande en la misma corrida.

Uso:
  blender -b --python enderezar.py -- <pieza.blend> [--tope F] [--angulo G] [--minimo N] [--marcadas] [--aplicar]

  --tope F      fraccion del alto de la pieza (0.002 por defecto, NO medido)
  --angulo G    grados a partir de los cuales una arista es "dura" (30)
  --minimo N    vertices minimos de un camino para considerarlo (3)
  --marcadas    usar SOLO las aristas marcadas como sharp en Blender, en vez
                de detectar crestas por angulo (ver arriba: es la via
                confiable en una malla de IA)
  --aplicar     escribe el resultado; sin esto, solo informa

Ejemplo:
  blender -b --python enderezar.py -- partes/arma.blend                 # informa
  blender -b --python enderezar.py -- partes/arma.blend --marcadas --aplicar
"""

import json
import math
import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import enderezar_puro as ep  # noqa: E402
from correr_en_blender import correr  # noqa: E402

TOPE = 0.002      # fraccion del alto; NO medido, punto de partida (docstring)
ANGULO = 30.0     # grados: a partir de aca la arista es una cresta
MINIMO = 3        # vertices: con dos no hay recta que ajustar


def aristas_duras(bm, angulo, orden, marcadas=False):
    """(pares de indices por tipo) de las aristas que son linea de diseno.

    Dos fuentes, y la diferencia importa:

      AUTOMATICA (por defecto)  aristas que doblan mas que `angulo`, mas los
                                bordes abiertos. En una malla de IA esto sale
                                RUIDOSO: la superficie es densa, el
                                generador no tiene bordes rectos y una cresta
                                de 60 grados aparece y desaparece a lo largo
                                de la misma linea. Por eso los caminos que
                                salen de aca son cortos y hay que bajar el
                                `--minimo` con cuidado.

      MARCADAS (`--marcadas`)   solo las aristas que marcaste como *sharp* en
                                Blender. Es la via confiable: la linea la
                                eligio una persona mirando la pieza, no un
                                umbral de grados. En una malla de IA es la
                                diferencia entre enderezar algo y enderezar
                                nada.

    El indice sale de `orden` y no de `v.index`: el indice del BMesh es -1
    hasta que se lo pide, y depender de eso es la clase de detalle que rompe
    lejos del lugar donde se escribio.
    """
    limites = math.radians(angulo)
    crestas, bordes = [], []
    for e in bm.edges:
        par = (orden[e.verts[0]], orden[e.verts[1]])
        n = len(e.link_faces)
        # `e.smooth` es el *sharp* de la interfaz: False = marcada.
        if marcadas:
            if not e.smooth:
                crestas.append(par)
            continue
        if n == 1:
            bordes.append(par)
        elif n == 2:
            try:
                dobla = e.calc_face_angle(0.0)
            except ValueError:
                continue
            if dobla >= limites:
                crestas.append(par)
    return crestas, bordes


def enderezar_malla(obj, tope, angulo, minimo, aplicar, marcadas=False):
    """El pase completo sobre una malla. Devuelve el informe."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    try:
        orden = {v: i for i, v in enumerate(bm.verts)}
        co = [v.co.copy() for v in bm.verts]
        if not co:
            return {"malla": obj.name, "motivo": "la malla no tiene vertices"}
        alto = max(c.z for c in co) - min(c.z for c in co)
        if alto <= 0.0:
            return {"malla": obj.name, "motivo": "alto 0: no hay escala a la "
                                                 "que referir el tope"}
        limite = alto * tope
        crestas, bordes = aristas_duras(bm, angulo, orden, marcadas)
        informe = {"malla": obj.name, "vertices": len(bm.verts),
                   "alto": round(alto, 6), "tope_unidades": round(limite, 8),
                   "fuente": "marcadas" if marcadas else "automatica",
                   "aristas_duras": len(crestas) + len(bordes),
                   "crestas": len(crestas), "bordes": len(bordes)}
        cadenas, motivos = ep.encadenar(crestas + bordes)
        # Los caminos que salen de un cruce miden 2 vertices y no se pueden
        # enderezar. Se cuentan aparte: si la corrida no hace nada, el motivo
        # suele ser este y no el tope --y el informe tiene que poder decirlo--.
        utiles = [c for c in cadenas if len(c) >= minimo]
        informe["cadenas"] = len(cadenas)
        informe["cadenas_utiles"] = len(utiles)
        enderezadas, rechazadas, candidatas = [], list(motivos), []
        for cadena in utiles:
            puntos = [tuple(co[i]) for i in cadena]
            desvio, _largo = ep.desviacion(puntos)
            if desvio is not None:
                candidatas.append(desvio)
            nuevos, info = ep.enderezar(puntos, limite)
            if nuevos is None:
                rechazadas.append("cadena de %d vertices: %s"
                                  % (len(cadena), info["motivo"]))
                continue
            enderezadas.append({"vertices": len(cadena),
                                "desvio_antes": round(info["desvio_antes"], 8),
                                "movimiento_max": round(info["movimiento_max"], 8)})
            if aplicar:
                for i, p in zip(cadena, nuevos):
                    co[i] = p
        informe["enderezadas"] = len(enderezadas)
        informe["detalle_enderezadas"] = enderezadas
        informe["rechazadas"] = rechazadas
        # La calibracion mira TODAS las candidatas --tambien las que el tope
        # rechazo--: es para elegir el tope, no para justificar el elegido.
        informe["calibracion"] = ep.calibracion(candidatas, alto)
        if aplicar and enderezadas:
            for v in bm.verts:
                v.co = co[orden[v]]
            bm.to_mesh(obj.data)
            obj.data.update()
        return informe
    finally:
        bm.free()


def _mal(texto):
    """Argumentos que no sirven: exit 2, no 1 (1 es "no hubo nada que hacer")."""
    print("[enderezar] %s" % texto)
    raise SystemExit(2)


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not args or args[0].startswith("--"):
        print(__doc__)
        return
    ruta = os.path.abspath(args[0])
    if not ruta.endswith(".blend"):
        _mal("esperaba un .blend, no %s" % ruta)
    if not os.path.exists(ruta):
        _mal("%s no existe" % ruta)
    opciones = {"--tope": TOPE, "--angulo": ANGULO, "--minimo": MINIMO}
    for flag, tipo in (("--tope", float), ("--angulo", float),
                       ("--minimo", int)):
        if flag not in args:
            continue
        try:
            valor = tipo(args[args.index(flag) + 1])
        except (IndexError, ValueError):
            _mal("%s necesita un numero" % flag)
        if valor <= 0:
            _mal("%s tiene que ser mayor que 0" % flag)
        opciones[flag] = valor
    tope, angulo, minimo = (opciones["--tope"], opciones["--angulo"],
                            opciones["--minimo"])
    aplicar = "--aplicar" in args
    marcadas = "--marcadas" in args

    bpy.ops.wm.open_mainfile(filepath=ruta)
    mallas = [o for o in bpy.data.objects if o.type == 'MESH']
    if not mallas:
        _mal("%s no tiene mallas" % ruta)
    informes = [enderezar_malla(o, tope, angulo, minimo, aplicar, marcadas)
                for o in mallas]
    print("[enderezar] " + json.dumps(
        {"aplicado": aplicar, "tope": tope, "angulo": angulo, "minimo": minimo,
         "fuente": "marcadas" if marcadas else "automatica",
         "mallas": informes}, ensure_ascii=False))
    total = sum(i.get("enderezadas", 0) for i in informes)
    for i in informes:
        for r in i.get("rechazadas", []):
            print("  sin tocar: %s" % r)
        cal = i.get("calibracion")
        if cal:
            print("  calibracion: %d cadenas candidatas; desvio/alto min %.5f "
                  "mediana %.5f p90 %.5f max %.5f"
                  % (cal["n_cadenas"], cal["min"], cal["p50"], cal["p90"],
                     cal["max"]))
            print("    con tope %s calificarian %s"
                  % (", ".join(sorted(cal["por_tope"])),
                     ", ".join("%d" % cal["por_tope"][t]
                               for t in sorted(cal["por_tope"]))))
    if not total:
        utiles = sum(i.get("cadenas_utiles", 0) for i in informes)
        print("[enderezar] ninguna cadena califico con tope %.6f (%d caminos, "
              "%d de %d vertices o mas): %s"
              % (tope, sum(i.get("cadenas", 0) for i in informes), utiles,
                 minimo, "no se guardo" if aplicar else "nada que guardar"))
        if not utiles:
            print("  los caminos cortos salen de los CRUCES: en una pieza dura "
                  "las lineas se cruzan y el cruce corta el camino. Marca las "
                  "lineas que quieras enderezar y corre con --marcadas.")
        if aplicar:
            sys.exit(1)
        return
    if not aplicar:
        print("[enderezar] %d cadenas calificarian. Correr con --aplicar para "
              "escribirlas." % total)
        return
    bpy.ops.wm.save_as_mainfile(filepath=ruta)
    print("[enderezar] %d cadenas enderezadas -> %s" % (total, ruta))


correr(main)
