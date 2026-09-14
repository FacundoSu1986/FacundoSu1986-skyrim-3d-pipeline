---
name: skyrim-3d-pipeline
description: >-
  Experimental workflow for inspecting, planning, preparing, converting and validating
  external 3D assets for Skyrim. Defaults to Skyrim SE/AE static props while the
  pipeline is under verification.
---

# Skyrim 3D Pipeline

## Operating rules

1. Default to **SE/AE + static prop** only when the user does not specify a target.
2. Never invent installed tools, vanilla paths, NIF settings, shader slots, CK records, or successful test results.
3. Treat facts listed in `docs/VERIFICATION_BACKLOG.md` as **unverified** until the referenced gate is closed.
4. Separate orchestration from deterministic work:
   - this skill decides what phase is needed;
   - code/scripts perform mechanical transformations;
   - validators decide whether a phase passed.
5. Do not advance past a failed validation gate.
6. Preserve the original asset. Transform copies into a workspace/output directory.
7. Prefer a known-good vanilla-equivalent fixture for scale, orientation, material and collision comparison.
8. Armor, creatures, animations and advanced Havok are outside the MVP unless explicitly requested.

## MVP phases

### F0 — Inspect
Collect source format, asset type, dimensions, vertex/triangle counts, materials, UV presence and texture-map availability.

**Output:** structured `AssetReport`.

### F1 — Classify and plan
Choose the smallest pipeline required for the asset type. Static props use the canonical MVP path.

**Output:** structured `PipelinePlan`.

### F2 — Prepare
Normalize transforms, orientation and scale against an explicit target or verified reference.

**Gate:** transformations are explicit and reversible from the preserved source.

### F3 — Topology
Measure real triangle count and detect obvious topology problems. Do not use polygon count as triangle count.

**Gate:** triangle budget and topology criteria are defined for the selected fixture/category.

### F4 — UV / textures
Inspect or regenerate UVs and prepare texture conversion/baking.

**Gate:** no convention is assumed unless verified for the target edition/toolchain.

### F5 — Export
Export through a verified NIF route only. If the installed addon/tool version is unknown, stop and report that the export path is unverified.

### F6 — Validate
Validate structure, paths, textures, scale and target-edition compatibility using deterministic checks where possible plus NifSkope/tool inspection.

### F7 — In-game acceptance
Test in an isolated mod/cell or disposable replacement workflow. Record observed behavior; never infer success from file creation alone.

## Expansion tracks

- Weapons
- Armor / BodySlide / Outfit Studio
- Creatures / skeletons / animations
- Havok collision generation
- LOD
- CK/xEdit automation

Each expansion requires its own fixtures, contracts and tests before becoming part of the default path.
