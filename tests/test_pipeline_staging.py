# -*- coding: utf-8 -*-
"""Tests del staging aislado por job.

Contratos: dos jobs no se pisan, un job_id malicioso no escapa de
workspace_raiz, las rutas de artefactos no escapan de su subdir, y la
limpieza ante fallo preserva diagnósticos (nunca borra evidencia).
"""
import os
import tempfile
import unittest
from pathlib import Path

from pipeline.errors import ConfigurationError
from pipeline.staging import JobWorkspace, SUBDIRS


class StagingAislamientoTests(unittest.TestCase):
    def test_dos_jobs_quedan_aislados(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp) / "workspace"
            a = JobWorkspace(raiz, "job-a").crear()
            b = JobWorkspace(raiz, "job-b").crear()
            # Act
            (a / "reports" / "x.json").write_text("{}", encoding="utf-8")
            # Assert
            self.assertTrue((a / "reports" / "x.json").is_file())
            self.assertFalse((b / "reports" / "x.json").exists())
            self.assertNotEqual(a, b)

    def test_subdirs_estandar_creados(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws_dir = JobWorkspace(Path(tmp), "job-a").crear()
            for sub in SUBDIRS:
                self.assertTrue((ws_dir / sub).is_dir(), sub)

    def test_job_id_con_traversal_no_escapa(self):
        # Arrange / Act / Assert: aun sin manifest validado, el workspace
        # rechaza un id que resolvería fuera de workspace_raiz.
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConfigurationError):
                JobWorkspace(Path(tmp), "..")

    def test_ruta_de_artefacto_no_escapa_del_subdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = JobWorkspace(Path(tmp), "job-a")
            ws.crear()
            with self.assertRaises(ConfigurationError):
                ws.ruta_segura(Path("..") / ".." / "fuera.bin", subdir="package")

    def test_ruta_absoluta_rechazada(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = JobWorkspace(Path(tmp), "job-a")
            ws.crear()
            with self.assertRaises(ConfigurationError):
                ws.ruta_segura(Path(tmp) / "absoluta.bin", subdir="package")

    def test_subdir_desconocido_rechazado(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = JobWorkspace(Path(tmp), "job-a")
            ws.crear()
            with self.assertRaises(ConfigurationError):
                ws.subdir("secreto")

    def test_fallo_preserva_diagnosticos(self):
        # Arrange
        with tempfile.TemporaryDirectory() as tmp:
            ws = JobWorkspace(Path(tmp), "job-a")
            d = ws.crear()
            (d / "reports" / "error.json").write_text("{}", encoding="utf-8")
            # Act: limpieza tras FALLO
            ws.limpiar(exito=False)
            # Assert: la evidencia sigue ahí
            self.assertTrue((d / "reports" / "error.json").is_file())

    def test_exito_permite_limpieza_explicita(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = JobWorkspace(Path(tmp), "job-a")
            d = ws.crear()
            ws.limpiar(exito=True)
            self.assertFalse(d.exists())


class StagingReintentoTests(unittest.TestCase):
    """Regresión del hallazgo de review: un workspace con artefactos de una
    corrida fallida NO se reutiliza en silencio (publicaría restos)."""

    def test_workspace_existente_se_rechaza(self):
        # Arrange: una corrida anterior (fallida o no) dejó el dir
        with tempfile.TemporaryDirectory() as tmp:
            ws = JobWorkspace(Path(tmp), "job-a")
            d = ws.crear()
            (d / "package" / "parcial.nif").write_bytes(b"restos")
            # Act / Assert
            with self.assertRaises(ConfigurationError):
                ws.crear()

    def test_reintento_explicito_limpia_todo(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = JobWorkspace(Path(tmp), "job-a")
            d = ws.crear()
            (d / "package" / "parcial.nif").write_bytes(b"restos")
            # Act: reintento EXPLÍCITO — decisión del llamador
            ws.crear(fresco=True)
            # Assert
            self.assertFalse((d / "package" / "parcial.nif").exists())
            self.assertTrue((d / "package").is_dir())


def _hacer_symlink(origen: Path, destino: Path) -> bool:
    """True si se pudo crear (Windows puede negarlo sin Developer Mode)."""
    try:
        os.symlink(origen, destino, target_is_directory=origen.is_dir())
        return True
    except OSError:
        return False


class StagingSymlinkTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        # Arrange común: un "afuera" real al que apuntan los symlinks
        self.afuera = Path(tempfile.mkdtemp())

    def tearDown(self):
        self._tmp.cleanup()
        import shutil
        shutil.rmtree(self.afuera, ignore_errors=True)

    def test_job_id_symlink_no_escapa(self):
        # Arrange: workspace/job-a es symlink al dir de otro job
        ws_raiz = self.tmp / "workspace"
        ws_raiz.mkdir()
        otro = ws_raiz / "job-otro"
        otro.mkdir()
        objetivo = ws_raiz / "job-a"
        if not _hacer_symlink(otro, objetivo):
            self.skipTest("symlinks no disponibles en este entorno")
        # Act / Assert: resolve() saca el dir fuera de su posición nominal
        with self.assertRaises(ConfigurationError):
            JobWorkspace(ws_raiz, "job-a").crear()

    def test_subdir_symlink_rechazado_en_crear(self):
        # Arrange: package/ pre-existe como symlink a un dir externo.
        # crear() lo rechaza de todas formas: ya sea por workspace
        # existente (fail-closed) — lo importante es que NUNCA se reutiliza
        # silenciosamente un árbol con un symlink dentro.
        ws_raiz = self.tmp / "workspace"
        job = ws_raiz / "job-a"
        job.mkdir(parents=True)
        if not _hacer_symlink(self.afuera, job / "package"):
            self.skipTest("symlinks no disponibles en este entorno")
        ws = JobWorkspace(ws_raiz, "job-a")
        with self.assertRaises(ConfigurationError):
            ws.crear()
        # Y con reintento explícito: el árbol con symlink se borra entero.
        ws.crear(fresco=True)
        self.assertFalse((job / "package").is_symlink())
        self.assertTrue((job / "package").is_dir())
        # El directorio externo no se tocó.
        self.assertTrue(self.afuera.is_dir())

    def test_ruta_segura_no_sale_por_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = JobWorkspace(Path(tmp), "job-a")
            ws.crear()
            # Act: reemplazar package/ por un symlink externo a media vida
            ws.subdir("package").rmdir()
            if not _hacer_symlink(self.afuera, ws.dir / "package"):
                self.skipTest("symlinks no disponibles en este entorno")
            # Assert: se detecta, no se devuelve la ruta externa
            with self.assertRaises(ConfigurationError):
                ws.ruta_segura(Path("asset.nif"), subdir="package")


if __name__ == "__main__":
    unittest.main()
