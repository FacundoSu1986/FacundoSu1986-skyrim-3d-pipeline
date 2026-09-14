from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SkyrimEdition(StrEnum):
    SE_AE = "se_ae"
    LE = "le"


class AssetType(StrEnum):
    STATIC = "static"
    CLUTTER = "clutter"
    WEAPON = "weapon"
    ARMOR = "armor"
    CREATURE = "creature"


class PipelinePhase(StrEnum):
    INSPECT = "inspect"
    CLASSIFY = "classify"
    PREPARE = "prepare"
    TOPOLOGY = "topology"
    UV = "uv"
    BAKE = "bake"
    EXPORT = "export"
    VALIDATE = "validate"
    IN_GAME_TEST = "in_game_test"


@dataclass(frozen=True, slots=True)
class AssetReport:
    source_format: str
    asset_type: AssetType
    vertices: int
    triangles: int
    dimensions: tuple[float, float, float]
    material_count: int
    has_uv: bool
    has_normal_map: bool
    has_metallic_map: bool
    has_roughness_map: bool

    def __post_init__(self) -> None:
        if not self.source_format.strip():
            raise ValueError("source_format must not be empty")
        if self.vertices < 0 or self.triangles < 0 or self.material_count < 0:
            raise ValueError("mesh counts must be non-negative")
        if len(self.dimensions) != 3 or any(value < 0 for value in self.dimensions):
            raise ValueError("dimensions must contain three non-negative values")


@dataclass(frozen=True, slots=True)
class PipelinePlan:
    edition: SkyrimEdition
    asset_type: AssetType
    phases: tuple[PipelinePhase, ...]
    experimental: bool
    notes: tuple[str, ...] = ()
