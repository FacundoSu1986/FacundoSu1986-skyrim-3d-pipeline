"""hornear.py corrido en Blender de verdad: la medicion de la fuente y
--sin-doble. Optativo: sin BLENDER_EXE se saltea, y eso es "no se probo", no
"paso".

La cuenta y los avisos (retencion, avisos_de_la_fuente, lados_de_imagenes) los
prueba el autotest de horneado_puro.py en CI. Esto prueba lo que solo Blender
puede: que el tamano de la textura se lee de la alta cargada del .blend, que
el area sale de su capa UV de render, y que sin el doble el bake es de <res>
y el PNG tambien.

La escena tiene la cuenta exacta: baja y alta son el mismo plano de 2 x 2
(area 4) con las UV en todo el cuadro, y la alta lleva una textura de 256.
Densidad de la fuente: sqrt(1 * 256^2 / 4) = 128 texeles por unidad; la de la
baja a <res>: res / 2. Retencion: res / 256.
"""
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

SCRIPT = (Path(__file__).resolve().parents[1] / "skills" / "modelo-ia-a-skyrim"
          / "scripts" / "hornear.py")


def _blender(*args):
    return subprocess.run(
        [os.environ["BLENDER_EXE"], "--background", "--factory-startup"] + list(args),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=600)


ESCENA = """
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_plane_add(size=2.0)
baja = bpy.context.active_object
baja.name = "pieza"
bpy.ops.wm.save_as_mainfile(filepath=%(baja)r)
baja.name = "pieza_alto"
if %(con_textura)r:
    mat = bpy.data.materials.new("pintura")
    mat.use_nodes = True
    img = bpy.data.images.new("tripo", 256, 256)
    img.generated_type = "UV_GRID"
    nodo = mat.node_tree.nodes.new("ShaderNodeTexImage")
    nodo.image = img
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    mat.node_tree.links.new(nodo.outputs["Color"], bsdf.inputs["Base Color"])
    baja.data.materials.append(mat)
bpy.ops.wm.save_as_mainfile(filepath=%(alta)r)
"""


def _lado_png(ruta):
    with open(ruta, "rb") as fh:
        cab = fh.read(24)
    return struct.unpack(">II", cab[16:24])


@unittest.skipUnless(os.environ.get("BLENDER_EXE"),
                     "requiere BLENDER_EXE; no se valido la API de Blender")
class HornearFuenteEnBlenderTests(unittest.TestCase):

    def _hornear(self, d, res, *extra, con_textura=True):
        baja, alta = Path(d) / "baja.blend", Path(d) / "alta.blend"
        if not baja.exists():
            p = _blender("--python-expr", ESCENA % {
                "baja": str(baja), "alta": str(alta), "con_textura": con_textura})
            self.assertTrue(alta.exists(), p.stdout + p.stderr)
        salida = Path(d) / ("salida_%d%s" % (res, "".join(extra)))
        p = _blender("--python", str(SCRIPT), "--", str(baja), str(salida),
                     str(res), str(alta), *extra)
        self.assertEqual(p.returncode, 0, p.stdout[-3000:] + p.stderr[-3000:])
        with open(salida / "baja_horneado.json", encoding="utf-8") as fh:
            return json.load(fh), salida

    @staticmethod
    def _de_la_fuente(rep):
        return [a for a in rep["avisos"]
                if "resolucion lineal" in a or "trampa 35" in a]

    def test_al_doble_avisa_cuando_el_atlas_tira_resolucion(self):
        with tempfile.TemporaryDirectory() as d:
            rep, salida = self._hornear(d, 64)
            self.assertFalse(rep["sin_doble"])
            self.assertEqual(rep["horneado_a"], 128)
            self.assertEqual(rep["densidad_fuente"]["pieza_alto"],
                             {"lado": [256, 256], "densidad": 128.0})
            self.assertEqual(rep["retencion"], {"pieza": 0.25})
            avisos = self._de_la_fuente(rep)
            self.assertEqual(len(avisos), 1, rep["avisos"])
            self.assertIn("pieza 25 %", avisos[0])
            self.assertEqual(_lado_png(salida / "baja_albedo.png"), (64, 64))

    def test_sin_doble_hornea_a_res_y_avisa_el_aliasing(self):
        with tempfile.TemporaryDirectory() as d:
            rep, salida = self._hornear(d, 128, "--sin-doble")
            self.assertTrue(rep["sin_doble"])
            self.assertEqual(rep["horneado_a"], 128)
            self.assertEqual(rep["retencion"], {"pieza": 0.5})
            avisos = self._de_la_fuente(rep)
            # 0,5 no es "poco" (el umbral es estricto) pero si es aliasing
            self.assertEqual(len(avisos), 1, rep["avisos"])
            self.assertIn("trampa 35", avisos[0])
            self.assertEqual(_lado_png(salida / "baja_normalgl.png"), (128, 128))

    def test_sin_doble_con_el_destino_mas_fino_no_avisa(self):
        with tempfile.TemporaryDirectory() as d:
            rep, salida = self._hornear(d, 512, "--sin-doble")
            self.assertEqual(rep["horneado_a"], 512)
            self.assertEqual(rep["retencion"], {"pieza": 2.0})
            self.assertEqual(self._de_la_fuente(rep), [], rep["avisos"])
            self.assertEqual(_lado_png(salida / "baja_ao.png"), (512, 512))

    def test_alta_sin_textura_no_tiene_fuente(self):
        with tempfile.TemporaryDirectory() as d:
            rep, _salida = self._hornear(d, 64, con_textura=False)
            self.assertEqual(rep["densidad_fuente"]["pieza_alto"],
                             {"lado": None, "densidad": None})
            self.assertEqual(rep["retencion"], {"pieza": None})
            self.assertEqual(self._de_la_fuente(rep), [], rep["avisos"])


if __name__ == "__main__":
    unittest.main()
