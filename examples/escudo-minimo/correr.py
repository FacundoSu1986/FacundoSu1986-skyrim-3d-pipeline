# -*- coding: utf-8 -*-
"""examples/escudo-minimo: de una "pieza de IA" a un NIF verificado, sin un
byte del juego.

    python examples/escudo-minimo/correr.py [--blender <blender.exe>] [--trabajo <carpeta>]

Corre en orden los pasos de las dos skills con los planes de esta carpeta, y
al final lee el NIF con lectores que no son PyNifly. Blender sale de
--blender o de la variable BLENDER_EXE; el donante y el export necesitan
ademas el addon PyNifly en ese Blender. Lo que no se puede correr se saltea
DICIENDOLO, y entonces el resultado es "incompleto", no "listo".

La carpeta de trabajo (por defecto `trabajo/`, al lado de este archivo) se
pisa en cada corrida.

Exit 0  todos los pasos corrieron y el NIF paso la verificacion.
     1  un paso que corrio fallo.
     2  los argumentos no sirven.
     3  incompleto: falta Blender o PyNifly. Lo que corrio, anduvo.
"""
import json
import os
import re
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
MODELO_IA = os.path.join(RAIZ, "skills", "modelo-ia-a-skyrim", "scripts")
ASSET_NUEVO = os.path.join(RAIZ, "skills", "asset-nuevo-skyrim", "scripts")
CENSUS = os.path.join(RAIZ, "census")
for _d in (AQUI, ASSET_NUEVO, CENSUS):
    if _d not in sys.path:
        sys.path.insert(0, _d)

import colision_caja  # noqa: E402
import nif_nodos  # noqa: E402
import parser_colision  # noqa: E402
import parser_nif  # noqa: E402
import parser_uv  # noqa: E402
import pieza_ia  # noqa: E402

EXIT_OK, EXIT_FALLA, EXIT_ARGS, EXIT_INCOMPLETO = 0, 1, 2, 3
PRN = "SHIELD"          # el nodo del que cuelga un escudo
PRESUPUESTO = 500       # triangulos de la baja: la placa trae 12
TOL = 0.01              # unidades de Skyrim (1/70 de metro)

PLAN_MARCO = os.path.join(AQUI, "plan_marco.json")
PLAN_NIF = os.path.join(AQUI, "plan_nif.json")

# (numero, que hace, que necesita). Cada paso usa lo que dejo el anterior.
PASOS = (
    (0, "la pieza de IA (pieza_ia.py)", "python"),
    (1, "medirla (medir_parte.py)", "blender"),
    (2, "soldar y presupuestar (preparar_parte.py)", "blender"),
    (3, "llevarla al marco del SHIELD (al_marco.py)", "blender"),
    (4, "el donante sintetico (donante_sintetico.py)", "pynifly"),
    (5, "exportar el NIF (exportar_nif.py)", "pynifly"),
    (6, "verificarlo sin PyNifly (nif_nodos, colision_caja, census)", "python"),
)
QUE_FALTA = {
    "blender": "requiere Blender (--blender o BLENDER_EXE)",
    "pynifly": "requiere el addon PyNifly en ese Blender",
}


def leer_json(ruta):
    with open(ruta, encoding="utf-8") as fh:
        return json.load(fh)


