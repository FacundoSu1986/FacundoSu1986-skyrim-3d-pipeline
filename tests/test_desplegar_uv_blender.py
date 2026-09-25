"""desplegar_uv.py corrido en Blender de verdad. Optativo: sin BLENDER_EXE se
saltea, y eso es "no se probo", no "paso".

El juicio (horneado_puro.juzgar_despliegue) lo prueba el autotest de
horneado_puro.py en CI. Esto prueba lo que solo Blender puede: que la
seleccion por bmesh hace que pack_islands mueva las UV (trampa 17), que varias
mallas en edicion a la vez quedan en un atlas sin pisarse, y que la capa queda
activa y de render en el archivo guardado.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = (Path(__file__).resolve().parents[1] / "skills" / "modelo-ia-a-skyrim"
          / "scripts" / "desplegar_uv.py")


def _blender(*args):
    return subprocess.run(
        [os.environ["BLENDER_EXE"], "--background", "--factory-startup"] + list(args),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300)


def _desplegar(*args):
    return _blender("--python", str(SCRIPT), "--", *args)


def _escena(ruta):
    """Una esfera, un toro y un cubo en un .blend, sin capas UV nuevas."""
    p = _blender("--python-expr",
                 "import bpy\n"
                 "bpy.ops.wm.read_factory_settings(use_empty=True)\n"
                 "bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16)\n"
                 "bpy.ops.mesh.primitive_torus_add(location=(3, 0, 0))\n"
                 "bpy.ops.mesh.primitive_cube_add(location=(-3, 0, 0), size=1.5)\n"
                 "bpy.ops.wm.save_as_mainfile(filepath=%r)\n" % str(ruta))
    assert os.path.isfile(ruta), p.stdout + p.stderr


@unittest.skipUnless(os.environ.get("BLENDER_EXE"),
                     "requiere BLENDER_EXE; no se valido la API de Blender")
class DesplegarUVEnBlenderTests(unittest.TestCase):

    def test_falsificar(self):
        """Sin marcar las UV tiene que reprobar por empaquetado; marcandolas,
        pasar. Si la primera mitad pasara, la REGLA no discrimina."""
        p = _desplegar("--falsificar")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("falsificar: 2 comprobaciones, 0 fallas", p.stdout)

    def test_tres_mallas_un_atlas(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "baja.blend"
            _escena(ruta)
            p = _desplegar(str(ruta))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            linea = next(l for l in p.stdout.splitlines()
                         if l.startswith("[uv] {"))
            informe = json.loads(linea[len("[uv] "):])
            self.assertEqual(informe["mallas"], 3)
            self.assertEqual(informe["fallas"], [])
            self.assertEqual(informe["solape"], 0.0)
            self.assertEqual(informe["fuera_del_cuadro"], 0)
            self.assertLess(informe["densidad_max_sobre_min"], 1.05)

            # Guardado: UV_Bake activa y de render; la capa original queda.
            p = _blender(str(ruta), "--python-expr",
                         "import bpy\n"
                         "for o in bpy.data.objects:\n"
                         "    if o.type == 'MESH':\n"
                         "        print('[capas]', o.name, [(c.name, c.active, "
                         "c.active_render) for c in o.data.uv_layers])\n")
            capas = [l for l in p.stdout.splitlines() if l.startswith("[capas]")]
            self.assertEqual(len(capas), 3, p.stdout + p.stderr)
            for l in capas:
                self.assertIn("('UV_Bake', True, True)", l)
                self.assertIn("('UVMap', False, False)", l)

            # Sin --force no pisa la capa; con --force la rehace.
            p = _desplegar(str(ruta))
            self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
            self.assertIn("usa --force", p.stdout + p.stderr)
            p = _desplegar(str(ruta), "--force")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_argumento_que_no_sirve_sale_con_2(self):
        p = _desplegar("no-existe.blend")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
