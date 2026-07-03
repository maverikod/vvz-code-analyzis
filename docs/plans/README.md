# `docs/plans/` — development plans

Two generations coexist here:

- **Legacy plans** — date-named directories (`YYYY-MM-DD-<slug>/`), free internal
  structure. Kept as-is for history; do not restructure them.
- **New multi-level plans** — follow the planning stack in
  [`docs/standards/planning/`](../standards/planning/):
  `plan_standard_machine.yaml` (hierarchy HRS/MRS/GS/TS/AS, invariants, cascade
  changes), `tactical_step_creation_standard.yaml` and
  `atomic_step_creation_standard.yaml` (levels 4–5),
  `hrs_mrs_gs_consistency_verification_standard.yaml` (verification).
  Directory convention: `G-NNN-<slug>/T-NNN-<slug>/atomic_steps/A-NNN-<slug>.yaml`;
  IDs are zero-padded, stable, never reused; changes flow top-down via the
  cascade procedure.

Small ad-hoc plans may still use a single date-named directory; anything with
more than one tactical step uses the multi-level stack.
