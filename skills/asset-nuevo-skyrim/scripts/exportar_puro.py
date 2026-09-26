# -*- coding: utf-8 -*-
"""Lo del export del NIF de un asset nuevo que NO necesita Blender, para CI.

    python exportar_puro.py --autotest

`exportar_nif.py` corre adentro de Blender (usa el PyNifly del addon). Lo que
se puede separar vive aca, en Python puro --esta skill no depende de nada
fuera de la biblioteca estandar--, con autotest:

  validar_plan       los problemas del plan, todos juntos
  soldar             un vertice por (posicion, UV, normal), la V invertida
                     (el NIF la guarda al reves que Blender y el OBJ,
                     trampa 29 de modelo-ia-a-skyrim) y el tope de 65.535
                     vertices del BSTriShape
  caja_colision      semiejes y centro en unidades de Havok (69,99 por
                     unidad: census/parser_colision.py) y el radio de la
                     REGLA de colision_caja.py
  inercia_escalada   la del donante, reescalada por la formula de la caja.
                     HEURISTICA declarada: el corpus no tiene formula para el
                     valor (la razon contra m(a2+b2)/12 va de 1,2 a 471). Lo
                     que si se exige es la REGLA masa > 0 <=> inercia > 0
  conciliar_flags    la receta copiada de una pieza vanilla, sin los bits que
                     dependen de la geometria de ESA pieza
  texturas_pieza     las del asset salen del plan; de la receta, solo el
                     cubemap (ranura EnvMap)
  modo_alfa          como es transparente la receta: opaca, testing, o
                     blending con el alfa en los colores de vertice o en la
                     textura (con el censo que dice que no hace falta un
                     BSOrderedNode)
  validar_alfa_vertice  el alfa por vertice tiene que variar (trampa 16)

EL ENFOQUE DONANTE, PARA UN ASSET NUEVO
---------------------------------------
Tres proyectos llegaron a lo mismo por separado (la espada de vidrio, el
hacha de una mano, el arco): no se inventa la estructura del NIF, se copia de
un vanilla de la misma clase --el DONANTE--: `Prn`, `BSXFlags`, `BSInvMarker`,
los 63 campos del cuerpo rigido y el material de la colision. Y la receta del
shader de cada pieza se copia de una pieza vanilla que se vea como ella: el
metal dorado de la espada de vidrio, el brillo de una pieza con Glow Shader.
Ninguna pieza vanilla combina mapa de entorno y mapa de brillo, asi que un
asset con metal y partes que brillan son DOS piezas.
"""
import math
import sys

try:
    import colision_caja
except ImportError:                     # al importarlo desde otra carpeta
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import colision_caja

HAVOK = 69.99            # unidades del juego por unidad de Havok (medido)
MAX_VERTICES = 65535     # indices de 16 bits del BSTriShape

# Bits de ShaderFlags1/2, los de nifdefs de PyNifly (exportar_nif.py compara
# estos numeros contra los del addon antes de usarlos).
SF1_SKINNED = 0x2
SF1_VERTEX_ALPHA = 0x8
SF1_MODEL_SPACE_NORMALS = 0x1000
SF2_VERTEX_COLORS = 0x20

# Ranuras con los mapas PROPIOS del asset: salen del plan, nunca de la receta
# (copiarlas pondria la textura de la pieza vanilla sobre el asset nuevo).
RANURAS_ASSET = ("Diffuse", "Normal", "Glow", "HeightMap", "EnvMask",
                 "InnerLayer", "Specular")
# Ranuras COMPARTIDAS con el vanilla: el cubemap se copia de la receta.
RANURAS_RECETA = ("EnvMap",)
RANURAS = RANURAS_ASSET + RANURAS_RECETA

# Campos del shader que NO son receta: identificadores del archivo y del
# buffer, que PyNifly asigna al escribir.
NO_RECETA = ("bufSize", "bufType", "nameID", "controllerID", "extraDataCount",
             "textureSetID", "rootMaterialNameID", "bBSLightingShaderProperty",
             "bslspShaderType")

TIPO_GLOW = 2            # Shader_Type "Glow Shader"

_CLAVES = {"donante", "marcador", "salida", "raiz", "piezas", "colision"}
_CLAVES_PIEZA = {"objeto", "shape", "receta", "texturas"}


