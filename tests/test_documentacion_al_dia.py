# -*- coding: utf-8 -*-
"""Los números y los índices de la documentación, contra lo que hay.

El README decía "23 fallos" cuando trampas.md tenía 36, y "15 hallazgos"
cuando hallazgos.md tenía 43; SKILL.md decía "veintitrés". Nadie los corrigió
porque nadie los contaba. Este test los cuenta: agregar una trampa, un
hallazgo, una referencia o un script sin actualizar el índice lo rompe.

Enumera, no enumera a mano: recorre las carpetas de skills y de census, así
que una skill o un archivo nuevo entran solos.
"""
import os
import re
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(RAIZ, "skills")

_UNIDADES = ("", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete",
             "ocho", "nueve", "diez", "once", "doce", "trece", "catorce",
             "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve",
             "veinte", "veintiuno", "veintidós", "veintitrés", "veinticuatro",
             "veinticinco", "veintiséis", "veintisiete", "veintiocho",
             "veintinueve")
_DECENAS = {3: "treinta", 4: "cuarenta", 5: "cincuenta", 6: "sesenta",
            7: "setenta", 8: "ochenta", 9: "noventa"}


def en_letras(n):
    """1..99 en castellano, como se escriben en los títulos."""
    if not 1 <= n <= 99:
        raise ValueError(n)
    if n < 30:
        return _UNIDADES[n]
    d, u = divmod(n, 10)
    return _DECENAS[d] + ("" if u == 0 else " y " + _UNIDADES[u])


def _leer(ruta):
    with open(ruta, encoding="utf-8") as fh:
        return fh.read()


def _plano(texto):
    """Sin saltos de línea: una frase partida en dos renglones sigue siendo
    la misma frase."""
    return " ".join(texto.split())


def _contiene(test, aguja, pajar, donde):
    """assertIn sin volcar el archivo entero en el mensaje."""
    test.assertTrue(aguja in pajar, "%r no aparece en %s" % (aguja, donde))


def _secciones(ruta, patron=r"^### (\d+)\."):
    return len(re.findall(patron, _leer(ruta), re.M))


def _skills():
    return sorted(d for d in os.listdir(SKILLS)
                  if os.path.exists(os.path.join(SKILLS, d, "SKILL.md")))


class EnLetrasTests(unittest.TestCase):

    def test_casos_conocidos(self):
        for n, texto in ((23, "veintitrés"), (24, "veinticuatro"),
                         (30, "treinta"), (36, "treinta y seis"),
                         (41, "cuarenta y uno")):
            self.assertEqual(en_letras(n), texto)


class TrampasTests(unittest.TestCase):

    def test_hay_skills_que_revisar(self):
        self.assertGreaterEqual(len(_skills()), 2)

    def test_el_titulo_skill_y_readme_dicen_cuantas_trampas_hay(self):
        readme = _leer(os.path.join(RAIZ, "README.md"))
        for skill in _skills():
            ruta = os.path.join(SKILLS, skill, "references", "trampas.md")
            if not os.path.exists(ruta):
                continue
            n = _secciones(ruta)
            palabras = en_letras(n)
            with self.subTest(skill=skill, trampas=n):
                self.assertGreater(n, 0)
                _contiene(self, "# Trampas: %s fallos" % palabras, _leer(ruta),
                          "el título de trampas.md")
                _contiene(self, "%s fallos" % palabras,
                          _plano(_leer(os.path.join(SKILLS, skill,
                                                    "SKILL.md"))),
                          "%s/SKILL.md" % skill)
                _contiene(self, "%d en `%s`" % (n, skill), _plano(readme),
                          "el README (qué problema resuelve)")
                fila = next((l for l in readme.splitlines()
                             if "skills/%s/references/trampas.md" % skill in l),
                            "")
                _contiene(self, "%d fallos" % n, fila,
                          "la fila de trampas.md del README")


class HallazgosTests(unittest.TestCase):

    def test_el_readme_dice_cuantos_hallazgos_hay(self):
        readme = _leer(os.path.join(RAIZ, "README.md"))
        census = os.path.join(RAIZ, "census")
        archivos = sorted(f for f in os.listdir(census)
                          if f.startswith("hallazgos") and f.endswith(".md"))
        self.assertGreater(len(archivos), 0)
        for f in archivos:
            n = _secciones(os.path.join(census, f))
            with self.subTest(archivo=f, hallazgos=n):
                fila = next((l for l in readme.splitlines()
                             if "(census/%s)" % f in l), None)
                self.assertIsNotNone(fila, "%s no está en el README" % f)
                _contiene(self, "%d hallazgos" % n, fila,
                          "la fila de %s del README" % f)


class IndicesTests(unittest.TestCase):
    """Cada referencia y cada script de cada skill, en su SKILL.md y en el
    README. Un archivo que no está en el índice no lo encuentra nadie."""

    def test_cada_archivo_esta_en_su_skill_y_en_el_readme(self):
        readme = _leer(os.path.join(RAIZ, "README.md"))
        vistos = 0
        for skill in _skills():
            indice = _leer(os.path.join(SKILLS, skill, "SKILL.md"))
            for carpeta, ext in (("references", ".md"), ("scripts", ".py")):
                base = os.path.join(SKILLS, skill, carpeta)
                if not os.path.isdir(base):
                    continue
                for f in sorted(os.listdir(base)):
                    if not f.endswith(ext):
                        continue
                    vistos += 1
                    with self.subTest(skill=skill, archivo=f):
                        _contiene(self, f, indice, "%s/SKILL.md" % skill)
                        _contiene(self, "skills/%s/%s/%s" % (skill, carpeta, f),
                                  readme, "el README")
        self.assertGreater(vistos, 0)


if __name__ == "__main__":
    unittest.main()
