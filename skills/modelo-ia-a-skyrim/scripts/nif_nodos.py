# -*- coding: utf-8 -*-
"""Lee la jerarquia de NiNode de un NIF de Skyrim SE y da posiciones de mundo.

No usa Blender ni PyNifly: parsea el binario. Existe porque PyNifly, al
importar, puede sustituir un esqueleto de referencia y devolver posiciones que
no son las del archivo -- y eso no da error, solo numeros equivocados.

Layout de un NiNode en SSE (version 20.2.0.7, user 12, BS 100):
  NiObjectNET : name(uint32 indice de string)
                numExtraData(uint32) + refs(int32 c/u)
                controller(int32)
  NiAVObject  : flags(uint32)
                translation(3 float) rotation(9 float) scale(float)
                collisionObject(int32)
  NiNode      : numChildren(uint32) + refs(int32 c/u)
                numEffects(uint32) + refs

Solo se parsea hasta children, que es lo unico que hace falta.
"""
import math
import os
import struct
import sys

# BSFurnitureMarkerNode NO hereda de NiNode (BSFurnitureMarker <- NiExtraData).
# Incluirlo revienta al leer children: 123 archivos de muebles en el corpus.
# BSMasterParticleSystem: 93 archivos del corpus, todos con el tipo
# como RAIZ. El layout de NiNode parsea coherente en 93 de 93 bloques
# (1 hijo en 92, 2 en uno; cola de 14 a 30 bytes, que son sus campos
# propios). Lo contrario de BSFurnitureMarkerNode, que se saco de aca
# porque el sufijo enganaba y rompia 123 archivos de muebles.
# BSRangeNode: 0 bloques en el corpus. No lo ejercita nada; va en las
# tres listas para que no vuelvan a separarse.
TIPOS_NODO = {
    "NiNode", "BSFadeNode", "BSLeafAnimNode", "BSTreeNode",
    "BSOrderedNode", "BSValueNode", "BSMultiBoundNode",
    "BSBlastNode", "BSDamageStage", "BSRangeNode", "NiBillboardNode",
    "NiSwitchNode", "BSMasterParticleSystem",
}

def _sized(datos, i):
    (n,) = struct.unpack_from("<I", datos, i)
    return datos[i + 4:i + 4 + n].decode("cp1252", "replace"), i + 4 + n


def _short(datos, i):
    n = datos[i]
    return datos[i + 1:i + 1 + n].rstrip(b"\x00").decode("cp1252", "replace"), i + 1 + n


def leer(ruta):
    with open(ruta, "rb") as fh:
        datos = fh.read()
    i = datos.index(b"\n") + 1
    version, = struct.unpack_from("<I", datos, i); i += 4
    i += 1                                              # endian
    user, = struct.unpack_from("<I", datos, i); i += 4
    n_bloques, = struct.unpack_from("<I", datos, i); i += 4
    bs, = struct.unpack_from("<I", datos, i); i += 4
    if bs >= 130:
        # Este script leia el campo de proceso como SizedString EN EL MEDIO de
        # los tres shorts; los parsers del censo leian un cuarto ShortString
        # DESPUES. Las dos lecturas no pueden ser ambas correctas y ninguna esta
        # validada: el corpus tiene 22.393 archivos con BS=100, uno con BS=83 y
        # CERO con BS>=130. Elegir una a ojo corre todos los offsets de bloque.
        raise ValueError(
            "BS version %d (>=130, Fallout 4/76): la cabecera no esta validada "
            "contra ningun archivo del corpus" % bs)
    _a, i = _short(datos, i)
    _p, i = _short(datos, i)
    _e, i = _short(datos, i)

    n_tipos, = struct.unpack_from("<H", datos, i); i += 2
    tipos = []
    for _ in range(n_tipos):
        t, i = _sized(datos, i)
        tipos.append(t)
    idx = struct.unpack_from("<%dH" % n_bloques, datos, i); i += 2 * n_bloques
    tam = struct.unpack_from("<%dI" % n_bloques, datos, i); i += 4 * n_bloques
    n_str, = struct.unpack_from("<I", datos, i); i += 4
    i += 4
    strings = []
    for _ in range(n_str):
        s, i = _sized(datos, i)
        strings.append(s)
    n_grupos, = struct.unpack_from("<I", datos, i); i += 4
    i += 4 * n_grupos

    # --- offsets de cada bloque ---
    base = i
    offs, o = [], base
    for t in tam:
        offs.append(o)
        o += t

    nodos = {}
    for b in range(n_bloques):
        tipo = tipos[idx[b]]
        if tipo not in TIPOS_NODO:
            continue
        p = offs[b]
        nombre_i, = struct.unpack_from("<i", datos, p); p += 4
        n_ed, = struct.unpack_from("<I", datos, p); p += 4 + 4 * n_ed
        p += 4                                          # controller
        p += 4                                          # flags
        tr = struct.unpack_from("<3f", datos, p); p += 12
        rot = struct.unpack_from("<9f", datos, p); p += 36
        esc, = struct.unpack_from("<f", datos, p); p += 4
        p += 4                                          # collision
        n_hijos, = struct.unpack_from("<I", datos, p); p += 4
        hijos = struct.unpack_from("<%di" % n_hijos, datos, p) if n_hijos else ()
        nodos[b] = {
            "tipo": tipo,
            "nombre": strings[nombre_i] if 0 <= nombre_i < len(strings) else "?",
            "tr": tr, "rot": rot, "esc": esc,
            "hijos": [h for h in hijos if h >= 0],
        }
    # La tabla de bloques va en el resultado porque el que quiera leer algo
    # que este lector no decodifica --la colision bhk*, por ejemplo-- no tiene
    # otra forma de ubicarlo, y escribir un SEGUNDO parser de cabecera para
    # eso es como se separan dos lectores del mismo formato.
    bloques = [(tipos[idx[b]], offs[b], tam[b]) for b in range(n_bloques)]
    return {"archivo": os.path.basename(ruta), "version": "0x%08X" % version,
            "bs": bs, "n_bloques": n_bloques, "nodos": nodos,
            "bloques": bloques, "datos": datos, "strings": strings}


