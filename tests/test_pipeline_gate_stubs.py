# -*- coding: utf-8 -*-
"""El gate de stubs (issue #23).

Seis fases del runner estan sin conectar y devolvian {"ejecutada": True}. Lo
unico que impedia publicar basura era que PACKAGE tambien fuera stub y dejara
`package/` vacio: el gate lo sostenia el ORDEN en que se fueron cableando las
fases, no una decision. Cablear PACKAGE es el proximo slice.

Estos tests no fijan el caso que encontramos sino la propiedad: ninguna fase
sin conectar puede terminar en una publicacion.
"""
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.manifest import JobManifest
from pipeline.runner import (FASES_POR_DEFECTO, ORDEN_FASES, Phase,
                             PipelineRunner, State, _fase_noop)
from glb_sintetico import construir


def _entorno():
    tmp = tempfile.TemporaryDirectory()
    raiz = Path(tmp.name)
    (raiz / "workspace").mkdir()
    (raiz / "salida").mkdir()
    mesh = raiz / "entrada.glb"
    mesh.write_bytes(construir())
    manifest = JobManifest(
        job_id="job-gate",
        source_mesh=mesh,
        raiz_proyecto=raiz,
        workspace_raiz=raiz / "workspace",
        raiz_salida=raiz / "salida",
    )
    return tmp, raiz, manifest


def _real(nombre):
    """Adaptador de mentira que informa haber usado una herramienta."""
    def fase(mani, ws):
        return {"ejecutada": True, "herramienta": "falso:%s" % nombre}
    return fase


def _package_real(mani, ws):
    """Deja algo en package/, que es lo que destraba PUBLISH."""
    artefacto = ws.ruta_segura(Path("asset.nif"), subdir="package")
    artefacto.write_bytes(b"NIF-sintetico-de-test")
    return {"ejecutada": True, "herramienta": "falso:package"}


def _todas_cableadas():
    """Todas las fases con adaptador funcional, salvo PUBLISH, que conserva el
    real: es el que de verdad publica, y el que el gate debe frenar.

    INGEST e INSPECT tambien van falseadas a proposito: con los reales, dejar
    INGEST en stub haria fallar INSPECT por falta de input, y el test mediria
    esa dependencia en vez del gate."""
    fases = {}
    for fase in ORDEN_FASES:
        if fase is Phase.PUBLISH:
            continue
        fases[fase] = _package_real if fase is Phase.PACKAGE else _real(fase.value)
    return fases


