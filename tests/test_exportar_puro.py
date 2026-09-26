# -*- coding: utf-8 -*-
"""exportar_puro.py: lo del export de un asset nuevo que corre sin Blender.

El autotest cubre el plan, la soldadura (la V invertida, las costuras, las
aristas duras, el color por vertice y el tope de 65.535 vertices), la caja,
la inercia, los flags, las texturas, el modo de alfa y el alfa parejo. Lo
ponen rojo diez mutantes: la V sin invertir, SKINNED sin apagar, copiar las
texturas del donante, el radio sin tope, y seis del alfa --aceptar el alfa
parejo en 1 o en 0, rechazar el parejo intermedio, no anotar el alfa
ignorado, ignorar VERTEX_ALPHA y sacar el color de la clave de la
soldadura--.
"""
import unittest

from _paths import preparar_path

preparar_path()

import exportar_puro as ep  # noqa: E402


class ExportarPuroTests(unittest.TestCase):

    def test_el_autotest_pasa(self):
        self.assertEqual(ep.autotest(), 0)

    def test_los_bits_que_concilia(self):
        # Los de nifdefs de PyNifly 27.2; exportar_nif.py los compara contra
        # los del addon antes de escribir.
        self.assertEqual((ep.SF1_SKINNED, ep.SF1_VERTEX_ALPHA,
                          ep.SF1_MODEL_SPACE_NORMALS, ep.SF2_VERTEX_COLORS),
                         (0x2, 0x8, 0x1000, 0x20))

    def test_las_ranuras(self):
        self.assertEqual(ep.RANURAS_RECETA, ("EnvMap",))
        self.assertEqual(set(ep.RANURAS_ASSET) & set(ep.RANURAS_RECETA), set())


if __name__ == "__main__":
    unittest.main()
