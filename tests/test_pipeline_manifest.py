# -*- coding: utf-8 -*-
"""Tests del JobManifest: validación de configuración.

Cubre los contratos de la slice: configuración válida, path traversal
rechazado, extensión inválida, salida fuera del root rechazado y fuente
inexistente. AAA: Arrange / Act / Assert.
"""
import tempfile
import unittest
from pathlib import Path

from pipeline.errors import ConfigurationError
from pipeline.manifest import JobManifest


def _raiz_y_mesh():
    """Crea un proyecto temporario con un source mesh válido."""
    tmp = tempfile.TemporaryDirectory()
    raiz = Path(tmp.name)
    mesh = raiz / "entrada.glb"
    mesh.write_bytes(b"glTF-sintetico-de-test")
    (raiz / "workspace").mkdir()
    (raiz / "salida").mkdir()
    return tmp, raiz, mesh


def _manifest(raiz: Path, mesh: Path, **kwargs) -> JobManifest:
    base = dict(
        job_id="job-001",
        source_mesh=mesh,
        raiz_proyecto=raiz,
        workspace_raiz=raiz / "workspace",
        raiz_salida=raiz / "salida",
    )
    base.update(kwargs)
    return JobManifest(**base)


class JobManifestValidoTests(unittest.TestCase):
    def test_configuracion_valida(self):
        # Arrange
        tmp, raiz, mesh = _raiz_y_mesh()
        with tmp:
            # Act
            mani = _manifest(raiz, mesh)
            # Assert: no lanza y es inmutable
            mani.validar()
            with self.assertRaises(Exception):
                mani.job_id = "otro"  # dataclass frozen

    def test_texture_inputs_validas(self):
        # Arrange
        tmp, raiz, mesh = _raiz_y_mesh()
        with tmp:
            tex = raiz / "albedo.png"
            tex.write_bytes(b"\x89PNG")
            mani = _manifest(raiz, mesh, texture_inputs=(tex,))
            # Act / Assert
            mani.validar()


class JobManifestRechazoTests(unittest.TestCase):
    def _assert_rechaza(self, **kwargs):
        tmp, raiz, mesh = _raiz_y_mesh()
        with tmp:
            with self.assertRaises(ConfigurationError):
                _manifest(raiz, mesh, **kwargs).validar()

    def test_job_id_con_path_traversal_rechazado(self):
        # Arrange / Act / Assert: "../fuera" no es un id, es una ruta
        self._assert_rechaza(job_id="../fuera")

    def test_job_id_con_separador_rechazado(self):
        self._assert_rechaza(job_id="un/dos")

    def test_extension_fuente_invalida(self):
        tmp, raiz, mesh = _raiz_y_mesh()
        with tmp:
            exe = raiz / "entrada.exe"
            exe.write_bytes(b"MZ")
            with self.assertRaises(ConfigurationError):
                _manifest(raiz, exe).validar()

    def test_fuente_inexistente_rechazada(self):
        tmp, raiz, mesh = _raiz_y_mesh()
        with tmp:
            with self.assertRaises(ConfigurationError):
                _manifest(raiz, raiz / "no-existe.glb").validar()

    def test_salida_fuera_de_raiz_rechazada(self):
        tmp, raiz, mesh = _raiz_y_mesh()
        with tmp:
            # Arrange: salida resuelve fuera de raiz_proyecto (\"..\" real)
            fuera = raiz.parent / "salida-clandestina"
            # Act / Assert
            with self.assertRaises(ConfigurationError) as ctx:
                _manifest(raiz, mesh, raiz_salida=fuera).validar()
            self.assertIn("fuera de raiz_proyecto", str(ctx.exception))

    def test_workspace_fuera_de_raiz_rechazado(self):
        self._assert_rechaza(workspace_raiz=Path("C:/") / "absolutamente-fuera")

    def test_categoria_fuera_del_mvp_rechazada(self):
        # Arrange: criatura no es MVP de esta slice
        self._assert_rechaza(asset_category="creature")

    def test_reporta_todos_los_problemas_de_una_vez(self):
        tmp, raiz, mesh = _raiz_y_mesh()
        with tmp:
            mani = _manifest(
                raiz, raiz / "no-existe.glb",
                job_id="../malo", asset_category="armor",
            )
            with self.assertRaises(ConfigurationError) as ctx:
                mani.validar()
            msg = str(ctx.exception)
            self.assertIn("job_id", msg)
            self.assertIn("asset_category", msg)
            self.assertIn("no-existe.glb", msg)


if __name__ == "__main__":
    unittest.main()
