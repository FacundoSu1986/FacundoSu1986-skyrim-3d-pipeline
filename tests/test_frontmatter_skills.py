# -*- coding: utf-8 -*-
"""El frontmatter de cada SKILL.md tiene que pasar el validador de subida.

claude.ai y la API de Skills rechazan un SKILL.md con claves de primer nivel
que no conocen: es la regla `ALLOWED_PROPERTIES` de `quick_validate.py`, el
validador de skill-creator que corre `package_skill.py`. Claude Code carga la
carpeta igual, asi que el error aparece recien al subir la skill: tarde y lejos
del cambio que lo causo. La issue #65 pedia `version`, `inputs`, `outputs`,
`prerequisites` y `rendering-path` como claves de primer nivel; escritas asi,
las dos skills dejaban de poder subirse. Lo que pedia entra donde el validador
lo acepta: los prerrequisitos en `compatibility` y lo demas en `metadata`.

Lo que se congela, por IGUALDAD y no por pertenencia:
  - que skills hay: una carpeta nueva con SKILL.md rompe el test hasta que
    alguien decida su frontmatter y lo escriba en FRONTMATTER_ESPERADO;
  - que claves lleva cada una, arriba y dentro de `metadata`. Agregar una
    clave es una decision: primero se mira si el validador la acepta
    (CLAVES_PERMITIDAS) y despues se agrega aca.
Y sobre cada skill, las reglas del validador que se rompen editando texto:
el nombre, el largo de la descripcion y de `compatibility`, los angulos.

El repo no depende de PyYAML: el frontmatter se escribe en el subconjunto que
lee `leer_frontmatter` --`clave: valor` en una linea y un nivel de anidado--,
y lo que ese lector no entiende es un error, no una clave que se pierde en
silencio (ElLectorNoCallaTests). Si PyYAML esta instalado, ademas se compara
lo leido contra el YAML de verdad: `yaml.safe_load`, el mismo parser con el que
quick_validate.py lee el frontmatter. requirements-dev.txt lo instala como
oraculo, y en CI que falte es un fallo, no un salteo: sin el, la suite decia
"OK" sin haber hecho la comparacion.
"""
import os
import re
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(RAIZ, "skills")

# quick_validate.py de skill-creator, copiado a mano (no se importa: el repo
# no lo trae). Si el validador cambia, esto se actualiza a mano.
CLAVES_PERMITIDAS = {"name", "description", "license", "allowed-tools",
                     "metadata", "compatibility"}
MAX_NOMBRE = 64
MAX_DESCRIPCION = 1024
MAX_COMPATIBILIDAD = 500

# skill -> (claves de primer nivel, claves dentro de `metadata`).
# Sin `version`: nadie la sube cuando cambia el flujo, y un numero que no se
# mantiene miente. Una copia instalada se identifica por el commit de main
# desde el que se empaqueto. `rendering-paths` solo en modelo-ia-a-skyrim:
# asset-nuevo-skyrim no cubre la rama de Community Shaders.
FRONTMATTER_ESPERADO = {
    "asset-nuevo-skyrim": (
        {"name", "description", "compatibility", "metadata"},
        {"inputs", "outputs"},
    ),
    "modelo-ia-a-skyrim": (
        {"name", "description", "compatibility", "metadata"},
        {"inputs", "outputs", "rendering-paths"},
    ),
}

CLAVE = re.compile(r"^([A-Za-z][\w-]*):(?: (.*))?$")
ANIDADA = re.compile(r"^  ([A-Za-z][\w-]*): (.+)$")


class FrontmatterIlegible(ValueError):
    pass