def cadena_extra(nif, nombre):
    """El valor del NiStringExtraData llamado `nombre`, o None si no hay.

    En SSE un NiStringExtraData son dos indices (i32) a la tabla de strings:
    el nombre y el valor. Asi se lee el `Prn` de un arma -- el nodo del
    esqueleto del que cuelga envainada--. Se compara el NOMBRE: el primer
    NiStringExtraData que aparezca no es necesariamente el que se busca."""
    s = nif["strings"]
    for tipo, off, tam in nif["bloques"]:
        if tipo != "NiStringExtraData" or tam < 8:
            continue
        nom, val = struct.unpack_from("<ii", nif["datos"], off)
        if 0 <= nom < len(s) and s[nom] == nombre:
            return s[val] if 0 <= val < len(s) else None
    return None


def mundo(nif):
    """Acumula transformadas desde la raiz. Devuelve {nombre: (x,y,z,escala)}.

    Lleva `vistos` y se queda con el PRIMER nodo que ve para cada nombre, igual
    que matrices() y que censo_nif. Antes no lo hacia, y ante un nombre
    repetido las dos funciones de ESTE MISMO archivo daban respuestas
    distintas: con dos nodos "Dup" en (10,0,0) y (0,0,99), mundo() devolvia el
    segundo y matrices() el primero. En el corpus no se manifestaba porque los
    2,49 % de archivos con nombre repetido lo repiten en InvMarker, con la
    misma transformada -- que es justo el caso en que un desacuerdo no se ve.
    """
    nodos = nif["nodos"]
    hijos_de_alguien = {h for n in nodos.values() for h in n["hijos"]}
    raices = [b for b in nodos if b not in hijos_de_alguien]
    fuera, prof = {}, {}
    vistos = set()

    def mul(Ma, ta, sa, Mb, tb, sb):
        """(Ma,ta,sa) padre compuesto con (Mb,tb,sb) hijo."""
        M = [sum(Ma[r * 3 + k] * Mb[k * 3 + c] for k in range(3))
             for r in range(3) for c in range(3)]
        t = tuple(ta[r] + sa * sum(Ma[r * 3 + k] * tb[k] for k in range(3))
                  for r in range(3))
        return M, t, sa * sb

    def bajar(b, M, t, s, d):
        if b in vistos:
            return
        vistos.add(b)
        n = nodos[b]
        M2, t2, s2 = mul(M, t, s, n["rot"], n["tr"], n["esc"])
        fuera.setdefault(n["nombre"], (round(t2[0], 2), round(t2[1], 2),
                                       round(t2[2], 2), round(s2, 4)))
        prof.setdefault(n["nombre"], d)
        for h in n["hijos"]:
            if h in nodos:
                bajar(h, M2, t2, s2, d + 1)

    I = [1, 0, 0, 0, 1, 0, 0, 0, 1]
    for r in raices:
        bajar(r, I, (0.0, 0.0, 0.0), 1.0, 0)
    return fuera, prof


