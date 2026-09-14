# Original proposal — provenance snapshot

> Status: **reference only / unverified**. This file preserves the intent of the initial design discussion. It is not a framework contract and must not override `SKILL.md` or `docs/VERIFICATION_BACKLOG.md`.

## Original intent

Build an Agent Skill plus deterministic Blender/tool scripts to move AI-generated or external 3D assets (Meshy, Tripo, Luma, Rodin, etc.) toward Skyrim-compatible assets.

The proposal covered:

- GLB / FBX / OBJ intake;
- mesh cleanup and retopology;
- scale/orientation normalization;
- UV work;
- PBR-to-Skyrim material conversion;
- NIF export and NifSkope inspection;
- DDS conversion;
- collision;
- armor/creature expansion tracks;
- Creation Kit/xEdit integration;
- in-game acceptance testing.

## Proposed phase model

```text
F0 inventory
F1 cleanup / positioning
F2 retopology / decimation
F3 UV
F4 texture bake / material conversion
F5 scale / pivot / orientation
F6 NIF export
F7 DDS
F8 collision
F9 game integration / acceptance
F10 advanced tracks
```

## Important design ideas retained

1. Start with a static SE/AE prop before weapons, armor or creatures.
2. Compare against a known-good vanilla equivalent whenever scale, pivot, material or collision behavior matters.
3. Separate agent decisions from deterministic transformations.
4. Run Blender operations headless where they are reproducible.
5. Treat in-game behavior as the final acceptance gate; file creation alone is not proof of success.

## Claims deliberately moved behind verification gates

The original draft contained concrete values and recipes for NIF versions, texture slots, DDS formats, scale conversions, shader parameters, Havok collision, Blender/NIF addon compatibility and PBR-to-Skyrim conversion. Those claims are intentionally **not copied into the normative skill** until they are verified against current tooling, primary documentation or reproducible fixtures.

See `VERIFICATION_BACKLOG.md` for the active verification work.

## Confirmed defect found during review

The draft `01_prepare_mesh.py` labelled `len(mesh.polygons)` as a triangle count. That is false whenever faces are not already triangulated. The production adapter must calculate loop triangles (for example with `mesh.calc_loop_triangles()` and `len(mesh.loop_triangles)`) or prove an equivalent triangulated count.

## Draft scripts

The two Blender scripts from the original discussion are intentionally **not shipped as executable production adapters** in the initial repository. They will be reintroduced one at a time only after a target Blender version, fixture, headless test and validation contract exist.
