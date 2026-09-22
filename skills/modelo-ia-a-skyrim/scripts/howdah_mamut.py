# -*- coding: utf-8 -*-
"""Howdah estilo mumak sobre el lomo de un mamut: geometria, atadura, verificacion.

    blender -b --python howdah_mamut.py -- --esqueleto skeleton.nif --listar-huesos
    blender -b --python howdah_mamut.py -- --esqueleto skeleton.nif \
            --huesos "NPC Spine1" "NPC Spine2" --salida howdah.blend
    blender -b --python howdah_mamut.py -- --declarar --alto-lomo-cm 260
    python howdah_mamut.py --esqueleto skeleton.nif --listar-huesos   # sin Blender

QUE HACE

  1. mide el lomo del vanilla: posiciones de hueso leidas del BINARIO con
     nif_nodos.py, no de PyNifly (ver trampa 1: PyNifly puede sustituir el
     esqueleto de referencia y devolver posiciones que no son las del archivo).
  2. arma la estructura con cajas CERRADAS. El motor tiene backface culling:
     una lamina suelta se ve invisible de atras (trampa de la cascara abierta).
  3. reparte cada vertice entre los huesos de la columna por longitud de arco
     -- 2 huesos por vertice, contra un maximo de 4 [INVARIANT].
  4. verifica e imprime, y sale con 1 si algo falla.

QUE **NO** HACE, Y CONVIENE SABERLO ANTES DE PEDIRLE OTRA COSA

  * No escribe el NIF. La howdah sale como .blend; el NIF lo exporta PyNifly
    contra el mammoth.nif vanilla importado con su reference_skel.
  * No genera texturas ni rutas: deja dos materiales vacios (madera y tela).
    Ponerles las texturas es parte de pasarlas a la convencion de Skyrim
    (references/limites-skyrim.md), no de este script.
  * No hace montable al mamut. Que el jugador se suba es actor, animacion y
    plugin: nada de eso es geometria. Aca queda un Empty JINETE en el piso de
    la cubierta, que es lo unico de la montura que se decide en Blender.
  * No inventa medidas. Sin --esqueleto no hay alto de lomo: hay que
    declararlo con --alto-lomo-cm y el informe lo marca [DECLARADO].
  * No mide el torso. El ancho de la cubierta es decision de diseno
    (--ancho-cm), no un dato del vanilla.

LAS DOS FORMAS DE DARLE EL LOMO

  * --esqueleto <skeleton.nif>  -> mide. Es la que hay que usar.
  * --declarar                  -> vos pones los numeros. Sirve para bocetar
    antes de extraer el BSA, y el informe dice que no midio nada.

Sin --esqueleto, --declarar exige --alto-lomo-cm: sin ese numero no hay donde
apoyar la cubierta, y el script lo dice en vez de inventarlo.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import nif_nodos  # noqa: E402

try:                                  # el calculo no necesita Blender: solo
    import bpy                        # la parte que crea la malla lo usa, asi
except ImportError:                   # el modulo se puede testear en CI.
    bpy = None

# --- unidades -------------------------------------------------------------
# [OBSERVED] references/limites-skyrim.md: 1 unidad de Skyrim ~= 1,42 cm,
# 1 metro son unas 70 unidades. Todo el script piensa en centimetros porque
# es como se mide un mueble, y convierte al final.
CM_A_U = 0.70

# --- limites del motor, con su procedencia --------------------------------
MAX_VERTICES_SHAPE = 65535    # [INVARIANT] indices de triangulo de 16 bits
MAX_HUESOS_POR_VERTICE = 4    # [INVARIANT] mas pesos se descartan en silencio
PRESUPUESTO_GRUPO = 20000     # [OBSERVED] criatura que aparece en grupo
PRESUPUESTO_UNICA = 60000     # [OBSERVED] criatura unica / jefe

# Un humano mide unas 120 unidades [OBSERVED] y el hombro con hombro de un
# actor es del orden de 45 cm. Debajo de 90 cm de ancho no entran dos, y una
# cubierta de menos de 120 cm de largo no deja estar de pie: es aviso, no falla.
ANCHO_MINIMO_CM = 90.0
LARGO_MINIMO_CM = 120.0

MADERA = "madera"
TELA = "tela"


# ==========================================================================
# Geometria pura: cajas y prismas cerrados. Sin Blender, se testea en CI.
# ==========================================================================

def _rotar(p, ang_x=0.0, ang_y=0.0):
    """Rota un punto alrededor del eje X y despues del Y, en radianes."""
    x, y, z = p
    if ang_x:
        c, s = math.cos(ang_x), math.sin(ang_x)
        y, z = c * y - s * z, s * y + c * z
    if ang_y:
        c, s = math.cos(ang_y), math.sin(ang_y)
        x, z = c * x + s * z, -s * x + c * z
    return (x, y, z)


def caja(centro, semiejes, ang_x=0.0, ang_y=0.0):
    """Ocho vertices y doce triangulos de una caja cerrada.

    El orden de los triangulos es el del cubo de tests/test_salud_malla.py
    (CUBO_TRIS): con ese orden, `salud()` da borde 0 y winding 0.
    """
    sx, sy, sz = semiejes
    locales = [(-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
               (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz)]
    cx, cy, cz = centro
    pos = []
    for lx, ly, lz in locales:
        rx, ry, rz = _rotar((lx, ly, lz), ang_x, ang_y)
        pos.append((cx + rx, cy + ry, cz + rz))
    tris = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
            (0, 1, 5), (0, 5, 4), (2, 3, 7), (2, 7, 6),
            (1, 2, 6), (1, 6, 5), (0, 4, 7), (0, 7, 3)]
    return pos, tris


def prisma(seccion, y0, y1):
    """Extruye una seccion cerrada del plano XZ a lo largo de Y.

    `seccion` es [(x, z), ...] en sentido ANTIHORARIO visto desde +Y. Las dos
    tapas y los costados salen coherentes entre si, cosa que se comprueba: el
    test le pasa el toldo a salud_malla y exige winding 0.
    """
    n = len(seccion)
    pos = [(x, y0, z) for x, z in seccion] + [(x, y1, z) for x, z in seccion]
    tris = []
    for i in range(1, n - 1):
        tris.append((0, i, i + 1))                 # tapa en y0, mira a -Y
        tris.append((n, n + i + 1, n + i))         # tapa en y1, mira a +Y
    # El sentido de los costados no es el obvio: con (i, j, n+j) las tres
    # caras laterales salen dadas vuelta y `salud` las marca como winding
    # incoherente (6 aristas en un prisma triangular: las que comparten con
    # las tapas). Costados afuera => (i, n+j, j) y (i, n+i, n+j).
    for i in range(n):
        j = (i + 1) % n
        tris.append((i, n + j, j))
        tris.append((i, n + i, n + j))
    return pos, tris


class Estructura(object):
    """Acumula piezas en mundo: vertices, triangulos y de que pieza es cada uno."""

    def __init__(self):
        self.pos = []
        self.tris = []
        # (nombre, material, i0, i1, apoya). `apoya` separa la estructura que
        # se sostiene sobre el lomo de lo que CUELGA de ella: la escalera sale
        # para atras y para abajo, por fuera del tramo de huesos medido, y
        # exigirle que caiga sobre un hueso reprobaria una pieza que esta
        # perfectamente colgada de la cubierta.
        self.piezas = []

    def _agregar(self, nombre, material, pos, tris, apoya=True):
        i0 = len(self.pos)
        self.pos.extend(pos)
        self.tris.extend([(a + i0, b + i0, c + i0) for a, b, c in tris])
        self.piezas.append((nombre, material, i0, len(self.pos), apoya))
        return i0

    def caja(self, nombre, material, centro, semiejes, ang_x=0.0, ang_y=0.0,
             apoya=True):
        pos, tris = caja(centro, semiejes, ang_x, ang_y)
        return self._agregar(nombre, material, pos, tris, apoya)

    def prisma(self, nombre, material, seccion, y0, y1, apoya=True):
        pos, tris = prisma(seccion, y0, y1)
        return self._agregar(nombre, material, pos, tris, apoya)

    def indices_que_apoyan(self):
        """Vertices de las piezas que se sostienen sobre el lomo."""
        fuera = []
        for _n, _m, i0, i1, apoya in self.piezas:
            if apoya:
                fuera.extend(range(i0, i1))
        return fuera

    def por_material(self):
        """{material: [indices de vertice]} en el orden en que se armaron."""
        fuera = {}
        for _nombre, material, i0, i1, _apoya in self.piezas:
            fuera.setdefault(material, []).extend(range(i0, i1))
        return fuera


# ==========================================================================
# Medir el vanilla
# ==========================================================================

def leer_huesos(ruta_esqueleto):
    """{nombre: (x, y, z)} en espacio de mundo, parseado del binario."""
    pos, _prof = nif_nodos.mundo(nif_nodos.leer(ruta_esqueleto))
    return dict((n, (p[0], p[1], p[2])) for n, p in pos.items())


def sugerir_huesos_lomo(huesos):
    """Ranking de candidatos a columna. ES UNA SUGERENCIA, no una medicion.

    No busca por nombre: los nombres de hueso de una criatura no se deducen,
    se leen del archivo (references/nodo-de-anclaje.md). Lo que hace es
    ordenar por tres cosas que si se pueden medir: altura (el lomo es lo mas
    alto del bicho, salvo la cabeza), cercania al plano medio X=0 (la columna
    va por el centro) y posicion intermedia en Y (ni trompa ni cola).

    La devolucion va al informe como [SUGERIDO] hasta que alguien la confirma
    mirando el esqueleto en NifSkope.
    """
    if not huesos:
        return []
    zs = [p[2] for p in huesos.values()]
    ys = [p[1] for p in huesos.values()]
    if not zs:
        return []
    zmax, zmin = max(zs), min(zs)
    ymax, ymin = max(ys), min(ys)
    alto = (zmax - zmin) or 1.0
    largo = (ymax - ymin) or 1.0
    fuera = []
    for nombre, (x, y, z) in huesos.items():
        # tercio superior del bicho, pegado al plano medio, en el medio del cuerpo
        puntaje = (z - zmin) / alto
        puntaje -= abs(x) / (largo or 1.0) * 0.5
        puntaje -= abs((y - ymin) / largo - 0.5) * 0.5
        fuera.append((puntaje, nombre, (x, y, z)))
    fuera.sort(reverse=True)
    return [(n, p) for _s, n, p in fuera]


def medidas_del_lomo(huesos, nombres):
    """(y_centro, largo_tramo, z_lomo) del tramo de huesos elegido.

    Devuelve None si falta algun nombre: un hueso que no existe no se repone
    con un invento, se avisa.
    """
    falta = [n for n in nombres if n not in huesos]
    if falta:
        return None, falta
    pts = [huesos[n] for n in nombres]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    return {
        "y_centro": (min(ys) + max(ys)) / 2.0,
        "largo_tramo": max(ys) - min(ys),
        "z_lomo": max(zs),
        "x_medio": sum(p[0] for p in pts) / float(len(pts)),
        "huesos": list(nombres),
    }, []


# ==========================================================================
# Diseno
# ==========================================================================

class Diseno(object):
    """Las medidas de la howdah. Son decisiones, no datos del vanilla.

    Todo en centimetros: es la unidad en la que se piensa un mueble. Se
    convierten a unidades de juego al construir (CM_A_U).
    """

    def __init__(self, ancho=150.0, largo=220.0, despeje=8.0, espesor=12.0,
                 alto_bordo=45.0, alto_poste=110.0, alto_cumbrera=45.0,
                 seccion_poste=10.0, seccion_baranda=6.0, tablas=7,
                 barrotes=5, toldo=True, escalera=True, correas=True,
                 largo_escalera=130.0, angulo_escalera=20.0, peldanos=6,
                 caida_correas=90.0, angulo_correas=12.0, hueco_tablas=1.0):
        self.ancho = ancho
        self.largo = largo
        self.despeje = despeje
        self.espesor = espesor
        self.alto_bordo = alto_bordo
        self.alto_poste = alto_poste
        self.alto_cumbrera = alto_cumbrera
        self.seccion_poste = seccion_poste
        self.seccion_baranda = seccion_baranda
        self.tablas = tablas
        self.barrotes = barrotes
        self.toldo = toldo
        self.escalera = escalera
        self.correas = correas
        self.largo_escalera = largo_escalera
        self.angulo_escalera = angulo_escalera
        self.peldanos = peldanos
        self.caida_correas = caida_correas
        self.angulo_correas = angulo_correas
        self.hueco_tablas = hueco_tablas


def construir(diseno, lomo):
    """Arma la estructura completa. Devuelve (Estructura, cotas).

    `lomo` es el dict de medidas_del_lomo() o, en modo declarado, uno con
    y_centro / largo_tramo / z_lomo / x_medio puestos a mano.

    Ejes: +Y adelante, +Z arriba (references/limites-skyrim.md). La escalera
    va atras, en -Y: si aparece adelante, el signo esta al reves y el control
    `orientacion` del informe lo ve.
    """
    u = CM_A_U
    e = Estructura()

    x_c = lomo["x_medio"]
    y_c = lomo["y_centro"]
    z_lomo = lomo["z_lomo"]

    ancho = diseno.ancho * u
    largo = diseno.largo * u
    espesor = diseno.espesor * u
    alto_bordo = diseno.alto_bordo * u
    alto_poste = diseno.alto_poste * u

    y0, y1 = y_c - largo / 2.0, y_c + largo / 2.0
    x0, x1 = x_c - ancho / 2.0, x_c + ancho / 2.0

    z_base = z_lomo + diseno.despeje * u          # cara de abajo de la cubierta
    z_piso = z_base + espesor                     # donde apoya el jinete
    z_bordo = z_piso + alto_bordo                 # borde de la baranda baja
    z_poste = z_piso + alto_poste                 # donde arranca el toldo

    # --- arnes: dos largueros bajo la cubierta -------------------------
    semilargo = largo / 2.0
    for lado in (-1, 1):
        e.caja("larguero", MADERA,
               (x_c + lado * (ancho / 2.0 - 15.0 * u), y_c, z_base - 3.0 * u),
               (5.0 * u, semilargo, 3.0 * u))

    # --- correas: bajan por el flanco -----------------------------------
    # [DECLARADO] la curvatura del flanco no se mide: el angulo y la caida son
    # parametros. Si el mamut las tiene que abrazar de verdad, hay que medir el
    # torso con la malla importada y ajustar. Ver docstring.
    if diseno.correas:
        ang = math.radians(diseno.angulo_correas)
        mitad = diseno.caida_correas * u / 2.0
        for lado in (-1, 1):
            for fraccion in (0.30, 0.70):
                y = y0 + largo * fraccion
                e.caja("correa", TELA,
                       (x_c + lado * (ancho / 2.0 - 6.0 * u), y,
                        z_base - mitad),
                       (2.5 * u, 4.0 * u, mitad),
                       ang_y=lado * ang)

    # --- piso de tablas --------------------------------------------------
    # Tablas a lo largo (eje Y) con una luz de 1 cm entre ellas: la costura se
    # ve y no cuesta geometria. Cada tabla es un solido cerrado aparte.
    n = max(1, int(diseno.tablas))
    luz = diseno.hueco_tablas * u
    ancho_tabla = (ancho - luz * (n - 1)) / float(n)
    for i in range(n):
        cx = x0 + i * (ancho_tabla + luz) + ancho_tabla / 2.0
        e.caja("tabla", MADERA, (cx, y_c, z_base + espesor / 2.0),
               (ancho_tabla / 2.0, semilargo, espesor / 2.0))

    # --- bordo: la baranda baja que no te deja caer ----------------------
    b = diseno.seccion_baranda * u
    e.caja("bordo_frente", MADERA, (x_c, y1 - b, z_piso + alto_bordo / 2.0),
           (ancho / 2.0, b, alto_bordo / 2.0))
    e.caja("bordo_atras", MADERA, (x_c, y0 + b, z_piso + alto_bordo / 2.0),
           (ancho / 2.0, b, alto_bordo / 2.0))
    for lado in (-1, 1):
        # entra entre las dos paredes de los extremos, no por debajo de ellas:
        # el semieje es semilargo - 2b, porque la pared del frente ocupa 2b.
        e.caja("bordo_lado", MADERA,
               (x_c + lado * (ancho / 2.0 - b), y_c, z_piso + alto_bordo / 2.0),
               (b, semilargo - 2.0 * b, alto_bordo / 2.0))

    # --- postes y barandas altas ----------------------------------------
    p = diseno.seccion_poste * u
    xi = x1 - p - 2.0 * u
    yi = y1 - p - 2.0 * u
    yo = y0 + p + 2.0 * u
    z_poste_alto = z_piso + alto_poste      # donde apoya el toldo
    for sx in (-1, 1):
        for y_poste in (yi, yo):
            # Atraviesa el piso y arranca en la cara de ABAJO de la cubierta:
            # empotrado, no apoyado (dos solidos que comparten una cara exacta
            # dejan aristas con 4 caras, que el informe cuenta de mas), y sin
            # llegar mas abajo, porque lo que esta debajo es el lomo.
            e.caja("poste", MADERA,
                   (x_c + sx * xi, y_poste, (z_base + z_poste_alto) / 2.0),
                   (p, p, (z_poste_alto - z_base) / 2.0))

    z_alto = z_poste_alto - diseno.seccion_baranda * u
    z_medio = z_piso + alto_poste * 0.55
    e.caja("baranda_frente", MADERA, (x_c, yi, z_alto), (xi, p, b))
    e.caja("baranda_atras", MADERA, (x_c, yo, z_alto), (xi, p, b))
    for lado in (-1, 1):
        # (yi - yo) / 2: la baranda va de poste a poste, y yi/yo son las
        # POSICIONES de los postes, no su separacion.
        e.caja("baranda_lado_alta", MADERA,
               (x_c + lado * xi, y_c, z_alto), (b, (yi - yo) / 2.0, p))
        e.caja("baranda_lado_media", MADERA,
               (x_c + lado * xi, y_c, z_medio), (b, (yi - yo) / 2.0, p))
        # barrotes: verticales entre la baranda media y la alta
        for i in range(max(0, int(diseno.barrotes))):
            t = (i + 1) / float(max(1, int(diseno.barrotes)) + 1)
            e.caja("barrote", MADERA,
                   (x_c + lado * xi, yo + (yi - yo) * t,
                    (z_medio + z_alto) / 2.0),
                   (b * 0.6, b * 0.6, (z_alto - z_medio) / 2.0))

    # --- toldo a dos aguas -----------------------------------------------
    if diseno.toldo:
        e.prisma("toldo", TELA,
                 [(x0 - 6.0 * u, z_alto),
                  (x1 + 6.0 * u, z_alto),
                  (x_c, z_alto + diseno.alto_cumbrera * u)],
                 y0 - 6.0 * u, y1 + 6.0 * u)

    # --- escalera: atras, en -Y -----------------------------------------
    # [INVARIANT] +Y es adelante. La escalera tiene que caer del lado de la
    # cola; el control `orientacion` del informe lo comprueba contra y_centro.
    if diseno.escalera:
        ang = math.radians(diseno.angulo_escalera)
        L = diseno.largo_escalera * u
        ca, sa = math.cos(ang), math.sin(ang)
        for lado in (-1, 1):
            e.caja("escalera_larguero", MADERA,
                   (x_c + lado * 25.0 * u, y0 - ca * L / 2.0,
                    z_piso - sa * L / 2.0),
                   (3.5 * u, L / 2.0, 3.5 * u), ang_x=ang, apoya=False)
        for i in range(max(1, int(diseno.peldanos))):
            t = (i + 1) / float(max(1, int(diseno.peldanos)) + 1)
            e.caja("escalera_peldano", MADERA,
                   (x_c, y0 - ca * L * t, z_piso - sa * L * t),
                   (25.0 * u, 3.0 * u, 2.0 * u), apoya=False)

    cotas = {
        "x": (x0, x1), "y": (y0, y1),
        "z_base": z_base, "z_piso": z_piso,
        "z_bordo": z_bordo, "z_poste": z_poste,
        "z_lomo": z_lomo,
        "jinete": (x_c, y0 + largo * 0.75, z_piso),
    }
    return e, cotas


# ==========================================================================
# Atadura: de cada vertice a los huesos de la columna
# ==========================================================================

def polilinea(huesos, nombres):
    """[(nombre, (x, y, z))] ordenados a lo largo del lomo (por Y).

    El orden importa: el reparto de pesos interpola entre vecinos, y si la
    lista esta mezclada la interpolacion salta de un lado al otro.
    """
    pts = [(n, huesos[n]) for n in nombres if n in huesos]
    pts.sort(key=lambda t: t[1][1])
    return pts


def pesos_en(punto, linea):
    """({hueso: peso}, fuera_del_tramo, exceso).

    Proyecta el punto sobre la polilinea y reparte entre los DOS huesos del
    segmento mas cercano: nunca mas de 2, contra un maximo de 4 [INVARIANT].

    Rigido a un hueso (una sola atadura) es mas simple y es lo que hace el
    Steam Centurion [OBSERVED], pero una cubierta de mas de dos metros
    atada a un solo hueso se despega del lomo cuando la columna se dobla: el
    hueso gira y la pieza gira con el, mientras la carne dibujada por los
    huesos de al lado no. Con el reparto por arco, la howdah acompaña la
    curva. Si la queres rigida, pasa un solo hueso en --huesos.

    `fuera_del_tramo` distingue "al costado" de "colgando": un vertice a 75 cm
    del eje esta lejos de la polilinea pero su proyeccion cae DENTRO del tramo,
    y eso esta bien. El que esta mal es el que cae antes del primer hueso o
    despues del ultimo: ese no tiene nada debajo.
    """
    if not linea:
        return {}, True, 0.0
    if len(linea) == 1:
        return {linea[0][0]: 1.0}, False, 0.0

    mejor = None
    largo_total = 0.0
    acumulados = [0.0]
    for i in range(len(linea) - 1):
        (_na, a), (_nb, b) = linea[i], linea[i + 1]
        d = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        largo_total += math.sqrt(sum(c * c for c in d))
        acumulados.append(largo_total)

    for i in range(len(linea) - 1):
        (_na, a), (_nb, b) = linea[i], linea[i + 1]
        d = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        dd = sum(c * c for c in d)
        if dd == 0.0:
            t = 0.0
        else:
            t = sum((punto[k] - a[k]) * d[k] for k in range(3)) / dd
        u = t                                   # sin acotar: dice si se paso
        t = min(1.0, max(0.0, t))
        c = (a[0] + d[0] * t, a[1] + d[1] * t, a[2] + d[2] * t)
        dist = math.sqrt(sum((punto[k] - c[k]) ** 2 for k in range(3)))
        s = acumulados[i] + u * math.sqrt(dd)
        if mejor is None or dist < mejor[0]:
            mejor = (dist, i, t, s)

    _dist, i, t, s = mejor
    fuera, exceso = False, 0.0
    if s < 0.0:
        fuera, exceso = True, -s
    elif s > largo_total:
        fuera, exceso = True, s - largo_total

    a, b = linea[i][0], linea[i + 1][0]
    if a == b:
        return {a: 1.0}, fuera, exceso
    w = {a: 1.0 - t, b: t}
    # Un peso de 0.0 no aporta nada y deja un grupo de vertices vacio en el
    # export. Se poda y se renormaliza: la suma tiene que seguir dando 1.
    w = dict((h, p) for h, p in w.items() if p > 1e-6)
    total = sum(w.values())
    if total <= 0.0:
        return {a: 1.0}, fuera, exceso
    return dict((h, p / total) for h, p in w.items()), fuera, exceso


def atadura(estructura, linea):
    """Pesos por vertice. Devuelve (lista de dicts, resumen).

    Todos los vertices quedan atados -- la escalera tambien, clavada al hueso
    del extremo -- pero el resumen cuenta `fuera` solo sobre las piezas que
    APOYAN (estructura.indices_que_apoyan()). Lo que cuelga puede quedar por
    fuera del tramo de huesos sin que eso sea un defecto.
    """
    apoyan = set(estructura.indices_que_apoyan())
    pesos = []
    resumen = {"sin_hueso": 0, "fuera": 0, "exceso_max": 0.0,
               "max_huesos": 0, "por_hueso": {}}
    for i, p in enumerate(estructura.pos):
        w, fuera, exceso = pesos_en(p, linea)
        if not w:
            resumen["sin_hueso"] += 1
        if fuera and i in apoyan:
            resumen["fuera"] += 1
            resumen["exceso_max"] = max(resumen["exceso_max"], exceso)
        resumen["max_huesos"] = max(resumen["max_huesos"], len(w))
        for h, peso in w.items():
            r = resumen["por_hueso"].setdefault(
                h, {"vertices": 0, "peso_max": 0.0, "peso_total": 0.0})
            r["vertices"] += 1
            r["peso_max"] = max(r["peso_max"], peso)
            r["peso_total"] += peso
        pesos.append(w)
    return pesos, resumen


# ==========================================================================
# Verificacion
# ==========================================================================

def _estado(falla, detalle, etiqueta=""):
    return {"estado": "FALLA" if falla else "ok", "detalle": detalle,
            "etiqueta": etiqueta}


def verificar(estructura, pesos, resumen, diseno, lomo, cotas, medida,
              presupuesto=PRESUPUESTO_GRUPO, con_uv=None, con_huesos=True):
    """La lista de controles. Cada uno dice de donde sale su numero."""
    u = CM_A_U
    controles = {}

    n_tri = len(estructura.tris)
    n_vert = len(estructura.pos)
    controles["triangulos"] = _estado(
        n_tri > presupuesto,
        "%d triangulos contra un presupuesto de %d (criatura que aparece en "
        "grupo: 8.000-20.000; unica: hasta 60.000). La mediana de `actors` en "
        "el censo es 3.706." % (n_tri, presupuesto),
        "[OBSERVED]")

    por_material = estructura.por_material()
    peor = max(len(v) for v in por_material.values()) if por_material else 0
    controles["vertices_por_shape"] = _estado(
        peor > MAX_VERTICES_SHAPE,
        "%d vertices en el shape mas grande, techo %d" % (peor, MAX_VERTICES_SHAPE),
        "[INVARIANT]")

    # Misma medicion que usa salud_malla.py para decidir si una malla se abrio.
    # Reusarla aca, en vez de reescribir el conteo de aristas de borde, es de
    # adrede: si el control cambia, cambia para los dos.
    try:
        import salud_malla
        salud = salud_malla.salud(estructura.pos, estructura.tris, 1)
    except ImportError:
        salud = None

    if salud is None:
        controles["malla_cerrada"] = {"estado": "NO MEDIDO",
                                      "detalle": "salud_malla no disponible",
                                      "etiqueta": ""}
    else:
        controles["malla_cerrada"] = _estado(
            salud["borde"] > 0,
            "%d aristas de borde sobre %d triangulos (cerrada: 0). Una malla "
            "abierta se ve invisible de atras por backface culling."
            % (salud["borde"], salud["tris"]),
            "[INVARIANT]")
        controles["winding"] = _estado(
            salud["winding"] > 0,
            "%d aristas con winding incoherente: triangulos dados vuelta, que "
            "con backface culling desaparecen." % salud["winding"],
            "[INVARIANT]")
        controles["caras_coincidentes"] = {
            "estado": "AVISO" if salud["no_manifold"] > 0 else "ok",
            "detalle": "%d aristas con mas de dos caras: piezas que se pisan. "
            "No rompe nada, pero son triangulos que no se ven."
            % salud["no_manifold"],
            "etiqueta": "[OBSERVED]"}

    # Sin esqueleto no hay nada que atar, y eso no es una falla de la malla:
    # es una medicion que falta. Decir "366 vertices sin hueso" en modo
    # declarado es ruido; decir NO MEDIDO obliga a medir.
    if con_huesos:
        controles["atadura_completa"] = _estado(
            resumen["sin_hueso"] > 0,
            "%d vertices sin ningun hueso" % resumen["sin_hueso"],
            "[INVARIANT]")
        controles["huesos_por_vertice"] = _estado(
            resumen["max_huesos"] > MAX_HUESOS_POR_VERTICE,
            "maximo %d huesos por vertice, limite %d"
            % (resumen["max_huesos"], MAX_HUESOS_POR_VERTICE),
            "[INVARIANT]")
    else:
        controles["atadura_completa"] = {
            "estado": "NO MEDIDO", "etiqueta": "[DECLARADO]",
            "detalle": "sin --esqueleto no hay a que atar la malla"}
        controles["huesos_por_vertice"] = {
            "estado": "NO MEDIDO", "etiqueta": "[DECLARADO]",
            "detalle": "sin huesos no se puede contar pesos"}

    if medida:
        controles["apoyo_en_el_tramo"] = _estado(
            resumen["fuera"] > 0,
            "%d vertices de las piezas que apoyan caen fuera del tramo de "
            "huesos medido (se pasan hasta %.1f cm del extremo). Esos vertices "
            "no tienen nada debajo: la cubierta se bambolea cuando el hueso "
            "del extremo se mueve. La escalera no cuenta: cuelga."
            % (resumen["fuera"], resumen["exceso_max"] / u),
            "[MEDIDO]")
        controles["despeje_sobre_el_lomo"] = _estado(
            cotas["z_base"] - cotas["z_lomo"] <= 0,
            "la cubierta arranca %.1f cm sobre el lomo medido"
            % ((cotas["z_base"] - cotas["z_lomo"]) / u),
            "[MEDIDO]")
        largo_tramo = lomo.get("largo_tramo", 0.0)
        controles["largo_vs_tramo"] = _estado(
            diseno.largo * u > largo_tramo,
            "cubierta %.0f cm contra un tramo de columna de %.0f cm: %s"
            % (diseno.largo, largo_tramo / u,
               "sobra" if diseno.largo * u > largo_tramo else "entra"),
            "[MEDIDO]")
    else:
        controles["apoyo_en_el_tramo"] = {
            "estado": "NO MEDIDO", "etiqueta": "[DECLARADO]",
            "detalle": "sin --esqueleto no hay tramo medido: corralo contra el "
                       "skeleton.nif para saber si la cubierta se apoya en algo."}

    controles["orientacion"] = _estado(
        cotas["jinete"][1] < cotas["y"][0] or cotas["jinete"][1] > cotas["y"][1],
        "el jinete queda en Y=%.1f, dentro de la cubierta (%.1f..%.1f). +Y es "
        "adelante: la escalera y el jinete atras serian un signo al reves."
        % (cotas["jinete"][1], cotas["y"][0], cotas["y"][1]),
        "[INVARIANT]")

    aviso = []
    if diseno.ancho < ANCHO_MINIMO_CM:
        aviso.append("ancho %.0f cm: no entran dos de frente" % diseno.ancho)
    if diseno.largo < LARGO_MINIMO_CM:
        aviso.append("largo %.0f cm: no se esta de pie ahi" % diseno.largo)
    controles["escala_humana"] = {
        "estado": "AVISO" if aviso else "ok", "etiqueta": "[OBSERVED]",
        "detalle": "; ".join(aviso) if aviso
                   else "%.0f x %.0f cm, entra una persona de pie"
                        % (diseno.ancho, diseno.largo)}

    if con_uv is not None:
        controles["uv"] = _estado(
            not con_uv,
            "UV %s. Sin capa de UV no hay tangentes y el normal map se aplica "
            "en un espacio equivocado." % ("presente" if con_uv else "AUSENTE"),
            "[INVARIANT]")

    return controles


def informe(estructura, pesos, resumen, diseno, lomo, cotas, medida,
            controles, origen_lomo):
    u = CM_A_U
    return {
        "como_se_dio_el_lomo": origen_lomo,
        "medidas": lomo,
        "cotas_cm": {"ancho": diseno.ancho, "largo": diseno.largo,
                     "alto_poste": diseno.alto_poste,
                     "despeje_sobre_lomo": (cotas["z_base"] - cotas["z_lomo"]) / u,
                     "alto_total": (cotas["z_poste"] - cotas["z_lomo"]) / u},
        "estructura": {"triangulos": len(estructura.tris),
                       "vertices": len(estructura.pos),
                       "piezas": [{"nombre": n, "material": m,
                                   "vertices": i1 - i0, "apoya": a}
                                  for n, m, i0, i1, a in estructura.piezas]},
        "atadura": resumen,
        "jinete": {"x": cotas["jinete"][0], "y": cotas["jinete"][1],
                   "z": cotas["jinete"][2]},
        "controles": controles,
        "fallas": sum(1 for c in controles.values()
                      if c.get("estado") == "FALLA"),
    }


# ==========================================================================
# Blender
# ==========================================================================

def _malla(nombre, pos, tris, indices):
    """Crea la malla de un material. Devuelve (objeto, {vertice_global: local})."""
    mapa = {}
    locales = []
    for i in indices:
        mapa[i] = len(locales)
        locales.append(pos[i])
    # Un triangulo entra solo si sus tres vertices son de este material. Como
    # cada pieza es un solido cerrado y entero, no hay triangulo a caballo de
    # dos materiales; el filtro igual esta por si alguien agrega una pieza que
    # cruce.
    nuevo_tri = [(mapa[a], mapa[b], mapa[c]) for a, b, c in tris
                 if a in mapa and b in mapa and c in mapa]

    mesh = bpy.data.meshes.new(nombre)
    mesh.from_pydata(locales, [], nuevo_tri)
    mesh.update()
    obj = bpy.data.objects.new(nombre, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj, mapa


def _uv_planar(obj):
    """UV plana por cara, proyectando sobre el eje dominante de su normal.

    No es un UV de produccion -- es el minimo para que exista la capa: sin UV
    no hay tangentes y el normal se aplica mal. Para un asset que se ve de
    cerca hay que hacer el UV de verdad.
    """
    mesh = obj.data
    if mesh.uv_layers:
        capa = mesh.uv_layers[0]
    else:
        capa = mesh.uv_layers.new(name="UVMap")
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    escala = [max(max(xs) - min(xs), 1e-6), max(max(ys) - min(ys), 1e-6),
              max(max(zs) - min(zs), 1e-6)]
    for poli in mesh.polygons:
        n = poli.normal
        ejes = [abs(n.x), abs(n.y), abs(n.z)]
        eje = ejes.index(max(ejes))
        for li in poli.loop_indices:
            v = mesh.loops[li].vertex_index
            co = mesh.vertices[v].co
            if eje == 0:
                uv = (co.y / escala[1], co.z / escala[2])
            elif eje == 1:
                uv = (co.x / escala[0], co.z / escala[2])
            else:
                uv = (co.x / escala[0], co.y / escala[1])
            capa.data[li].uv = uv


def construir_en_blender(estructura, pesos, cotas, diseno, nombre="Howdah",
                         unir=True, con_jinete=True, ruta_salida=None):
    """Crea los objetos, los grupos de vertices, las UV y el Empty del jinete."""
    if bpy is None:
        raise SystemExit("Este paso necesita Blender: correrlo con "
                         "`blender -b --python howdah_mamut.py -- ...`")

    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)

    materiales = {}
    for mat in (MADERA, TELA):
        m = bpy.data.materials.new("%s_%s" % (nombre, mat))
        m.use_nodes = True
        materiales[mat] = m

    objetos = []
    mapas = {}
    for material, indices in sorted(estructura.por_material().items()):
        obj, mapa = _malla("%s_%s" % (nombre, material), estructura.pos,
                           estructura.tris, indices)
        obj.data.materials.append(materiales[material])
        _uv_planar(obj)
        objetos.append(obj)
        mapas[obj.name] = mapa

    # grupos de vertices: uno por hueso, pesos por vertice
    huesos = sorted({h for w in pesos for h in w})
    for obj in objetos:
        mapa = mapas[obj.name]
        grupos = dict((h, obj.vertex_groups.new(name=h)) for h in huesos)
        for global_i, local_i in mapa.items():
            w = pesos[global_i]
            if not w:
                continue
            for h, peso in w.items():
                if peso > 0:
                    grupos[h].add([local_i], peso, "REPLACE")

    if con_jinete:
        vacio = bpy.data.objects.new("JINETE", None)
        vacio.location = cotas["jinete"]
        bpy.context.scene.collection.objects.link(vacio)

    if unir and len(objetos) > 1:
        # Un solo objeto = menos draw calls. Los slots de material se mantienen,
        # y PyNifly separa por material al exportar.
        for o in objetos:
            o.select_set(True)
        bpy.context.view_layer.objects.active = objetos[0]
        bpy.ops.object.join()
        objetos = [bpy.context.view_layer.objects.active]

    for obj in objetos:
        obj.data.update()

    if ruta_salida:
        bpy.ops.wm.save_as_mainfile(filepath=ruta_salida)

    return objetos


# ==========================================================================
# CLI
# ==========================================================================

def _imprimir_huesos(huesos, sugeridos):
    print("Huesos del esqueleto, de mas alto a mas bajo:")
    print("  %-34s %10s %10s %10s" % ("nombre", "x", "y", "z"))
    for nombre, (x, y, z) in sorted(huesos.items(), key=lambda t: -t[1][2]):
        marca = "  <- sugerido" if nombre in sugeridos else ""
        print("  %-34s %10.2f %10.2f %10.2f%s" % (nombre, x, y, z, marca))


def _imprimir_informe(inf):
    print("")
    print("=" * 70)
    print("HOWDAH  --  lomo: %s" % inf["como_se_dio_el_lomo"])
    print("=" * 70)
    c = inf["estructura"]
    print("  %d triangulos, %d vertices, %d piezas"
          % (c["triangulos"], c["vertices"], len(c["piezas"])))
    for p in c["piezas"]:
        print("    %-22s %-7s %6d verts" % (p["nombre"], p["material"],
                                            p["vertices"]))
    print("  cota: %.0f x %.0f cm, %.0f cm de alto sobre el lomo, "
          "despeje %.1f cm"
          % (inf["cotas_cm"]["ancho"], inf["cotas_cm"]["largo"],
             inf["cotas_cm"]["alto_total"], inf["cotas_cm"]["despeje_sobre_lomo"]))
    at = inf["atadura"]
    print("  atadura: maximo %d huesos por vertice, %d vertices sin hueso, "
          "%d fuera del tramo" % (at["max_huesos"], at["sin_hueso"], at["fuera"]))
    for h, r in sorted(at["por_hueso"].items()):
        print("    %-30s %6d verts  peso_max %.2f"
              % (h, r["vertices"], r["peso_max"]))
    print("  jinete (Empty JINETE): x=%.1f y=%.1f z=%.1f"
          % (inf["jinete"]["x"], inf["jinete"]["y"], inf["jinete"]["z"]))
    print("  --- controles ---")
    for nombre, c2 in sorted(inf["controles"].items()):
        print("   [%s] %-24s %s" % (c2["estado"], nombre, c2["detalle"]))
    print("  --- fallas: %d ---" % inf["fallas"])


def _argv_original():
    """Los argumentos tal cual se llamo al script, para repetirlos en un aviso."""
    if "--" in sys.argv:
        return sys.argv[sys.argv.index("--") + 1:]
    return sys.argv[1:]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in sys.argv and argv == sys.argv[1:]:
        argv = sys.argv[sys.argv.index("--") + 1:]
    if not argv:
        print(__doc__)
        return 2

    def sacar(clave, n=0):
        """Saca --clave (con n valores) y devuelve los valores. None si no esta."""
        if clave not in argv:
            return None
        i = argv.index(clave)
        if n:
            valor = argv[i + 1:i + 1 + n]
        else:
            valor = argv[i:i + 1]
        del argv[i:i + 1 + n]
        return valor

    esqueleto = sacar("--esqueleto", 1)
    malla = sacar("--malla", 1)
    salida = sacar("--salida", 1)
    json_out = sacar("--json", 1)
    listar = sacar("--listar-huesos") is not None
    declarar = sacar("--declarar") is not None
    sin_toldo = sacar("--sin-toldo") is not None
    sin_escalera = sacar("--sin-escalera") is not None
    sin_correas = sacar("--sin-correas") is not None
    sin_jinete = sacar("--sin-jinete") is not None
    no_unir = sacar("--sin-unir") is not None
    solo_calculo = sacar("--solo-calculo") is not None

    huesos_arg = []
    while "--huesos" in argv:
        i = argv.index("--huesos")
        del argv[i]
        while i < len(argv) and not argv[i].startswith("--"):
            huesos_arg.append(argv[i])
            del argv[i]

    def numero(clave, defecto):
        v = sacar(clave, 1)
        if v is None:
            return defecto
        try:
            return float(v[0])
        except ValueError:
            raise SystemExit("%s: no es un numero: %s" % (clave, v[0]))

    def entero(clave, defecto):
        v = sacar(clave, 1)
        if v is None:
            return defecto
        try:
            return int(v[0])
        except ValueError:
            raise SystemExit("%s: no es un entero: %s" % (clave, v[0]))

    presupuesto = entero("--presupuesto", PRESUPUESTO_GRUPO)
    # Se consumen aca y no en la rama que los usa: sacar borra
    # el flag de argv, y leerlo dos veces da el default.
    alto_lomo_cm = numero("--alto-lomo-cm", None)
    y_centro = numero("--y-centro", 0.0)
    d = Diseno(
        ancho=numero("--ancho-cm", 150.0),
        largo=numero("--largo-cm", 220.0),
        despeje=numero("--despeje-cm", 8.0),
        espesor=numero("--espesor-cm", 12.0),
        alto_bordo=numero("--alto-bordo-cm", 45.0),
        alto_poste=numero("--alto-poste-cm", 110.0),
        alto_cumbrera=numero("--alto-cumbrera-cm", 45.0),
        tablas=entero("--tablas", 7),
        barrotes=entero("--barrotes", 5),
        toldo=not sin_toldo,
        escalera=not sin_escalera,
        correas=not sin_correas,
        largo_escalera=numero("--largo-escalera-cm", 130.0),
        angulo_escalera=numero("--angulo-escalera", 20.0),
        peldanos=entero("--peldanos", 6),
        caida_correas=numero("--caida-correas-cm", 90.0),
        angulo_correas=numero("--angulo-correas", 12.0),
    )

    if argv:
        print("argumentos sin reconocer: %s" % " ".join(argv))
        print(__doc__)
        return 2

    huesos = {}
    if esqueleto:
        huesos = leer_huesos(esqueleto[0])
        if listar:
            sugeridos = [n for n, _p in sugerir_huesos_lomo(huesos)[:8]]
            _imprimir_huesos(huesos, sugeridos)
            print("\nPasan a --huesos los que recorren el lomo, en orden:")
            print('  --huesos %s' % " ".join('"%s"' % n for n in sugeridos[:3]))
            return 0

    # --- de donde sale el lomo: medido o declarado -----------------------
    if huesos_arg:
        lomo, falta = medidas_del_lomo(huesos, huesos_arg)
        if lomo is None:
            print("Estos huesos no estan en el esqueleto: %s" % ", ".join(falta))
            print("Correlo con --listar-huesos para ver los nombres reales.")
            return 2
        origen = "[MEDIDO] %s" % ", ".join(huesos_arg)
        medida = True
        linea = polilinea(huesos, huesos_arg)
    elif esqueleto and not declarar:
        sugeridos = [n for n, _p in sugerir_huesos_lomo(huesos)[:3]]
        lomo, falta = medidas_del_lomo(huesos, sugeridos)
        origen = ("[SUGERIDO] %s -- heuristico, confirmalo en NifSkope y "
                  "pasalo con --huesos" % ", ".join(sugeridos))
        medida = True
        linea = polilinea(huesos, sugeridos)
    else:
        if not declarar:
            print("Falta --esqueleto <skeleton.nif> (lo que hay que usar) o "
                  "--declarar con --alto-lomo-cm para bocetar sin el vanilla.")
            return 2
        if alto_lomo_cm is None:
            print("--declarar necesita --alto-lomo-cm: es la altura del lomo "
                  "en centimetros. Sin ese numero no hay donde apoyar nada.")
            return 2
        lomo = {"y_centro": y_centro,
                "largo_tramo": d.largo * CM_A_U,
                "z_lomo": alto_lomo_cm * CM_A_U,
                "x_medio": 0.0,
                "huesos": []}
        origen = ("[DECLARADO] sin --esqueleto: el lomo lo pusiste vos "
                  "(alto %.0f cm)" % alto_lomo_cm)
        medida = False
        linea = []

    estructura, cotas = construir(d, lomo)
    pesos, resumen = atadura(estructura, linea)
    controles = verificar(estructura, pesos, resumen, d, lomo, cotas, medida,
                          presupuesto, con_uv=None, con_huesos=bool(linea))
    inf = informe(estructura, pesos, resumen, d, lomo, cotas, medida,
                  controles, origen)

    objetos = []
    if not solo_calculo and bpy is None:
        print("[aviso] no hay Blender: se calculo y se verifico, pero no se "
              "escribio ninguna malla. Para eso:")
        print("  blender -b --python howdah_mamut.py -- %s"
              % " ".join(_argv_original()))
    if not solo_calculo and bpy is not None:
        objetos = construir_en_blender(
            estructura, pesos, cotas, d, unir=not no_unir,
            con_jinete=not sin_jinete, ruta_salida=salida[0] if salida else None)

    _imprimir_informe(inf)

    if json_out:
        import json
        with open(json_out[0], "w", encoding="utf-8") as fh:
            json.dump(inf, fh, indent=1, ensure_ascii=False, sort_keys=True)
        print("[json] %s" % json_out[0])

    if objetos:
        print("[blender] %d objeto(s)%s"
              % (len(objetos), (" -> %s" % salida[0]) if salida else ""))

    print("\nSiguiente paso (esto no lo hace ningun script):")
    print("  1. importar el mammoth.nif vanilla con PyNifly, pasandole su")
    print("     skeleton como reference_skel -- sin eso las posiciones de")
    print("     hueso que devuelve pueden no ser las del archivo (trampa 1);")
    print("  2. unir la howdah y HEREDAR el material, las flags y las")
    print("     particiones del vanilla: reconstruir eso a mano es inventar;")
    print("  3. exportar y recien ahi correr verificar_export.py contra el")
    print("     mammoth.nif original.")
    if inf["fallas"]:
        print("\nHay %d falla(s): no exportes todavia." % inf["fallas"])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
