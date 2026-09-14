# Verification backlog

These claims from the original proposal must not be treated as stable framework contracts until verified.

## P0 — Blocks a trustworthy static-prop MVP

- [ ] Establish a known-good Skyrim SE/AE vanilla static fixture and record its NIF tree, root node, shader property and texture-path conventions.
- [ ] Verify the exact NIF version/block expectations for current Skyrim SE/AE tooling.
- [ ] Verify PyNifly and/or NifTools compatibility against the Blender version selected for CI/manual fixtures.
- [ ] Verify texture path syntax written by current tools and accepted by the game.
- [ ] Verify actual `BSShaderTextureSet` slot semantics using vanilla fixtures/tool docs.
- [ ] Verify DDS formats/colorspace/mipmap rules with current SE/AE behavior and tooling.
- [ ] Define a reproducible PBR metal/rough -> Skyrim material conversion contract. Do not use a heuristic formula as a universal truth.
- [ ] Define triangle-count measurement using triangulated loop triangles, not polygon count.

## P1 — Needed after visual static MVP

- [ ] Collision workflow and Havok layer/shape conventions.
- [ ] Environment mapping / envmask conventions.
- [ ] Alpha blend/test behavior and thresholds.
- [ ] LOD naming/generation and DynDOLOD interaction.

## P2 — Expansion tracks

- [ ] Weapon pivot/orientation fixture.
- [ ] Armor / ArmorAddon / partitions / BodySlide workflow.
- [ ] Creature skeleton / animation pipeline.
- [ ] LE compatibility matrix.

## Known issue in the original proposal

The original `01_prepare_mesh.py` reports `len(me.polygons)` as `tris`. That is incorrect whenever faces are not already triangulated. A future Blender adapter must call `mesh.calc_loop_triangles()` and report `len(mesh.loop_triangles)` or otherwise prove equivalent behavior.
