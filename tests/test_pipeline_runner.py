# -*- coding: utf-8 -*-
"""Tests del PipelineRunner con adaptadores falsos.

Demuestran los cinco contratos de la slice sin Blender/BAE/TexConv/PyNifly:

  1. un job válido progresa hasta PUBLISHED;
  2. un job inválido no arranca (ni crea staging);
  3. una fase que falla detiene el pipeline (fases posteriores no corren);
  4. el destino final no se toca ante un fallo;
  5. el source_mesh no se modifica (hash antes = hash después).

Además: publicación fail-closed ante destino existente, y un detector
falso (paquete vacío -> no publicar) prueba que la guarda puede fallar.
"""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from pipeline.errors import PublishError
from pipeline.manifest import JobManifest
from pipeline.runner import Phase, PipelineRunner, State
from pipeline.staging import JobWorkspace


def _entorno():
    """Crea proyecto temporario: raiz, workspace, salida y un source mesh."""
    tmp = tempfile.TemporaryDirectory()
    raiz = Path(tmp.name)
    (raiz / "workspace").mkdir()
    (raiz / "salida").mkdir()
    mesh = raiz / "entrada.glb"
    mesh.write_bytes(b"mesh-sintetico-determinista")
    manifest = JobManifest(
        job_id="job-test",
        source_mesh=mesh,
        raiz_proyecto=raiz,
        workspace_raiz=raiz / "workspace",
        raiz_salida=raiz / "salida",
    )
    return tmp, raiz, mesh, manifest


def _hash(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _fase_package_real(mani, ws):
    """Fake de PACKAGE: deja un artefacto sintético en package/."""
    artefacto = ws.ruta_segura(Path("asset.nif"), subdir="package")
    artefacto.write_bytes(b"NIF-sintetico-de-test")
    return {"artefactos": [artefacto.name]}


def _fase_ok(mani, ws):
    return {"ejecutada": True}


class RunnerCaminoFelizTests(unittest.TestCase):
    def test_job_valido_progresa_hasta_published(self):
        # Arrange
        tmp, raiz, mesh, manifest = _entorno()
        with tmp:
            # Act
            res = PipelineRunner(
                manifest, {Phase.PACKAGE: _fase_package_real}
            ).run()
            # Assert
            self.assertIs(res.estado, State.PUBLISHED)
            self.assertIsNone(res.error)
            destino = raiz / "salida" / "job-test" / "asset.nif"
            self.assertTrue(destino.is_file())
            # evidencia estructurada en el staging
            final = json.loads(
                (raiz / "workspace" / "job-test" / "reports" / "final.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(final["estado"], "PUBLISHED")
            self.assertIn("ingest", final["fases"])

    def test_ingest_no_modifica_la_fuente(self):
        tmp, raiz, mesh, manifest = _entorno()
        with tmp:
            antes = _hash(mesh)
            PipelineRunner(manifest, {Phase.PACKAGE: _fase_package_real}).run()
            self.assertEqual(_hash(mesh), antes)


class RunnerFallasTests(unittest.TestCase):
    def test_manifest_invalido_no_arranca_ni_crea_staging(self):
        tmp, raiz, mesh, manifest = _entorno()
        with tmp:
            malo = JobManifest(
                job_id="../malo",
                source_mesh=mesh,
                raiz_proyecto=raiz,
                workspace_raiz=raiz / "workspace",
                raiz_salida=raiz / "salida",
            )
            from pipeline.errors import ConfigurationError
            with self.assertRaises(ConfigurationError):
                PipelineRunner(malo).run()
            self.assertFalse((raiz / "workspace" / "job-test").exists())

    def test_fase_que_falla_detiene_el_pipeline(self):
        # Arrange
        tmp, raiz, mesh, manifest = _entorno()
        with tmp:
            corrieron = []

            def rompe(mani, ws):
                raise RuntimeError("boom en prepare")

            def espia(nombre):
                def f(mani, ws):
                    corrieron.append(nombre)
                    return {}
                return f

            fases = {
                Phase.PREPARE: rompe,
                Phase.PROCESS_TEXTURES: espia("textures"),
                Phase.PUBLISH: espia("publish"),
            }
            res = PipelineRunner(manifest, fases).run()
            # Assert
            self.assertIs(res.estado, State.FAILED)
            self.assertIn("boom en prepare", res.error)
            self.assertNotIn("textures", corrieron)
            self.assertNotIn("publish", corrieron)
            # el destino final no existe
            self.assertFalse((raiz / "salida" / "job-test").exists())
            # diagnósticos preservados
            final = json.loads(
                (raiz / "workspace" / "job-test" / "reports" / "final.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(final["estado"], "FAILED")

    def test_destino_no_se_toca_cuando_publish_falla(self):
        # Arrange: package vacío -> publish debe fallar y no crear destino
        tmp, raiz, mesh, manifest = _entorno()
        with tmp:
            res = PipelineRunner(manifest).run()
            # Assert: la guarda puede fallar (detector real)
            self.assertIs(res.estado, State.FAILED)
            self.assertFalse((raiz / "salida" / "job-test").exists())

    def test_publish_fail_closed_ante_destino_existente(self):
        # Arrange: el destino ya existe; nunca se sobrescribe en silencio
        tmp, raiz, mesh, manifest = _entorno()
        with tmp:
            destino = raiz / "salida" / "job-test"
            destino.mkdir()
            (destino / "preexistente.txt").write_text("yo estaba aquí")
            fases = {Phase.PACKAGE: _fase_package_real}
            res = PipelineRunner(manifest, fases).run()
            # Assert
            self.assertIs(res.estado, State.FAILED)
            contenido = (destino / "preexistente.txt").read_text()
            self.assertEqual(contenido, "yo estaba aquí")
            self.assertFalse((destino / "asset.nif").exists())
            # no queda temp .part
            self.assertFalse((raiz / "salida" / "job-test.part").exists())

    def test_no_hay_api_para_saltar_a_published(self):
        # Assert estático: el runner no expone set_state; el estado solo
        # avanza ejecutando fases en orden.
        self.assertFalse(hasattr(PipelineRunner, "set_state"))
        self.assertFalse(hasattr(PipelineRunner, "goto"))


if __name__ == "__main__":
    unittest.main()