def matrices(nif):
    """{nombre: M} con M = [[r00,r01,r02,tx],[...],[...]] en espacio de mundo.

    mundo() da solo posiciones, que alcanza para comparar esqueletos. Para
    colgar un asset de un nodo hacen falta los EJES: el motor dibuja la malla
    en el espacio local del nodo de anclaje, y ese nodo tiene rotacion propia.
    """
    nodos = nif["nodos"]
    hijos_de_alguien = {h for n in nodos.values() for h in n["hijos"]}
    fuera = {}

    def mul(A, B):
        M = [[0.0] * 4 for _ in range(3)]
        for f in range(3):
            for c in range(3):
                M[f][c] = sum(A[f][k] * B[k][c] for k in range(3))
            M[f][3] = sum(A[f][k] * B[k][3] for k in range(3)) + A[f][3]
        return M

    def local(n):
        M = [[0.0] * 4 for _ in range(3)]
        for f in range(3):
            for c in range(3):
                M[f][c] = n["rot"][f * 3 + c] * n["esc"]
            M[f][3] = n["tr"][f]
        return M

    vistos = set()

    def bajar(b, M):
        if b in vistos:
            return
        vistos.add(b)
        n = nodos[b]
        M2 = mul(M, local(n))
        fuera.setdefault(n["nombre"], M2)
        for h in n["hijos"]:
            if h in nodos:
                bajar(h, M2)

    I = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]]
    for r in [b for b in nodos if b not in hijos_de_alguien]:
        bajar(r, I)
    return fuera


def _invertir(M):
    """Inversa de una matriz de rotacion-con-escala-uniforme mas traslacion.

    Se asume escala uniforme, que es lo que trae un esqueleto. La comprobacion
    va en el autotest: si la columna no tiene la misma norma, la inversa es
    otra cosa y el resultado seria plausible y falso.
    """
    e2 = sum(M[f][0] ** 2 for f in range(3))
    if e2 == 0.0:
        raise ValueError("matriz degenerada: escala 0")
    inv = [[0.0] * 4 for _ in range(3)]
    for f in range(3):
        for c in range(3):
            inv[f][c] = M[c][f] / e2
    for f in range(3):
        inv[f][3] = -sum(inv[f][k] * M[k][3] for k in range(3))
    return inv


def _aplicar(M, p):
    return tuple(sum(M[f][c] * p[c] for c in range(3)) + M[f][3]
                 for f in range(3))


# Por debajo de esta norma, el +Z del mundo es casi perpendicular al plano XY
# local y el angulo no significa nada: atan2(0, 0) devuelve 0,0 y se imprime
# como si fuera una medida. Medido sobre los 116 marcos de anclaje de los 64
# esqueletos del corpus: 4 caen en 0,0000 --el SHIELD, el QUIVER y el
# WeaponBow del dwarvenballistacenturion, mas el SHIELD del troll en 0,0297--
# y el siguiente mas chico esta en 0,7635. El umbral no es un juicio: entre
# 0,03 y 0,76 el corpus no tiene NADA.
MINIMO_PROYECCION = 0.10


def angulo_de_arriba(M):
    """(grados, arriba, norma_xy) del +Z del mundo en el plano XY local de M.

    Es LA medida que hay que tomar antes de modelar un asset que se cuelga de
    un nodo: el motor dibuja la malla en el espacio local del nodo, y si el
    nodo esta girado, modelar con el arriba en +Y (90 grados) saca el asset
    girado esa diferencia en el juego y perfecto en Blender.

    `norma_xy` viene con el angulo y no se puede ignorar: cuando es chica, el
    arriba del mundo apunta casi a lo largo del eje Z local y NO hay angulo
    que compensar en ese plano. Devolver solo los grados imprimia "0,0" --que
    parece una medida-- para cuatro nodos reales del juego.
    """
    inv = _invertir(M)
    arriba = tuple(sum(inv[f][c] * (0.0, 0.0, 1.0)[c] for c in range(3))
                   for f in range(3))
    norma = math.hypot(arriba[0], arriba[1])
    ang = math.degrees(math.atan2(arriba[1], arriba[0])) % 360.0
    return ang, arriba, norma


