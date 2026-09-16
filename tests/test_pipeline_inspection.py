# -*- coding: utf-8 -*-
"""Tests del inspector GLB (issue #4) sobre el fixture sintético.

El principio conductor: el conteo de "triángulos" debe salir del modo e
índices de cada primitive, nunca de una heurística; y el detector debe saber
fallar — por eso la mitad de los tests corrompe el fixture a propósito.
"""
import tempfile
import unittest
from pathlib import Path

from glb_sintetico import construir
from pipeline.errors import ArtifactValidationError
from pipeline.inspection import inspeccionar_malla


def _escribir(tmp: str, datos: bytes, nombre: str = "malla.glb") -> Path:
    ruta = Path(tmp) / nombre
    ruta.write_bytes(datos)
    return ruta


class InspeccionFelizTests(unittest.TestCase):
    def test_cuenta_triangulos_reales_indexados(self):
        # Arrange: 4 vértices, 4 índices, modo TRIANGLES → 4//3 = 1
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, construir(modo=4, con_indices=True))
            # Act
            rep = inspeccionar_malla(ruta)
            # Assert
            self.assertTrue(rep["inspeccionado"])
            self.assertEqual(rep["triangulos_total"], 1)
            self.assertEqual(rep["vertices_total"], 4)
            self.assertTrue(rep["todos_triangulares"])
            self.assertTrue(rep["checks"]["parseable"])

    def test_strip_cuenta_tira_no_vertices(self):
        # Arrange: STRIP con 4 elementos → 2 triángulos (n-2), no 4/3
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, construir(modo=5, con_indices=True))
            rep = inspeccionar_malla(ruta)
            self.assertEqual(rep["triangulos_total"], 2)

    def test_non_indexed_usa_vertices(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 3 vértices sin índices → 1 triángulo
            con3 = tuple((float(i), 0.0, 0.0) for i in range(3))
            ruta = _escribir(
                tmp, construir(con_indices=False, vertices=con3)
            )
            rep = inspeccionar_malla(ruta)
            self.assertEqual(rep["triangulos_total"], 1)

    def test_modo_no_triangular_no_se_cuenta_a_ojo(self):
        # Arrange: LINES — reportar honesto, no adivinar
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, construir(modo=1))
            rep = inspeccionar_malla(ruta)
            # Assert
            self.assertTrue(rep["inspeccionado"])
            self.assertIsNone(rep["triangulos_total"])
            self.assertFalse(rep["todos_triangulares"])

    def test_atributos_uv_y_dimensiones(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, construir())
            rep = inspeccionar_malla(ruta)
            self.assertTrue(rep["uv_presente"])
            self.assertTrue(rep["normales_presentes"])
            self.assertEqual(rep["dimensiones"]["tamano"], [1.0, 1.0, 0.0])

    def test_sin_uv_se_reporta_como_tal(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, construir(con_uv=False))
            self.assertFalse(inspeccionar_malla(ruta)["uv_presente"])

    def test_slots_semanticos_desde_el_formato_no_del_nombre(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, construir())
            rep = inspeccionar_malla(ruta)
            mat = rep["materiales"][0]
            # Assert: los slots vienen de pbrMetallicRoughness/material,
            # no de parsear "albedo.png" como nombre
            self.assertEqual(mat["slots"]["baseColor"]["uri"], "albedo.png")
            self.assertEqual(mat["slots"]["normal"]["uri"], "normal.png")
            self.assertEqual(
                mat["slots"]["metallicRoughness"]["uri"], "mr.png"
            )
            self.assertEqual(mat["slots"]["occlusion"]["uri"],
                             "occlusion.png")
            self.assertEqual(mat["slots"]["emissive"]["uri"],
                             "emissive.png")

    def test_formato_sin_soporte_se_reporta_honesto(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, b"datos", nombre="malla.fbx")
            rep = inspeccionar_malla(ruta)
            self.assertFalse(rep["inspeccionado"])
            self.assertFalse(rep["checks"]["parseable"])

    def test_inspeccion_es_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            datos = construir()
            ruta = _escribir(tmp, datos)
            inspeccionar_malla(ruta)
            self.assertEqual(ruta.read_bytes(), datos)


class InspeccionFalsificacionTests(unittest.TestCase):
    """Qué pasa cuando el archivo miente o está roto: tiene que explotar
    ArtifactValidationError, no devolver números inventados."""

    def test_magic_incorrecto(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = _escribir(tmp, construir().replace(b"glTF", b"XXXX", 1))
            with self.assertRaises(ArtifactValidationError):
                inspeccionar_malla(ruta)

    def test_largo_declarado_distinto(self):
        with tempfile.TemporaryDirectory() as tmp:
            datos = bytearray(construir())
            datos[8] ^= 0xFF  # corromper el largo total
            ruta = _escribir(tmp, bytes(datos))
            with self.assertRaises(ArtifactValidationError):
                inspeccionar_malla(ruta)

    def test_chunk_json_truncado(self):
        with tempfile.TemporaryDirectory() as tmp:
            datos = construir()
            ruta = _escribir(tmp, datos[: len(datos) // 2])
            with self.assertRaises(ArtifactValidationError):
                inspeccionar_malla(ruta)

    def test_accessor_fuera_del_bin(self):
        # Arrange: el accessor POSITION declara un count que excede el BIN.
        # "4" → "99" mantiene el mismo largo de JSON, así la falsificación
        # ejercita exactamente el chequeo de containment y no otro.
        with tempfile.TemporaryDirectory() as tmp:
            datos = construir().replace(b'"count": 4', b'"count": 99', 1)
            ruta = _escribir(tmp, datos)
            with self.assertRaises(ArtifactValidationError):
                inspeccionar_malla(ruta)


if __name__ == "__main__":
    unittest.main()
