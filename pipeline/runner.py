# -*- coding: utf-8 -*-
"""PipelineRunner: máquina de estados explícita + ejecución de fases.

Modelo deliberadamente mínimo: un enum de estados, una lista ordenada de
fases y un bucle. No hay framework de state machines: no hace falta.

Estados (uno por fase completada, más PENDING/FAILED):

    PENDING → INGESTED → INSPECTED → PREPARED → TEXTURES_READY
    → NIF_EXPORTED → READ_BACK_OK → VALIDATED → PACKAGED → PUBLISHED

Cualquier excepción en cualquier fase:

    * → FAILED (con diagnósticos preservados en el workspace)

Garantías:
  - las fases se ejecutan en orden; no hay API para saltar estados;
  - si una fase falla, las siguientes no corren (en particular, PUBLISH
    nunca corre tras un fallo: el destino final queda intacto);
  - cada fase produce un reporte JSON en reports/ (qué entró, qué salió);
  - el manifest se valida ANTES de crear cualquier directorio.

Fases por defecto: INGEST (copia con hash, no mueve el original), INSPECT
(inspección read-only de la copia), PROCESS_TEXTURES (PBR -> DDS con la
convención de Skyrim, ver texturas.py) y PUBLISH (fail-closed: si el destino
existe, error; copia del árbol package/ completo a un temp vecino y
os.replace). El resto son stubs que se declaran como tales (`stub=True`,
`ejecutada=False`): puntos de enganche donde las slices siguientes conectarán
los verificadores existentes (parser_nif, parser_dds, scripts Blender)
mediante adaptadores inyectables.

Ninguna fase sin conectar puede terminar en una publicación: `run()` rechaza
PUBLISH si alguna fase ejecutada -- incluido el propio PUBLISH -- se declaró
stub. Con PROCESS_TEXTURES cableada, el gate sigue frenando exactamente igual:
lo que cambia es que ahora frena por PREPARE, EXPORT_NIF, READ_BACK, VALIDATE
y PACKAGE, que son las que de verdad faltan.

Publicación: os.replace de directorio es atómico dentro del mismo volumen
en NTFS/Linux; si la plataforma no lo garantiza, queda documentado aquí
como mejor esfuerzo fail-closed (nunca sobrescribe un destino existente).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping

from .errors import ArtifactValidationError, PipelineError, PublishError
from .manifest import JobManifest
from .staging import JobWorkspace
from .texturas import copiar_entradas, fase_process_texturas


class Phase(Enum):
    INGEST = "ingest"
    INSPECT = "inspect"
    PREPARE = "prepare"
    PROCESS_TEXTURES = "process_textures"
    EXPORT_NIF = "export_nif"
    READ_BACK = "read_back"
    VALIDATE = "validate"
    PACKAGE = "package"
    PUBLISH = "publish"


class State(Enum):
    PENDING = 0
    INGESTED = 1
    INSPECTED = 2
    PREPARED = 3
    TEXTURES_READY = 4
    NIF_EXPORTED = 5
    READ_BACK_OK = 6
    VALIDATED = 7
    PACKAGED = 8
    PUBLISHED = 9
    FAILED = -1


_FASE_A_ESTADO = {
    Phase.INGEST: State.INGESTED,
    Phase.INSPECT: State.INSPECTED,
    Phase.PREPARE: State.PREPARED,
    Phase.PROCESS_TEXTURES: State.TEXTURES_READY,
    Phase.EXPORT_NIF: State.NIF_EXPORTED,
    Phase.READ_BACK: State.READ_BACK_OK,
    Phase.VALIDATE: State.VALIDATED,
    Phase.PACKAGE: State.PACKAGED,
    Phase.PUBLISH: State.PUBLISHED,
}

ORDEN_FASES = tuple(_FASE_A_ESTADO)

# Un adaptador de fase devuelve un dict con campos JSON-serializables.
Adapter = Callable[[JobManifest, JobWorkspace], dict]


def _fase_inspect(mani: JobManifest, ws: JobWorkspace) -> dict:
    """Inspección veraz read-only (issue #4): corre sobre la copia en
    input/, nunca sobre el source_mesh original. Formatos sin inspector se
    reportan honestamente (inspeccionado=False), no se fingen."""
    from .inspection import inspeccionar_malla

    # La malla se busca por SU nombre. Antes se tomaba el primer archivo de
    # input/, y desde que INGEST copia también las texturas (input/texturas/)
    # "el primero" podía ser esa carpeta.
    malla = ws.subdir("input") / Path(mani.source_mesh).name
    if not malla.is_file():
        raise ArtifactValidationError(
            "fase INSPECT sin entrada en input/: falta %s" % malla.name)
    return inspeccionar_malla(malla)


# Marca que distingue "esta fase no existe todavia" de "esta fase corrio y no
# tenia nada que hacer". Son cosas distintas y el reporte las confundia.
CLAVE_STUB = "stub"


def _fase_noop(mani: JobManifest, ws: JobWorkspace) -> dict:
    """Placeholder explícito: la fase no está conectada a herramientas reales.

    `ejecutada` es False a propósito. Antes devolvía True, y eso es una mentira
    barata con consecuencia cara: lo único que impedía publicar basura era que
    PACKAGE también fuera stub y dejara `package/` vacío. O sea que el gate lo
    sostenía el orden en que se fueron cableando las fases, no una decisión.

    Cablear PACKAGE es el próximo slice. El día que pase, EXPORT_NIF, READ_BACK
    y VALIDATE seguirían informando éxito sin hacer nada, y el runner publicaría
    con el estado PUBLISHED.
    """
    return {"ejecutada": False, CLAVE_STUB: True, "herramienta": None,
            "nota": "fase stub: no conectada a ninguna herramienta"}


def fases_stub(reports: dict[str, dict]) -> list[str]:
    """Fases que informaron ser un stub, en orden de aparición.

    Límite conocido: es una declaración explícita del adaptador. Un adaptador
    que no hace nada pero se declara ejecutado no se detecta acá; para PACKAGE,
    la guarda de `package/` vacío en PUBLISH es el backstop.
    """
    return [nombre for nombre, rep in reports.items()
            if isinstance(rep, dict) and rep.get(CLAVE_STUB) is True]


def _error_publicacion_con_stubs(stubs: list[str]) -> PublishError:
    """Mensaje único para las dos vías de rechazo: stubs antes de PUBLISH, y
    el propio PUBLISH declarado stub."""
    return PublishError(
        "no se publica: %d fase(s) sin conectar (%s). Un stub informa que no "
        "hizo nada; publicar igual seria dar por bueno un asset que nadie "
        "produjo." % (len(stubs), ", ".join(stubs))
    )


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _fase_ingest(mani: JobManifest, ws: JobWorkspace) -> dict:
    """Copia la entrada al staging. Nunca modifica ni mueve el original.

    Las texturas también: van a input/texturas/ y PROCESS_TEXTURES lee esas
    copias. Así el hash del reporte y los bytes que se convierten son los
    mismos aunque alguien reescriba el original durante la corrida.
    """
    fuente = Path(mani.source_mesh)
    destino = ws.ruta_segura(Path(fuente.name), subdir="input")
    shutil.copyfile(fuente, destino)
    reporte = {
        "ejecutada": True,
        "herramienta": "shutil.copyfile",
        "entrada": str(fuente),
        "salida": destino.name,
        "sha256": _sha256(destino),
    }
    if mani.texture_inputs:
        reporte["texturas"] = [
            {"entrada": str(original), "salida": "texturas/" + copia.name,
             "sha256": _sha256(copia)}
            for original, copia in copiar_entradas(mani.texture_inputs, ws)]
    return reporte


def _fase_publish(mani: JobManifest, ws: JobWorkspace) -> dict:
    """Publica package/ al destino final con política fail-closed.

    - destino existente -> PublishError (nunca sobrescribe en silencio);
    - se construye el árbol en un temp vecino al destino y se renombra con
      os.replace (atómico en el mismo volumen NTFS/POSIX; si no lo es, el
      peor caso es un destino ausente, jamás un destino mezclado).
    """
    origen = ws.subdir("package")
    if not any(origen.iterdir()):
        raise PublishError(
            "package/ vacío: no hay nada que publicar (falló una fase previa)"
        )
    destino = (Path(mani.raiz_salida) / mani.job_id).resolve()
    if destino.exists():
        raise PublishError(
            f"destino ya existe, no se sobrescribe (fail-closed): {destino}"
        )
    tmp = destino.with_name(destino.name + ".part")
    if tmp.exists():
        shutil.rmtree(tmp)
    try:
        shutil.copytree(origen, tmp)
        destino.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, destino)
    except PipelineError:
        raise
    except OSError as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise PublishError(f"falló la publicación a {destino}: {e}") from e
    return {
        "ejecutada": True,
        "herramienta": "copytree+os.replace",
        "destino": str(destino),
        "archivos": sorted(p.name for p in destino.rglob("*") if p.is_file()),
    }


FASES_POR_DEFECTO: Mapping[Phase, Adapter] = {
    Phase.INGEST: _fase_ingest,
    Phase.INSPECT: _fase_inspect,
    Phase.PREPARE: _fase_noop,
    Phase.PROCESS_TEXTURES: fase_process_texturas,
    Phase.EXPORT_NIF: _fase_noop,
    Phase.READ_BACK: _fase_noop,
    Phase.VALIDATE: _fase_noop,
    Phase.PACKAGE: _fase_noop,
    Phase.PUBLISH: _fase_publish,
}


@dataclass
class RunResult:
    """Resultado estructurado de una corrida. evidencia, no narración."""

    estado: State
    reports: dict[str, dict]
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.estado is State.PUBLISHED

    @property
    def fases_sin_conectar(self) -> list[str]:
        """Las fases que corrieron como stub, en orden de ejecución. Una
        corrida con esta lista no vacía no produjo un asset: si hay stubs,
        `estado` nunca es PUBLISHED."""
        return fases_stub(self.reports)


class PipelineRunner:
    """Ejecuta las fases en orden sobre un JobManifest validado."""

    def __init__(
        self,
        manifest: JobManifest,
        fases: Mapping[Phase, Adapter] | None = None,
    ) -> None:
        self.manifest = manifest
        self.fases = dict(FASES_POR_DEFECTO)
        if fases:
            self.fases.update(fases)
        self._validar_fases()

    def _validar_fases(self) -> None:
        desconocidas = set(self.fases) - set(ORDEN_FASES)
        if desconocidas:
            raise PipelineError(f"fases desconocidas: {desconocidas}")
        faltantes = set(ORDEN_FASES) - set(self.fases)
        if faltantes:
            raise PipelineError(f"fases sin adaptador: {faltantes}")

    def run(self) -> RunResult:
        """Ejecuta el pipeline. Devuelve RunResult; nunca lanza por fallo de
        fase (el fallo queda en result.error y estado=FAILED). Sí lanza por
        manifest inválido -- error previo a cualquier ejecución -- y por
        OSError si la evidencia (reports/) no se puede escribir."""
        self.manifest.validar()
        ws = JobWorkspace(self.manifest.workspace_raiz, self.manifest.job_id)
        ws.crear()

        reports: dict[str, dict] = {}
        estado = State.PENDING
        for fase in ORDEN_FASES:
            # El gate vive aca y no dentro de _fase_publish a proposito: es una
            # propiedad del pipeline, no de un adaptador. Puesto en el
            # adaptador, cualquiera que registre su propio PUBLISH se lo saltea
            # sin enterarse -- y registrar adaptadores propios es justamente lo
            # que la API ofrece.
            if fase is Phase.PUBLISH:
                pendientes = fases_stub(reports)
                if pendientes:
                    e = _error_publicacion_con_stubs(pendientes)
                    reports[fase.value] = {
                        "ejecutada": False,
                        "error": f"{type(e).__name__}: {e}",
                    }
                    estado = State.FAILED
                    self._escribir_final(ws, estado, reports, str(e))
                    return RunResult(estado=estado, reports=reports, error=str(e))
            try:
                reporte = self.fases[fase](self.manifest, ws)
            except Exception as e:
                reports[fase.value] = {
                    "ejecutada": False,
                    "error": f"{type(e).__name__}: {e}",
                }
                estado = State.FAILED
                self._escribir_final(ws, estado, reports, str(e))
                return RunResult(estado=estado, reports=reports, error=str(e))
            reports[fase.value] = reporte
            # El gate previo audita lo ya ejecutado; que PUBLISH sea stub recién
            # se sabe después de correrlo. Sin este chequeo la corrida termina
            # PUBLISHED/ok=True sin haber publicado nada: exactamente la mentira
            # que este cambio elimina. El reporte stub se conserva para que
            # fases_sin_conectar lo liste.
            if (fase is Phase.PUBLISH and isinstance(reporte, dict)
                    and reporte.get(CLAVE_STUB) is True):
                e = _error_publicacion_con_stubs([fase.value])
                reporte["error"] = f"{type(e).__name__}: {e}"
                estado = State.FAILED
                self._escribir_final(ws, estado, reports, str(e))
                return RunResult(estado=estado, reports=reports, error=str(e))
            estado = _FASE_A_ESTADO[fase]
        self._escribir_final(ws, estado, reports, None)
        return RunResult(estado=estado, reports=reports)

    @staticmethod
    def _escribir_final(
        ws: JobWorkspace,
        estado: State,
        reports: dict[str, dict],
        error: str | None,
    ) -> None:
        """Persiste evidencia estructurada. Es I/O directo: si `reports/` no
        es escribible, la OSError propaga (no hay canal alternativo para dejar
        el diagnóstico)."""
        final = {
            "estado": estado.name,
            "error": error,
            "fases": reports,
        }
        ruta = ws.subdir("reports") / "final.json"
        ruta.write_text(
            json.dumps(final, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