class Corrida:
    def __init__(self, blender, trabajo):
        self.blender = blender
        self.trabajo = trabajo
        self.plan_marco = leer_json(PLAN_MARCO)
        self.plan_nif = leer_json(PLAN_NIF)

    def ruta(self, *partes):
        return os.path.join(self.trabajo, *partes)

    @property
    def nif(self):
        return self.ruta(*self.plan_nif["salida"].split("/"))

    def _en_blender(self, n, script, args, resumen=None):
        """(ok, detalle): corre `script` en Blender y guarda su salida en
        log_<n>.txt. `correr(main)` hace que un script que revienta salga
        con 1, no con 0. `resumen`, un patron con un grupo: lo que el script
        imprimio que vale la pena mostrar."""
        p = subprocess.run([self.blender, "-b", "--factory-startup", "--python",
                            script, "--"] + args, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        log = self.ruta("log_%d.txt" % n)
        with open(log, "w", encoding="utf-8") as fh:
            fh.write(p.stdout + p.stderr)
        if p.returncode != 0:
            cola = (p.stdout + p.stderr).strip().splitlines()[-12:]
            return False, "salio con %d (%s):\n      %s" % (
                p.returncode, os.path.basename(log), "\n      ".join(cola))
        m = re.search(resumen, p.stdout, re.M) if resumen else None
        return True, "%s (%s)" % (m.group(1) if m else "sin resumen",
                                  os.path.basename(log))

    def paso_0(self):
        n = pieza_ia.escribir(self.ruta("pieza_ia.glb"))
        return True, "%d bytes, %d triangulos, %d vertices sin soldar" % (
            n, pieza_ia.TRIANGULOS, 4 * len(pieza_ia.caras()))

    def paso_1(self):
        ok, det = self._en_blender(1, os.path.join(MODELO_IA, "medir_parte.py"),
                                   [self.ruta("pieza_ia.glb"), "--json",
                                    self.ruta("medida.json")])
        if not ok:
            return ok, det
        m = leer_json(self.ruta("medida.json"))[0]
        return True, "%d triangulos, %d cuerpo(s), %s" % (
            m["triangulos"], m["cuerpos_sueltos"],
            "cerrado" if m["cerrado"] else "ABIERTO")

    def paso_2(self):
        return self._en_blender(2, os.path.join(MODELO_IA, "preparar_parte.py"),
                                [self.ruta("pieza_ia.glb"), self.ruta("escudo.blend"),
                                 str(PRESUPUESTO), "--force"],
                                r"^\[escudo\] (.*? tris)")

    def paso_3(self):
        return self._en_blender(3, os.path.join(MODELO_IA, "al_marco.py"),
                                [PLAN_MARCO, self.ruta("escudo.blend"),
                                 self.ruta("escudo_marco.blend"), "--force"],
                                r"^\[marco\] (escala [0-9.]+)")

    def paso_4(self):
        return self._en_blender(4, os.path.join(ASSET_NUEVO, "donante_sintetico.py"),
                                [self.ruta("donante.nif"), "--prn", PRN, "--force"],
                                r"^\[donante\] .* escrito: (.*)$")

    def paso_5(self):
        # exportar_nif resuelve las rutas del plan desde SU carpeta: la copia
        # va a la de trabajo, junto al donante.
        plan = self.ruta("plan_nif.json")
        shutil.copyfile(PLAN_NIF, plan)
        return self._en_blender(5, os.path.join(ASSET_NUEVO, "exportar_nif.py"),
                                [plan, self.ruta("escudo_marco.blend"), "--force"],
                                r"^\[nif\] .* escrito y releido: (.*?) ->")

    def paso_6(self):
        fallas, hechas = verificar(self.nif, self.plan_marco, self.plan_nif)
        if not hechas:
            return False, "cero comprobaciones: no comprobar nada no es exito"
        if fallas:
            return False, "%d de %d fallan:\n      %s" % (
                len(fallas), hechas, "\n      ".join(fallas))
        return True, "%d comprobaciones, 0 fallas" % hechas


def verificar(ruta, plan_marco, plan_nif):
    """(fallas, cuantas se hicieron) sobre el NIF final, con lectores que
    no son PyNifly: nif_nodos (estructura), colision_caja (las REGLAS de la
    colision vanilla) y los parsers de census/ (la geometria). Los numeros
    esperados salen de los dos planes, no de lo que dijo el export."""
    fallas, hechas = [], [0]

    def exigir(cond, texto):
        hechas[0] += 1
        if not cond:
            fallas.append(texto)

    crudo = nif_nodos.leer(ruta)
    raiz = crudo["nodos"].get(0, {})
    exigir(raiz.get("tipo") == "BSFadeNode" and raiz.get("nombre") == plan_nif["raiz"],
           "la raiz es %s %r, se esperaba BSFadeNode %r"
           % (raiz.get("tipo"), raiz.get("nombre"), plan_nif["raiz"]))
    exigir(nif_nodos.cadena_extra(crudo, "Prn") == PRN,
           "el Prn es %r, el del donante es %r"
           % (nif_nodos.cadena_extra(crudo, "Prn"), PRN))
    tipos = {t for t, _o, _s in crudo["bloques"]}
    exigir({"BSXFlags", "BSInvMarker", "bhkCollisionObject"} <= tipos,
           "faltan bloques del donante: %s"
           % sorted({"BSXFlags", "BSInvMarker", "bhkCollisionObject"} - tipos))

    # la colision: una caja, con las REGLAS vanilla y la inercia > 0; y el
    # comando, como lo correria cualquiera
    cajas = colision_caja.cajas(crudo)
    exigir(len(cajas) == 1 and not colision_caja.juzgar(cajas[0])[0]
           and max(cajas[0]["inercia"]) > 0,
           "la colision: %r" % [colision_caja.juzgar(c)[0] for c in cajas])
    p = subprocess.run([sys.executable, os.path.join(ASSET_NUEVO, "colision_caja.py"),
                        ruta], capture_output=True, text=True)
    exigir(p.returncode == 0, "colision_caja.py salio con %d" % p.returncode)

    # la geometria, en el espacio de la raiz: donde el plan del marco dijo
    nif = parser_nif.Nif(ruta)
    formas = parser_uv.geometria(nif)
    nombres = [pz["shape"] for pz in plan_nif["piezas"]]
    exigir([f.get("nombre") for f in formas] == nombres
           and not any("error" in f for f in formas),
           "las piezas son %r, se esperaba %r"
           % ([(f.get("nombre"), f.get("error")) for f in formas], nombres))
    if formas and "error" not in formas[0]:
        exigir(len(formas[0]["tris"]) == pieza_ia.TRIANGULOS,
               "%d triangulos, la pieza tiene %d"
               % (len(formas[0]["tris"]), pieza_ia.TRIANGULOS))
        idx = [i for i, (t, _o, _s) in enumerate(nif.bloques) if t == "BSTriShape"][0]
        pts = parser_colision.a_mundo(nif, idx, formas[0]["pos"])
        eje = plan_marco["ejes"][plan_marco["largo"]["eje"]]
        norma = sum(c * c for c in eje) ** 0.5
        proy = [sum(p[k] * eje[k] for k in range(3)) / norma for p in pts]
        largo = max(proy) - min(proy)
        exigir(abs(largo - plan_marco["largo"]["valor"]) < TOL,
               "el largo es %.4f, el plan pide %.4f" % (largo, plan_marco["largo"]["valor"]))
        dorso = max(p[2] for p in pts)
        exigir(abs(dorso - plan_marco["topes"]["+Z"]) < TOL,
               "el dorso quedo en Z %.4f, el tope es %.4f" % (dorso, plan_marco["topes"]["+Z"]))
        # los 8 vertices de una placa son simetricos: su promedio es el centro
        centro = [sum(p[k] for p in pts) / len(pts) for k in range(2)]
        pedido = plan_marco["ancla"]["marco"][:2]
        exigir(all(abs(centro[k] - pedido[k]) < TOL for k in range(2)),
               "el centro quedo en %s, el ancla pide %s"
               % ([round(c, 4) for c in centro], pedido))
    return fallas, hechas[0]


def hay_pynifly(blender):
    """El addon, probado adentro de Blender: --python-exit-code hace que un
    import que falla salga con 1 (sin eso, Blender sale con 0)."""
    p = subprocess.run([blender, "-b", "--factory-startup", "--python-exit-code", "1",
                        "--python-expr",
                        "import addon_utils; addon_utils.enable('io_scene_nifly', "
                        "default_set=True); import io_scene_nifly.pyn.pynifly"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode == 0


def _mal(msg):
    print("[ejemplo] %s" % msg)
    print(__doc__)
    return EXIT_ARGS


def main(argv):
    blender = os.environ.get("BLENDER_EXE") or None
    trabajo = os.path.join(AQUI, "trabajo")
    args = list(argv)
    while args:
        a = args.pop(0)
        if a in ("--blender", "--trabajo"):
            if not args:
                return _mal("%s necesita un valor" % a)
            valor = args.pop(0)
            if a == "--blender":
                blender = valor
            else:
                trabajo = valor
        else:
            return _mal("argumento desconocido: %s" % a)
    if blender and not os.path.isfile(blender):
        return _mal("no existe el Blender %s" % blender)
    trabajo = os.path.abspath(trabajo)
    os.makedirs(trabajo, exist_ok=True)

    tiene = {"python": True, "blender": bool(blender)}
    tiene["pynifly"] = tiene["blender"] and hay_pynifly(blender)
    corrida = Corrida(blender, trabajo)
    print("[ejemplo] trabajo: %s" % trabajo)
    print("[ejemplo] Blender: %s; PyNifly: %s" % (
        blender or "no", "si" if tiene["pynifly"] else "no"))

    parada, estado_final = None, EXIT_OK
    for n, que, requiere in PASOS:
        if parada:
            print("  %d. %-58s salteado: %s" % (n, que, parada))
            continue
        if not tiene[requiere]:
            parada = "no corrio el paso %d" % n
            estado_final = EXIT_INCOMPLETO
            print("  %d. %-58s salteado: %s" % (n, que, QUE_FALTA[requiere]))
            continue
        ok, detalle = getattr(corrida, "paso_%d" % n)()
        print("  %d. %-58s %s: %s" % (n, que, "hecho" if ok else "FALLA", detalle))
        if not ok:
            parada = "fallo el paso %d" % n
            estado_final = EXIT_FALLA

    if estado_final == EXIT_OK:
        print("[ejemplo] LISTO: %s, verificado sin PyNifly" % corrida.nif)
    elif estado_final == EXIT_INCOMPLETO:
        print("[ejemplo] INCOMPLETO: corrio lo que se podia sin %s. No es un "
              "exito: el NIF no se hizo." % ("Blender" if not tiene["blender"] else "PyNifly"))
    else:
        print("[ejemplo] FALLA: %s" % parada)
    return estado_final


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
