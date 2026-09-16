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
    def test_job_id_con_salto_de_linea_final_rechazado(self):
        # Regresión review: r"...$" + match() aceptaba "job-1\n".
        self._assert_rechaza(job_id="job-1\n")

    def test_job_id_no_string_rechazado(self):
        self._assert_rechaza(job_id=123)

    def test_source_mesh_none_da_configuration_error(self):
        tmp, raiz, mesh = _raiz_y_mesh()
        with tmp:
            mani = _manifest(raiz, mesh, source_mesh=None)
            with self.assertRaises(ConfigurationError) as ctx:
                mani.validar()
            self.assertIn("source_mesh", str(ctx.exception))

    def test_rutas_none_dan_configuration_error(self):
        tmp, raiz, mesh = _raiz_y_mesh()
        with tmp:
            mani = _manifest(
                raiz, mesh, workspace_raiz=None, raiz_salida=None,
            )
            with self.assertRaises(ConfigurationError) as ctx:
                mani.validar()
            msg = str(ctx.exception)
            self.assertIn("workspace_raiz", msg)
            self.assertIn("raiz_salida", msg)

    def test_string_vacio_rechazado(self):
        # "" no se convierte silenciosamente a Path(".") (cwd): se reporta.
        tmp, raiz, mesh = _raiz_y_mesh()
        with tmp:
            mani = _manifest(raiz, mesh, source_mesh="")
            with self.assertRaises(ConfigurationError) as ctx:
                mani.validar()
            self.assertIn("inválido o vacío", str(ctx.exception))

    def test_reference_asset_string_invalido_no_se_traga(self):
        # Antes: "if self.reference_asset" trataba "" como ausente.
        tmp, raiz, mesh = _raiz_y_mesh()
        with tmp:
            mani = _manifest(raiz, mesh, reference_asset="")
            with self.assertRaises(ConfigurationError) as ctx:
                mani.validar()
            self.assertIn("reference_asset", str(ctx.exception))

    def test_acepta_rutas_como_strings(self):
        # Configuración declarativa: el JSON trae strings, no Paths.
        tmp, raiz, mesh = _raiz_y_mesh()
        with tmp:
            mani = JobManifest(
                job_id="job-str",
                source_mesh=str(mesh),
                raiz_proyecto=str(raiz),
                workspace_raiz=str(raiz / "workspace"),
                raiz_salida=str(raiz / "salida"),
                texture_inputs=str(raiz / "albedo.png"),
            )
            (raiz / "albedo.png").write_bytes(b"\x89PNG")
            mani.validar()
            self.assertIsInstance(mani.source_mesh, Path)
            self.assertEqual(len(mani.texture_inputs), 1)

    def test_texture_inputs_tipo_invalido_rechazado(self):
        tmp, raiz, mesh = _raiz_y_mesh()
        with tmp:
            mani = _manifest(raiz, mesh, texture_inputs=42)
            with self.assertRaises(ConfigurationError) as ctx:
                mani.validar()
            self.assertIn("texture_inputs", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