class GateDeStubsTests(unittest.TestCase):

    def setUp(self):
        self.tmp, self.raiz, self.manifest = _entorno()
        self.addCleanup(self.tmp.cleanup)

    def _correr(self, fases):
        return PipelineRunner(self.manifest, fases=fases).run()

    def _publicado(self):
        destino = self.raiz / "salida" / self.manifest.job_id
        if not destino.exists():
            return []
        return sorted(p.name for p in destino.rglob("*") if p.is_file())

    # --- el par: con todo cableado SI publica -------------------------------

    def test_con_todas_las_fases_cableadas_publica(self):
        """Sin esto, los tests de abajo pasarian con un runner que no publica
        nunca -- y 'no publica nunca' no es el arreglo que se pidio."""
        r = self._correr(_todas_cableadas())
        self.assertIs(State.PUBLISHED, r.estado, r.error)
        self.assertTrue(r.ok)
        self.assertEqual([], r.fases_sin_conectar)
        self.assertEqual(["asset.nif"], self._publicado())

    # --- la familia entera --------------------------------------------------

    def test_cualquier_fase_sin_conectar_impide_publicar(self):
        """Enumera. No alcanza con tapar el caso que encontramos: se prueba
        CADA fase de ORDEN_FASES, dejandola como stub y cableando todas las
        demas. Incluye PUBLISH: si la ultima fase es stub, la corrida no puede
        terminar PUBLISHED (el gate previo solo audita los reportes previos).

        Si manana se cablea PACKAGE y se deja VALIDATE en stub -- que es
        exactamente lo que va a pasar en el proximo slice -- cae aca.
        """
        for fase in ORDEN_FASES:
            with self.subTest(fase=fase.value):
                tmp, raiz, manifest = _entorno()
                self.addCleanup(tmp.cleanup)
                fases = _todas_cableadas()
                fases[fase] = _fase_noop          # esta queda sin conectar
                r = PipelineRunner(manifest, fases=fases).run()

                self.assertIs(State.FAILED, r.estado,
                              "con %s sin conectar igual llego a %s"
                              % (fase.value, r.estado))
                self.assertIn(fase.value, r.fases_sin_conectar)
                self.assertIn(fase.value, r.error or "")
                destino = raiz / "salida" / manifest.job_id
                self.assertFalse(destino.exists(),
                                 "publico con %s sin conectar" % fase.value)

    def test_el_caso_del_issue(self):
        """PACKAGE cableado, el resto en stub: era el escenario que publicaba
        un .txt con estado PUBLISHED y ok=True."""
        r = self._correr({Phase.PACKAGE: _package_real})
        self.assertIs(State.FAILED, r.estado)
        self.assertFalse(r.ok)
        self.assertEqual([], self._publicado())
        for fase in ("prepare", "process_textures", "export_nif",
                     "read_back", "validate"):
            self.assertIn(fase, r.fases_sin_conectar)

    # --- el gate no se puede esquivar ---------------------------------------

    def test_un_publish_stub_no_se_reporta_como_exito(self):
        """Hallazgo de review: el gate previo audita los reportes anteriores;
        si el que se declara stub es PUBLISH, recien se sabe despues de
        correrlo. La corrida no puede terminar PUBLISHED/ok=True sin haber
        publicado nada."""
        fases = _todas_cableadas()
        fases[Phase.PUBLISH] = _fase_noop
        r = self._correr(fases)

        self.assertIs(State.FAILED, r.estado)
        self.assertFalse(r.ok, "un PUBLISH stub no puede informar exito")
        self.assertIn(Phase.PUBLISH.value, r.fases_sin_conectar)
        self.assertIn(Phase.PUBLISH.value, r.error or "")
        self.assertEqual([], self._publicado())
        final = json.loads(
            (self.raiz / "workspace" / self.manifest.job_id / "reports"
             / "final.json").read_text(encoding="utf-8")
        )
        self.assertEqual("FAILED", final["estado"])

    def test_un_publish_propio_no_saltea_el_gate(self):
        """Por eso el gate vive en el runner y no dentro de _fase_publish: la
        API deja registrar adaptadores propios, incluido el de PUBLISH."""
        publicado = []

        def publish_propio(mani, ws):
            publicado.append(True)
            return {"ejecutada": True, "herramienta": "publish_propio"}

        fases = {Phase.PACKAGE: _package_real, Phase.PUBLISH: publish_propio}
        r = self._correr(fases)
        self.assertIs(State.FAILED, r.estado)
        self.assertEqual([], publicado,
                         "el PUBLISH propio llego a correr con fases en stub")

    # --- el stub tiene que declararse ---------------------------------------

    def test_toda_fase_noop_se_declara_stub(self):
        """Un stub que no se marca vuelve a ser invisible para el gate. Se
        compara contra el mapa por defecto, no contra una lista escrita a mano:
        si manana alguien agrega una fase apuntando a _fase_noop, entra sola.
        """
        esperadas = sorted(f.value for f, a in FASES_POR_DEFECTO.items()
                           if a is _fase_noop)
        r = self._correr({})          # el pipeline tal como viene
        self.assertEqual(esperadas, sorted(r.fases_sin_conectar))

    def test_el_stub_no_dice_que_se_ejecuto(self):
        rep = _fase_noop(self.manifest, None)
        self.assertFalse(rep["ejecutada"],
                         "el stub vuelve a informar exito sin hacer nada")
        self.assertTrue(rep["stub"])
        self.assertIsNone(rep["herramienta"])


if __name__ == "__main__":
    unittest.main()