class ExportError(ValueError):
    pass


def _es_nif(x):
    return isinstance(x, str) and x.lower().endswith(".nif")


def validar_plan(plan):
    """Lista de problemas (vacia = sirve), todos de una vez."""
    if not isinstance(plan, dict):
        return ["el plan no es un objeto JSON"]
    p = ["clave desconocida en el plan: %r" % k for k in sorted(set(plan) - _CLAVES)]
    for k in ("donante", "salida"):
        if not _es_nif(plan.get(k)):
            p.append("%s: tiene que ser la ruta de un .nif" % k)
    if "marcador" in plan and not _es_nif(plan["marcador"]):
        p.append("marcador: la ruta de un .nif de la clase que traiga BSInvMarker")
    if _es_nif(plan.get("donante")) and plan.get("donante") == plan.get("salida"):
        p.append("salida: es el mismo archivo que el donante")
    if not (isinstance(plan.get("raiz"), str) and plan["raiz"].strip()):
        p.append("raiz: el nombre del nodo raiz")
    piezas = plan.get("piezas")
    if not (isinstance(piezas, list) and piezas):
        p.append("piezas: una lista con al menos una pieza")
        piezas = []
    objetos, shapes = [], []
    for i, pz in enumerate(piezas):
        donde = "piezas[%d]" % i
        if not isinstance(pz, dict):
            p.append("%s: no es un objeto" % donde)
            continue
        for k in sorted(set(pz) - _CLAVES_PIEZA):
            p.append("%s: clave desconocida %r" % (donde, k))
        for k in ("objeto", "shape"):
            if not (isinstance(pz.get(k), str) and pz[k].strip()):
                p.append("%s.%s: un nombre" % (donde, k))
        objetos.append(pz.get("objeto"))
        shapes.append(pz.get("shape"))
        rc = pz.get("receta")
        if not (isinstance(rc, dict) and isinstance(rc.get("shape"), str)
                and set(rc) <= {"nif", "shape"}
                and ("nif" not in rc or _es_nif(rc["nif"]))):
            p.append('%s.receta: {"shape": "Pieza:1"} de la pieza vanilla que '
                     'se ve como esta, con "nif" si no es del donante' % donde)
        tx = pz.get("texturas")
        if not isinstance(tx, dict):
            p.append("%s.texturas: {ranura: ruta}" % donde)
            continue
        for r in sorted(set(tx) - set(RANURAS)):
            p.append("%s.texturas: %r no es una ranura (%s)"
                     % (donde, r, ", ".join(RANURAS)))
        for r in ("Diffuse", "Normal"):
            if not (isinstance(tx.get(r), str) and tx[r].strip()):
                p.append("%s.texturas: falta %s" % (donde, r))
        for r, ruta in tx.items():
            if isinstance(ruta, str) and "/" in ruta:
                p.append("%s.texturas.%s: con barras invertidas, como las "
                         "rutas del juego (%r)" % (donde, r, ruta))
    for nombre, lista in (("objeto", objetos), ("shape", shapes)):
        repetidos = sorted({x for x in lista if x and lista.count(x) > 1})
        if repetidos:
            p.append("piezas: %s repetido: %s" % (nombre, repetidos))
    col = plan.get("colision")
    if col is not None:
        if not (isinstance(col, dict) and set(col) == {"objetos"}
                and isinstance(col["objetos"], list) and col["objetos"]):
            p.append('colision: {"objetos": ["Metal"]}: de que piezas sale la caja')
        else:
            for o in col["objetos"]:
                if o not in objetos:
                    p.append("colision: %r no es el objeto de ninguna pieza" % (o,))
    return p


