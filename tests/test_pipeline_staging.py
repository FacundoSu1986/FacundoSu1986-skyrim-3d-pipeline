# -*- coding: utf-8 -*-
"""Tests del staging aislado por job.

Contratos: dos jobs no se pisan, un job_id malicioso no escapa de
workspace_raiz, las rutas de artefactos no escapan de su subdir, y la
limpieza ante fallo preserva diagnósticos (nunca borra evidencia).
"""
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


if __name__ == "__main__":
    unittest.main()