def _escalar(valor, donde):
    """Un valor de una linea: entre comillas, o plano sin lo que en YAML
    cambia el sentido (`: ` abre un mapa, ` #` un comentario, y un primer
    caracter de bloque, flujo, ancla o etiqueta)."""
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
        return valor[1:-1]
    if valor[:1] in ("|", ">", "[", "{", "&", "*", "!", "'", '"', "%", "@", "`"):
        raise FrontmatterIlegible("%s: valor que este lector no entiende: %r" % (donde, valor))
    if ": " in valor or " #" in valor:
        raise FrontmatterIlegible("%s: valor plano con ': ' o ' #' (en YAML "
                                  "cambia el sentido): %r" % (donde, valor))
    return valor


def leer_frontmatter(ruta):
    """({clave: valor} de primer nivel, {clave: {subclave: valor}}).

    Una clave de primer nivel sin valor abre un mapa, que solo puede tener
    subclaves con dos espacios. Cualquier otra linea es FrontmatterIlegible."""
    with open(ruta, encoding="utf-8") as fh:
        lineas = [l.rstrip("\r") for l in fh.read().split("\n")]
    if lineas[0] != "---":
        raise FrontmatterIlegible("%s no empieza con ---" % ruta)
    try:
        fin = lineas.index("---", 1)
    except ValueError:
        raise FrontmatterIlegible("%s: el frontmatter no se cierra con ---" % ruta)
    arriba, anidado, abierta = {}, {}, None
    for n in range(1, fin):
        linea, donde = lineas[n], "%s:%d" % (ruta, n + 1)
        if not linea.strip():
            continue
        m = CLAVE.match(linea)
        if m:
            clave, valor = m.group(1), (m.group(2) or "").strip()
            if clave in arriba:
                raise FrontmatterIlegible("%s: clave repetida %r" % (donde, clave))
            arriba[clave] = _escalar(valor, donde) if valor else ""
            abierta = clave if not valor else None
            continue
        m = ANIDADA.match(linea)
        if m and abierta is not None:
            sub = anidado.setdefault(abierta, {})
            if m.group(1) in sub:
                raise FrontmatterIlegible("%s: subclave repetida %r" % (donde, m.group(1)))
            sub[m.group(1)] = _escalar(m.group(2).strip(), donde)
            continue
        raise FrontmatterIlegible("%s: linea que este lector no entiende: %r" % (donde, linea))
    for clave in list(arriba):
        if clave in anidado:
            arriba[clave] = anidado[clave]
        elif arriba[clave] == "" and clave == "metadata":
            raise FrontmatterIlegible("%s: `metadata` vacio" % ruta)
    return arriba


def _skill_md(nombre):
    return os.path.join(SKILLS, nombre, "SKILL.md")