def relativo_a(nif, base, nombres):
    """Imprime el marco de `base` y donde caen `nombres` dentro de el."""
    M = matrices(nif)
    if base not in M:
        print("NO encontrado el nodo base: %s" % base)
        return 1
    Mb = M[base]
    ang, arriba, norma = angulo_de_arriba(Mb)
    print("base %s  pos mundo=(%.2f,%.2f,%.2f)"
          % (base, Mb[0][3], Mb[1][3], Mb[2][3]))
    print("  el +Z del mundo, en local de %s: (%.3f,%.3f,%.3f)"
          % ((base,) + arriba))
    if norma < MINIMO_PROYECCION:
        print("  el arriba del mundo cae casi sobre el eje Z LOCAL "
              "(proyeccion en XY = %.4f): NO hay angulo que compensar en ese "
              "plano. Cuatro nodos reales del juego estan asi." % norma)
    else:
        print("  ARRIBA esta a %.1f grados en el plano XY local (proyeccion "
              "%.3f). +Y seria 90: la diferencia es lo que hay que girar al "
              "modelar." % (ang, norma))
    inv = _invertir(Mb)
    for nombre in nombres:
        if nombre not in M:
            print("  NO encontrado: %s" % nombre)
            continue
        Mn = M[nombre]
        p = _aplicar(inv, (Mn[0][3], Mn[1][3], Mn[2][3]))
        print("  %-26s local=(%8.2f,%8.2f,%8.2f)" % ((nombre,) + p))
    return 0


# Medido con este mismo lector sobre el esqueleto humano vanilla. Cada entrada
# se abrio antes de escribir el codigo: son las respuestas que ya se conocian.
# Sin esta tabla, --relativo-a imprime numeros plausibles y nadie sabe si el
# marco esta bien compuesto.
AUTOTEST = [
    ("actors/character/character assets/skeleton.nif", {
        "n_nodos": 99,
        # El dato que cambia como se modela un asset: NINGUN nodo de anclaje
        # mira al +Y. Medido sobre los 116 marcos de anclaje de los 64
        # esqueletos del corpus, cero caen a menos de 5 grados de 90.
        "angulos": {"SHIELD": 155.7, "WeaponSword": 306.8,
                    "WeaponBack": 249.1, "QUIVER": 294.3},
        # Por donde pasa el brazo DENTRO del marco del escudo: a lo largo del
        # -X local, no del -Y. Es la medida que faltaba cuando las correas se
        # subieron en Z y siguieron sin tocar el antebrazo.
        "locales": {"SHIELD|NPC L Forearm [LLar]": (-22.0, 0.3, 7.2),
                    "SHIELD|NPC L Hand [LHnd]": (-7.6, 0.0, 0.2)},
    }),
    ("actors/character/character assets/skeletonbeast.nif", {
        # El de bestia comparte los marcos de anclaje con el humano: los
        # mismos tres angulos, sobre 104 nodos en vez de 99. Sin este segundo
        # archivo, "155,7" seria un numero de un solo esqueleto.
        "n_nodos": 104,
        "angulos": {"SHIELD": 155.7, "WeaponSword": 306.8,
                    "WeaponBack": 249.1},
        "locales": {"SHIELD|NPC L Forearm [LLar]": (-22.0, 0.3, 7.2)},
    }),
    ("actors/dwarvenspherecenturion/character assets/skeleton.nif", {
        # El contraejemplo, y por eso esta: aca el SHIELD esta a 95,7, no a
        # 155,7. El angulo NO es una constante del juego -- es del esqueleto
        # que tengas enfrente, y hay que medirlo.
        "angulos": {"SHIELD": 95.7},
    }),
    ("actors/dlc02/dwarvenballistacenturion/character assets/skeleton.nif", {
        # El caso donde el angulo NO SIGNIFICA NADA: el arriba del mundo cae
        # sobre el eje Z local y la proyeccion en XY es 0,0000. Sin esta
        # entrada, el lector imprimia "0,0 grados" como si fuera una medida.
        "degenerados": ("SHIELD", "QUIVER", "WeaponBow"),
    }),
]


