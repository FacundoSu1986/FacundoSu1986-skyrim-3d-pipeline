# -*- coding: utf-8 -*-
"""SourceAsset: representación canónica de un asset de entrada, y adapters.

Separa las APIs de los providers generativos del pipeline del motor: el resto
del pipeline nunca conoce a Meshy/Tripo directamente; ve un SourceAsset.

En esta slice solo existe LocalAdapter (archivo ya en disco): los adapters de
red de providers requieren APIs reales y evidencia de formato por provider —
eso es trabajo futuro, no se simula acá.

Las semánticas de textura (normal, baseColor, etc.) llegan desde el formato
(slots glTF) vía pipeline.inspection, NUNCA desde nombres de archivo.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .errors import ArtifactValidationError

# Proveedores conocidos SOLO para trazabilidad del origen; no agregan lógica.
PROVIDERS_REGISTRABLES = frozenset({
    "local", "meshy", "tripo", "csm", "hunyuan3d", "rodin", "trellis",
})


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


@dataclass(frozen=True)
class SourceAsset:
    """El asset de entrada, normalizado. La inspección semántica real la hace
    pipeline/inspection.py sobre el archivo, no este DTO."""

    ruta: Path
    formato: str            # extensión sin punto, minúscula ("glb")
    provider: str           # "local" cuando no viene de una API
    sha256: str
    bytes: int
    provider_task_id: str | None = None


def asset_desde_local(
    ruta: Path | str,
    provider: str = "local",
    provider_task_id: str | None = None,
) -> SourceAsset:
    """LocalAdapter: normaliza un archivo ya presente en disco.

    Es la única vía de entrada implementada: no se finge una descarga de red.
    Las extensiones válidas las fija el JobManifest al validar; acá solo se
    exige existencia para poder declarar el hash.
    """
    if provider not in PROVIDERS_REGISTRABLES:
        raise ArtifactValidationError(f"provider desconocido: {provider!r}")
    p = Path(ruta).expanduser().resolve()
    if not p.is_file():
        raise ArtifactValidationError(f"source asset inexistente: {p}")
    return SourceAsset(
        ruta=p,
        formato=p.suffix.lower().lstrip("."),
        provider=provider,
        sha256=_sha256(p),
        bytes=p.stat().st_size,
        provider_task_id=provider_task_id,
    )
