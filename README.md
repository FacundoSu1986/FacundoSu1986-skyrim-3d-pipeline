# Skyrim 3D Pipeline

Experimental framework + Agent Skill for converting external/AI-generated 3D assets into a Skyrim-oriented asset pipeline.

## Status

**Early development.** Technical claims about NIF versions, shader texture slots, DDS conventions, Havok collision, Blender/NIF addon compatibility, and PBR-to-Skyrim conversion are treated as **unverified until backed by reproducible fixtures or primary/tool documentation**.

The first milestone is deliberately narrow: **static props for Skyrim SE/AE**. Weapons, armor, creatures, animation, and advanced Havok are expansion tracks, not MVP requirements.

## Goals

- Keep agent reasoning/routing in `SKILL.md`.
- Keep deterministic operations in scripts/code.
- Exchange structured DTOs between phases instead of prose.
- Validate outputs against known-good vanilla-style fixtures before expanding scope.
- Fail closed when a required tool, input, or verified convention is missing.

## Repository layout

```text
skyrim-3d-pipeline/
├── SKILL.md
├── README.md
├── pyproject.toml
├── src/skyrim_3d_pipeline/
│   ├── __init__.py
│   ├── models.py
│   └── planning.py
├── scripts/
│   └── README.md
├── tests/
│   └── test_planning.py
└── docs/
    ├── ARCHITECTURE.md
    ├── VERIFICATION_BACKLOG.md
    └── original-proposal.md
```

## MVP pipeline

```text
INPUT (GLB/FBX/OBJ)
  -> INSPECT
  -> CLASSIFY
  -> PREPARE
  -> TOPOLOGY
  -> UV
  -> BAKE
  -> EXPORT
  -> VALIDATE
  -> IN-GAME TEST
```

The framework does **not** currently claim to automate NIF export or Creation Kit integration end-to-end.

## Local validation

No third-party Python dependency is required for the current core tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Blender-specific scripts will be added behind separate validation gates because normal CPython cannot verify `bpy` behavior.

## License

No license has been selected yet. Do not assume redistribution rights until a license is explicitly added.
