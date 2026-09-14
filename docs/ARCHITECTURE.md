# Architecture

## Intent

Keep the project small until one vertical slice is reproducible in-game.

```text
Agent / SKILL.md
       |
       v
 planner (pure Python)
       |
       v
 structured contracts (AssetReport / PipelinePlan)
       |
       +--> deterministic Blender/tool adapters [future]
       |
       +--> validators [future]
       |
       v
 evidence + acceptance result
```

## Boundaries

### Skill layer
Chooses phases, requests missing inputs and interprets validator results. It must not fabricate tool output.

### Core layer
Pure Python contracts and planning logic. No `bpy`, NifSkope, CK or filesystem side effects.

### Adapter layer (future)
Blender, PyNifly/NifTools, texconv/CAO, NifSkope inspection helpers, CK/xEdit integration.

### Validation layer (future)
Deterministic gates for triangle counts, paths, dimensions, texture presence and other facts that can be mechanically verified.

## MVP decision

The first supported target is a static Skyrim SE/AE prop. This is intentional: it removes rigging, animation and body-partition complexity while preserving the hard parts of mesh cleanup, textures, NIF export and in-game validation.
