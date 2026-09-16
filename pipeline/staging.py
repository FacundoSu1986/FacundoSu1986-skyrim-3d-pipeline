# -*- coding: utf-8 -*-
"""Staging aislado por job.

Cada job trabaja en workspace_raiz/<job_id>/ con subdirectorios fijos. Nada
escribe fuera de ahí hasta la fase de publicación, y el source_mesh nunca se
modifica (las fases reciben copias, no el original).

Contención: toda ruta que se entrega a una fase pasa por resolve() y se
comprueba contra el directorio del job; un job no puede apuntar a otro.

Política de limpieza ante fallo: se preservan los diagnósticos por defecto
(NO se borra evidencia sin política explícita). cleanup() solo borra cuando
se le pide explícitamente y el job terminó en éxito.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .errors import ConfigurationError

SUBDIRS = (
    "input",
    "inspect",
    "geometry",
    "textures",
    "nif",
    "reports",
    "package",
)


class JobWorkspace:
    """Workspace aislado de un job. No crea nada hasta llamar a crear()."""

    def __init__(self, workspace_raiz: Path, job_id: str) -> None:
        self.raiz = Path(workspace_raiz)
        self.job_id = job_id
        self.dir = (self.raiz / job_id).resolve()
        raiz_res = self.raiz.resolve()
        # El dir del job debe ser hijo directo de workspace_raiz: con un
        # job_id malicioso ("../otro") esto falla aquí aunque el llamador
        # no haya validado el manifest.
        if self.dir.parent != raiz_res:
            raise ConfigurationError(
                f"job_id {job_id!r} escapa de workspace_raiz ({self.dir})"
            )

    def crear(self) -> Path:
        """Crea el directorio del job y sus subdirectorios fijos."""
        for sub in SUBDIRS:
            (self.dir / sub).mkdir(parents=True, exist_ok=True)
        return self.dir

    def subdir(self, nombre: str) -> Path:
        """Devuelve un subdirectorio conocido del job. Nombre desconocido =
        error de programación, no ruta silenciosa."""
        if nombre not in SUBDIRS:
            raise ConfigurationError(
                f"subdir desconocido: {nombre!r} (conocidos: {SUBDIRS})"
            )
        return self.dir / nombre

    def ruta_segura(self, relativa: Path, subdir: str = "package") -> Path:
        """Resuelve una ruta relativa dentro de un subdir y garantiza que el
        resultado siga dentro de ese subdir (anti path traversal en nombres
        de artefactos generados)."""
        if Path(relativa).is_absolute():
            raise ConfigurationError(f"ruta absoluta no permitida: {relativa}")
        base = self.subdir(subdir).resolve()
        res = (base / relativa).resolve()
        try:
            res.relative_to(base)
        except ValueError:
            raise ConfigurationError(
                f"ruta {relativa!r} escapa del subdir {subdir!r} (resuelta: {res})"
            ) from None
        return res

    def limpiar(self, exito: bool) -> None:
        """Borra el staging SOLO en éxito y solo si se pidió explícitamente.
        Ante fallo no se toca nada: los diagnósticos son evidencia."""
        if not exito:
            return
        if self.dir.exists():
            shutil.rmtree(self.dir)