def soldar(esquinas, dec_pos=4, dec_uv=5, dec_normal=3, dec_color=3):
    """(verts, uvs, normales, tris, colores) desde las esquinas.

    `esquinas`: [(pos, uv, normal)] --o [(pos, uv, normal, rgba)] con color
    por vertice-- de a tres por triangulo, como las da Blender (uv con el
    origen abajo). Un vertice por combinacion distinta: pegar lo que la
    textura, la luz o el alfa separan rompe la costura. La V sale INVERTIDA:
    el NIF tiene el origen arriba (trampa 29). `colores` es None sin color."""
    if len(esquinas) % 3:
        raise ExportError("%d esquinas: no son triangulos" % len(esquinas))
    con_color = bool(esquinas) and len(esquinas[0]) == 4
    if any((len(e) == 4) != con_color for e in esquinas):
        raise ExportError("unas esquinas traen color y otras no")
    indice, verts, uvs, normales, tris, colores = {}, [], [], [], [], []
    tri = []
    for e in esquinas:
        pos, uv, nor = e[0], e[1], e[2]
        clave = (tuple(round(c, dec_pos) for c in pos),
                 tuple(round(c, dec_uv) for c in uv),
                 tuple(round(c, dec_normal) for c in nor),
                 tuple(round(c, dec_color) for c in e[3]) if con_color else ())
        k = indice.get(clave)
        if k is None:
            k = len(verts)
            if k >= MAX_VERTICES:
                raise ExportError(
                    "mas de %d vertices soldados: el BSTriShape usa indices de "
                    "16 bits. Pasarlo no da error al escribir, da un NIF que el "
                    "juego no lee" % MAX_VERTICES)
            indice[clave] = k
            verts.append(tuple(float(c) for c in pos))
            uvs.append((float(uv[0]), 1.0 - float(uv[1])))
            normales.append(tuple(float(c) for c in nor))
            if con_color:
                colores.append(tuple(float(c) for c in e[3]))
        tri.append(k)
        if len(tri) == 3:
            tris.append(tuple(tri))
            tri = []
    return verts, uvs, normales, tris, (colores if con_color else None)


# NiAlphaProperty.flags: bit 0 = blending, bit 9 = testing (trampa 14).
ALFA_BLENDING = 0x1
ALFA_TESTING = 0x200
VARIACION_MINIMA = 0.01


def modo_alfa(alfa, f1):
    """Como es transparente la receta: "opaco" (sin NiAlphaProperty),
    "testing" (recorta, no transparenta), "blending_vertice" (el alfa sale de
    los colores de vertice: VERTEX_ALPHA) o "blending_textura" (sale del alfa
    del difuso).

    [MEASURED] armaduras y armas vanilla, 2.148 NIF: 262 piezas Lighting con
    blending, 59 con VERTEX_ALPHA y alfa que varia, 203 con el alfa en la
    textura; 234 cuelgan de la raiz, 28 de un NiNode, NINGUNA de un
    BSOrderedNode (el unico de esas carpetas, en el escudo enano de cristal
    de Dawnguard en primera persona, no tiene hijos)."""
    if alfa is None:
        return "opaco"
    flags = alfa[0]
    if not flags & ALFA_BLENDING:
        return "testing" if flags & ALFA_TESTING else "opaco"
    return "blending_vertice" if f1 & SF1_VERTEX_ALPHA else "blending_textura"


def validar_alfa_vertice(alfas):
    """(minimo, maximo) del alfa por vertice. Uniforme es un error: un panel
    con el alfa parejo se ve opaco aunque la NiAlphaProperty este bien
    (trampa 16), y sin la capa, el alfa vale 0 y la pieza es invisible."""
    if not alfas:
        raise ExportError("no hay alfa por vertice")
    lo, hi = min(alfas), max(alfas)
    if hi - lo <= VARIACION_MINIMA:
        raise ExportError("el alfa por vertice es uniforme (%.3f): el panel se "
                          "veria opaco (trampa 16)" % lo)
    return lo, hi


def caja_colision(puntos):
    """{"semi", "centro", "radio"} en unidades de Havok, de la caja de los
    puntos (unidades del juego). El radio es el de la REGLA de
    colision_caja.py: min(semieje menor, 0,1)."""
    if not puntos:
        raise ExportError("no hay vertices para la caja de colision")
    lo = [min(p[i] for p in puntos) for i in range(3)]
    hi = [max(p[i] for p in puntos) for i in range(3)]
    semi = [(hi[i] - lo[i]) / 2.0 / HAVOK for i in range(3)]
    if min(semi) <= 0:
        raise ExportError("la caja de colision es plana (semiejes %s): una pieza "
                          "sin espesor no hace caja" % [round(s, 5) for s in semi])
    centro = [(hi[i] + lo[i]) / 2.0 / HAVOK for i in range(3)]
    return {"semi": semi, "centro": centro,
            "radio": colision_caja.radio_esperado(semi)}


