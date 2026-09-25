# -*- coding: utf-8 -*-
"""La logica de conservar_uv, sin Blender: corre en CI.

tests/test_uv_exportacion_blender.py prueba lo que solo Blender puede probar
(que la coleccion RNA real se comporta como se cree) y se saltea sin
BLENDER_EXE. Esto prueba el resto con una malla falsa: las guardas rechazan
ANTES de borrar, queda la capa pedida activa y de render, los valores no
cambian, y los nodos que nombraban una capa borrada se avisan.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "skills", "modelo-ia-a-skyrim", "scripts"))
import uv_exportacion as ux  # noqa: E402


class _Dato:
    def __init__(self, uv):
        self.uv = uv


class _Capa:
    def __init__(self, nombre, uvs):
        self.name = nombre
        self.data = [_Dato(uv) for uv in uvs]
        self.active_render = False


class _Capas:
    def __init__(self, capas):
        self._capas = list(capas)
        self.active = self._capas[0] if self._capas else None

    def keys(self):
        return [c.name for c in self._capas]

    def __contains__(self, nombre):
        return nombre in self.keys()

    def __getitem__(self, clave):
        if isinstance(clave, int):
            return self._capas[clave]
        return next(c for c in self._capas if c.name == clave)

    def remove(self, capa):
        self._capas.remove(capa)


class _Nodo:
    def __init__(self, nombre, tipo, **attrs):
        self.name, self.type = nombre, tipo
        for k, v in attrs.items():
            setattr(self, k, v)


class _Material:
    def __init__(self, nombre, nodos):
        self.name, self.use_nodes = nombre, True
        self.node_tree = type("Arbol", (), {"nodes": nodos})()


class _Malla:
    def __init__(self, nombres, usuarios=1, editmode=False, materiales=()):
        self.uv_layers = _Capas(_Capa(n, [(k * .2, k * .1), (k * .2 + .03, .05)])
                                for k, n in enumerate(nombres))
        self.users, self.is_editmode = usuarios, editmode
        self.materials = list(materiales)
        self.actualizada = False

    def update(self):
        self.actualizada = True


NOMBRES = ("UV_Original", "UV_Bake", "UV_Aux")


class ConservarUVTests(unittest.TestCase):

    def test_deja_solo_la_pedida_activa_y_de_render(self):
        m = _Malla(NOMBRES)
        antes = [d.uv for d in m.uv_layers["UV_Bake"].data]
        self.assertEqual(ux.conservar_uv(m, "UV_Bake"), [])
        self.assertEqual(m.uv_layers.keys(), ["UV_Bake"])
        self.assertIs(m.uv_layers.active, m.uv_layers["UV_Bake"])
        self.assertTrue(m.uv_layers["UV_Bake"].active_render)
        self.assertEqual([d.uv for d in m.uv_layers["UV_Bake"].data], antes)
        self.assertTrue(m.actualizada)

    def test_las_guardas_rechazan_antes_de_borrar(self):
        for nombre, malla, pedida in (
                ("edit mode", _Malla(NOMBRES, editmode=True), "UV_Bake"),
                ("compartida", _Malla(NOMBRES, usuarios=2), "UV_Bake"),
                ("nombre ausente", _Malla(NOMBRES), "UV_NoExiste")):
            with self.subTest(nombre):
                with self.assertRaises(ValueError):
                    ux.conservar_uv(malla, pedida)
                self.assertEqual(malla.uv_layers.keys(), list(NOMBRES))

    def test_coordenadas_cambiadas_dicen_cuantas(self):
        m = _Malla(NOMBRES)
        remove = m.uv_layers.remove

        def remove_que_corre(capa):
            remove(capa)
            m.uv_layers["UV_Bake"].data[1].uv = (9, 9)
        m.uv_layers.remove = remove_que_corre
        with self.assertRaises(RuntimeError) as ctx:
            ux.conservar_uv(m, "UV_Bake")
        self.assertIn("1 de 2", str(ctx.exception))
        self.assertIn("indice 1", str(ctx.exception))

    def test_avisa_los_nodos_que_nombraban_una_capa_borrada(self):
        mat = _Material("Metal", [
            _Nodo("UV vieja", "UVMAP", uv_map="UV_Original"),
            _Nodo("UV buena", "UVMAP", uv_map="UV_Bake"),
            _Nodo("Atributo", "ATTRIBUTE", attribute_name="UV_Aux"),
            _Nodo("Otro", "BSDF_PRINCIPLED")])
        m = _Malla(NOMBRES, materiales=[mat, None])
        self.assertEqual(ux.conservar_uv(m, "UV_Bake"),
                         ["Metal / UV vieja -> UV_Original",
                          "Metal / Atributo -> UV_Aux"])


if __name__ == "__main__":
    unittest.main()
