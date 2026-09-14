# Tool adapters

The scripts from the original proposal are intentionally **not promoted to production adapters yet**.

Reason: Blender/NIF APIs are version-sensitive and the draft contains at least one confirmed contract bug (polygon count labelled as triangle count) plus operations that have not been executed in the target Blender version.

`docs/original-proposal.md` preserves the draft scripts for review. Promote each script here only after:

1. selecting a target Blender version;
2. adding a fixture;
3. running it headless;
4. validating the emitted report;
5. documenting rollback/input preservation.
