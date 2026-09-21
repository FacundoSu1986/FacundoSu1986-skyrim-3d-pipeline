# -*- coding: utf-8 -*-
"""Las cajas de colision de un NIF, contra lo que hace el corpus vanilla.

    python scripts/colision_caja.py <archivo.nif> [<archivo.nif> ...]
    python scripts/colision_caja.py --autotest
    python scripts/colision_caja.py --falsificar <carpeta meshes>

Exit 0 si pasa, 1 si no pasa o si no hubo NADA que comprobar, 2 si los
argumentos no sirven. Python puro, sin Blender ni PyNifly.

POR QUE EXISTE

Armar la colision copiando un donante campo por campo es lo correcto para casi
todo --masa, capa, material, amortiguacion-- pero hay campos que dependen de
ESTA caja y copiarlos deja un cuerpo que no corresponde a su forma. Havok no
avisa.

LAS DOS REGLAS, Y CON QUE NUMERO ATRAS

Medido sobre las 22.394 mallas del corpus:

  REGLA radio     bhkRadius == min(semieje_menor, 0,1)
                  2.667 de 2.684 cajas (99,37 %), y COINCIDENCIA EXACTA: la
                  cuenta no se mueve entre tolerancia 1e-6 y 5e-2.
                  Las 17 excepciones son volumenes de trampa y de marcador
                  (traptripwire01, oiltrappuddle01, hammertablemarker...) que
                  se quedaron en 0,1 con un semieje mas chico, mas
                  argatedoor01 con 0,034.

  REGLA inercia   masa > 0  <=>  diagonal de inercia > 0
                  1.194 de 1.194 cuerpos con bhkBoxShape, en los DOS sentidos:
                  con masa 0, inercia cero en 383 de 383; con masa > 0,
                  inercia cero en 0 de 811. Sin una sola excepcion.

LO QUE **NO** SE PUEDE EXIGIR, Y ES IMPORTANTE

1. "bhkRadius es el semieje menor" a secas. Sobre las armas daba 62 de 62 y
   parecia una regla; sobre el corpus entero es 73,25 %. El subconjunto estaba
   sesgado porque las armas son finas y su semieje menor casi siempre cae
   debajo de 0,1.

2. "la diagonal de inercia tiene que ser > 0" a secas. Un tercio del corpus la
   tiene en CERO --383 de 1.194-- y son exactamente los cuerpos de masa 0. Esa
   regla, escrita sin la condicion, rechaza a Bethesda.

3. Cualquier formula para el VALOR de la inercia. Resultado negativo medido:
   contra m(a^2+b^2)/12, la razon va de 1,2 a 471 con mediana 7,1 y solo 1 de
   2.433 ejes cae dentro del +-10 %. Y tampoco se sostienen las PROPORCIONES
   entre los tres ejes: apenas el 3,6 % de las cajas queda dentro del 10 %, con
   desvio mediano del 51,5 %. Adaptar la inercia de un donante escalandola por
   la formula de la caja es una HEURISTICA razonable, no una regla -- y este
   control no la exige.

DE DONDE SALEN LOS OFFSETS

Todos por correlacion contra valores conocidos, no de una especificacion:

  bhkBoxShape    +4   radio        +16  medias extensiones (3 x f32)
  bhkRigidBody   +116 Ixx  +136 Iyy  +156 Izz   (matriz 3x4, paso de fila 16)
                 +180 masa         +224 motionSystem (u8)

El de las dimensiones ya estaba fijado por round-trip en
census/parser_colision.py. Los demas se ubicaron buscando, dentro del bloque,
los flotantes que coincidieran con lo que PyNifly reporta para el mismo
archivo, y exigiendo que el offset fuera el MISMO en varios archivos con
valores distintos.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import nif_nodos  # noqa: E402

RADIO_TOPE = 0.1
OFF_RADIO = 4
OFF_DIMS = 16
OFF_INERCIA = (116, 136, 156)
OFF_MASA = 180
OFF_MOTION = 224
MIN_CUERPO = 232          # hace falta llegar hasta motionSystem
MIN_CAJA = 32


def cajas(nif):
    """[{...}] por bhkRigidBody cuya forma es una bhkBoxShape."""
    bloques = nif["bloques"]
    d = nif["datos"]
    fuera = []
    for idx, (tipo, o, s) in enumerate(bloques):
        if not tipo.startswith("bhkRigidBody"):
            continue
        if s < MIN_CUERPO:
            fuera.append({"error": "%s de %d bytes: no llega a los campos "
                                   "que hay que mirar" % (tipo, s)})
            continue
        ref, = struct.unpack_from("<i", d, o)
        if not (0 <= ref < len(bloques)):
            fuera.append({"error": "%s apunta a la forma %d, que no existe"
                                   % (tipo, ref)})
            continue
        t2, o2, s2 = bloques[ref]
        if t2 != "bhkBoxShape":
            continue                      # otra forma: no es asunto de aca
        if s2 < MIN_CAJA:
            fuera.append({"error": "bhkBoxShape de %d bytes" % s2})
            continue
        radio, = struct.unpack_from("<f", d, o2 + OFF_RADIO)
        dims = struct.unpack_from("<3f", d, o2 + OFF_DIMS)
        masa, = struct.unpack_from("<f", d, o + OFF_MASA)
        inercia = [struct.unpack_from("<f", d, o + k)[0] for k in OFF_INERCIA]
        fuera.append({"cuerpo": tipo, "dims": list(dims), "radio": radio,
                      "masa": masa, "inercia": inercia,
                      "motion": d[o + OFF_MOTION]})
    return fuera


def radio_esperado(dims):
    return min(min(dims), RADIO_TOPE)


def juzgar(c):
    """(fallas, notas) de UNA caja."""
    fallas, notas = [], []
    if c.get("error"):
        return ["no se pudo leer: %s" % c["error"]], notas
    dims = c["dims"]
    if min(dims) <= 0:
        return ["la caja tiene un semieje <= 0: %s" % [round(x, 5)
                                                       for x in dims]], notas

    esperado = radio_esperado(dims)
    if abs(c["radio"] - esperado) > 1e-6:
        fallas.append(
            "REGLA radio: bhkRadius %.5f, se esperaba %.5f = min(semieje "
            "menor %.5f, %.1f). Vanilla lo cumple en 2.667 de 2.684 cajas "
            "(99,37 %%), exacto. Copiar el radio de un donante con otra caja "
            "es como se rompe."
            % (c["radio"], esperado, min(dims), RADIO_TOPE))

    hay_inercia = max(c["inercia"]) > 0
    if c["masa"] > 0 and not hay_inercia:
        fallas.append(
            "REGLA inercia: masa %.3f > 0 y la diagonal de inercia esta en "
            "cero. Vanilla: 0 de 811 cuerpos con masa > 0 tienen inercia "
            "cero. Havok con inercia cero da NaN -- el objeto sale volando al "
            "soltarlo y es invisible al equiparlo." % c["masa"])
    if c["masa"] <= 0 and hay_inercia:
        fallas.append(
            "REGLA inercia: masa %.3f y sin embargo hay inercia %s. Vanilla: "
            "383 de 383 cuerpos con masa 0 tienen la diagonal en cero."
            % (c["masa"], [round(x, 4) for x in c["inercia"]]))

    if hay_inercia and c["masa"] > 0:
        lados = [2.0 * x for x in dims]
        libro = [c["masa"] * (lados[a] ** 2 + lados[b] ** 2) / 12.0
                 for a, b in ((1, 2), (0, 2), (0, 1))]
        if min(libro) > 0:
            razon = [c["inercia"][k] / libro[k] for k in range(3)]
            notas.append(
                "OBS inercia / formula de caja = %s. En vanilla esa razon va "
                "de 1,2 a 471 con mediana 7,1: NO hay formula, y por eso esto "
                "no reprueba." % [round(x, 2) for x in razon])
    return fallas, notas


def revisar(rutas):
    total, con_falla, comprobadas = 0, 0, 0
    for ruta in rutas:
        try:
            nif = nif_nodos.leer(ruta)
        except Exception as e:
            print("== %s\n   NO se pudo leer: %s: %s"
                  % (os.path.basename(ruta), type(e).__name__, e))
            con_falla += 1
            continue
        cs = cajas(nif)
        print("== %s  (%d caja%s de colision)"
              % (os.path.basename(ruta), len(cs), "" if len(cs) == 1 else "s"))
        if not cs:
            print("   sin bhkBoxShape: nada que comprobar aca")
            continue
        for c in cs:
            total += 1
            fallas, notas = juzgar(c)
            if not c.get("error"):
                comprobadas += 1
                print("   %-14s dims=%s radio=%.5f masa=%.2f inercia=%s"
                      % (c["cuerpo"], [round(x, 5) for x in c["dims"]],
                         c["radio"], c["masa"],
                         [round(x, 3) for x in c["inercia"]]))
            for n in notas:
                print("      %s" % n)
            for f in fallas:
                print("      FALLA %s" % f)
            if fallas:
                con_falla += 1
    if comprobadas == 0:
        print("\nFALLA: cero cajas comprobadas -- no comprobar nada no es "
              "exito")
        return 1
    print("\n%d cajas comprobadas, %d con falla" % (comprobadas, con_falla))
    return 1 if con_falla else 0


# --------------------------------------------------------------------------
def _caja(dims, radio=None, masa=9.0, inercia=(2.5, 0.5, 2.9), motion=3):
    c = {"cuerpo": "bhkRigidBodyT", "dims": list(dims), "masa": masa,
         "inercia": list(inercia), "motion": motion}
    c["radio"] = radio_esperado(dims) if radio is None else radio
    return c


def autotest():
    fallas = []

    def exigir(cond, texto):
        if not cond:
            fallas.append(texto)

    # radio: los dos lados del tope
    f, _ = juzgar(_caja((0.28, 0.64, 0.06)))
    exigir(not f, "la caja fina correcta reprobo: %s" % f)
    f, _ = juzgar(_caja((3.5, 1.8, 2.0)))
    exigir(not f, "la caja gruesa correcta reprobo: %s" % f)
    exigir(abs(radio_esperado((3.5, 1.8, 2.0)) - 0.1) < 1e-9,
           "el tope de 0,1 no se aplica en una caja gruesa")
    exigir(abs(radio_esperado((0.28, 0.64, 0.06)) - 0.06) < 1e-9,
           "en una caja fina el radio tiene que ser el semieje menor")

    f, _ = juzgar(_caja((0.28, 0.64, 0.06), radio=0.0297))
    exigir(f and "REGLA radio" in f[0],
           "un radio copiado de otro donante no reprobo")
    f, _ = juzgar(_caja((3.5, 1.8, 2.0), radio=1.8))
    exigir(f and "REGLA radio" in f[0],
           "un radio por encima del tope no reprobo")

    # inercia: el bicondicional, en los dos sentidos
    f, _ = juzgar(_caja((0.28, 0.64, 0.06), masa=9.0, inercia=(0.0, 0.0, 0.0)))
    exigir(f and any("REGLA inercia" in x for x in f),
           "masa > 0 con inercia cero no reprobo")
    f, _ = juzgar(_caja((0.28, 0.64, 0.06), masa=0.0, inercia=(0.0, 0.0, 0.0)))
    exigir(not f, "masa 0 con inercia 0 reprobo, y vanilla lo hace 383 veces")
    f, _ = juzgar(_caja((0.28, 0.64, 0.06), masa=0.0, inercia=(1.0, 1.0, 1.0)))
    exigir(f and any("REGLA inercia" in x for x in f),
           "masa 0 CON inercia no reprobo")

    # una caja degenerada no se deja pasar en silencio
    f, _ = juzgar(_caja((0.0, 0.64, 0.06)))
    exigir(f, "un semieje en cero no reprobo")

    # la observacion de la formula NO reprueba
    f, n = juzgar(_caja((0.28, 0.64, 0.06), inercia=(999.0, 999.0, 999.0)))
    exigir(not f, "una inercia absurda reprobo: no hay formula para exigirla")
    exigir(any("formula de caja" in x for x in n),
           "no informo la razon contra la formula")

    print("autotest: %d comprobaciones, %d fallas" % (13, len(fallas)))
    for x in fallas:
        print("  FALLA %s" % x)
    return 1 if fallas else 0


def falsificar(raiz):
    """Sobre cajas REALES del corpus: torcer cada campo tiene que reprobar."""
    archivos = []
    for base, _, nombres in os.walk(raiz):
        for n in sorted(nombres):
            if n.lower().endswith(".nif"):
                archivos.append(os.path.join(base, n))
    usados, roturas, fallas = 0, 0, []
    for ruta in archivos:
        if usados >= 25:
            break
        try:
            cs = [c for c in cajas(nif_nodos.leer(ruta)) if not c.get("error")]
        except Exception:
            continue
        cs = [c for c in cs if min(c["dims"]) > 0]
        if not cs:
            continue
        c = cs[0]
        base_fallas, _ = juzgar(c)
        if base_fallas:
            continue              # esta caja ya no cumple: no sirve de patron
        usados += 1
        mutaciones = [
            ("radio a la mitad", dict(c, radio=c["radio"] * 0.5)),
            ("radio al doble", dict(c, radio=c["radio"] * 2.0 + 1e-3)),
            ("inercia a cero", dict(c, inercia=[0.0, 0.0, 0.0])),
            ("masa a cero", dict(c, masa=0.0)),
        ]
        for nombre, mut in mutaciones:
            roturas += 1
            f, _ = juzgar(mut)
            if not f:
                fallas.append("%s / %s: no reprobo"
                              % (os.path.basename(ruta), nombre))
    print("falsificar: %d cajas x 4 roturas = %d comprobaciones, %d fallas"
          % (usados, roturas, len(fallas)))
    for x in fallas:
        print("  FALLA %s" % x)
    if usados == 0:
        print("FALLA: cero cajas vanilla utilizables -- no comprobar nada no "
              "es exito")
        return 1
    return 1 if fallas else 0


def main(argv):
    if len(argv) == 1 and argv[0] == "--autotest":
        return autotest()
    if len(argv) == 2 and argv[0] == "--falsificar":
        return falsificar(argv[1])
    if argv and all(a.lower().endswith(".nif") for a in argv):
        return revisar(argv)
    print("uso: colision_caja.py <archivo.nif> [...] | --autotest | "
          "--falsificar <carpeta>")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
