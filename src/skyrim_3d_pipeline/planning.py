from __future__ import annotations

from .models import AssetType, PipelinePhase, PipelinePlan, SkyrimEdition

_BASE_PHASES = (
    PipelinePhase.INSPECT,
    PipelinePhase.CLASSIFY,
    PipelinePhase.PREPARE,
    PipelinePhase.TOPOLOGY,
    PipelinePhase.UV,
    PipelinePhase.BAKE,
    PipelinePhase.EXPORT,
    PipelinePhase.VALIDATE,
    PipelinePhase.IN_GAME_TEST,
)


def build_plan(
    asset_type: AssetType = AssetType.STATIC,
    edition: SkyrimEdition = SkyrimEdition.SE_AE,
) -> PipelinePlan:
    """Build the smallest currently supported plan without pretending unsupported paths are stable."""
    experimental = asset_type not in {AssetType.STATIC, AssetType.CLUTTER}
    notes: list[str] = []

    if experimental:
        notes.append(
            f"{asset_type.value} is outside the static-prop MVP and requires a dedicated verified expansion track."
        )

    if edition is SkyrimEdition.LE:
        notes.append("LE-specific NIF/DDS conventions remain verification-gated.")

    return PipelinePlan(
        edition=edition,
        asset_type=asset_type,
        phases=_BASE_PHASES,
        experimental=experimental,
        notes=tuple(notes),
    )