class FrontmatterDeLasSkillsTests(unittest.TestCase):

    def test_las_skills_son_exactamente_estas(self):
        encontradas = {d for d in os.listdir(SKILLS)
                       if os.path.isfile(_skill_md(d))}
        self.assertEqual(
            encontradas, set(FRONTMATTER_ESPERADO),
            "skills con SKILL.md distintas de las congeladas: decidí el "
            "frontmatter de la nueva (qué claves, y que el validador las "
            "acepte) y escribilo en FRONTMATTER_ESPERADO")

    def test_lo_congelado_lo_acepta_el_validador(self):
        for nombre, (arriba, _meta) in sorted(FRONTMATTER_ESPERADO.items()):
            with self.subTest(skill=nombre):
                self.assertEqual(arriba - CLAVES_PERMITIDAS, set(),
                                 "claves que claude.ai rechaza al subir")

    def test_cada_skill_lleva_exactamente_sus_claves(self):
        for nombre, (arriba, meta) in sorted(FRONTMATTER_ESPERADO.items()):
            with self.subTest(skill=nombre):
                fm = leer_frontmatter(_skill_md(nombre))
                self.assertEqual(set(fm), arriba)
                self.assertIsInstance(fm["metadata"], dict)
                self.assertEqual(set(fm["metadata"]), meta)
                for clave in set(fm) - {"metadata"}:
                    self.assertIsInstance(fm[clave], str, clave)

    def test_las_reglas_del_validador(self):
        for nombre in sorted(FRONTMATTER_ESPERADO):
            with self.subTest(skill=nombre):
                fm = leer_frontmatter(_skill_md(nombre))
                self.assertEqual(fm["name"], nombre,
                                 "el nombre tiene que ser el de la carpeta")
                self.assertRegex(fm["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
                self.assertLessEqual(len(fm["name"]), MAX_NOMBRE)
                self.assertTrue(fm["description"].strip())
                self.assertLessEqual(len(fm["description"]), MAX_DESCRIPCION)
                self.assertNotRegex(fm["description"], "[<>]")
                self.assertTrue(fm["compatibility"].strip())
                self.assertLessEqual(len(fm["compatibility"]), MAX_COMPATIBILIDAD)
                for sub, valor in fm["metadata"].items():
                    self.assertTrue(valor.strip(), "metadata.%s vacío" % sub)

    def test_y_coincide_con_el_yaml_de_verdad(self):
        try:
            import yaml
        except ImportError:
            if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
                self.fail("CI sin PyYAML: la comparación contra YAML real "
                          "se saltearía y la suite diría OK sin haberla "
                          "hecho (requirements-dev.txt lo instala)")
            self.skipTest("PyYAML no está: la comparación contra YAML real "
                          "no se corrió (no cuenta como comprobada)")
        for nombre in sorted(FRONTMATTER_ESPERADO):
            with self.subTest(skill=nombre):
                with open(_skill_md(nombre), encoding="utf-8") as fh:
                    texto = fh.read()
                bloque = texto.split("\n---", 1)[0].split("---\n", 1)[1]
                self.assertEqual(leer_frontmatter(_skill_md(nombre)),
                                 yaml.safe_load(bloque))


class ElLectorNoCallaTests(unittest.TestCase):
    """Un lector que ignora lo que no entiende haría pasar a una skill con
    claves perdidas. Cada caso es algo que YAML lee distinto o que el
    validador rechaza, y el lector tiene que cortar o reportarlo."""

    def _leer(self, frontmatter):
        fd, ruta = tempfile.mkstemp(suffix=".md")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write("---\n" + frontmatter + "---\n\n# cuerpo\n")
            return leer_frontmatter(ruta)
        finally:
            os.remove(ruta)

    def test_una_clave_de_primer_nivel_de_mas_se_ve(self):
        fm = self._leer("name: x\ndescription: y\nversion: 1.0.0\n")
        self.assertEqual(set(fm), {"name", "description", "version"})
        self.assertNotEqual(set(fm) - CLAVES_PERMITIDAS, set())

    def test_un_valor_en_bloque_corta(self):
        with self.assertRaises(FrontmatterIlegible):
            self._leer("name: x\ndescription: >\n  texto\n")

    def test_dos_puntos_en_un_valor_plano_cortan(self):
        with self.assertRaises(FrontmatterIlegible):
            self._leer("name: x\ndescription: hace esto: y aquello\n")

    def test_un_comentario_en_un_valor_plano_corta(self):
        with self.assertRaises(FrontmatterIlegible):
            self._leer("name: x\ndescription: algo #que YAML se come\n")

    def test_un_anidado_mas_profundo_corta(self):
        with self.assertRaises(FrontmatterIlegible):
            self._leer("name: x\nmetadata:\n  a:\n    b: c\n")

    def test_una_clave_repetida_corta(self):
        with self.assertRaises(FrontmatterIlegible):
            self._leer("name: x\nname: y\n")

    def test_sin_cierre_corta(self):
        fd, ruta = tempfile.mkstemp(suffix=".md")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write("---\nname: x\n")
            with self.assertRaises(FrontmatterIlegible):
                leer_frontmatter(ruta)
        finally:
            os.remove(ruta)

    def test_lo_que_si_entiende(self):
        fm = self._leer('name: x\ndescription: "a: b"\nmetadata:\n  k: v\n')
        self.assertEqual(fm, {"name": "x", "description": "a: b",
                              "metadata": {"k": "v"}})


if __name__ == "__main__":
    unittest.main()
