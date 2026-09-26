"""al_marco.py corrido en Blender de verdad. Optativo: sin BLENDER_EXE se
saltea, y eso es "no se probo", no "paso".

La matematica (montaje_puro.rotacion_por_ejes, validar_marco,
matriz_al_marco) la prueba el autotest de montaje_puro.py en CI, con sus
mutantes. Esto prueba lo que solo Blender puede: que la transformada de cada
objeto se hornea antes de medir, que la MISMA matriz llega a la baja y a la
alta, que el remedido en Blender da lo pedido, y las guardas.
"""
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = (Path(__file__).resolve().parents[1] / "skills" / "modelo-ia-a-skyrim"
          / "scripts" / "al_marco.py")


def _blender(*args):
    return subprocess.run(
        [os.environ["BLENDER_EXE"], "--background", "--factory-startup"] + list(args),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300)


def _marco(*args):
    return _blender("--python", str(SCRIPT), "--", *args)


def _ovalo(ruta, escala=(0.2, 0.05, 0.5)):
    """Un ovalo con la transformada del objeto sin aplicar (corrido y
    escalado): al_marco la tiene que hornear antes de medir."""
    _blender("--python-expr",
             "import bpy\n"
             "bpy.ops.wm.read_factory_settings(use_empty=True)\n"
             "bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, "
             "location=(5, 2, 1))\n"
             "bpy.context.object.scale = %r\n"
             "bpy.ops.wm.save_as_mainfile(filepath=%r)\n" % (escala, str(ruta)))
    assert os.path.isfile(ruta)


def _plan_escudo(ruta):
    a = math.radians(66.0)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump({"ejes": {"+Z": [math.cos(a), math.sin(a), 0.0], "+Y": "+Z"},
                   "largo": {"eje": "+Z", "valor": 67.39},
                   "ancla": {"modelo": "centro", "marco": [0.0, -7.0, None]},
                   "topes": {"+Z": 2.2}}, fh)


@unittest.skipUnless(os.environ.get("BLENDER_EXE"),
                     "requiere BLENDER_EXE; no se valido la API de Blender")
class AlMarcoEnBlenderTests(unittest.TestCase):

    def test_falsificar(self):
        p = _marco("--falsificar")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("falsificar: 2 comprobaciones, 0 fallas", p.stdout)

    def test_escudo_baja_y_alta_con_la_misma_matriz(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            _ovalo(d / "baja.blend")
            _ovalo(d / "alta.blend")
            _plan_escudo(d / "plan.json")
            p = _marco(str(d / "plan.json"), str(d / "baja.blend"),
                       str(d / "baja_m.blend"), str(d / "alta.blend"),
                       str(d / "alta_m.blend"))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            with open(d / "baja_m_marco.json", encoding="utf-8") as fh:
                inf = json.load(fh)
            lo, hi = inf["baja"]["caja"]
            self.assertAlmostEqual(hi[2], 2.2, places=3)
            self.assertAlmostEqual((lo[0] + hi[0]) / 2, 0.0, places=3)
            self.assertAlmostEqual((lo[1] + hi[1]) / 2, -7.0, places=3)
            # la transformada del objeto (escala 0,5 en Z) se horneo: el
            # modelo medía 1,0 de alto, y la escala es 67,39 / 1,0
            self.assertAlmostEqual(inf["escala"], 67.39, places=3)
            self.assertGreater(inf["determinante"], 0)
            # la alta es la misma malla: con la misma matriz, la misma caja
            self.assertEqual(inf["baja"]["caja"], inf["alta"]["caja"])

            p = _marco(str(d / "plan.json"), str(d / "baja.blend"),
                       str(d / "baja_m.blend"))
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            p = _marco(str(d / "plan.json"), str(d / "baja.blend"),
                       str(d / "baja.blend"))
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)

    def test_plan_sin_fijar_y_escala_negativa_reprueban(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            _ovalo(d / "baja.blend")
            (d / "malo.json").write_text(
                '{"ejes": {"+Z": "+Y", "+X": "+X"}, '
                '"largo": {"eje": "+Z", "valor": 10}}', encoding="utf-8")
            p = _marco(str(d / "malo.json"), str(d / "baja.blend"),
                       str(d / "x.blend"))
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("queda sin fijar", p.stdout)
            self.assertFalse((d / "x.blend").exists())

            _ovalo(d / "espejo.blend", escala=(-0.2, 0.05, 0.5))
            _plan_escudo(d / "plan.json")
            p = _marco(str(d / "plan.json"), str(d / "espejo.blend"),
                       str(d / "e.blend"))
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("trampa 38", p.stdout + p.stderr)
            self.assertFalse((d / "e.blend").exists())


if __name__ == "__main__":
    unittest.main()
