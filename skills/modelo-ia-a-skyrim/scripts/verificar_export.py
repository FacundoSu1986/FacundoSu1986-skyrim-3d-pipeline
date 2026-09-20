# -*- coding: utf-8 -*-
"""Reimporta el NIF exportado y lo compara contra el vanilla. Paso 8b.

    python scripts/verificar_export.py <nuevo.nif> <vanilla.nif>

Exit 0 si pasa, 1 si no. Python puro: NO abre Blender, NO usa PyNifly.

POR QUE SOBRE EL ARCHIVO Y NO SOBRE LA ESCENA

Entre la escena de Blender y el archivo que carga el juego hay un exportador, y
ese exportador puede perder cosas sin avisar. Verificar la escena en memoria
confirma lo que armaste, no lo que se va a cargar. Y reimportar CON Blender
tampoco sirve: PyNifly puede sustituir un esqueleto de referencia al importar y
devolver posiciones que no son las del archivo. Por eso esto lee los bytes.

QUE COMPRUEBA, Y CON QUE NUMERO ATRAS

Una REGLA reprueba y lleva atras el numero de archivos vanilla que la cumplen.
Una OBSERVACION se informa y no reprueba. La distincion importa porque el modo
de fallar de este repo es al reves del habitual: no que falten reglas, sino que
sobren inventadas.

  REGLA  bloques        mismos tipos y cantidades de bloque
  REGLA  nodos          mismo juego de nombres de nodo (el esqueleto)
  REGLA  posiciones     cada nodo comun, a <= 0,01 unidades
  REGLA  piezas         mismo juego de nombres de shape
  REGLA  huesos/pieza   cada pieza, con el mismo juego de huesos
  REGLA  body parts     cada pieza, con las mismas particiones de dismember

La tolerancia de 0,01 no es un numero elegido: `mundo()` redondea a dos
decimales y esa es la unidad mas chica que el lector distingue. Medido sobre
`actors/character/character assets/` --569 archivos sobre el mismo esqueleto
humano-- 2.108 de 2.112 comparaciones dan posicion IDENTICA y las 4 restantes
difieren en exactamente 0,010, que es el redondeo. Y medido sobre 1.166 pares
`_0.nif`/`_1.nif` (el mismo asset a peso 0 y a peso 100), 21.641 de 21.683
comparaciones son identicas; los 42 desacuerdos son TODOS `InvMarker`, el
marcador de camara del inventario, que no es un hueso.

La tolerancia esta muy por debajo de la senal que tiene que atrapar: ponerle a
`childbody.nif` el esqueleto de `frostgiant2.nif` mueve los 10 huesos
comparables, el que menos 57,34 unidades. Son 5.734 veces la tolerancia.

LO QUE **NO** COMPRUEBA, DECLARADO

"Cada hueso dentro de la caja de la pieza que lo usa" ESTA REFUTADO como regla
absoluta. Medido sobre el corpus: de 27.927 shapes skinneados, solo 6.719
(24,1 %) tienen TODOS sus huesos dentro de su propia caja, y de 114.751 pares
(pieza, hueso) solo el 64,8 % cae adentro. Escribirla habria reprobado a tres
de cada cuatro mallas vanilla.

Lo que si sirve es su forma RELATIVA --que la distancia del hueso a la caja no
crezca respecto del vanilla-- y para eso hace falta la geometria de la pieza,
que vive en el NiSkinPartition. Ese recorrido no esta en la skill a proposito
(ver censo_nif.py): esta en `census/parser_uv.py`, validado contra 42.243
particiones, y la comparacion de colocacion la hace
`fixtures/comparar.py --fiel <original.nif> <exportado.nif>`.

Tampoco compara UV ni capa de color por pieza. No estan medidos aca.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

import censo_nif  # noqa: E402

# Ver cabecera: es el redondeo de mundo(), no un umbral elegido.
TOLERANCIA = 0.01

# 42 de 42 desacuerdos entre `_0.nif` y `_1.nif` del mismo asset son este nodo,
# que es el marcador de camara del inventario y no mueve geometria. Se informa
# y no reprueba. La lista es explicita: si manana aparece otro nodo con la
# misma excusa, tiene que llegar aca con su medicion, no colarse por un patron.
NODOS_NO_HUESO = ("InvMarker",)


def _nombre_raiz(nif):
    """Nombre del nodo raiz, o None si el bloque 0 no es un nodo.

    Hace falta porque EL NOMBRE DE LA RAIZ ES EL NOMBRE DEL ARCHIVO. Medido
    sobre una muestra de 3.000 archivos del corpus: en 2.786 (92,9 %) el nodo
    raiz se llama igual que el .nif que lo contiene. Comparar el juego de
    nombres de nodo sin sacar la raiz es comparar nombres de archivo: sobre los
    1.216 pares `_0.nif`/`_1.nif` --el MISMO asset-- reprobaba 1.198, y en los
    LOD, que traen un solo nodo, los dos archivos quedaban sin ningun nodo en
    comun. La diferencia de nombre de la raiz se informa; lo que reprueba es
    que cambie su TIPO.
    """
    nodos = nif.nodos()
    return nodos[0]["nombre"] if 0 in nodos else None


# Las reglas que reprueban, enumeradas. Existe como constante y no solo en la
# cabecera para que el test pueda exigir que CADA UNA tenga un caso que la haga
# fallar. Agregar una regla sin ese caso es agregar una garantia que no se sabe
# si puede fallar -- el modo de error mas caro que tuvo este repo.
REGLAS = ("bloques", "raiz", "nodos", "posiciones", "piezas",
          "huesos/pieza", "body parts")


class Falla(object):
    def __init__(self, regla, detalle):
        if regla not in REGLAS:
            raise ValueError("regla no declarada en REGLAS: %r" % regla)
        self.regla = regla
        self.detalle = detalle

    def __str__(self):
        return "[FALLA] %-14s %s" % (self.regla, self.detalle)


class Nota(object):
    def __init__(self, tema, detalle):
        self.tema = tema
        self.detalle = detalle

    def __str__(self):
        return "[obs]   %-14s %s" % (self.tema, self.detalle)


def _desvio(a, b):
    """Peor diferencia por coordenada. Las tuplas son (x, y, z, escala)."""
    return max(abs(a[i] - b[i]) for i in range(3))


def comparar(ruta_nuevo, ruta_vanilla):
    """Devuelve (fallas, notas). Lista vacia de fallas = paso."""
    nuevo = censo_nif.Nif(ruta_nuevo)
    van = censo_nif.Nif(ruta_vanilla)
    fallas, notas = [], []

    # --- bloques -----------------------------------------------------------
    bn, bv = nuevo.cuenta_tipos(), van.cuenta_tipos()
    for tipo in sorted(set(bn) | set(bv)):
        if bn.get(tipo, 0) != bv.get(tipo, 0):
            fallas.append(Falla("bloques", "%s: nuevo %d, vanilla %d"
                                % (tipo, bn.get(tipo, 0), bv.get(tipo, 0))))

    # --- raiz ---------------------------------------------------------------
    rn, rv = _nombre_raiz(nuevo), _nombre_raiz(van)
    if nuevo.raiz() != van.raiz():
        fallas.append(Falla("raiz", "tipo %s, vanilla %s"
                            % (nuevo.raiz(), van.raiz())))
    if rn != rv:
        notas.append(Nota("raiz", "se llama %r y el vanilla %r (en el 92,9 %% "
                                  "del corpus la raiz lleva el nombre del "
                                  "archivo)" % (rn, rv)))

    # --- nodos y posiciones ------------------------------------------------
    mn, mv = nuevo.mundo(), van.mundo()
    # La raiz sale de la comparacion por nombre: ver _nombre_raiz.
    nn = set(mn) - {rn}
    nv = set(mv) - {rv}
    for nom in sorted(nv - nn):
        fallas.append(Falla("nodos", "falta el nodo %r" % nom))
    for nom in sorted(nn - nv):
        fallas.append(Falla("nodos", "sobra el nodo %r" % nom))

    comunes = sorted(nn & nv)
    hay_huesos = any(v["huesos"] for v in van.skin_por_shape().values())
    if not comunes and hay_huesos:
        # Cero nodos comparables no es exito. Es el mismo agujero que "cero
        # comprobaciones" en el autotest: sin nada que comparar, "0 desvios"
        # se imprime como un ok que no probo nada. Solo aplica si el vanilla
        # TIENE huesos: un estatico de un solo nodo no tiene nada que
        # comparar por diseno, y exigirselo seria inventar una regla.
        fallas.append(Falla(
            "posiciones",
            "el vanilla usa huesos y los dos archivos no comparten NI UN "
            "nodo: no hay nada que comparar, y eso no es pasar"))
    for nom in comunes:
        d = _desvio(mn[nom], mv[nom])
        de = abs(mn[nom][3] - mv[nom][3])
        if nom in NODOS_NO_HUESO:
            if d > TOLERANCIA or de > 1e-4:
                notas.append(Nota("no-hueso",
                                  "%s movido %.3f u / escala %.4f vs %.4f "
                                  "(en vanilla tambien se mueve: 42 de 42)"
                                  % (nom, d, mn[nom][3], mv[nom][3])))
            continue
        if d > TOLERANCIA:
            fallas.append(Falla("posiciones",
                                "%s desviado %.3f u  nuevo=%s vanilla=%s"
                                % (nom, d, mn[nom][:3], mv[nom][:3])))
        if de > 1e-4:
            fallas.append(Falla("posiciones",
                                "%s con escala %.4f, vanilla %.4f"
                                % (nom, mn[nom][3], mv[nom][3])))

    # --- piezas, huesos por pieza y particiones ----------------------------
    sn, sv = nuevo.skin_por_shape(), van.skin_por_shape()
    for nom in sorted(set(sv) - set(sn)):
        fallas.append(Falla("piezas", "falta la pieza %r" % nom))
    for nom in sorted(set(sn) - set(sv)):
        fallas.append(Falla("piezas", "sobra la pieza %r" % nom))

    for nom in sorted(set(sn) & set(sv)):
        hn, hv = sn[nom]["huesos"], sv[nom]["huesos"]
        # Perder un hueso NO da error en el juego: se pierde articulacion. Por
        # eso se comparan TODAS las piezas y no las que uno se acuerda que
        # tenian varios. steamcenturion.nif reparte 20 huesos entre 15 piezas:
        # doce usan uno solo, y el torso usa cuatro, dos de ellos parpados.
        for h in sorted(set(hv) - set(hn)):
            fallas.append(Falla("huesos/pieza",
                                "%s perdio el hueso %r" % (nom, h)))
        for h in sorted(set(hn) - set(hv)):
            fallas.append(Falla("huesos/pieza",
                                "%s gano el hueso %r" % (nom, h)))
        if sn[nom]["body_parts"] != sv[nom]["body_parts"]:
            fallas.append(Falla("body parts", "%s: nuevo %s, vanilla %s"
                                % (nom, sn[nom]["body_parts"],
                                   sv[nom]["body_parts"])))
        if sn[nom]["skin"] != sv[nom]["skin"]:
            fallas.append(Falla("body parts",
                                "%s: skin instance %s, vanilla %s"
                                % (nom, sn[nom]["skin"], sv[nom]["skin"])))

    # --- observaciones ------------------------------------------------------
    tn, tv = set(nuevo.texturas()), set(van.texturas())
    for t in sorted(tv - tn):
        notas.append(Nota("texturas",
                          "el vanilla referencia %r y el nuevo no" % t))
    for t in sorted(tn - tv):
        notas.append(Nota("texturas",
                          "el nuevo referencia %r y el vanilla no" % t))

    usados = set()
    for v in sn.values():
        usados.update(v["huesos"])
    if usados:
        sueltos = sorted(n for n in comunes
                         if n not in usados and n not in NODOS_NO_HUESO)
        if sueltos:
            notas.append(Nota("nodos", "%d nodo(s) que ninguna pieza usa: %s"
                              % (len(sueltos), ", ".join(sueltos[:6])
                                 + ("..." if len(sueltos) > 6 else ""))))
    return fallas, notas


# --- falsificacion ----------------------------------------------------------
#
# Un chequeo tiene que poder fallar. Si pasa siempre, no prueba nada.
#
# Estos cuatro casos son archivos vanilla reales, elegidos midiendo el corpus:
# se buscaron pares que COMPARTIERAN nombres de hueso para que haya algo que
# comparar. Un humano contra un dragon no sirve de control -- comparten CERO
# nombres, y el control no llega ni a mirar posiciones.
#
#   identidad   el archivo contra si mismo: 0 fallas. Sin esto, un control que
#               reprueba siempre tambien daria "revento" en los dos de abajo.
#   frostgiant  el esqueleto del gigante de escarcha: 10 huesos comparables,
#               los 10 mal, el que menos 57,34 unidades.
#   werebear    18 comparables, los 18 mal, el que menos 10,56.
#   manekin     EL PAR: el maniqui usa el MISMO esqueleto humano. 22 huesos
#               comparables, los 22 a 0,00. Reprueba por bloques y piezas
#               --es otra malla-- pero por posiciones NO. Sin este caso,
#               "revienta con el esqueleto equivocado" seria compatible con
#               "revienta con cualquier cosa".
FALSIFICACION = [
    ("actors/character/character assets/childbody.nif",
     "actors/character/character assets/childbody.nif",
     {"fallas": 0, "posiciones": 0}),
    ("actors/dlc01/frostgiant/frostgiant2.nif",
     "actors/character/character assets/childbody.nif",
     {"posiciones": 10}),
    ("actors/dlc02/werebear/werebear.nif",
     "actors/character/character assets/childbody.nif",
     {"posiciones": 18}),
    ("actors/manekin/manekin.nif",
     "actors/character/character assets/childbody.nif",
     {"posiciones": 0, "fallas_min": 1}),
]


def _buscar(raiz, rel):
    cola = rel.replace("/", os.sep).lower()
    for base, _d, archivos in os.walk(raiz):
        for f in archivos:
            ruta = os.path.join(base, f)
            if ruta.lower().endswith(cola):
                return ruta
    return None


def falsificar(raiz):
    """Corre los casos de FALSIFICACION contra el corpus. True si todos dan."""
    ok = mal = falta = 0
    for rel_n, rel_v, esperado in FALSIFICACION:
        a, b = _buscar(raiz, rel_n), _buscar(raiz, rel_v)
        if a is None or b is None:
            print("  [falta]  %s" % (rel_n if a is None else rel_v))
            falta += 1
            continue
        fallas, _notas = comparar(a, b)
        real = {"fallas": len(fallas),
                "posiciones": sum(1 for f in fallas
                                  if f.regla == "posiciones")}
        for campo, valor in esperado.items():
            if campo == "fallas_min":
                bien = real["fallas"] >= valor
                texto = "fallas >= %d" % valor
            else:
                bien = real[campo] == valor
                texto = "%s == %d" % (campo, valor)
            if bien:
                ok += 1
            else:
                mal += 1
                print("  [FALLA]  %s vs %s :: %s, obtenido %r"
                      % (os.path.basename(rel_n), os.path.basename(rel_v),
                         texto, real))
    print("")
    print("  %d comprobaciones ok, %d fallidas, %d archivos no encontrados"
          % (ok, mal, falta))
    if ok == 0:
        # Cero comprobaciones no es exito. Es la misma guarda que en el
        # autotest de censo_nif y de parser_uv, donde ya se colo una vez.
        print("  NO se comprobo NADA. Revisa la ruta del corpus.")
        return False
    if mal or falta:
        print("  La falsificacion NO cierra: el [ok] de este script no vale.")
        return False
    print("  Falsificado: el control revienta cuando tiene que reventar, y "
          "NO cuando no.")
    return True


def main():
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "--falsificar":
        return 0 if falsificar(a[1]) else 1
    if len(a) != 2:
        print(__doc__)
        return 2
    nuevo, vanilla = a
    for r in (nuevo, vanilla):
        if not os.path.exists(r):
            print("no existe: %s" % r)
            return 2
    fallas, notas = comparar(nuevo, vanilla)
    print("nuevo   : %s" % nuevo)
    print("vanilla : %s" % vanilla)
    print("")
    for n in notas:
        print("  %s" % n)
    for f in fallas:
        print("  %s" % f)
    print("")
    if fallas:
        print("  NO pasa: %d falla(s), %d observacion(es)"
              % (len(fallas), len(notas)))
        return 1
    print("  pasa: 0 fallas, %d observacion(es)" % len(notas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
