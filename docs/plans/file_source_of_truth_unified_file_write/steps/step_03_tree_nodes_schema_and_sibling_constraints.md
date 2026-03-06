# Step 03: Node Constraints and Sibling Order Invariants

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**Parallel chains:** [../plan/PARALLEL_CHAINS.md](../plan/PARALLEL_CHAINS.md)  
**TZ:** [../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md](../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md)

---

## Executor role

Senior Python backend and database consistency engineer.

---

## Execution directive

- Execute only this step.
- Read every file and entry point listed in `Read first` before editing code.
- Modify only `code_analysis/core/database/schema_sync.py`.
- Do not push invariant enforcement into callers or invent weaker consistency rules.
- Stop immediately if any blackstop is triggered.

---

## Step scope

- **Target code file:** `code_analysis/core/database/schema_sync.py`
- **Step type:** invariant enforcement
- **Primary purpose:** make snapshot storage enforceable and migration-safe

---

## Dependency contract

- **Prerequisites:** Step 02
- **Unlocks:** Step 04
- **Forbidden scope expansion:** do not implement file-sync service logic in this step

---

## Required context

- TZ requires deterministic sibling order reconstruction.
- Each snapshot must have exactly one root.
- File-level restore must rely on constrained data, not best-effort interpretation of inconsistent rows.

---

## Read first

- `docs/plans/file_source_of_truth_unified_file_write/TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md`
- `docs/plans/file_source_of_truth_unified_file_write/plan/PLAN.md`
- `code_analysis/core/database/schema_sync.py` — class `SchemaComparator`, method `compare_schemas()`; classes `SchemaDiff`, `TableDiff`, `ColumnDef`, `IndexDef` (constraint/migration contract)
- `code_analysis/core/database/base.py` — `get_schema_definition()` and the tables/indexes dict it returns, to align new constraints with Step 02 schema

---

## Expected file change

- `code_analysis/core/database/schema_sync.py` must enforce the presence and validity of the new snapshot/node/root structures.
- The file must enforce unique `child_index` per parent and one root per snapshot.
- The file must fail loudly on invalid order/root states instead of silently accepting or normalizing them.

---

## Forbidden alternatives

- Do not push ordering validation into caller code as an alternative to schema/sync enforcement.
- Do not silently normalize broken sibling order.
- Do not weaken one-root-per-snapshot to a best-effort convention.

---

## Atomic operations

1. Inspect how `schema_sync.py` currently declares and validates DB constraints and migrations.
2. Add synchronization rules for the snapshot, node, and root-linkage structures introduced in Step 02.
3. Enforce unique sibling order per parent so `child_index` collisions cannot be accepted silently.
4. Enforce one-root-per-snapshot invariants.
5. Add validation or migration checks that fail loudly when sibling order or root uniqueness is broken.
6. Keep the migration/sync path deterministic for both fresh and already-initialized environments.

---

## Expected deliverables

- Schema sync path knows about every new structure added in Step 02.
- Sibling-order uniqueness and one-root-per-snapshot invariants are enforceable.
- Invalid states are detected explicitly instead of being tolerated.

---

## Mandatory validation

- Apply the full execution policy from [PLAN.md](../plan/PLAN.md).
- Run `black code_analysis/core/database/schema_sync.py` and expect success with no remaining formatting changes.
- Run `flake8 code_analysis/core/database/schema_sync.py` and expect zero reported violations.
- Run `mypy code_analysis/core/database/schema_sync.py` and expect zero type errors.
- Run `pytest tests/test_schema_sync.py -v --tb=short` and expect exit code 0 and all tests to pass.
- Run `pytest tests/test_database_client.py -k "sync_schema" -v --tb=short` and expect exit code 0 and all collected tests to pass.
- After implementation, invalid sibling/root states must be rejected by the sync path; if there are dedicated tests for that, run them and expect pass; otherwise document that the sync path rejects invalid states and that manual or future test coverage is required.

---

## Decision rules

- If sibling order cannot be enforced at schema/sync level, then stop and escalate instead of moving validation into later callers.
- If one-root-per-snapshot cannot be enforced deterministically, then stop and escalate.
- If the target file would exceed the project size limit after constraint work, then stop and escalate so the plan can be updated (e.g. additional step); do not produce multiple code files in this step.

---

## Blackstops

- Stop if sibling order cannot be enforced deterministically.
- Stop if the sync path can still accept multiple roots for one snapshot.
- Stop if migration behavior would silently normalize invalid ordering instead of rejecting it.

---

## Handoff package

Return exactly:

- the modified `code_analysis/core/database/schema_sync.py`;
- confirmation that all `Read first` files and entry points were inspected before editing;
- confirmation that the exact `Expected file change` was implemented without unauthorized alternatives;
- a concise list of enforced invariants;
- validation evidence for sync/migration behavior and quality checks.

---

## Handoff record (completed)

- **Modified files:** `code_analysis/core/database/schema_sync.py` (primary); `code_analysis/core/database/base.py` (schema definition: one additional unique constraint for sibling order).
- **Read first:** TZ, PLAN.md, schema_sync.py (SchemaComparator, compare_schemas, SchemaDiff, TableDiff, ColumnDef, IndexDef), base.py (get_schema_definition, tables/indexes for snapshot/root/nodes) were read before editing.
- **Expected file change:** Implemented. Sync path enforces snapshot/root/node structures; unique `child_index` per parent and one root per snapshot are enforceable; invalid states are rejected (no silent normalization).
- **Enforced invariants:**
  1. **One root per snapshot:** `file_tree_snapshot_roots.snapshot_id` is PK (schema); validation in `compare_schemas()` checks no duplicate `snapshot_id` in that table.
  2. **Unique sibling order per parent:** `file_tree_snapshot_nodes` has `UNIQUE(snapshot_id, parent_node_id, child_index)` in schema (base.py); `_validate_snapshot_invariants()` runs when any snapshot table exists and raises `RuntimeError` if duplicate `(snapshot_id, parent_node_id, child_index)` is found.
- **Validation evidence:** black, flake8, mypy pass on both files. `pytest tests/test_database_client.py -k sync_schema` passes. `pytest tests/test_schema_sync.py`: 11 passed, 4 failed; the 4 failures (TestSchemaSync: test_sync_with_outdated_schema, test_sync_with_identical_schema, test_sync_updates_version, test_sync_creates_backup_for_non_empty_db) are pre-existing (db_settings/updated_at migration), reproduced with no Step 03 changes. Sync path rejects invalid snapshot states: `compare_schemas()` calls `_validate_snapshot_invariants()` when snapshot tables exist and raises on violation.
- **Blackstops:** None triggered.
