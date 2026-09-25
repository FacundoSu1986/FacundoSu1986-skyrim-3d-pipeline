"""Control optativo real, separado de las pruebas de Python puro de CI.

La logica de conservar_uv la prueba tests/test_uv_exportacion.py en CI con una
malla falsa. Esto prueba lo que solo Blender puede: que la coleccion RNA real
se comporta como la falsa. Sin BLENDER_EXE se saltea, y eso es "no se probo",
no "paso".
"""
import os
from pathlib import Path
import subprocess
import unittest

SCRIPT = Path(__file__).with_name("blender_uv_exportacion.py")


def _correr(*extra):
    return subprocess.run(
        [os.environ["BLENDER_EXE"], "--background", "--factory-startup",
         "--python-exit-code", "1", "--python", str(SCRIPT), "--"] + list(extra),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120)


@unittest.skipUnless(os.environ.get("BLENDER_EXE"),
                     "requiere BLENDER_EXE; no se valido la API de Blender")
class UVEnBlenderTests(unittest.TestCase):
    def test_conserva_atlas_en_mesh_real(self):
        proceso = _correr()
        self.assertEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
        self.assertIn("Ran 6 tests", proceso.stderr)

    def test_la_limpieza_vieja_falla(self):
        """El control negativo: el bucle con referencias RNA guardadas
        (trampa 40) tiene que reprobar la misma prueba. Si pasara, la prueba
        no discrimina y el arreglo no demuestra nada."""
        proceso = _correr("--repro")
        self.assertNotEqual(proceso.returncode, 0, proceso.stdout + proceso.stderr)
        self.assertIn("Ran 1 test", proceso.stderr)


if __name__ == "__main__":
    unittest.main()
