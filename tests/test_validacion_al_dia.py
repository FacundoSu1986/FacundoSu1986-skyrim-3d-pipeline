# -*- coding: utf-8 -*-
"""docs/validacion.md nombra los flags que los scripts aceptan de verdad.

La reseña que pidió la página (issue #73 del repo) citaba un `--benchmark`
que no existe en ningún script. Una tabla de controles escrita de memoria
miente apenas el código cambia; esta se compara contra el código en los dos
sentidos:

  - PÁGINA -> CÓDIGO: cada `script.py --flag` que la página escribe en código
    tiene que existir como constante en ese script. Un flag inventado, o
    atribuido al script equivocado, pone rojo el test.
  - CÓDIGO -> PÁGINA: cada flag de CONTROL que un script acepta tiene que
    estar en la página, junto a su script.

Qué flag es de control es una decisión, escrita a mano en CONTROLES y
NO_CONTROLES. Las dos juntas tienen que ser EXACTAMENTE los flags del código:
uno nuevo rompe el test hasta que alguien decida en cuál va, y si va en
CONTROLES, hasta que lo documente.

Los flags se leen del árbol sintáctico de cada script: una constante de texto
que es exactamente `--algo`. Así no cuentan los que solo aparecen en un
docstring o en un comentario.
"""
import ast
import glob
import os
import re
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGINA = os.path.join(RAIZ, "docs", "validacion.md")

# Donde viven los scripts. Enumerado, no excluido: tests/ no entra (llama a
# los scripts con sus flags, no los acepta).
PATRONES = ("census/*.py", "fixtures/*.py", "pipeline/*.py",
            "skills/*/scripts/*.py", "build_skill.py")

# Flags que eligen QUÉ se comprueba, o que aflojan un control.
CONTROLES = {
    "--autotest", "--censo", "--falsificar", "--falsificar-prn",
    "--contrato", "--identico", "--fiel", "--uv", "--verificar", "--arma",
    "--permitir-solape",   # baja a aviso el tope de solape de hornear.py
}
# Flags de salida, de opciones o de escritura: no hace falta documentarlos acá.
NO_CONTROLES = {
    "--clase", "--continuar", "--distancia-ao", "--extrusion", "--force",
    "--frente-az", "--girar-180", "--guardar-alto", "--help", "--json",
    "--marcar", "--maximo", "--muestras-ao", "--quitar", "--relativo-a",
    "--salida", "--soldadura", "--vistas",
}
# Flags de la línea de comandos de Blender, que la página escribe al lado de
# un script (`blender -b --python hornear.py -- ...`) y no son del script.
DE_BLENDER = {"--python", "--python-exit-code", "--background",
              "--factory-startup"}

FLAG = re.compile(r"^--[a-z][a-z0-9-]*$")
EN_TEXTO = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*)")
SCRIPT = re.compile(r"\b([a-z_][a-z0-9_]*\.py)\b")
CODIGO = re.compile(r"`([^`\n]+)`")


def flags_del_codigo():
    """{nombre de script: {flags}}. Dos scripts con el mismo nombre (las dos
    copias de nif_nodos.py) se juntan."""
    por_script = {}
    for patron in PATRONES:
        for ruta in sorted(glob.glob(os.path.join(RAIZ, patron))):
            with open(ruta, encoding="utf-8") as fh:
                arbol = ast.parse(fh.read(), ruta)
            flags = {n.value for n in ast.walk(arbol)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)
                     and FLAG.match(n.value)}
            por_script.setdefault(os.path.basename(ruta), set()).update(flags)
    return por_script


def pares_de_la_pagina(texto):
    """{(script, flag)} de cada fragmento de código que nombra un script y
    uno o más flags."""
    pares = set()
    for fragmento in CODIGO.findall(texto):
        scripts = SCRIPT.findall(fragmento)
        flags = set(EN_TEXTO.findall(fragmento)) - DE_BLENDER
        pares.update((s, f) for s in scripts for f in flags)
    return pares


def inventados(pares, por_script):
    """Los pares de la página que el código no respalda."""
    return sorted((s, f) for s, f in pares
                  if f not in por_script.get(s, set()))


def sin_documentar(pares, por_script):
    """Los flags de control del código que la página no nombra con su script."""
    return sorted((s, f) for s, flags in por_script.items() for f in flags
                  if f in CONTROLES and (s, f) not in pares)


class LaPaginaDiceLoQueHayTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.por_script = flags_del_codigo()
        with open(PAGINA, encoding="utf-8") as fh:
            cls.pares = pares_de_la_pagina(fh.read())

    def test_el_barrido_ve_los_scripts(self):
        # Si el barrido no lee nada, "nada sin documentar" pasa solo.
        for script, flag in (("salud_malla.py", "--falsificar"),
                             ("comparar.py", "--contrato"),
                             ("parser_nif.py", "--censo"),
                             ("hornear.py", "--permitir-solape")):
            self.assertIn(flag, self.por_script.get(script, set()), script)
        self.assertIn(("verificar_uv.py", "--autotest"), self.pares)

    def test_cada_flag_del_codigo_esta_clasificado(self):
        todos = set().union(*self.por_script.values())
        self.assertEqual(CONTROLES & NO_CONTROLES, set())
        self.assertEqual(
            todos, CONTROLES | NO_CONTROLES,
            "flags del código que no están en CONTROLES ni en NO_CONTROLES "
            "(%s), o clasificados que ya no existen (%s): decidí en cuál va "
            "cada uno" % (sorted(todos - CONTROLES - NO_CONTROLES),
                          sorted((CONTROLES | NO_CONTROLES) - todos)))

    def test_la_pagina_no_inventa_flags(self):
        self.assertEqual(inventados(self.pares, self.por_script), [],
                         "docs/validacion.md nombra flags que ese script no "
                         "acepta")

    def test_cada_control_esta_en_la_pagina(self):
        self.assertEqual(sin_documentar(self.pares, self.por_script), [],
                         "flags de control sin documentar en "
                         "docs/validacion.md")


class LasComparacionesMuerdenTests(unittest.TestCase):
    """Las dos comparaciones, sobre casos armados a mano."""

    CODIGO = {"salud_malla.py": {"--autotest", "--falsificar", "--uv"},
              "hornear.py": {"--force", "--permitir-solape"}}

    def test_un_flag_inventado_se_ve(self):
        pares = pares_de_la_pagina("corré `salud_malla.py --benchmark <x>`")
        self.assertEqual(inventados(pares, self.CODIGO),
                         [("salud_malla.py", "--benchmark")])

    def test_un_flag_en_el_script_equivocado_se_ve(self):
        pares = pares_de_la_pagina("`hornear.py --uv <a> <b>`")
        self.assertEqual(inventados(pares, self.CODIGO), [("hornear.py", "--uv")])

    def test_un_control_sin_documentar_se_ve(self):
        pares = pares_de_la_pagina("`salud_malla.py --autotest` y "
                                   "`salud_malla.py --uv <a> <b>`")
        self.assertEqual(sin_documentar(pares, self.CODIGO),
                         [("hornear.py", "--permitir-solape"),
                          ("salud_malla.py", "--falsificar")])

    def test_la_linea_de_blender_no_cuenta(self):
        pares = pares_de_la_pagina(
            "`blender -b --python hornear.py -- <b> [--permitir-solape]`")
        self.assertEqual(pares, {("hornear.py", "--permitir-solape")})

    def test_un_flag_sin_script_no_arma_par(self):
        self.assertEqual(pares_de_la_pagina("pasá `--permitir-solape`"), set())


if __name__ == "__main__":
    unittest.main()
