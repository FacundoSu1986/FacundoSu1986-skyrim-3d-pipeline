"""Control optativo real, separado de las pruebas de Python puro de CI."""
import os
from pathlib import Path
import subprocess
import unittest


@unittest.skipUnless(os.environ.get("BLENDER_EXE"),
                     "requiere BLENDER_EXE; no se valido la API de Blender")
class UVEnBlenderTests(unittest.TestCase):
    def test_conserva_atlas_en_mesh_real(self):
        script = Path(__file__).with_name("blender_uv_exportacion.py")
        proceso = subprocess.run(
            [os.environ["BLENDER_EXE"], "--background", "--factory-startup",
             "--python-exit-code", "1", "--python", str(script)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120)
        self.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
        self.assertIn("Ran 4 tests", proceso.stderr)


if __name__ == "__main__":
    unittest.main()
