# Step 03: Node Constraints and Sibling Order Invariants

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**TZ:** [../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md](../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md)

---

## Role

Senior Python backend/database consistency engineer.

## Target code file

`code_analysis/core/database/schema_sync.py`

## Goal

Enforce schema-level and sync-level invariants for full tree storage, especially sibling order preservation.

## Tasks

1. Add schema sync rules for new snapshot/node/root tables.
2. Enforce sibling order uniqueness per parent (`child_index` uniqueness).
3. Enforce root uniqueness per snapshot.
4. Add validation hooks/checks for node-order invariants during schema validation.
5. Ensure migration path is deterministic and safe.

## Acceptance checks

- Schema sync validates presence of new constraints.
- Invalid sibling order states are detected and reported.
- One-root-per-snapshot invariant is enforced.

## Blackstops

- Stop if sibling order cannot be guaranteed deterministically.
- Stop if sync logic can silently accept multiple roots in one snapshot.
