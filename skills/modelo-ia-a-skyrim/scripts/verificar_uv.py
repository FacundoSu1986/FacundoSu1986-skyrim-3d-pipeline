# -*- coding: utf-8 -*-
"""La V se escribe INVERTIDA en el NIF. Python puro, sin Blender.

    python scripts/verificar_uv.py <origen.obj> <exportado.nif>
    python scripts/verificar_uv.py --autotest

Exit 0 si pasa, 1 si no pasa o si no hubo NADA que comparar, 2 si los
argumentos no sirven.

POR QUE EXISTE

Un NIF guarda la V con el origen ARRIBA de la imagen; un OBJ y Blender la
guardan con el origen ABAJO. Un conversor OBJ -> NIF que copie la V tal cual
deja TODO el mapeo espejado en vertical. No da error: el archivo se escribe
bien, el juego lo carga, y la textura sale corrida.

Con un atlas ruidoso --el de una IA 3D, con una isla por triangulo-- ni se
nota, porque ya era ruido. Con una textura horneada salta a la vista, y el
sintoma se confunde con "el horneado salio mal", que es caro de rehacer.

LAS TRES LINEAS QUE FIJAN LA CONVENCION

1. `[MEASURED]` **PyNifly**, el importador que usa la comunidad, INVIERTE la V
   al importar. Sobre tres armas vanilla: 2.648 / 1.370 / 2.716 loops
   invertidos contra 13 / 23 / 16 iguales (los pocos "iguales" son los que
   caen cerca de v=0,5, donde invertir no cambia nada).

2. `[MEASURED]` **El corpus**. Las zonas vacias de un atlas son negro solido, y
   eso se detecta en los bytes comprimidos de DXT1/DXT5 sin decodificar nada
   (un bloque con color0 == color1 == 0). Muestreando las UV vanilla sobre esos
   mapas, tomar v como fila desde ARRIBA cae sobre pintura el 69,5 % de las
   veces contra el 58,3 % de la version invertida, y gana en 86 de 120
   archivos con al menos 25 % de atlas vacio. Es una tendencia, no una prueba:
   se anota como tal.

3. `[OBSERVED]` **Un control vanilla renderizado**: la malla de
   `elvenbattleaxe.nif` con su propia textura vanilla sale correcta SOLO con la
   V invertida.

  REGLA  v_invertida    la V del NIF tiene que ser el complemento de la del
                        origen (v_nif ~ 1 - v_obj) en la mayoria de los
                        vertices apareados
  OBS    fuera_de_rango UV fuera de [0,1]; el corpus las tiene, no reprueban
  OBS    u_distinta     vertices apareados cuya U no coincide

POR QUE SE APAREA POR POSICION NORMALIZADA

El conversor escala el modelo a tamano de arma --en el hacha, x79,7-- asi que
las posiciones absolutas no coinciden con las del OBJ. Se normaliza cada lado
por su propia caja antes de aparear. Eso tolera escala uniforme y traslacion,
que es lo que hace un conversor; NO tolera rotacion, y si alguien la agrega
esto deja de aparear y reprueba por "nada que comparar" -- que es el modo de
fallar correcto.
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import censo_nif  # noqa: E402

# Rejilla de apareo sobre la caja normalizada. 1e-4 de la caja: mas fino que
# cualquier detalle y mas grueso que el error de un float de 32 bits.
REJILLA = 1e-4

# Cerca de v=0,5 invertir no cambia nada, asi que esos vertices no votan.
MARGEN_MEDIO = 0.02

# Tolerancia al comparar coordenadas UV. Las del NIF son half-floats: ~3
# decimales utiles.
TOL_UV = 0.01


def _normalizar(pos):
    """Posiciones llevadas a su propia caja unitaria, como clave de rejilla."""
    finitos = [p for p in pos if all(-1e9 < c < 1e9 for c in p)]
    if not finitos:
        return None
    lo = [min(p[k] for p in finitos) for k in range(3)]
    hi = [max(p[k] for p in finitos) for k in range(3)]
    dim = max(hi[k] - lo[k] for k in range(3))
    if dim <= 0:
        return None
    claves = []
    for p in pos:
        if not all(-1e9 < c < 1e9 for c in p):
            claves.append(None)
            continue
        claves.append(tuple(round((p[k] - lo[k]) / dim / REJILLA)
                            for k in range(3)))
    return claves


def _leer_obj(ruta):
    """(pos, uv) por VERTICE de posicion. Un OBJ indexa posicion y UV por
    separado, asi que se recorren las caras para juntar cada par."""
    v, vt = [], []
    pares = defaultdict(set)
    with open(ruta, "r", errors="ignore") as fh:
        for linea in fh:
            if linea.startswith("v "):
                p = linea.split()
                v.append((float(p[1]), float(p[2]), float(p[3])))
            elif linea.startswith("vt "):
                p = linea.split()
                vt.append((float(p[1]), float(p[2])))
            elif linea.startswith("f "):
                for t in linea.split()[1:]:
                    c = t.split("/")
                    vi = int(c[0]) - 1
                    ti = int(c[1]) - 1 if len(c) > 1 and c[1] else None
                    if ti is not None and 0 <= ti < len(vt):
                        pares[vi].add(vt[ti])
    return v, pares


def comparar(pos_obj, uv_por_vertice, pos_nif, uv_nif):
    """(votos, notas). votos: cuantos vertices dicen 'invertida' y cuantos
    'igual'."""
    ka = _normalizar(pos_obj)
    kb = _normalizar(pos_nif)
    notas = []
    if ka is None or kb is None:
        return {"invertida": 0, "igual": 0, "otra": 0, "apareados": 0}, notas

    origen = defaultdict(set)
    for i, k in enumerate(ka):
        if k is None:
            continue
        for uv in uv_por_vertice.get(i, ()):
            origen[k].add((round(uv[0], 3), round(uv[1], 3)))

    votos = {"invertida": 0, "igual": 0, "otra": 0, "apareados": 0}
    fuera = 0
    u_distinta = 0
    for i, k in enumerate(kb):
        if k is None or k not in origen:
            continue
        u, v = uv_nif[i]
        if not (0.0 <= u <= 1.0 and 0.0 <= v <= 1.0):
            fuera += 1
        if abs(v - 0.5) < MARGEN_MEDIO:
            continue                      # no discrimina: no vota
        candidatas = [c for c in origen[k] if abs(c[0] - u) <= TOL_UV]
        if not candidatas:
            u_distinta += 1
            continue
        votos["apareados"] += 1
        igual = any(abs(c[1] - v) <= TOL_UV for c in candidatas)
        inv = any(abs((1.0 - c[1]) - v) <= TOL_UV for c in candidatas)
        if inv and not igual:
            votos["invertida"] += 1
        elif igual and not inv:
            votos["igual"] += 1
        else:
            votos["otra"] += 1
    if fuera:
        notas.append("OBS %d UV fuera de [0,1] en el NIF (el corpus tambien "
                     "las tiene: no reprueba)" % fuera)
    if u_distinta:
        notas.append("OBS %d vertices apareados por posicion cuya U no "
                     "coincide con ninguna del origen" % u_distinta)
    return votos, notas


def juzgar(votos):
    """(fallas, resumen). La REGLA."""
    fallas = []
    if votos["apareados"] == 0:
        fallas.append("cero vertices comparables: no comprobar nada no es "
                      "exito. Aparear falla si el conversor ROTA el modelo, "
                      "o si el OBJ no es el que se convirtio.")
        return fallas, "sin datos"
    if votos["igual"] >= votos["invertida"]:
        fallas.append(
            "REGLA v_invertida: %d vertices con la V IGUAL a la del origen "
            "contra %d invertida. El conversor no esta invirtiendo la V y "
            "toda la textura sale espejada en vertical. PyNifly invierte la V "
            "al importar en 2.648 / 1.370 / 2.716 loops de tres armas vanilla "
            "contra 13 / 23 / 16 que quedan igual."
            % (votos["igual"], votos["invertida"]))
    return fallas, ("invertida %d, igual %d, ambigua %d, de %d apareados"
                    % (votos["invertida"], votos["igual"], votos["otra"],
                       votos["apareados"]))


def revisar(ruta_obj, ruta_nif):
    pos_obj, uv_por_vertice = _leer_obj(ruta_obj)
    if not uv_por_vertice:
        print("   el OBJ no trae UV (vt): no hay nada que comparar")
        return 1
    shapes = [s for s in censo_nif.Nif(ruta_nif).geometria(con_uv=True)
              if not s.get("error")]
    avisos = [s for s in censo_nif.Nif(ruta_nif).geometria(con_uv=True)
              if s.get("error")]
    if not shapes:
        print("   el NIF no tiene shapes con geometria legible")
        for s in avisos:
            print("   AVISO %s: %s" % (s.get("nombre"), s["error"]))
        return 1

    total = {"invertida": 0, "igual": 0, "otra": 0, "apareados": 0}
    notas = []
    for s in shapes:
        if not s.get("uv"):
            notas.append("OBS %s no declara UV" % s["nombre"])
            continue
        v, n = comparar(pos_obj, uv_por_vertice, s["pos"], s["uv"])
        for k in total:
            total[k] += v[k]
        notas.extend("%s: %s" % (s["nombre"], x) for x in n)

    fallas, resumen = juzgar(total)
    print("== %s  ->  %s" % (os.path.basename(ruta_obj),
                             os.path.basename(ruta_nif)))
    print("   V: %s" % resumen)
    for n in notas:
        print("   %s" % n)
    for s in avisos:
        print("   AVISO %s: %s" % (s.get("nombre"), s["error"]))
    for f in fallas:
        print("   FALLA %s" % f)
    return 1 if fallas else 0


# --------------------------------------------------------------------------
def autotest():
    fallas = []

    def exigir(cond, texto):
        if not cond:
            fallas.append(texto)

    pos = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
    uvs = {0: {(0.0, 0.0)}, 1: {(1.0, 0.1)}, 2: {(1.0, 0.9)}, 3: {(0.0, 1.0)}}

    # el conversor correcto: invierte la V. Y escala, que es lo normal.
    escalado = [(x * 80.0, y * 80.0, z * 80.0) for x, y, z in pos]
    inv = [(u, 1.0 - v) for u, v in
           [(0.0, 0.0), (1.0, 0.1), (1.0, 0.9), (0.0, 1.0)]]
    votos, _ = comparar(pos, uvs, escalado, inv)
    exigir(votos["invertida"] > 0, "no conto ningun voto 'invertida'")
    exigir(votos["igual"] == 0, "voto 'igual' en el caso correcto")
    f, _ = juzgar(votos)
    exigir(not f, "el caso correcto reprobo")

    # el conversor roto: copia la V tal cual
    tal_cual = [(0.0, 0.0), (1.0, 0.1), (1.0, 0.9), (0.0, 1.0)]
    votos, _ = comparar(pos, uvs, escalado, tal_cual)
    exigir(votos["igual"] > 0, "no conto ningun voto 'igual'")
    f, _ = juzgar(votos)
    exigir(f, "el conversor sin invertir NO reprobo")

    # v ~ 0,5 no vota: invertir no cambia nada ahi
    medio = {0: {(0.0, 0.5)}, 1: {(1.0, 0.5)}, 2: {(1.0, 0.5)},
             3: {(0.0, 0.5)}}
    votos, _ = comparar(pos, medio, escalado, [(0.0, 0.5)] * 4)
    exigir(votos["apareados"] == 0,
           "los vertices de v=0,5 votaron: %d" % votos["apareados"])
    f, _ = juzgar(votos)
    # Se exige la RAZON, no solo que repruebe: con 0 votos de cada lado la
    # otra condicion (igual >= invertida) tambien es cierta, asi que exigir la
    # verdad a secas pasaba aunque se borrara la guarda de "cero
    # comprobaciones". Lo pesco mutar el codigo.
    exigir(f and "cero vertices comparables" in f[0],
           "cero apareados tiene que reprobar POR esa razon")

    # trasladar NO rompe el apareo, y es a proposito: se normaliza cada lado
    # por su propia caja, asi que escala uniforme y traslacion se toleran.
    # Queda afirmado para que nadie lo "arregle" por error.
    movido = [(x * 80.0 + 1000.0, y * 80.0 - 7.0, z * 80.0) for x, y, z in pos]
    votos, _ = comparar(pos, uvs, movido, inv)
    exigir(votos["invertida"] > 0,
           "una traslacion rompio el apareo: la normalizacion dejo de "
           "tolerarla")

    # sin nada que aparear: el origen no trae ninguna UV
    votos, _ = comparar(pos, {}, escalado, inv)
    f, _ = juzgar(votos)
    exigir(f and "cero vertices comparables" in f[0],
           "sin UV en el origen tiene que reprobar POR falta de datos")

    # una U que no coincide se informa y no vota
    votos, notas = comparar(pos, uvs, escalado,
                            [(0.42, 1.0 - v) for _u, v in tal_cual])
    exigir(votos["apareados"] == 0, "voto con la U distinta")
    exigir(any("U no coincide" in n for n in notas),
           "no informo las U distintas")

    print("autotest: %d comprobaciones, %d fallas" % (12, len(fallas)))
    for x in fallas:
        print("  FALLA %s" % x)
    return 1 if fallas else 0


def main(argv):
    if len(argv) == 1 and argv[0] == "--autotest":
        return autotest()
    if len(argv) == 2:
        obj, nif = argv
        if not obj.lower().endswith(".obj") or not nif.lower().endswith(".nif"):
            print("uso: verificar_uv.py <origen.obj> <exportado.nif>")
            return 2
        return revisar(obj, nif)
    print("uso: verificar_uv.py <origen.obj> <exportado.nif> | --autotest")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
