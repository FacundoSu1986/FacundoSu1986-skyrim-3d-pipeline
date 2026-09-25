"""Regresion con Mesh real: no necesita PyNifly ni assets del juego.

Ejecutar mediante test_uv_exportacion_blender.py con BLENDER_EXE configurado.
--repro reproduce la limpieza defectuosa previa, y debe fallar en Blender 4.4.1.
"""
import itertools
from pathlib import Path
import sys
import unittest

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "skills/modelo-ia-a-skyrim/scripts"))

if "--repro" in sys.argv:
    def conservar_uv(mesh, nombre):
        for capa in list(mesh.uv_layers):
            if capa.name != nombre:
                mesh.uv_layers.remove(capa)
else:
    from uv_exportacion import conservar_uv


def crear_malla(orden):
    mesh = bpy.data.meshes.new("regresion_uv")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    for numero, nombre in enumerate(orden):
        capa = mesh.uv_layers.new(name=nombre, do_init=False)
        for i, dato in enumerate(capa.data):
            dato.uv = (numero * 0.2 + i * 0.03, numero * 0.1 + i * 0.05)
    mesh.uv_layers.active = mesh.uv_layers["UV_Bake"]
    mesh.uv_layers["UV_Bake"].active_render = True
    return mesh


def coordenadas(mesh, nombre):
    return [tuple(v.uv) for v in mesh.uv_layers[nombre].data]


class ConservarUVTests(unittest.TestCase):
    def test_retiene_nombre_y_coordenadas_en_cualquier_posicion(self):
        for orden in itertools.permutations(("UV_Original", "UV_Bake", "UV_Aux")):
            with self.subTest(orden=orden):
                mesh = crear_malla(orden)
                try:
                    esperado = coordenadas(mesh, "UV_Bake")
                    conservar_uv(mesh, "UV_Bake")
                    self.assertEqual(list(mesh.uv_layers.keys()), ["UV_Bake"])
                    self.assertEqual(coordenadas(mesh, "UV_Bake"), esperado)
                    self.assertEqual(mesh.uv_layers.active.name, "UV_Bake")
                    self.assertTrue(mesh.uv_layers[0].active_render)
                    # Volver a preparar no cambia el atlas ni sus coordenadas.
                    conservar_uv(mesh, "UV_Bake")
                    self.assertEqual(coordenadas(mesh, "UV_Bake"), esperado)
                finally:
                    bpy.data.meshes.remove(mesh)

    def test_nombre_inexistente_no_borra_capas(self):
        mesh = crear_malla(("UV_Original", "UV_Bake", "UV_Aux"))
        try:
            antes = {n: coordenadas(mesh, n) for n in mesh.uv_layers.keys()}
            with self.assertRaises(ValueError):
                conservar_uv(mesh, "UV_NoExiste")
            self.assertEqual({n: coordenadas(mesh, n) for n in mesh.uv_layers.keys()}, antes)
        finally:
            bpy.data.meshes.remove(mesh)

    def test_trabajar_en_copia_conserva_la_fuente(self):
        fuente = crear_malla(("UV_Original", "UV_Bake", "UV_Aux"))
        copia = fuente.copy()
        try:
            antes = {n: coordenadas(fuente, n) for n in fuente.uv_layers.keys()}
            conservar_uv(copia, "UV_Bake")
            self.assertEqual(list(copia.uv_layers.keys()), ["UV_Bake"])
            self.assertEqual({n: coordenadas(fuente, n) for n in fuente.uv_layers.keys()}, antes)
        finally:
            bpy.data.meshes.remove(copia)
            bpy.data.meshes.remove(fuente)

    def test_edit_mode_rechazado_sin_perder_uv(self):
        mesh = crear_malla(("UV_Original", "UV_Bake", "UV_Aux"))
        obj = bpy.data.objects.new("regresion_uv", mesh)
        bpy.context.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        try:
            bpy.ops.object.mode_set(mode='EDIT')
            with self.assertRaises(ValueError):
                conservar_uv(mesh, "UV_Bake")
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')
            self.assertEqual(len(mesh.uv_layers), 3)
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.meshes.remove(mesh)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ConservarUVTests)
    if "--repro" in sys.argv:
        suite = unittest.TestSuite([ConservarUVTests(
            "test_retiene_nombre_y_coordenadas_en_cualquier_posicion")])
    resultado = unittest.TextTestRunner(verbosity=2).run(suite)
    if not resultado.wasSuccessful():
        raise RuntimeError("regresion de capas UV")
