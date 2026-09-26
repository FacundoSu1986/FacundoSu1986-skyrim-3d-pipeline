"""exportar_nif.py corrido en Blender con PyNifly. Optativo: sin BLENDER_EXE
se saltea, y eso es "no se probo", no "paso".

Lo puro (plan, soldadura, caja, inercia, flags, texturas) lo prueba
test_exportar_puro.py en CI. Esto prueba lo que solo Blender y el addon
pueden: la falsificacion arma con PyNifly un donante sintetico y exporta
cuatro planes --el bueno, con metal, un vidrio con alfa por vertice y un panel
con el alfa en la textura, sale con las recetas copiadas y conciliadas y el
alfa como estaba en la escena; un vidrio sin capa VERTEX_ALPHA, uno con la
capa pareja y un donante sin inercia reprueban--.
"""
import os
from pathlib import Path
import subprocess
import unittest

SCRIPT = (Path(__file__).resolve().parents[1] / "skills" / "asset-nuevo-skyrim"
          / "scripts" / "exportar_nif.py")


def _exportar(*args):
    return subprocess.run(
        [os.environ["BLENDER_EXE"], "--background", "--factory-startup",
         "--python", str(SCRIPT), "--"] + list(args),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300)


@unittest.skipUnless(os.environ.get("BLENDER_EXE"),
                     "requiere BLENDER_EXE y PyNifly; no se valido")
class ExportarNifEnBlenderTests(unittest.TestCase):

    def test_falsificar(self):
        p = _exportar("--falsificar")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("falsificar: 17 comprobaciones, 0 fallas", p.stdout)

    def test_argumento_que_no_sirve_sale_con_2(self):
        p = _exportar("no-existe.json", "no-existe.blend")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
