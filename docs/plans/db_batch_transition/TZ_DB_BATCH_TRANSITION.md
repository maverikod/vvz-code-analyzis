# Technical Specification: DB Batch Transition

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Source audit:** [docs/reports/DB_TABLES_AND_BATCH_AUDIT.md](../../reports/DB_TABLES_AND_BATCH_AUDIT.md)  
**Plan:** [PLAN.md](PLAN.md)  
**Parallel chains:** [PARALLEL_CHAINS.md](PARALLEL_CHAINS.md)

---

## 1. Objective

Transition hot-path and clear-path database writes from single-row `_execute` / `execute` calls to batched `execute_batch` where the audit recommends it:

1. **clear_file_data** (files/crud.py): Replace multiple sequential `_execute("DELETE FROM ...")` with one `execute_batch(ops)` for all DELETEs after vector cleanup.
2. **Indexing cycle** (indexing_worker_pkg/processing.py): Replace per-file `database.execute()` for `indexing_errors` (DELETE/INSERT) and `indexing_worker_stats` (two UPDATEs) with per-cycle accumulation and one `execute_batch` at end of cycle.

No change to tables or schema. No new features. Behaviour must remain identical; only the number and shape of DB round-trips change.

---

## 2. Mandatory completion condition

A step is complete only when:

1. Code changes match the step file exactly (target file only).
2. `black`, `flake8`, and `mypy` pass for the touched file.
3. **Full test suite green** (`pytest` from project root).

---

## 3. Scope

### In scope

- `code_analysis/core/database/files/crud.py`: function `clear_file_data` — build one list of DELETE operations and run `self.execute_batch(ops)` instead of multiple `self._execute(...)` (and optionally inline `delete_entity_cross_ref_for_file` into one batch op).
- `code_analysis/core/indexing_worker_pkg/processing.py`: inside `process_cycle`, accumulate indexing_errors (clears + inserts) and indexing_worker_stats counters per cycle; remove per-file `database.execute()` for those tables; flush one batch at end of cycle (before "End indexing_worker_stats cycle" UPDATE cycle_end_time).

### Out of scope

- Tables "single by design" (db_settings, watch_dirs, projects, file_watcher_stats, vectorization_stats).
- Adding code_content, usages, issues, entity_cross_ref to `update_file_data_atomic_batch` (separate plan if product needs).
- Any change to `_clear_file_vectors`, `delete_entity_cross_ref_for_file` signatures or callers other than their use inside `clear_file_data`.

---

## 4. Root-cause map (from audit)

| Location | Current behaviour | Target behaviour |
|----------|-------------------|------------------|
| files/crud.clear_file_data | Many `_execute("DELETE FROM ...")` in sequence (code_content_fts, methods, classes, functions, imports, issues, usages, code_content, ast_trees, cst_trees) plus `delete_entity_cross_ref_for_file` (one _execute). | One `execute_batch(ops)` with all DELETE ops in correct order; optionally one batch op for entity_cross_ref instead of calling `delete_entity_cross_ref_for_file`. |
| indexing_worker_pkg/processing.py | Per file: `database.execute("DELETE FROM indexing_errors ...")` or `INSERT OR REPLACE INTO indexing_errors ...`; then two `database.execute("UPDATE indexing_worker_stats ...")`. | Per cycle: accumulate (project_id, path) to clear and (project_id, path, error_type, error_message) to insert; accumulate files_indexed, files_failed, total_processing_time_seconds; at end of cycle run one `execute_batch` (all DELETEs, all INSERTs, one UPDATE for stats). |

---

## 5. Non-negotiable rules for executor (LLAMA)

- Implement only the target file of each step; do not change other modules.
- Do not add TODOs, placeholders, or alternative code paths.
- Imports only at top of file (no lazy import unless already present).
- On ambiguity: stop and report; do not guess.

---

## 6. Step inventory (parallelizable)

| Step | Step file | Target file | Goal |
|------|------------|--------------|------|
| 01 | steps/step_01_clear_file_data_batch.md | code_analysis/core/database/files/crud.py | clear_file_data: one execute_batch of DELETE ops. |
| 02 | steps/step_02_indexing_cycle_batch.md | code_analysis/core/indexing_worker_pkg/processing.py | Per-cycle batch for indexing_errors and indexing_worker_stats. |

**Dependency:** None between step 01 and step 02. They touch different files and different code paths. Execute in any order or in parallel (see PARALLEL_CHAINS.md).

---

## 7. References

- Audit: `docs/reports/DB_TABLES_AND_BATCH_AUDIT.md`
- execute_batch signature: `code_analysis/core/database/base.py` — `execute_batch(self, operations: List[Tuple[str, Optional[tuple]]], transaction_id=None) -> List[Dict]`
- clear_file_data current: `code_analysis/core/database/files/crud.py` (function `clear_file_data`)
- delete_entity_cross_ref_for_file: `code_analysis/core/database/entity_cross_ref.py` (WHERE build logic)
- Indexing cycle: `code_analysis/core/indexing_worker_pkg/processing.py` (`process_cycle`, loop over projects/files, cycle_id, cycle_end_time UPDATE)