def autotest(raiz):
    """Reproduce los valores medidos. Cero comprobaciones NO es exito."""
    ok = fallo = falta = 0
    for rel, esperado in AUTOTEST:
        ruta = _buscar(raiz, rel)
        if ruta is None:
            print("  [falta]  %s" % rel)
            falta += 1
            continue
        try:
            M = matrices(leer(ruta))
        except Exception as e:
            fallo += 1
            print("  [ilegible] %s :: %s" % (rel, type(e).__name__))
            continue
        real = {"n_nodos": len(M)}
        for nodo, grados in esperado.get("angulos", {}).items():
            if nodo not in M:
                real["ang:" + nodo] = None
                continue
            real["ang:" + nodo] = round(angulo_de_arriba(M[nodo])[0], 1)
        for nodo in esperado.get("degenerados", ()):
            if nodo not in M:
                real["deg:" + nodo] = None
                continue
            real["deg:" + nodo] = (angulo_de_arriba(M[nodo])[2]
                                   < MINIMO_PROYECCION)
        for nodo, pos in esperado.get("locales", {}).items():
            base, destino = nodo.split("|")
            if base not in M or destino not in M:
                real["loc:" + nodo] = None
                continue
            p = _aplicar(_invertir(M[base]),
                         (M[destino][0][3], M[destino][1][3],
                          M[destino][2][3]))
            real["loc:" + nodo] = tuple(round(v, 1) for v in p)
        plano = {"n_nodos": esperado.get("n_nodos")}
        plano.update({"ang:" + k: v
                      for k, v in esperado.get("angulos", {}).items()})
        plano.update({"loc:" + k: tuple(v)
                      for k, v in esperado.get("locales", {}).items()})
        plano.update({"deg:" + k: True
                      for k in esperado.get("degenerados", ())})
        for campo, valor in plano.items():
            if valor is None:
                continue
            if campo not in real:
                fallo += 1
                print("  [FALLA]  %s :: campo desconocido %r" % (rel, campo))
                continue
            if real[campo] == valor:
                ok += 1
            else:
                fallo += 1
                print("  [FALLA]  %s :: %s" % (os.path.basename(rel), campo))
                print("           esperado %r" % (valor,))
                print("           obtenido %r" % (real[campo],))
    print("")
    print("  %d comprobaciones ok, %d fallidas, %d archivos no encontrados"
          % (ok, fallo, falta))
    if ok == 0:
        print("  NO se comprobo NADA. Revisa la ruta del corpus.")
        return False
    if fallo or falta:
        print("  El lector NO reproduce lo medido.")
        return False
    print("  Lector validado.")
    return True


def _buscar(raiz, rel):
    cola = rel.replace("/", os.sep).lower()
    directa = os.path.join(raiz, rel.replace("/", os.sep))
    if os.path.exists(directa):
        return directa
    encontrados = []
    for base, _d, archivos in os.walk(raiz):
        for f in archivos:
            ruta = os.path.join(base, f)
            if ruta.lower().endswith(cola):
                encontrados.append(ruta)
    if len(encontrados) > 1:
        raise SystemExit(
            "AMBIGUO: %d archivos terminan en %s.\n%s\n"
            "Apunta --autotest a la carpeta donde BAE extrajo el vanilla, no "
            "a un proyecto que tenga copias." % (
                len(encontrados), rel,
                "\n".join("  " + e for e in encontrados)))
    return encontrados[0] if encontrados else None


def _leer_o_avisar(ruta):
    """El NIF, o None con una linea que se entiende.

    Un archivo que no existe salia por FileNotFoundError y uno que no es un
    NIF por "ValueError: subsection not found". No poder leer un archivo no es
    un detalle de implementacion: es el resultado.
    """
    try:
        return leer(ruta)
    except Exception as e:
        print("no se pudo leer %s: %s: %s"
              % (ruta, type(e).__name__, str(e)[:100]))
        return None


def main():
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "--autotest":
        return 0 if autotest(a[1]) else 1
    if len(a) >= 3 and a[1] == "--relativo-a":
        nif = _leer_o_avisar(a[0])
        return 1 if nif is None else relativo_a(nif, a[2], a[3:])
    if not a:
        print(__doc__)
        return 2
    return _volcar(a)


def _volcar(rutas):
    malos = 0
    for ruta in rutas:
        nif = _leer_o_avisar(ruta)
        if nif is None:
            malos += 1
            continue
        pos, prof = mundo(nif)
        print("=== %s  (bloques=%d, BS=%d, nodos=%d)" % (
            nif["archivo"], nif["n_bloques"], nif["bs"], len(pos)))
        for nom, p in sorted(pos.items(), key=lambda kv: -kv[1][2]):
            print("   %s%-28s %9.2f %9.2f %9.2f  esc=%.3f" % (
                "  " * prof[nom], nom, p[0], p[1], p[2], p[3]))
        print()
    return 1 if malos else 0


if __name__ == "__main__":
    raise SystemExit(main())
