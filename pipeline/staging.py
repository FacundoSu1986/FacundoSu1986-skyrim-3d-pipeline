# -*- coding: utf-8 -*-
"""Staging aislado por job.

Cada job trabaja en workspace_raiz/<job_id>/ con subdirectorios fijos. Nada
escribe fuera de ahí hasta la fase de publicación, y el source_mesh nunca se
modifica (las fases reciben copias, no el original).

Contención: toda ruta que se entrega a una fase pasa por resolve() y se
comprueba contra el directorio del job; un job no puede apuntar a otro.

    Política ante reintentos: crear() rechaza un directorio de job ya
    existente (fail-closed). La razón: si una corrida falla dejó artefactos
    en package/, una segunda corrida que no los regenere terminaría
    publicando artefactos viejos o parciales. Un reintento válido exige
    crear(fresco=True) explícito, que borra el staging anterior completo
    (diagnósticos incluidos): la decisión de descartar evidencia queda en
    el llamador, no en un efecto colateral silencioso.

    Política de limpieza ante fallo: se preservan los diagnósticos por
    defecto (NO se borra evidencia sin política explícita). cleanup() solo
    borra cuando se le pide explícitamente y el job terminó en éxito.

    Symlinks: el directorio del job y sus subdirectorios fijos no pueden
    ser symlinks; ruta_segura() comprueba el resultado resuelto contra el
    directorio del job resuelto, no contra la base ya resuelta (una base
    symlink resolvería fuera y la comprobación pasaría igual).
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


def _rechazar_symlink(ruta: Path, que: str) -> None:
    if ruta.is_symlink():
        raise ConfigurationError(f"{que} es un symlink, no se permite: {ruta}")


class JobWorkspace:
    """Workspace aislado de un job. No crea nada hasta llamar a crear()."""

    def __init__(self, workspace_raiz: Path, job_id: str) -> None:
        self.raiz = Path(workspace_raiz)
        self.job_id = job_id
        self.dir = (self.raiz / job_id).resolve()
        raiz_res = self.raiz.resolve()
        # El dir del job debe ser hijo directo de workspace_raiz: con un
        # job_id malicioso ("../otro") esto falla aquí aunque el llamador
        # no haya validado el manifest. Un job_id que sea symlink hacia
        # otro lado da un resolve() que no cuelga de aquí: mismo rechazo.
        if self.dir.parent != raiz_res:
            raise ConfigurationError(
                f"job_id {job_id!r} escapa de workspace_raiz ({self.dir})"
            )

    def crear(self, fresco: bool = False) -> Path:
        """Crea el dir del job y sus subdirectorios.

        - Si el dir ya existe: fail-closed. Un staging previo puede contener
          artefactos de una corrida fallida; reutilizarlo pondría en riesgo
          publicar esos restos. fresco=True es el reintento EXPLÍCITO:
          borra el staging anterior entero (incluidos diagnósticos).
        - Ni el dir del job ni sus subdirectorios pueden ser symlinks.
        """
        if self.dir.exists() or self.dir.is_symlink():
            if not fresco:
                raise ConfigurationError(
                    f"el workspace del job {self.job_id!r} ya existe: "
                    f"{self.dir}. Reintento: crear(fresco=True) explícito."
                )
            if self.dir.is_symlink():
                self.dir.unlink()
            else:
                shutil.rmtree(self.dir)
        self.dir.mkdir(parents=True)
        for sub in SUBDIRS:
            ruta = self.dir / sub
            _rechazar_symlink(ruta, f"subdir {sub!r}")
            ruta.mkdir()
        return self.dir

    def subdir(self, nombre: str) -> Path:
        """Devuelve un subdirectorio conocido del job. Nombre desconocido =
        error de programación, no ruta silenciosa. Un subdir convertido en
        symlink entre fases se rechaza acá."""
        if nombre not in SUBDIRS:
            raise ConfigurationError(
                f"subdir desconocido: {nombre!r} (conocidos: {SUBDIRS})"
            )
        ruta = self.dir / nombre
        _rechazar_symlink(self.dir, "dir del job")
        _rechazar_symlink(ruta, f"subdir {nombre!r}")
        return ruta

    def ruta_segura(self, relativa: Path, subdir: str = "package") -> Path:
        """Resuelve una ruta relativa dentro de un subdir y garantiza que el
        resultado resuelto siga dentro del DIR DEL JOB resuelto (no solo de
        la base ya resuelta: si la base fuera symlink externo, resolver contra
        ella validaría contra el destino del symlink, no contra el job)."""
        if Path(relativa).is_absolute():
            raise ConfigurationError(f"ruta absoluta no permitida: {relativa}")
        base = self.subdir(subdir)  # symlinks del subdir rechazados aquí
        res = (base / relativa).resolve()
        for raiz, desc in ((self.dir, "el dir del job"),
                           (Path(base).resolve(), f"el subdir {subdir!r}")):
            try:
                res.relative_to(raiz)
            except ValueError:
                raise ConfigurationError(
                    f"ruta {relativa!r} escapa de {desc} (resuelta: {res})"
                ) from None
        return res

    def limpiar(self, exito: bool) -> None:
        """Borra el staging SOLO en éxito y solo si se pidió explícitamente.
        Ante fallo no se toca nada: los diagnósticos son evidencia."""
        if not exito:
            return
        if self.dir.exists():
            shutil.rmtree(self.dir)
