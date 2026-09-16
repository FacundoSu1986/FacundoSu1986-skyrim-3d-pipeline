# -*- coding: utf-8 -*-
"""JobManifest: configuración declarativa, inmutable y validada de un job.

Implementa la hipótesis 2 del issue #5 (configuración declarativa) para el
alcance MVP del repo: Skyrim SE/AE, static/clutter, asset no skinned. Cualquier
dominio fuera de eso (criaturas, armaduras, BodySlide, Havok) queda fuera del
enum y da error de configuración, no soporte silencioso.

Reglas de validación (todas verificables con tests):
  - job_id seguro para usar como nombre de directorio;
  - rutas resueltas con containment: workspace_raiz y raiz_salida deben vivir
    dentro de raiz_proyecto; una ruta que escapa del root se rechaza;
  - source_mesh y texture_inputs deben existir y ser archivos;
  - extensiones por whitelist;
  - los campos nulos/vacíos no son válidos.

No hay paths hardcodeados: todas las rutas vienen del llamador.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigurationError

# Alcance MVP acordado (spec + issues #2/#3/#5): SE/AE, static/clutter.
EDICIONES_SOPORTADAS = frozenset({"skyrim-se-ae"})
CATEGORIAS_SOPORTADAS = frozenset({"static", "clutter"})

# [PROVIDER] Las extensiones que el runner acepta hoy de entrada. Generadores
# de IA entregan sobre todo GLB/GLTF; FBX/OBJ están por compatibilidad con los
# scripts existentes (medir_parte.py los acepta). Ampliar = evidencia, no deseo.
EXTENSIONES_MESH = frozenset({".glb", ".gltf", ".fbx", ".obj"})
EXTENSIONES_TEXTURA = frozenset({".png", ".tga", ".dds"})

# job_id se usa como nombre de directorio: se restringe a un alfabeto seguro
# en vez de "sanitizar" (sanitizar silencioso = proyectos que pisan a otros).
_PATRON_JOB_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _resuelta(ruta: Path) -> Path:
    """Resuelve una ruta sin exigir que exista (resolve() no lo exige)."""
    return Path(ruta).expanduser().resolve()


def _contenida_hijo(ruta_resuelta: Path, raiz_resuelta: Path) -> bool:
    """True si ruta_resuelta está dentro de raiz_resuelta (o es ella)."""
    try:
        ruta_resuelta.relative_to(raiz_resuelta)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class JobManifest:
    """Config declarativa e inmutable de un job del pipeline.

    raiz_proyecto delimita todo lo que el pipeline puede escribir:
    workspace_raiz (staging por job) y raiz_salida (destino de publicación)
    deben quedar dentro. Los insumos (source_mesh, texture_inputs) solo se
    leen, así que se exige existencia pero no containment.
    """

    job_id: str
    source_mesh: Path
    raiz_proyecto: Path
    workspace_raiz: Path
    raiz_salida: Path
    target_edition: str = "skyrim-se-ae"
    asset_category: str = "static"
    texture_inputs: tuple[Path, ...] = ()
    enabled_transformations: tuple[str, ...] = ()
    reference_asset: Path | None = None

    def validar(self) -> None:
        """Valida el manifest completo. Lanza ConfigurationError agregando
        TODOS los problemas encontrados (no uno a la vez), para que el error
        sea accionable en una sola pasada."""
        problemas: list[str] = []

        if not _PATRON_JOB_ID.match(self.job_id):
            problemas.append(
                f"job_id inválido: {self.job_id!r} "
                "(minúsculas, dígitos, '.', '-', '_'; 1-64 chars; sin '/' ni '..')"
            )

        if self.target_edition not in EDICIONES_SOPORTADAS:
            problemas.append(
                f"target_edition no soportada: {self.target_edition!r} "
                f"(soportadas: {sorted(EDICIONES_SOPORTADAS)})"
            )
        if self.asset_category not in CATEGORIAS_SOPORTADAS:
            problemas.append(
                f"asset_category no soportada: {self.asset_category!r} "
                f"(soportadas: {sorted(CATEGORIAS_SOPORTADAS)})"
            )

        raiz = _resuelta(self.raiz_proyecto)
        for nombre, ruta in (
            ("workspace_raiz", self.workspace_raiz),
            ("raiz_salida", self.raiz_salida),
        ):
            res = _resuelta(ruta)
            if not _contenida_hijo(res, raiz):
                problemas.append(
                    f"{nombre} fuera de raiz_proyecto: {ruta} "
                    f"(resuelta: {res}; raíz: {raiz})"
                )

        # Inspección de entradas: existencia + whitelist de extensión.
        for nombre, rutas, exts in (
            ("source_mesh", (self.source_mesh,), EXTENSIONES_MESH),
            ("texture_inputs", self.texture_inputs, EXTENSIONES_TEXTURA),
            (
                "reference_asset",
                (self.reference_asset,) if self.reference_asset else (),
                EXTENSIONES_MESH | frozenset({".nif"}),
            ),
        ):
            for ruta in rutas:
                if ruta.suffix.lower() not in exts:
                    problemas.append(
                        f"{nombre}: extensión no admitida en {ruta.name!r} "
                        f"(admitidas: {sorted(exts)})"
                    )
                if not ruta.is_file():
                    problemas.append(f"{nombre}: no existe o no es archivo: {ruta}")

        if problemas:
            raise ConfigurationError(
                "JobManifest inválido:\n  - " + "\n  - ".join(problemas)
            )
