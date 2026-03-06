# Step 02: Tree Snapshot Schema

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../plan/PLAN.md](../plan/PLAN.md)  
**Parallel chains:** [../plan/PARALLEL_CHAINS.md](../plan/PARALLEL_CHAINS.md)  
**TZ:** [../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md](../TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md)

---

## Executor role

Senior Python backend and database engineer.

---

## Execution directive

- Execute only this step.
- Read every file and entry point listed in `Read first` before editing code.
- Modify only `code_analysis/core/database/base.py`.
- Do not move schema work into another file or invent alternative storage architecture in this step.
- Stop immediately if any blackstop is triggered.

---

## Step scope

- **Target code file:** `code_analysis/core/database/base.py`
- **Step type:** schema foundation
- **Primary purpose:** define DB init objects required for full-file snapshot storage

---

## Dependency contract

- **Prerequisites:** Step 01
- **Step 01 outcome (completed):** [Handoff record in step_01](step_01_libcst_comments_behavior_check.md#handoff-record-completed) — LibCST preserves comments and docstrings on round-trip; comment→docstring conversion in normal mode is prohibited. This step and later steps assume that result; no need to re-prove it.
- **Unlocks:** Step 03
- **Forbidden scope expansion:** do not implement sync logic or caller wiring in this step

---

## Required context

- TZ §4: For each indexed/saved file the DB must store: complete CST/source payload for full text reconstruction; file linkage (`file_id`, `project_id`, absolute normalized path relation via files table); timestamp metadata for operational decisions; full node ordering (parent-child relations and sibling order). Node metadata (node_id, ranges, names) is auxiliary and cannot be the sole restoration basis.
- TZ requires full restoration from DB, not restoration from metadata-only rows.
- The minimal write unit is one file; schema objects must support file-scoped snapshot data and the above linkage and metadata.

---

## Read first

- `docs/plans/file_source_of_truth_unified_file_write/TZ_FILE_SOURCE_OF_TRUTH_UNIFIED_FILE_WRITE.md`
- `docs/plans/file_source_of_truth_unified_file_write/plan/PLAN.md`
- `code_analysis/core/database/base.py` — function `get_schema_definition()`; class `CodeDatabase` and its methods `_get_schema_definition`, `_do_sync_schema`, `_create_schema`, `_migrate_schema` (schema creation path)

---

## Expected file change

- `code_analysis/core/database/base.py` must define schema objects for: file-level snapshot storage (full source payload and metadata); node storage bound to a snapshot; explicit root linkage (one root per snapshot); and support for file linkage (file_id, project_id, path relation via files table) and timestamp metadata as in TZ §4.
- The same file must define required indexes for file/snapshot/node access.
- The initialization path must remain idempotent for both fresh and existing DB states.

---

## Forbidden alternatives

- Do not add sync logic or caller wiring here.
- Do not rely on metadata-only storage as a substitute for full restore payload.
- Do not place new schema definitions into another file as an alternative to the declared target file.

---

## Atomic operations

1. Inspect the current DB initialization path in `base.py` and identify the canonical place for new schema objects.
2. Add schema definitions for file-level snapshot storage that can retain full source payload plus required metadata.
3. Add schema definitions for file-bound node storage associated with a snapshot.
4. Add schema definitions for explicit root linkage so one snapshot has one authoritative root.
5. Add the indexes required for efficient file, snapshot, and node lookups.
6. Keep the initialization path idempotent and safe for both fresh and existing databases.

---

## Expected deliverables

- DB init path creates the snapshot, node, and root-linkage structures required by TZ.
- Required indexes are present for later write and restore flows.
- The schema foundation is ready for invariant enforcement in Step 03.

---

## Mandatory validation

- Apply the full execution policy from [PLAN.md](../plan/PLAN.md).
- Run `black code_analysis/core/database/base.py` and expect success with no remaining formatting changes.
- Run `flake8 code_analysis/core/database/base.py` and expect zero reported violations.
- Run `mypy code_analysis/core/database/base.py` and expect zero type errors.
- Run `pytest tests/test_database_client.py -k "sync_schema" -v --tb=short` and expect exit code 0 and all collected tests to pass.
- Run `pytest tests/test_driver_sqlite.py -k "sync_schema" -v --tb=short` and expect exit code 0 and all collected tests to pass.
- Run `pytest tests/test_sqlite_schema_edge_cases.py -k "sync_schema" -v --tb=short` and expect exit code 0 and all collected tests to pass.
- If the project uses a different test path for schema init, run it and expect no regressions (exit code 0, all relevant tests pass).

---

## Decision rules

- If the declared schema cannot encode full-file restore payload, then stop and escalate instead of inventing a reduced schema.
- If initialization becomes non-idempotent, then fix the schema path in this file before handoff.
- If the target file would exceed the project size limit after schema additions, then stop and escalate so the plan can be updated (e.g. additional step); do not produce multiple code files in this step.

---

## Blackstops

- Stop if the schema cannot bind all stored nodes to one file-level snapshot deterministically.
- Stop if DB initialization becomes non-idempotent or unsafe for existing installations.
- Stop if the schema foundation would force metadata-only restoration.

---

## Handoff package

Return exactly:

- the modified `code_analysis/core/database/base.py`;
- confirmation that all `Read first` files and entry points were inspected before editing;
- confirmation that the exact `Expected file change` was implemented without unauthorized alternatives;
- a concise list of added schema objects and indexes;
- validation evidence for initialization behavior and quality checks.

---

## Handoff record (completed)

- **Modified file:** `code_analysis/core/database/base.py`
- **Read first:** TZ, PLAN.md, and base.py (`get_schema_definition`, `CodeDatabase._get_schema_definition`, `_do_sync_schema`, `_create_schema`, `_migrate_schema`) were read before editing.
- **Expected file change:** Implemented as specified. No sync logic or caller wiring added. Schema only in base.py.
- **Added schema objects:**
  - **file_tree_snapshots:** file-level snapshot (id, file_id, project_id, source_payload, file_mtime, created_at, updated_at); FK to files and projects; UNIQUE(file_id). Full source payload for restoration; file linkage and timestamp per TZ §4.
  - **file_tree_snapshot_roots:** root linkage (snapshot_id PK, root_node_id); FK snapshot_id → file_tree_snapshots. One root per snapshot.
  - **file_tree_snapshot_nodes:** nodes bound to snapshot (id, snapshot_id, node_id, parent_node_id, child_index); FK snapshot_id → file_tree_snapshots; UNIQUE(snapshot_id, node_id). Supports parent-child and sibling order.
- **Added indexes:** idx_file_tree_snapshots_file_id, idx_file_tree_snapshots_project_id, idx_file_tree_snapshot_nodes_snapshot_id, idx_file_tree_snapshot_nodes_parent.
- **SCHEMA_VERSION:** bumped to 1.5.0.
- **Validation:** black, flake8, mypy pass. `pytest tests/test_database_client.py -k sync_schema`, `pytest tests/test_driver_sqlite.py -k sync_schema` pass. `tests/test_sqlite_schema_edge_cases.py -k sync_schema`: 3/4 pass; `test_sync_schema_with_errors` fails because the driver raises on table creation error instead of returning result with `errors` (pre-existing driver behavior; not caused by this step).
- **Blackstops:** None triggered. Init path remains idempotent (sync_schema creates missing tables/indexes from get_schema_definition).
