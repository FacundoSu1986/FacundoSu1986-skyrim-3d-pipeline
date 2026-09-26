# -*- coding: utf-8 -*-
"""enderezar.py corrido en Blender de verdad. Optativo: sin BLENDER_EXE se

saltea, y eso es "no se probo", no "paso".

La matematica (la cuerda, la proyeccion, el tope, el rechazo) la prueba
`test_enderezar_puro.py` en CI. Lo que SOLO Blender puede probar es lo que este
archivo mira:

  * que la API de bmesh que usa el script exista y se comporte como el script
    espera (`e.calc_face_angle`, `e.smooth` para el *sharp*, asignar `v.co`);
  * que `--aplicar` mueva EXACTAMENTE los vertices interiores y ninguno de los
    extremos --medido leyendo las coordenadas del .blend guardado, no de la
    salida del script--;
  * que sin `--aplicar` el archivo quede intacto;
  * que un arco de diseno no se toque, y que con `--marcadas` se sigan las
    aristas que marco una persona y no un umbral de grados.

La geometria es sintetica y conocida: una barra larga (seccion de 4 lados, sin
subdividir a lo ancho) con la linea del canto ondulada a proposito. Los cruces
de la seccion son los vertices de las esquinas, asi que los cuatro cantos
quedan como caminos largos entre cruces --el caso que el detector automatico
tiene que encontrar y el enderezado tiene que arreglar--.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = (Path(__file__).resolve().parents[1] / "skills" / "modelo-ia-a-skyrim"
          / "scripts" / "enderezar.py")

# Barra larga con el canto ondulado. `NUDO` es la amplitud de la ondulacion
# (del orden del 1 % del alto de la pieza, que es 1,0).
NUDO = 0.02
ALTO = 1.0
LARGO = 10


def _blender(*args):
    return subprocess.run(
        [os.environ["BLENDER_EXE"], "--background", "--factory-startup"]
        + list(args),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300)


def _enderezar(*args):
    return _blender("--python", str(SCRIPT), "--", *args)


def expr_barra(ruta, ondulacion=1.0, marcadas=False):
    """La expresion que arma la barra. Separada para poder compilarla."""
    return (
        "import bpy\n"
        "bpy.ops.wm.read_factory_settings(use_empty=True)\n"
        "n, alto, nudo = %d, %r, %r\n"
        "offs = [0.0] + [(nudo * %r) * (1 if i %% 2 else -1) "
        "for i in range(1, n - 1)] + [0.0]\n"
        "verts, faces = [], []\n"
        "for i in range(n):\n"
        "    x, y = float(i), offs[i]\n"
        "    verts += [(x, y - 0.1, 0.0), (x, y + 0.1, 0.0),\n"
        "              (x, y + 0.1, alto), (x, y - 0.1, alto)]\n"
        "for i in range(n - 1):\n"
        "    a, b = 4 * i, 4 * (i + 1)\n"
        "    for k in range(4):\n"
        "        k2 = (k + 1) %% 4\n"
        "        faces.append((a + k, a + k2, b + k2, b + k))\n"
        "faces.append((0, 1, 2, 3))\n"
        "faces.append((4 * (n - 1), 4 * (n - 1) + 3, 4 * (n - 1) + 2, "
        "4 * (n - 1) + 1))\n"
        "m = bpy.data.meshes.new('barra')\n"
        "m.from_pydata(verts, [], faces)\n"
        "m.update()\n"
        "o = bpy.data.objects.new('barra', m)\n"
        "bpy.context.scene.collection.objects.link(o)\n"
        "if %r:\n"
        "    for e in m.edges:\n"
        "        e.use_edge_sharp = True\n"
        "bpy.ops.wm.save_as_mainfile(filepath=%r)\n"
        "print('[xy]', ' '.join('%%d:%%r:%%r' %% (i, v.co.x, v.co.y) "
        "for i, v in enumerate(m.vertices)))\n"
        % (LARGO + 1, ALTO, NUDO, ondulacion, marcadas, str(ruta)))


def _barra(ruta, ondulacion=1.0, marcadas=False):
    """Escribe el .blend de una barra; devuelve las coordenadas originales.

    La seccion son cuatro vertices, asi que el eje largo son cuatro caminos de
    `LARGO + 1` vertices. `ondulacion=0.0` da una barra recta.
    """
    p = _blender("--python-expr", expr_barra(ruta, ondulacion, marcadas))
    assert os.path.isfile(ruta), p.stdout + p.stderr
    linea = next(l for l in p.stdout.splitlines() if l.startswith("[xy]"))
    return _leer(linea)


def expr_curvar(ruta):
    """Curva la barra entera: es una curva de diseno, no una ondulacion."""
    return ("import bpy\n"
            "o = bpy.data.objects['barra']\n"
            "for v in o.data.vertices:\n"
            "    v.co.y += 0.3 * (1.0 - (2.0 * v.co.x / %d - 1.0) ** 2)\n"
            "bpy.ops.wm.save_as_mainfile(filepath=%r)\n" % (LARGO, str(ruta)))


def expr_marcar_un_canto(ruta):
    """Ondula y marca SOLO el canto superior: lo que haria una persona."""
    return ("import bpy\n"
            "o = bpy.data.objects['barra']\n"
            "for i in range(%d):\n"
            "    o.data.vertices[4 * i + 2].co.y += 0.02\n"
            "    o.data.vertices[4 * i + 3].co.y += 0.02\n"
            "for e in o.data.edges:\n"
            "    a, b = e.vertices\n"
            "    if a %% 4 == 2 and b %% 4 == 2:\n"
            "        e.use_edge_sharp = True\n"
            "bpy.ops.wm.save_as_mainfile(filepath=%r)\n" % (LARGO, str(ruta)))


def _leer(linea):
    """'[xy] 0:0.0:0.0 1:1.0:0.02 ...' -> {0: (0.0, 0.0), 1: (1.0, 0.02)}"""
    out = {}
    for trozo in linea.split()[1:]:
        i, x, y = trozo.split(":")
        out[int(i)] = (float(x), float(y))
    return out


def expr_coordenadas():
    """La expresion que imprime las coordenadas, para poder compilarla.

    Ojo con los `%`: esta cadena NO se formatea, asi que un `%%` quedaria
    literal y Blender recibiria un `%%` que no es un operador. Los tres sitios
    que SI formatean usan `%%` a proposito; el test de sintaxis de abajo los
    distingue, porque compila lo que de verdad se le pasa a Blender.
    """
    return ("import bpy\n"
            "print('[xy]', ' '.join('%d:%r:%r' % (i, v.co.x, v.co.y) "
            "for i, v in enumerate(bpy.data.objects['barra'].data.vertices)))\n")


def _coordenadas(ruta):
    p = _blender(str(ruta), "--python-expr", expr_coordenadas())
    linea = next(l for l in p.stdout.splitlines() if l.startswith("[xy]"))
    return _leer(linea)


def _informe(salida):
    linea = next(l for l in salida.splitlines() if l.startswith("[enderezar] {"))
    return json.loads(linea[len("[enderezar] "):])


class LasExpresionesSonPythonValidoTests(unittest.TestCase):
    """Lo unico de este archivo que corre sin Blender.

    El codigo que se le pasa a Blender va como texto: un `%%` de mas --que es
    facil de dejar cuando la cadena se formatea-- no lo ve el compileall, no lo
    ve el linter y no lo ve nadie hasta que Blender imprime un SyntaxError en
    medio de la corrida. Se compila aca, con las mismas cadenas.
    """

    def test_las_expresiones_compilan(self):
        for nombre, expr in (("barra", expr_barra("/tmp/x.blend")),
                             ("barra recta", expr_barra("/tmp/x.blend", 0.0)),
                             ("barra marcada",
                              expr_barra("/tmp/x.blend", 1.0, True)),
                             ("curvar", expr_curvar("/tmp/x.blend")),
                             ("marcar", expr_marcar_un_canto("/tmp/x.blend")),
                             ("coordenadas", expr_coordenadas())):
            with self.subTest(expresion=nombre):
                try:
                    compile(expr, "<%s>" % nombre, "exec")
                except SyntaxError as e:
                    self.fail("%s no compila: %s\n%s" % (nombre, e, expr))

    def test_la_barra_se_arma_con_lo_que_el_test_espera(self):
        """La geometria es la promesa del archivo: se mira el texto armado.

        Si alguien cambia LARGO o la cuenta de vertices por cara, las cuentas
        de los tests de Blender dejan de significar lo mismo y el error
        aparece como un indice fuera de rango, lejos de la causa.
        """
        expr = expr_barra("/tmp/x.blend")
        # Las anillas: LARGO + 1 columnas de 4 vertices.
        self.assertIn("n, alto, nudo = %d," % (LARGO + 1), expr)
        # El mapeo cara -> vertices de la seccion, con el `%` ya desescapado.
        self.assertIn("k2 = (k + 1) % 4", expr)
        # Las dos tapas.
        self.assertIn("faces.append((0, 1, 2, 3))", expr)
        self.assertIn("4 * (n - 1) + 3", expr)
        # La salida que los tests parsean.
        self.assertIn("[xy]", expr)
        # El alto y el nudo son los que usan las cuentas del tope: la altura
        # es la escala a la que se refiere --tope, asi que cambiarla cambia el
        # resultado de los tests de Blender sin tocar el script.
        self.assertIn("n, alto, nudo = %d, %r, %r" % (LARGO + 1, ALTO, NUDO),
                      expr)

    def test_los_porcentajes_que_quedan_son_los_del_codigo_de_blender(self):
        """Un `%%` sobreviviente seria un error de sintaxis en Blender."""
        for nombre, expr in (("barra", expr_barra("/tmp/x.blend")),
                             ("curvar", expr_curvar("/tmp/x.blend")),
                             ("marcar", expr_marcar_un_canto("/tmp/x.blend"))):
            with self.subTest(expresion=nombre):
                self.assertNotIn("%%", expr)


@unittest.skipUnless(os.environ.get("BLENDER_EXE"),
                     "requiere BLENDER_EXE; no se valido la API de Blender")
class EnderezarEnBlenderTests(unittest.TestCase):

    def test_informa_y_no_escribe_nada(self):
        """Sin --aplicar: encuentra el canto ondulado y deja el archivo igual."""
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "barra.blend"
            _barra(ruta)
            antes = _coordenadas(ruta)
            p = _enderezar(str(ruta), "--tope", "0.05")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            informe = _informe(p.stdout)
            self.assertFalse(informe["aplicado"])
            self.assertEqual("automatica", informe["fuente"])
            malla = informe["mallas"][0]
            self.assertGreaterEqual(malla["enderezadas"], 1, p.stdout)
            self.assertEqual(antes, _coordenadas(ruta),
                             "sin --aplicar no se puede tocar el archivo")

    def test_aplicar_mueve_el_interior_y_no_los_extremos(self):
        """Los dos extremos del canto ondulado quedan donde estaban."""
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "barra.blend"
            antes = _barra(ruta)
            p = _enderezar(str(ruta), "--tope", "0.05", "--aplicar")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            despues = _coordenadas(ruta)
            # Los vertices de las tapas --los 4 de cada punta-- no se mueven.
            for i in list(range(4)) + list(range(4 * LARGO, 4 * (LARGO + 1))):
                self.assertEqual(antes[i], despues[i],
                                 "se movio el vertice %d, que es un extremo" % i)
            # Y la linea quedo derecha: todos los cantos con la misma Y.
            for k in range(4):
                ys = {round(despues[4 * i + k][1], 6) for i in range(LARGO + 1)}
                self.assertEqual(len(ys), 1,
                                 "el canto %d no quedo derecho: %r" % (k, ys))

    def test_el_arco_de_diseno_no_se_toca(self):
        """Con una curvatura grande no califica nada: no guarda y sale con 1."""
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "arco.blend"
            antes = _barra(ruta, ondulacion=0.0)
            # Se curva la barra entera: es una curva de diseno, no ondulacion.
            _blender("--python-expr", expr_curvar(ruta))
            curvada = _coordenadas(ruta)
            p = _enderezar(str(ruta), "--tope", "0.05", "--aplicar")
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("no se guardo", p.stdout)
            self.assertEqual(curvada, _coordenadas(ruta))

    def test_marcadas_usa_lo_que_marco_la_persona(self):
        """`--marcadas` endereza exactamente las aristas marcadas."""
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "marcada.blend"
            _barra(ruta, ondulacion=0.0, marcadas=False)
            # Una sola linea del canto superior, marcada a mano.
            _blender("--python-expr", expr_marcar_un_canto(ruta))
            p = _enderezar(str(ruta), "--marcadas", "--tope", "0.05")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            informe = _informe(p.stdout)
            self.assertEqual("marcadas", informe["fuente"])
            malla = informe["mallas"][0]
            self.assertEqual(1, malla["cadenas_utiles"],
                             "tiene que ver una sola linea: %r" % (malla,))
            self.assertEqual(1, malla["enderezadas"], p.stdout)

    def test_argumento_que_no_sirve_sale_con_2(self):
        p = _enderezar("no-existe.blend")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        p = _enderezar(str(Path("/tmp") / "algo.obj"))
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