def inercia_escalada(inercia_donante, masa_donante, lados_donante, lados_nuevos):
    """La matriz de inercia (12 floats, 3x4 por filas) del donante, con la
    diagonal reescalada por (a2 + b2) de la caja nueva sobre la del donante.

    HEURISTICA: el corpus no tiene formula para el valor. Lo que el corpus SI
    respalda, y aca se exige: masa > 0 <=> diagonal > 0 (colision_caja.py,
    1.194 de 1.194). Un donante que la viola no sirve de donante."""
    diag = [inercia_donante[i] for i in (0, 5, 10)]
    if masa_donante > 0 and max(diag) <= 0:
        raise ExportError("el donante tiene masa %.3f y la diagonal de inercia "
                          "en cero: viola la REGLA inercia, no sirve de donante"
                          % masa_donante)
    nueva = [float(x) for x in inercia_donante]
    if masa_donante <= 0:
        return [0.0] * 12
    for k, (a, b) in ((0, (1, 2)), (5, (0, 2)), (10, (0, 1))):
        den = lados_donante[a] ** 2 + lados_donante[b] ** 2
        num = lados_nuevos[a] ** 2 + lados_nuevos[b] ** 2
        if den <= 1e-12:
            raise ExportError("el donante no tiene tamano en los ejes %d y %d"
                              % (a, b))
        nueva[k] = inercia_donante[k] * num / den
    return nueva


def conciliar_flags(f1, f2, colores=False):
    """(f1, f2, cambios): los flags de la receta sin lo que depende de la
    geometria de la pieza vanilla. Una pieza nueva estatica no esta
    skinneada ni usa normales en espacio de modelo; y sin colores de vertice
    no hay alfa de vertice ni flag de colores."""
    cambios = []

    def apagar(f, bit, nombre):
        if f & bit:
            cambios.append("se apago %s" % nombre)
        return f & ~bit

    f1 = apagar(f1, SF1_SKINNED, "SKINNED")
    f1 = apagar(f1, SF1_MODEL_SPACE_NORMALS, "MODEL_SPACE_NORMALS")
    if colores:
        if not f2 & SF2_VERTEX_COLORS:
            cambios.append("se prendio VERTEX_COLORS")
        f2 |= SF2_VERTEX_COLORS
    else:
        f1 = apagar(f1, SF1_VERTEX_ALPHA, "VERTEX_ALPHA")
        f2 = apagar(f2, SF2_VERTEX_COLORS, "VERTEX_COLORS")
    return f1, f2, cambios


def texturas_pieza(receta, plan, tipo):
    """({ranura: ruta}, notas). Del plan, las propias; de la receta, solo las
    de RANURAS_RECETA (el cubemap) que el plan no pise. Una pieza con Glow
    Shader sin mapa de brillo es un error: el tipo y el flag GLOW_MAP van
    juntos (material_arma.py) y leerian una ranura vacia."""
    out = {r: v for r, v in plan.items() if v}
    notas = []
    for r in RANURAS_RECETA:
        if r not in out and receta.get(r):
            out[r] = receta[r]
    descartadas = sorted(r for r in RANURAS_ASSET
                         if receta.get(r) and r not in plan)
    if descartadas:
        notas.append("de la receta no se copian %s: son los mapas de la pieza "
                     "vanilla" % ", ".join(descartadas))
    if tipo == TIPO_GLOW and not out.get("Glow"):
        raise ExportError("la receta es Glow Shader y el plan no da la ranura "
                          "Glow: el brillo leeria una ranura vacia")
    return out, notas


