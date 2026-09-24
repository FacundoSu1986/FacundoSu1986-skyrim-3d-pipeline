# -*- coding: utf-8 -*-
"""El material de un arma, contra el de las armas vanilla.

    python scripts/material_arma.py <arma.nif> [--clase <clase>]
    python scripts/material_arma.py --autotest
    python scripts/material_arma.py --censo <carpeta meshes>
    python scripts/material_arma.py --falsificar <carpeta meshes>

Exit 0 si pasa, 1 si no pasa o si no hubo NADA que medir, 2 si los argumentos
no sirven. Python puro, sin Blender: lee los bytes del NIF.

POR QUE EXISTE

El hacha de Tencent llego al juego con el shader `Default` y glossiness 20.
La malla y las texturas estaban bien y se veia opaca al lado de las vanilla.
La pieza principal de 16 de las 17 hachas a dos manos del corpus usa el shader
`EnvMap` (reflejo de un cubemap), y la glossiness mediana de las armas vanilla
es 80. Ninguno de los otros verificadores mira el material.

El 20 no lo eligio nadie: es lo que deja PyNifly cuando no se fija la
glossiness. Comprobado escribiendo un NIF con `createShapeFromData` y
leyendolo con este script: las formas sin ajustar salen con 20.

QUE LEE, Y COMO SE SABE QUE LO LEE BIEN

El BSLightingShaderProperty de SSE (BS 100). Despues de la ref al texture set
vienen: color emisivo (3f), multiplicador emisivo, modo de clamp (u32), alfa,
refraccion, glossiness, color especular (3f), intensidad especular, luz suave,
luz de borde, y un bloque final que depende del tipo de shader (EnvMap agrega
la escala del reflejo, 4 bytes; SkinTint y HairTint un color, 12; etc.).

Validado sobre el corpus entero, no sobre un par de archivos:

  * 74.489 de 74.489 bloques, en 22.393 NIF, CIERRAN EXACTO en su tamano
    declarado con esos extras por tipo. Un campo de mas o de menos en
    cualquier tipo lo romperia en miles de bloques.
  * El cierre no fija el ORDEN de los campos. Lo fijan los rangos: el alfa cae
    en [0, 1] y las tres componentes del color especular en [0, 1] en los
    74.489 bloques; la glossiness, que va entre los dos, no.
  * Los nombres y el orden coinciden con los de PyNifly (`Alpha`,
    `Refraction_Str`, `Glossiness`, `Spec_Color`, `Spec_Str`,
    `Soft_Lighting`, `Rim_Light_Power`).

Los tipos de shader que no aparecen en el corpus (7 ParallaxOcc, 8-10, 12,
13, 15, 17 en adelante) NO tienen su extra validado: con uno de esos el
material no se puede verificar, y se dice en vez de adivinar.

REGLAS (reprueban), cada una con su numero

  cierre    el bloque cierra exacto (y su texture set tambien).
            74.489 de 74.489.
  envmap    tipo EnvMap => flag Environment_Mapping (flags1, bit 7).
            6.843 de 6.843. La inversa NO: 13 bloques tienen el flag con
            otro tipo.
  glow      tipo Glow <=> flag Glow_Map (flags2, bit 6), en los dos sentidos.
            1.396 de 1.396 con el tipo tienen el flag, y 73.093 de 73.093 sin
            el tipo no lo tienen.
  cubemap   (armas) tipo EnvMap => cubemap en la ranura 4 del texture set.
            149 de 149 armas. En el corpus entero son 6.829 de 6.843: los 14
            que no lo tienen son de Alduin y de unas tunicas del Creation
            Club. Por eso es regla de ARMAS y no del motor.

OBSERVACIONES (se informan): de la pieza con mas triangulos, el tipo de
shader contra las armas de su clase; si falta la mascara `_m` (ranura 5; la
traen 143 de las 149 armas con EnvMap); si el cubemap no esta en una carpeta
`cubemaps`; y en que tramo de la distribucion vanilla caen la glossiness, la
intensidad especular y la escala del reflejo.

El shader `Default` en un arma NO es una regla: 46 de 198 armas vanilla lo
usan. Es una observacion con el numero de su clase al lado.

LA POBLACION

Las armas son los NIF bajo una carpeta `weapons`, sin los de primera persona
(`1stperson*`, que repiten el material del de tercera), cuya clase reconoce
`proporciones_arma.clase_por_nombre` -- el mismo clasificador, para que las
dos herramientas hablen de las mismas armas. De cada archivo cuenta la pieza
con mas triangulos. `--censo <carpeta meshes>` regenera la tabla y los
numeros de las reglas.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import censo_nif  # noqa: E402
import proporciones_arma  # noqa: E402

# Bytes que agrega cada tipo de shader al final del bloque, en SSE. Solo los
# tipos que aparecen en el corpus: el cierre exacto los valida. Un tipo que no
# esta aca no tiene su layout validado.
EXTRA_POR_TIPO = {0: 0, 1: 4, 2: 0, 3: 0, 4: 0, 5: 12, 6: 12, 11: 20,
                  14: 16, 16: 28}
TIPOS = {0: "Default", 1: "EnvMap", 2: "Glow", 3: "Parallax", 4: "FaceTint",
         5: "SkinTint", 6: "HairTint", 7: "ParallaxOcc", 11: "MultiLayer",
         14: "SparkleSnow", 16: "EyeEnvmap"}
TIPO_ENVMAP = 1
TIPO_GLOW = 2
BIT_ENVMAP = 7          # flags1
BIT_GLOW_MAP = 6        # flags2
RANURA_CUBEMAP = 4
RANURA_MASCARA = 5
# Lo que deja PyNifly si no se fija la glossiness (medido, ver arriba).
GLOSS_PYNIFLY = 20.0

# --- numeros del corpus (regenerar con --censo) ------------------------------
CORPUS = {"archivos": 22393, "bloques": 74489, "envmap": 6843,
          "envmap_cubemap": 6829, "glow": 1396, "sin_glow": 73093}

# De la pieza principal de cada arma. Cuantiles: (min, p10, p25, p50, p75,
# p90, max).
ARMAS = {
    "n": 198,
    "tipos": {"EnvMap": 149, "Default": 46, "Glow": 3},
    "envmap_con_mascara": 143,
    "envmap_con_cubemap": 149,
    "clases": {"arco": (19, 26), "baston": (7, 16), "daga": (12, 15),
               "espada": (22, 30), "flecha": (27, 38), "hacha1m": (9, 12),
               "hacha2m": (16, 17), "mandoble": (13, 16),
               "martillo2m": (12, 13), "maza": (12, 15)},
    "gloss": (6.0, 30.0, 50.0, 80.0, 80.0, 80.0, 164.0),
    "spec_str": (0.64, 0.8, 1.0, 1.0, 1.0, 1.87, 2.92),
    "env_scale": (0.2, 0.2, 0.5, 1.0, 1.0, 2.0, 5.0),
}
ETIQUETAS = ("min", "p10", "p25", "p50", "p75", "p90", "max")


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

def leer_texset(d, o, s):
    """(rutas, cierra) de un BSShaderTextureSet: i32 n + n strings con largo."""
    n, = struct.unpack_from("<i", d, o)
    if n < 0 or n > 64:
        return [], False
    p = o + 4
    rutas = []
    for _ in range(n):
        if p + 4 > o + s:
            return rutas, False
        largo, = struct.unpack_from("<I", d, p)
        p += 4
        rutas.append(d[p:p + largo].decode("cp1252", "replace").rstrip("\x00"))
        p += largo
    return rutas, p == o + s


def leer_material(d, o, s):
    """El BSLightingShaderProperty de SSE que empieza en `o` y mide `s`.

    Devuelve un dict. `cierra` dice si el bloque termina exacto donde declara
    su tamano; si es False, o si el tipo no esta validado (`validado` False),
    los numeros no son confiables y no se juzgan.
    """
    tipo, = struct.unpack_from("<I", d, o)
    _nombre, n_extra = struct.unpack_from("<iI", d, o + 4)
    q = o + 16 + 4 * n_extra
    m = {"tipo": tipo, "tipo_nombre": TIPOS.get(tipo, "tipo %d" % tipo),
         "validado": tipo in EXTRA_POR_TIPO, "cierra": False,
         "texset_ref": -1, "rutas": [], "texset_cierra": None}
    if q + 84 > o + s:
        return m
    f1, f2 = struct.unpack_from("<2I", d, q)
    m["texset_ref"], = struct.unpack_from("<i", d, q + 24)
    emisivo = struct.unpack_from("<3f", d, q + 28)
    em_mult, clamp = struct.unpack_from("<fI", d, q + 40)
    alfa, refraccion, gloss = struct.unpack_from("<3f", d, q + 48)
    especular = struct.unpack_from("<3f", d, q + 60)
    spec_str, suave, borde = struct.unpack_from("<3f", d, q + 72)
    m.update({"flags1": f1, "flags2": f2, "emisivo": emisivo,
              "emisivo_mult": em_mult, "clamp": clamp, "alfa": alfa,
              "refraccion": refraccion, "gloss": gloss,
              "spec_color": especular, "spec_str": spec_str,
              "luz_suave": suave, "luz_borde": borde, "env_scale": None})
    if m["validado"]:
        m["cierra"] = q + 84 + EXTRA_POR_TIPO[tipo] == o + s
        if tipo == TIPO_ENVMAP and m["cierra"]:
            m["env_scale"], = struct.unpack_from("<f", d, q + 84)
    return m


def piezas(nif):
    """[(nombre, triangulos, material)] de cada shape con BSLightingShaderProperty.

    Los shapes con otro shader (BSEffectShaderProperty, sin shader) se cuentan
    aparte en `otros`, para poder decir que se vieron.
    """
    fuera, otros = [], []
    d = nif.d
    for tipo_b, o, s in nif.bloques:
        if tipo_b not in censo_nif.TIPOS_SHAPE:
            continue
        p, nombre = nif._saltar_niavobject(o)
        p += 16                                          # esfera envolvente
        _skin, shader, _alfa = struct.unpack_from("<3i", d, p)
        tri, = struct.unpack_from("<H", d, p + 12 + 8)
        if not (0 <= shader < len(nif.bloques)) or \
                nif.bloques[shader][0] != "BSLightingShaderProperty":
            otros.append(nombre)
            continue
        _t, so, ss = nif.bloques[shader]
        m = leer_material(d, so, ss)
        ref = m["texset_ref"]
        if 0 <= ref < len(nif.bloques) and \
                nif.bloques[ref][0] == "BSShaderTextureSet":
            _t, to, ts = nif.bloques[ref]
            m["rutas"], m["texset_cierra"] = leer_texset(d, to, ts)
        fuera.append((nombre, tri, m))
    return fuera, otros


def principal(lista):
    """La pieza con mas triangulos; con empate, la primera."""
    return max(lista, key=lambda x: x[1]) if lista else None


def _ranura(m, i):
    r = m.get("rutas") or []
    return r[i] if len(r) > i else ""


def _bit(valor, bit):
    return bool((valor or 0) >> bit & 1)


# ---------------------------------------------------------------------------
# Juicio
# ---------------------------------------------------------------------------

def reglas(nombre, m, es_arma=True):
    """(fallas, comprobaciones) de UNA pieza."""
    fallas = []
    if not m["validado"]:
        return (["%s: shader %s, que no aparece en el corpus; su layout no "
                 "esta validado y el material no se puede verificar"
                 % (nombre, m["tipo_nombre"])], 1)
    if not m["cierra"] or m["texset_cierra"] is False:
        que = ("el BSLightingShaderProperty" if not m["cierra"]
               else "su BSShaderTextureSet")
        return (["REGLA cierre: %s: %s no termina donde declara su tamano "
                 "(74.489 de 74.489 vanilla si). Lo que sigue seria basura"
                 % (nombre, que)], 1)
    n = 1
    if m["tipo"] == TIPO_ENVMAP and not _bit(m["flags1"], BIT_ENVMAP):
        fallas.append("REGLA envmap: %s: shader EnvMap sin el flag "
                      "Environment_Mapping (flags1 bit 7); 6.843 de 6.843 "
                      "vanilla lo llevan" % nombre)
    n += 1
    tiene_glow = _bit(m["flags2"], BIT_GLOW_MAP)
    if (m["tipo"] == TIPO_GLOW) != tiene_glow:
        fallas.append(
            "REGLA glow: %s: shader %s %s el flag Glow_Map (flags2 bit 6); "
            "en vanilla van juntos en los dos sentidos (1.396 y 73.093)"
            % (nombre, m["tipo_nombre"], "con" if tiene_glow else "sin"))
    n += 1
    if es_arma and m["tipo"] == TIPO_ENVMAP:
        n += 1
        if not _ranura(m, RANURA_CUBEMAP):
            fallas.append("REGLA cubemap: %s: shader EnvMap sin cubemap en la "
                          "ranura 4; 149 de 149 armas vanilla con EnvMap lo "
                          "tienen" % nombre)
    return fallas, n


def _donde(v, cuantiles):
    """En que tramo de la distribucion vanilla cae `v`, dicho en palabras."""
    if v < cuantiles[0]:
        return "por DEBAJO del minimo vanilla (%g)" % cuantiles[0]
    if v > cuantiles[-1]:
        return "por ENCIMA del maximo vanilla (%g)" % cuantiles[-1]
    iguales = [e for e, c in zip(ETIQUETAS, cuantiles) if c == v]
    if iguales:
        return "igual a %s de las armas vanilla" % "/".join(iguales)
    for i in range(len(cuantiles) - 1):
        if cuantiles[i] < v < cuantiles[i + 1]:
            return "entre %s (%g) y %s (%g)" % (
                ETIQUETAS[i], cuantiles[i], ETIQUETAS[i + 1], cuantiles[i + 1])
    return "?"


def observaciones(nombre, m, es_principal, clase):
    """Las OBS de una pieza. Los tramos vanilla son de PIEZAS PRINCIPALES:
    una pieza secundaria (la sangre del filo, una gema) no se compara contra
    ellos -- la sangre de daedricbattleaxe tiene glossiness 500 y seria
    'por encima del maximo' sin que eso diga nada."""
    notas = []
    if es_principal:
        env, tot = ARMAS["clases"].get(clase, (None, None))
        de_clase = ("; de su clase (%s), %d de %d" % (clase, env, tot)
                    if env is not None else "")
        notas.append("OBS shader %s en la pieza principal. En vanilla, la "
                     "pieza principal de %d de %d armas usa EnvMap%s"
                     % (m["tipo_nombre"], ARMAS["tipos"]["EnvMap"],
                        ARMAS["n"], de_clase))
    if m["tipo"] == TIPO_ENVMAP:
        if not _ranura(m, RANURA_MASCARA):
            notas.append("OBS sin mascara _m en la ranura 5: el reflejo cubre "
                         "la pieza entera. La traen %d de %d armas con EnvMap"
                         % (ARMAS["envmap_con_mascara"],
                            ARMAS["envmap_con_cubemap"]))
        cub = _ranura(m, RANURA_CUBEMAP).lower().replace("/", "\\")
        if cub and "\\cubemaps\\" not in cub:
            notas.append("OBS el cubemap (%s) no esta en una carpeta "
                         "cubemaps: las armas vanilla usan los de "
                         "textures\\cubemaps. Si es propio, tiene que viajar "
                         "con el mod" % _ranura(m, RANURA_CUBEMAP))
    # A 2 decimales, como la tabla: un float32 que otra herramienta guardo
    # como "2" puede no ser 2.0 exacto, y entonces no igualaba al p90.
    gloss = round(m["gloss"], 2)
    spec = round(m["spec_str"], 2)
    pynifly = (" -- es el valor que deja PyNifly si no se fija"
               if gloss == GLOSS_PYNIFLY else "")
    if not es_principal:
        notas.append("OBS glossiness %g%s, intensidad especular %g (pieza "
                     "secundaria: la tabla vanilla es de piezas principales)"
                     % (gloss, pynifly, spec))
        return notas
    if m["tipo"] == TIPO_ENVMAP:
        esc = round(m["env_scale"], 2)
        notas.append("OBS escala del reflejo %g: %s"
                     % (esc, _donde(esc, ARMAS["env_scale"])))
    notas.append("OBS glossiness %g: %s%s"
                 % (gloss, _donde(gloss, ARMAS["gloss"]), pynifly))
    notas.append("OBS intensidad especular %g: %s"
                 % (spec, _donde(spec, ARMAS["spec_str"])))
    return notas


def juzgar(lista, clase=None, es_arma=True):
    """(fallas, notas, comprobaciones) de todas las piezas de un NIF."""
    fallas, notas, n = [], [], 0
    if not lista:
        return (["ninguna pieza con BSLightingShaderProperty: no hay material "
                 "que medir"], [], 0)
    prin = principal(lista)
    for pieza in lista:
        nombre, tri, m = pieza
        f, k = reglas(nombre, m, es_arma)
        fallas.extend(f)
        n += k
        if f or not es_arma:
            continue
        notas.append("-- %s (%d tri%s): shader %s"
                     % (nombre, tri, ", principal" if pieza is prin else "",
                        m["tipo_nombre"]))
        notas.extend("   " + x for x in
                     observaciones(nombre, m, pieza is prin, clase))
    return fallas, notas, n


def revisar(ruta, clase=None):
    if clase is None:
        clase = proporciones_arma.clase_por_nombre(ruta)
    print("== %s" % os.path.basename(ruta))
    try:
        nif = censo_nif.Nif(ruta)
    except Exception as e:
        print("   no se pudo leer: %s: %s" % (type(e).__name__, e))
        return 1
    if nif.bs != 100:
        print("   BS %d: el layout del material esta validado solo en SSE "
              "(BS 100)" % nif.bs)
        return 1
    lista, otros = piezas(nif)
    fallas, notas, n = juzgar(lista, clase)
    if clase is None:
        print("   clase no reconocida por el nombre; sin comparacion por "
              "clase (pasala con --clase: %s)"
              % ", ".join(sorted(ARMAS["clases"])))
    for x in notas:
        print("   %s" % x)
    if otros:
        print("   (%d pieza(s) sin BSLightingShaderProperty, no se miran: %s)"
              % (len(otros), ", ".join(otros)))
    for f in fallas:
        print("   FALLA %s" % f)
    print("   %d comprobaciones, %d fallas" % (n, len(fallas)))
    # Cero comprobaciones no llega aca sin falla: juzgar() reprueba la lista
    # vacia, y cada pieza cuenta al menos el cierre.
    return 1 if fallas else 0


# ---------------------------------------------------------------------------
# Autotest: bloques construidos aca, con la respuesta conocida
# ---------------------------------------------------------------------------

def _bloque(tipo=0, f1=0, f2=0, gloss=80.0, spec_str=1.0, env=1.0,
            extra=None, texset_ref=1):
    """BSLightingShaderProperty de SSE armado byte a byte."""
    b = struct.pack("<IiI", tipo, -1, 0)            # tipo, nombre, n extra
    b += struct.pack("<i", -1)                      # controller
    b += struct.pack("<2I", f1, f2)
    b += struct.pack("<4f", 0.0, 0.0, 1.0, 1.0)     # UV offset, UV scale
    b += struct.pack("<i", texset_ref)
    b += struct.pack("<3f", 0.1, 0.2, 0.3)          # emisivo
    b += struct.pack("<fI", 1.5, 3)                 # mult, clamp
    b += struct.pack("<3f", 1.0, 0.0, gloss)        # alfa, refraccion, gloss
    b += struct.pack("<3f", 1.0, 0.9, 0.8)          # color especular
    b += struct.pack("<3f", spec_str, 0.3, 2.0)     # spec, suave, borde
    n_extra = EXTRA_POR_TIPO.get(tipo, 0) if extra is None else extra
    if tipo == TIPO_ENVMAP and n_extra >= 4:
        b += struct.pack("<f", env) + b"\x00" * (n_extra - 4)
    else:
        b += b"\x00" * n_extra
    return b


def _texset(rutas):
    b = struct.pack("<i", len(rutas))
    for r in rutas:
        e = r.encode("cp1252")
        b += struct.pack("<I", len(e)) + e
    return b


def _mat(tipo=0, f1=0, f2=0, rutas=("a.dds", "a_n.dds"), **kw):
    b = _bloque(tipo, f1, f2, **kw)
    m = leer_material(b, 0, len(b))
    t = _texset(list(rutas))
    m["rutas"], m["texset_cierra"] = leer_texset(t, 0, len(t))
    return m


def autotest():
    fallas = []
    cuenta = [0]

    def exigir(cond, texto):
        cuenta[0] += 1
        if not cond:
            fallas.append(texto)

    env_f1 = 1 << BIT_ENVMAP
    glow_f2 = 1 << BIT_GLOW_MAP
    rutas_env = ("a.dds", "a_n.dds", "", "", r"textures\cubemaps\x_e.dds",
                 "a_m.dds")

    # 1. la lectura devuelve lo que se escribio
    m = _mat(TIPO_ENVMAP, env_f1, 0, rutas_env, gloss=64.0, spec_str=1.25,
             env=0.75)
    exigir(m["cierra"], "un EnvMap bien armado no cierra")
    exigir(m["gloss"] == 64.0, "gloss %r" % m["gloss"])
    exigir(m["spec_str"] == 1.25, "spec_str %r" % m["spec_str"])
    exigir(m["env_scale"] == 0.75, "env_scale %r" % m["env_scale"])
    exigir(m["alfa"] == 1.0 and m["refraccion"] == 0.0,
           "alfa/refraccion %r %r" % (m["alfa"], m["refraccion"]))
    exigir(abs(m["spec_color"][1] - 0.9) < 1e-6, "color especular corrido")
    exigir(m["clamp"] == 3, "clamp %r" % m["clamp"])
    exigir(m["rutas"][RANURA_CUBEMAP].endswith("x_e.dds"),
           "ranura 4: %r" % m["rutas"])
    exigir(m["texset_cierra"] is True, "el texture set no cierra")

    # 2. cada tipo validado cierra con su extra, y NO con 4 bytes de mas o
    #    de menos: el cierre tiene que poder fallar
    for tipo, extra in sorted(EXTRA_POR_TIPO.items()):
        exigir(_mat(tipo)["cierra"], "tipo %d no cierra con %d" % (tipo, extra))
        exigir(not _mat(tipo, extra=extra + 4)["cierra"],
               "tipo %d cierra con 4 bytes de mas" % tipo)
        if extra:
            exigir(not _mat(tipo, extra=extra - 4)["cierra"],
                   "tipo %d cierra con 4 bytes de menos" % tipo)
    no_val = _mat(7, extra=8)
    exigir(not no_val["validado"], "ParallaxOcc (7) no deberia estar validado")
    f, _n = reglas("x", no_val)
    exigir(len(f) == 1 and "no esta validado" in f[0],
           "un tipo no validado tiene que reprobar diciendo por que: %r" % f)

    # 3. las reglas pasan en el caso bueno y fallan cada una en el suyo
    bueno = _mat(TIPO_ENVMAP, env_f1, 0, rutas_env)
    f, n = reglas("x", bueno)
    exigir(not f and n == 4, "EnvMap correcto: fallas %r, %d comprobaciones"
           % (f, n))
    f, _n = reglas("x", _mat(TIPO_ENVMAP, 0, 0, rutas_env))
    exigir(len(f) == 1 and f[0].startswith("REGLA envmap"),
           "EnvMap sin flag: %r" % f)
    f, _n = reglas("x", _mat(TIPO_ENVMAP, env_f1, 0, ("a.dds", "a_n.dds")))
    exigir(len(f) == 1 and f[0].startswith("REGLA cubemap"),
           "EnvMap sin cubemap: %r" % f)
    f, _n = reglas("x", _mat(TIPO_ENVMAP, env_f1, 0, ("a.dds", "a_n.dds")),
                   es_arma=False)
    exigir(not f, "sin cubemap fuera de las armas no es regla: %r" % f)
    f, _n = reglas("x", _mat(TIPO_GLOW, 0, 0))
    exigir(len(f) == 1 and f[0].startswith("REGLA glow"),
           "Glow sin flag: %r" % f)
    f, _n = reglas("x", _mat(0, 0, glow_f2))
    exigir(len(f) == 1 and f[0].startswith("REGLA glow"),
           "flag Glow_Map sin el tipo: %r" % f)
    f, _n = reglas("x", _mat(TIPO_GLOW, 0, glow_f2))
    exigir(not f, "Glow con su flag: %r" % f)
    f, _n = reglas("x", _mat(0, env_f1, 0))
    exigir(not f, "el flag Environment_Mapping sin el tipo NO es regla "
                  "(13 vanilla lo tienen): %r" % f)
    f, _n = reglas("x", _mat(TIPO_ENVMAP, env_f1, 0, rutas_env, extra=0))
    exigir(len(f) == 1 and f[0].startswith("REGLA cierre"),
           "un bloque que no cierra: %r" % f)

    # 4. un texture set que no cierra tambien reprueba
    malo = _mat(TIPO_ENVMAP, env_f1, 0, rutas_env)
    t = _texset(list(rutas_env)) + b"\x00\x00"
    malo["rutas"], malo["texset_cierra"] = leer_texset(t, 0, len(t))
    f, _n = reglas("x", malo)
    exigir(len(f) == 1 and "BSShaderTextureSet" in f[0],
           "texture set con bytes de mas: %r" % f)

    # 5. el juicio de un NIF entero
    f, notas, n = juzgar([], "hacha2m")
    exigir(f and n == 0, "sin piezas tiene que reprobar con 0 comprobaciones")
    hacha = [("Hoja", 8000, _mat(0, 0, 0, gloss=20.0))]
    f, notas, n = juzgar(hacha, "hacha2m")
    texto = "\n".join(notas)
    exigir(not f, "el Default no es regla: %r" % f)
    exigir("de su clase (hacha2m), 16 de 17" in texto,
           "no dio el numero de la clase: %s" % texto)
    exigir("PyNifly" in texto and "entre min (6) y p10 (30)" in texto,
           "glossiness 20 mal ubicada: %s" % texto)

    # 6. _donde
    q = (1.0, 2.0, 3.0, 5.0, 5.0, 5.0, 9.0)
    exigir(_donde(0.5, q).startswith("por DEBAJO"), _donde(0.5, q))
    exigir(_donde(10.0, q).startswith("por ENCIMA"), _donde(10.0, q))
    exigir(_donde(5.0, q) == "igual a p50/p75/p90 de las armas vanilla",
           _donde(5.0, q))
    exigir(_donde(2.5, q) == "entre p10 (2) y p25 (3)", _donde(2.5, q))

    print("autotest: %d comprobaciones, %d fallas" % (cuenta[0], len(fallas)))
    for x in fallas:
        print("  FALLA %s" % x)
    return 1 if fallas else 0


# ---------------------------------------------------------------------------
# Censo y falsificacion sobre el corpus
# ---------------------------------------------------------------------------

def _es_arma(ruta):
    partes = ruta.lower().replace("/", "\\").split("\\")
    nombre = partes[-1]
    return ("weapons" in partes[:-1] and not nombre.startswith("1stperson")
            and proporciones_arma.clase_por_nombre(nombre) is not None)


def _recorrer(raiz):
    for base, _, nombres in os.walk(raiz):
        for nom in sorted(nombres):
            if nom.lower().endswith(".nif"):
                yield os.path.join(base, nom)


def _cuantiles(v):
    """(min, p10, p25, p50, p75, p90, max), redondeados a 2 decimales."""
    v = sorted(v)
    q = [v[min(len(v) - 1, int(len(v) * p))]
         for p in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9)]
    return tuple(round(x, 2) for x in q + [v[-1]])


def censo(raiz):
    """Regenera CORPUS y ARMAS. Tarda: recorre todos los NIF."""
    c = dict.fromkeys(("archivos", "bloques", "cierran", "envmap",
                       "envmap_flag", "envmap_cubemap", "glow", "glow_flag",
                       "sin_glow", "sin_glow_sin_flag", "fuera_de_rango"), 0)
    armas = []
    for ruta in _recorrer(raiz):
        try:
            nif = censo_nif.Nif(ruta)
        except Exception:
            continue
        if nif.bs != 100:
            continue
        c["archivos"] += 1
        lista, _otros = piezas(nif)
        for tipo_b, o, s in nif.bloques:
            if tipo_b != "BSLightingShaderProperty":
                continue
            m = leer_material(nif.d, o, s)
            c["bloques"] += 1
            c["cierran"] += m["cierra"]
            if not m["cierra"]:
                continue
            if not (0 <= m["alfa"] <= 1 and
                    all(0 <= x <= 1.0001 for x in m["spec_color"])):
                c["fuera_de_rango"] += 1
            ref = m["texset_ref"]
            rutas = []
            if 0 <= ref < len(nif.bloques) and \
                    nif.bloques[ref][0] == "BSShaderTextureSet":
                rutas, _ok = leer_texset(nif.d, *nif.bloques[ref][1:])
            if m["tipo"] == TIPO_ENVMAP:
                c["envmap"] += 1
                c["envmap_flag"] += _bit(m["flags1"], BIT_ENVMAP)
                c["envmap_cubemap"] += bool(len(rutas) > 4 and rutas[4])
            glow = _bit(m["flags2"], BIT_GLOW_MAP)
            if m["tipo"] == TIPO_GLOW:
                c["glow"] += 1
                c["glow_flag"] += glow
            else:
                c["sin_glow"] += 1
                c["sin_glow_sin_flag"] += not glow
        if _es_arma(ruta) and lista:
            armas.append((ruta, principal(lista)[2]))
    print("corpus: %(archivos)d NIF de BS 100, %(bloques)d bloques, "
          "%(cierran)d cierran, %(fuera_de_rango)d con alfa o especular "
          "fuera de [0, 1]" % c)
    print("  EnvMap %(envmap)d: con flag %(envmap_flag)d, con cubemap "
          "%(envmap_cubemap)d" % c)
    print("  Glow %(glow)d: con flag %(glow_flag)d;  sin Glow %(sin_glow)d: "
          "sin flag %(sin_glow_sin_flag)d" % c)
    if not armas:
        print("ninguna arma en %s" % raiz)
        return 1
    tipos, clases = {}, {}
    for ruta, m in armas:
        tipos[m["tipo_nombre"]] = tipos.get(m["tipo_nombre"], 0) + 1
        clase = proporciones_arma.clase_por_nombre(os.path.basename(ruta))
        e, t = clases.get(clase, (0, 0))
        clases[clase] = (e + (m["tipo"] == TIPO_ENVMAP), t + 1)
    env = [m for _r, m in armas if m["tipo"] == TIPO_ENVMAP]
    print("ARMAS = {")
    print('    "n": %d,' % len(armas))
    print('    "tipos": %r,' % dict(sorted(tipos.items(),
                                            key=lambda x: -x[1])))
    print('    "envmap_con_mascara": %d,'
          % sum(1 for m in env if _ranura(m, RANURA_MASCARA)))
    print('    "envmap_con_cubemap": %d,'
          % sum(1 for m in env if _ranura(m, RANURA_CUBEMAP)))
    print('    "clases": %r,' % dict(sorted(clases.items())))
    print('    "gloss": %r,' % (_cuantiles([m["gloss"] for _r, m in armas]),))
    print('    "spec_str": %r,'
          % (_cuantiles([m["spec_str"] for _r, m in armas]),))
    print('    "env_scale": %r,' % (_cuantiles([m["env_scale"] for m in env]),))
    print("}")
    return 0


def _con_flags(d, so, n_extra, f1=None, f2=None, tipo=None):
    """Copia de `d` con flags o tipo cambiados en el bloque que empieza en so."""
    d = bytearray(d)
    q = so + 16 + 4 * n_extra
    if tipo is not None:
        struct.pack_into("<I", d, so, tipo)
    if f1 is not None:
        struct.pack_into("<I", d, q, f1)
    if f2 is not None:
        struct.pack_into("<I", d, q + 4, f2)
    return bytes(d)


def falsificar(raiz):
    """Rompe el material de armas vanilla reales y exige que se note.

    Antes de romper: ninguna arma vanilla tiene que reprobar (una regla que
    reprueba al corpus del que salio esta mal). Despues, cinco roturas:

      sin_flag_env   EnvMap con el bit 7 de flags1 apagado     -> envmap
      flag_glow      bit 6 de flags2 prendido sin tipo Glow    -> glow
      tipo_glow      Default pasado a Glow, mismo tamano       -> glow
      tipo_envmap    Default pasado a EnvMap: faltan 4 bytes   -> cierre
      sin_cubemap    EnvMap con la ranura 4 vacia              -> cubemap

    Las cuatro primeras cambian bytes del bloque y se releen. La quinta
    reescribe el texture set y lo relee: vaciar una ruta cambia el tamano del
    bloque, y en vez de reescribir la tabla de tamanos del NIF se lee el
    texture set nuevo por separado.
    """
    esperada = {"sin_flag_env": "REGLA envmap", "flag_glow": "REGLA glow",
                "tipo_glow": "REGLA glow", "tipo_envmap": "REGLA cierre",
                "sin_cubemap": "REGLA cubemap"}
    roturas = dict.fromkeys(esperada, 0)
    escapes = dict.fromkeys(esperada, 0)
    falsos, armas, piezas_vistas = [], 0, 0

    def probar(clave, nombre, m):
        roturas[clave] += 1
        f, _n = reglas(nombre, m)
        if not any(x.startswith(esperada[clave]) for x in f):
            escapes[clave] += 1

    for ruta in _recorrer(raiz):
        if not _es_arma(ruta):
            continue
        try:
            nif = censo_nif.Nif(ruta)
        except Exception:
            continue
        if nif.bs != 100:
            continue
        lista, _otros = piezas(nif)
        if not lista:
            continue
        armas += 1
        f, _notas, n = juzgar(lista)
        piezas_vistas += len(lista)
        if f or n == 0:
            falsos.append((ruta, f))
            continue
        d = nif.d
        for tipo_b, so, ss in nif.bloques:
            if tipo_b != "BSLightingShaderProperty":
                continue
            m = leer_material(d, so, ss)
            n_extra, = struct.unpack_from("<I", d, so + 8)
            rutas, ok = [], None
            ref = m["texset_ref"]
            if 0 <= ref < len(nif.bloques) and \
                    nif.bloques[ref][0] == "BSShaderTextureSet":
                rutas, ok = leer_texset(d, *nif.bloques[ref][1:])

            def releer(nuevo):
                x = leer_material(nuevo, so, ss)
                x["rutas"], x["texset_cierra"] = rutas, ok
                return x

            if m["tipo"] == TIPO_ENVMAP and len(rutas) > RANURA_CUBEMAP:
                probar("sin_flag_env", ruta, releer(_con_flags(
                    d, so, n_extra, f1=m["flags1"] & ~(1 << BIT_ENVMAP))))
                vacio = list(rutas)
                vacio[RANURA_CUBEMAP] = ""
                t = _texset(vacio)
                x = dict(m)
                x["rutas"], x["texset_cierra"] = leer_texset(t, 0, len(t))
                probar("sin_cubemap", ruta, x)
            if m["tipo"] != TIPO_GLOW:
                probar("flag_glow", ruta, releer(_con_flags(
                    d, so, n_extra, f2=m["flags2"] | (1 << BIT_GLOW_MAP))))
            if m["tipo"] == 0:
                probar("tipo_glow", ruta,
                       releer(_con_flags(d, so, n_extra, tipo=TIPO_GLOW)))
                probar("tipo_envmap", ruta,
                       releer(_con_flags(d, so, n_extra, tipo=TIPO_ENVMAP)))
    print("armas vanilla: %d (%d piezas con material); reprobadas sin romper "
          "nada: %d" % (armas, piezas_vistas, len(falsos)))
    for ruta, f in falsos[:5]:
        print("   FALSO POSITIVO %s: %s" % (ruta, f[:1]))
    for clave in esperada:
        print("   %-13s %5d roturas, %d sin detectar"
              % (clave, roturas[clave], escapes[clave]))
    total = sum(roturas.values())
    if armas == 0 or total == 0 or any(v == 0 for v in roturas.values()):
        print("FALLA: alguna rotura no se pudo probar ni una vez -- no "
              "comprobar nada no es exito")
        return 1
    return 1 if falsos or any(escapes.values()) else 0


def main(argv):
    if argv == ["--autotest"]:
        return autotest()
    if len(argv) == 2 and argv[0] == "--censo":
        return censo(argv[1])
    if len(argv) == 2 and argv[0] == "--falsificar":
        return falsificar(argv[1])
    clase = None
    if len(argv) == 3 and argv[1] == "--clase":
        clase = argv[2]
        argv = argv[:1]
    if len(argv) == 1 and argv[0].lower().endswith(".nif"):
        return revisar(argv[0], clase)
    print("uso: material_arma.py <arma.nif> [--clase <clase>] | --autotest | "
          "--censo <carpeta meshes> | --falsificar <carpeta meshes>")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
