# -*- coding: utf-8 -*-
"""Toda referencia a una issue o un PR de GitHub dice cual es, con un link.

Los titulos de census/hallazgos*.md llevaban marcadores (#N) sueltos. Dentro
de un archivo del repo GitHub no los convierte en links, y nada decia si N era
una issue, un PR o una trampa (issue #67). Rastreados contra la historia de
git, eran de dos clases: la issue que motivo el hallazgo, o el PR que lo
trajo. Y cuatro de los PR estaban corridos en uno --los hallazgos de colision
decian el numero del PR de la mascara especular--: probablemente se escribio
el numero que se esperaba que tuviera el PR, y le toco otro.

Dos reglas, sobre TODOS los .md y .py de las carpetas del repo (lista escrita
a mano abajo, no un barrido que excluya: un directorio nuevo del repo se
agrega a CARPETAS como decision):

  1. Ningun numero de issue o PR suelto entre parentesis, del estilo (#N). Se
     escribe como link: "PR [#N](https://github.com/.../pull/N)", o, en un
     docstring, "(issue #N del repo)". Un link interno de markdown, [36](#36),
     no es un marcador: apunta a un ancla {#36} del mismo archivo.
  2. En un link a una issue o un PR, el numero del texto es el de la URL: es
     el error de los marcadores corridos, que un link mal copiado reintroduce.
"""
import os
import re
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Donde vive el texto del repo. Enumerado, no excluido.
CARPETAS = ("census", "docs", "examples", "fixtures", "pipeline", "skills", "tests")
SUELTOS_EN_RAIZ = ("README.md", "build_skill.py")
EXTENSIONES = (".md", ".py")

# Un parentesis que abre con un numero de issue o PR. El "#" va separado para
# que este mismo archivo no contenga el patron que busca.
MARCADOR = re.compile(r"(?<!\])\(" + "#" + r"[0-9]+")
LINK = re.compile(r"\[([^\]\n]*?#([0-9]+)[^\]\n]*)\]"
                  r"\((https://github\.com/[^/\s)]+/[^/\s)]+/(?:issues|pull)/([0-9]+))\)")


def archivos_de_texto():
    rutas = [os.path.join(RAIZ, f) for f in SUELTOS_EN_RAIZ]
    for carpeta in CARPETAS:
        for base, dirs, archivos in os.walk(os.path.join(RAIZ, carpeta)):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            rutas.extend(os.path.join(base, f) for f in archivos
                         if f.endswith(EXTENSIONES))
    return sorted(rutas)


def marcadores_sueltos(texto):
    """[(linea, texto)] de cada (#N) suelto."""
    return [(texto.count("\n", 0, m.start()) + 1, m.group(0))
            for m in MARCADOR.finditer(texto)]


def links_cruzados(texto):
    """[(linea, texto del link, url)] donde el #N del texto no es el de la URL.
    Tambien devuelve cuantos links a issues/PR reviso."""
    malos, revisados = [], 0
    for m in LINK.finditer(texto):
        revisados += 1
        if m.group(2) != m.group(4):
            malos.append((texto.count("\n", 0, m.start()) + 1, m.group(1),
                          m.group(3)))
    return malos, revisados


class ReferenciasExplicitasTests(unittest.TestCase):

    def setUp(self):
        self.textos = {}
        for ruta in archivos_de_texto():
            with open(ruta, encoding="utf-8") as fh:
                self.textos[os.path.relpath(ruta, RAIZ).replace(os.sep, "/")] = fh.read()

    def test_el_barrido_ve_los_archivos_que_tenian_marcadores(self):
        # Si el recorrido se rompe y no lee nada, las dos reglas pasan solas.
        for ruta in ("census/hallazgos.md", "census/hallazgos_plugins.md",
                     "census/hallazgos_texturas.md", "census/hallazgos_uv.md",
                     "docs/DECISIONS.md", "tests/test_contrato_texturas.py",
                     "README.md"):
            self.assertIn(ruta, self.textos)

    def test_ningun_marcador_suelto(self):
        sueltos = ["%s:%d %s" % (ruta, linea, m)
                   for ruta, texto in sorted(self.textos.items())
                   for linea, m in marcadores_sueltos(texto)]
        self.assertEqual(sueltos, [],
                         "número de issue o PR suelto entre paréntesis: "
                         "escribí de cuál se trata, con un link (ver el "
                         "docstring de este test)")

    def test_cada_link_dice_el_numero_de_su_url(self):
        cruzados, revisados = [], 0
        for ruta, texto in sorted(self.textos.items()):
            malos, n = links_cruzados(texto)
            revisados += n
            cruzados.extend("%s:%d [%s](%s)" % ((ruta,) + m) for m in malos)
        self.assertEqual(cruzados, [])
        self.assertGreater(revisados, 0, "no revisó ningún link: cero "
                                         "comprobaciones no es éxito")


class LasReglasMuerdenTests(unittest.TestCase):
    """Cada regla, contra lo que tiene que atrapar y lo que tiene que dejar
    pasar. Los casos se arman concatenando, por la misma razón que MARCADOR."""

    URL = "https://github.com/FacundoSu1986/FacundoSu1986-skyrim-3d-pipeline"

    def test_atrapa_el_marcador_del_titulo(self):
        texto = "intro\n### 16. (" + "#19) Reparto de los tipos de shape\n"
        self.assertEqual(marcadores_sueltos(texto), [(2, "(" + "#19")])

    def test_atrapa_la_lista_entre_parentesis(self):
        self.assertEqual(len(marcadores_sueltos("links rotos (" + "#36, #37)")), 1)

    def test_no_confunde_un_link_interno(self):
        self.assertEqual(marcadores_sueltos("| síntoma | [36](" + "#36) |"), [])

    def test_no_confunde_la_forma_explicita(self):
        texto = ("**ORIGEN**: issue [#19](%s/issues/19) → PR [#24](%s/pull/24)."
                 % (self.URL, self.URL))
        self.assertEqual(marcadores_sueltos(texto), [])
        self.assertEqual(links_cruzados(texto), ([], 2))

    def test_atrapa_el_link_corrido(self):
        texto = "PR [#42](%s/pull/41)" % self.URL
        malos, n = links_cruzados(texto)
        self.assertEqual(n, 1)
        self.assertEqual(malos, [(1, "#42", self.URL + "/pull/41")])


if __name__ == "__main__":
    unittest.main()