# --------------------------------------------------------------------------
# autotest
# --------------------------------------------------------------------------
def autotest():
    fallas = []
    hechas = [0]

    def exigir(cond, texto):
        hechas[0] += 1
        if not cond:
            fallas.append(texto)

    def falla_con(fn, args, trozo, que):
        try:
            fn(*args)
        except ExportError as e:
            exigir(trozo in str(e), "%s: el error no dice %r: %s" % (que, trozo, e))
        else:
            exigir(False, "%s no fallo" % que)

    # --- soldar ---
    a, b, c = (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    d = (1.0, 1.0, 0.0)
    n = (0.0, 0.0, 1.0)
    quad = [(a, (0, 0), n), (b, (1, 0), n), (c, (0, 1), n),
            (b, (1, 0), n), (d, (1, 1), n), (c, (0, 1), n)]
    v, uv, nr, t, col = soldar(quad)
    exigir(len(v) == 4 and len(t) == 2 and col is None,
           "soldar: un quad son 4 vertices y 2 triangulos, sin color; salio "
           "%d, %d y %r" % (len(v), len(t), col))
    exigir(uv[0] == (0.0, 1.0) and uv[2] == (0.0, 0.0),
           "soldar: la V no salio invertida: %r" % uv[:3])
    costura = list(quad)
    costura[3] = (b, (0.5, 0), n)          # misma posicion, otra UV: costura
    v, _uv, _nr, t, _c = soldar(costura)
    exigir(len(v) == 5, "soldar: una costura de UV no se suelda, %d vertices" % len(v))
    duro = list(quad)
    # otra normal en un vertice COMPARTIDO (b esta en los dos triangulos):
    # arista dura, se parte en dos
    duro[3] = (b, (1, 0), (0.0, 1.0, 0.0))
    v, _uv, _nr, _t, _c = soldar(duro)
    exigir(len(v) == 5, "soldar: una arista dura no se suelda, %d vertices" % len(v))
    falla_con(soldar, (quad[:4],), "no son triangulos", "soldar con 4 esquinas")
    # con color: el mismo vertice con otro alfa es otro vertice
    blanco, medio = (1.0, 1.0, 1.0, 1.0), (1.0, 1.0, 1.0, 0.3)
    con = [e + (blanco,) for e in quad]
    v, _uv, _nr, _t, col = soldar(con)
    exigir(len(v) == 4 and col == [blanco] * 4,
           "soldar con color: %d vertices, colores %r" % (len(v), col))
    con[3] = quad[3] + (medio,)            # b compartido, con otro alfa
    v, _uv, _nr, _t, col = soldar(con)
    exigir(len(v) == 5 and medio in col,
           "soldar: otro alfa en un vertice compartido no se suelda: %d" % len(v))
    falla_con(soldar, ([e + (blanco,) for e in quad[:3]] + quad[3:],),
              "unas esquinas traen color", "soldar con color a medias")

    # --- el modo de alfa, con los numeros de la trampa 14 ---
    exigir([modo_alfa(None, 0), modo_alfa((4844, 128), 0),
            modo_alfa((4333, 128), 0x82400381),
            modo_alfa((4333, 128), 0x82400389)] ==
           ["opaco", "testing", "blending_textura", "blending_vertice"],
           "modo_alfa con 4844 (testing) y 4333 (blending)")
    exigir(validar_alfa_vertice([0.3, 0.96, 0.5]) == (0.3, 0.96),
           "validar_alfa_vertice con alfa que varia")
    falla_con(validar_alfa_vertice, ([1.0, 1.0, 0.995],), "uniforme",
              "alfa por vertice uniforme")
    muchos = []
    for k in range(MAX_VERTICES // 3 + 2):
        muchos += [((k, 0, 0), (0, 0), n), ((k, 1, 0), (0, 0), n),
                   ((k, 0, 1), (0, 0), n)]
    falla_con(soldar, (muchos,), "16 bits", "soldar por encima del tope")

    # --- caja ---
    cj = caja_colision([(-HAVOK, -2 * HAVOK, 0.0), (HAVOK, 2 * HAVOK, 0.1 * HAVOK)])
    exigir([round(x, 9) for x in cj["semi"]] == [1.0, 2.0, 0.05]
           and [round(x, 9) for x in cj["centro"]] == [0.0, 0.0, 0.05]
           and abs(cj["radio"] - 0.05) < 1e-12,
           "caja: %r" % cj)
    cj = caja_colision([(0, 0, 0), (HAVOK, HAVOK, HAVOK)])
    exigir(abs(cj["radio"] - 0.1) < 1e-12, "caja: el radio no topa en 0,1: %r" % cj)
    falla_con(caja_colision, ([(0, 0, 0), (1, 1, 0)],), "plana", "caja plana")

    # --- inercia ---
    donante = [2.0, 0, 0, 0, 0, 0.4, 0, 0, 0, 0, 2.3, 0]
    nueva = inercia_escalada(donante, 10.0, [1.0, 2.0, 0.2], [1.0, 2.0, 0.2])
    exigir([nueva[i] for i in (0, 5, 10)] == [2.0, 0.4, 2.3],
           "inercia: con la misma caja tiene que dar la del donante: %r" % nueva)
    nueva = inercia_escalada(donante, 10.0, [1.0, 2.0, 0.2], [2.0, 4.0, 0.4])
    exigir(all(abs(nueva[i] - 4 * donante[i]) < 1e-9 for i in (0, 5, 10)),
           "inercia: el doble de caja tiene que dar el cuadruple: %r" % nueva)
    falla_con(inercia_escalada, ([0.0] * 12, 10.0, [1, 1, 1], [1, 1, 1]),
              "REGLA inercia", "donante con masa y sin inercia")
    exigir(inercia_escalada([0.0] * 12, 0.0, [1, 1, 1], [1, 1, 1]) == [0.0] * 12,
           "inercia: masa 0 tiene que quedar sin inercia")

    # --- flags ---
    f1, f2, cambios = conciliar_flags(0x80 | SF1_SKINNED | SF1_MODEL_SPACE_NORMALS
                                      | SF1_VERTEX_ALPHA, 0x8001 | SF2_VERTEX_COLORS)
    exigir(f1 == 0x80 and f2 == 0x8001 and len(cambios) == 4,
           "flags: 0x%X 0x%X %r" % (f1, f2, cambios))
    f1, f2, cambios = conciliar_flags(0x82400381, 0x00008011)
    exigir((f1, f2, cambios) == (0x82400381, 0x00008011, []),
           "flags: la receta del metal de la espada no se toca: 0x%X 0x%X %r"
           % (f1, f2, cambios))

    # --- texturas ---
    receta = {"Diffuse": r"textures\weapons\glass\GlassSword.dds",
              "Normal": r"textures\weapons\glass\GlassSword_n.dds",
              "EnvMap": r"textures\cubemaps\Ore_Gold_e.dds",
              "EnvMask": r"textures\weapons\glass\GlassSword_m.dds"}
    plan_tx = {"Diffuse": r"textures\mia\mia.dds", "Normal": r"textures\mia\mia_n.dds"}
    tx, notas = texturas_pieza(receta, plan_tx, 1)
    exigir(tx == dict(plan_tx, EnvMap=r"textures\cubemaps\Ore_Gold_e.dds")
           and notas and "EnvMask" in notas[0],
           "texturas: %r %r" % (tx, notas))
    falla_con(texturas_pieza, (receta, plan_tx, TIPO_GLOW), "Glow Shader",
              "Glow Shader sin ranura Glow")

    # --- plan ---
    bueno = {"donante": "d.nif", "salida": "s.nif", "raiz": "Mia",
             "piezas": [{"objeto": "Metal", "shape": "Mia:0",
                         "receta": {"shape": "GlassSword01:1"},
                         "texturas": dict(plan_tx)}],
             "colision": {"objetos": ["Metal"]}}
    exigir(validar_plan(bueno) == [], "plan bueno: %r" % validar_plan(bueno))
    malo = {"donante": "d.nif", "salida": "d.nif", "raiz": "", "extra": 1,
            "piezas": [{"objeto": "M", "shape": "S", "receta": {"shape": "x", "otro": 1},
                        "texturas": {"Diffuse": "a/b.dds", "Brillo": "x"}},
                       {"objeto": "M", "shape": "S2", "receta": {"shape": "y"},
                        "texturas": {"Diffuse": "a.dds", "Normal": "n.dds"}}],
            "colision": {"objetos": ["Nada"]}}
    problemas = validar_plan(malo)
    for trozo in ("'extra'", "mismo archivo que el donante", "raiz:", "receta:",
                  "'Brillo' no es una ranura", "falta Normal", "barras invertidas",
                  "objeto repetido", "'Nada' no es el objeto"):
        exigir(any(trozo in x for x in problemas),
               "plan: no se vio %r en %s" % (trozo, problemas))

    if not hechas[0]:
        print("autotest: NO se comprobo NADA")
        return 1
    print("autotest: %d comprobaciones, %d fallas" % (hechas[0], len(fallas)))
    for x in fallas:
        print("  FALLA %s" % x)
    return 1 if fallas else 0


def main(argv):
    if argv == ["--autotest"]:
        return autotest()
    print(__doc__.strip().splitlines()[0])
    print("uso: exportar_puro.py --autotest")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
