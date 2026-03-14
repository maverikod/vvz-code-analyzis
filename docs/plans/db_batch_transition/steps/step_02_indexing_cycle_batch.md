# Step 02: Indexing cycle — per-cycle batch for indexing_errors and indexing_worker_stats

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Plan:** [../PLAN.md](../PLAN.md)  
**Parallel chains:** [../PARALLEL_CHAINS.md](../PARALLEL_CHAINS.md)  
**TZ:** [../TZ_DB_BATCH_TRANSITION.md](../TZ_DB_BATCH_TRANSITION.md)

---

## Executor role

Implementer: change only the function `process_cycle` in the target file so that no per-file `database.execute()` is used for `indexing_errors` (DELETE or INSERT) or for `indexing_worker_stats` (UPDATE). Instead, accumulate per cycle and run one `database.execute_batch(batch_ops)` at the end of each cycle, before the existing "End indexing_worker_stats cycle" UPDATE that sets cycle_end_time.

---

## Execution directive

- Execute only this step. Do not change step 01 or any other file.
- Read every file listed in "Read first" before writing code.
- Modify only `code_analysis/core/indexing_worker_pkg/processing.py`; do not change the driver, RPC, or any other module.
- Do not add alternative logic (e.g. do not keep per-file execute for indexing_errors or stats).
- Stop immediately if any blackstop is triggered.

---

## Step scope

- **Target code file:** `code_analysis/core/indexing_worker_pkg/processing.py`
- **Step type:** Refactor loop and add end-of-cycle batch
- **Purpose:** Accumulate indexing_errors DELETEs/INSERTs and indexing_worker_stats counters per cycle; flush one execute_batch at end of cycle.

---

## Dependency contract

- **Prerequisites:** None. This step is independent of step 01.
- **Unlocks:** Nothing else in this plan.
- **Forbidden scope:** Do not change `database.index_file`, discovery queries, cycle_start_time, INSERT INTO indexing_worker_stats at cycle start, or the final UPDATE that sets cycle_end_time; only remove per-file execute calls and add accumulators + one execute_batch.

---

## Required context

- `database` is a DatabaseClient (RPC) and has `execute_batch(operations, transaction_id=None)`. See `code_analysis/core/database_client/client_operations.py` for the signature. Each element of operations is `(sql_string, params_tuple)`.
- Current behaviour: after each file, one of (DELETE FROM indexing_errors WHERE project_id = ? AND file_path = ?) or (INSERT OR REPLACE INTO indexing_errors ...); then two UPDATE indexing_worker_stats (increment files_indexed/files_failed and total_processing_time; set average_processing_time_seconds). All via `database.execute(...)`.
- Target behaviour: during the loop over projects and files, do not call database.execute for indexing_errors or indexing_worker_stats. Instead: append (project_id, path) to a list for successful files (to clear errors); append (project_id, path, error_type, error_message) for failed files (to insert errors); add 1 to cycle_files_indexed or cycle_files_failed; add elapsed to cycle_total_time. After the loop over project_ids, build one list of ops: all DELETEs, all INSERTs, one UPDATE indexing_worker_stats with aggregated values; call database.execute_batch(batch_ops). The existing database.execute that sets cycle_end_time stays as is.

---

## Read first

- `docs/plans/db_batch_transition/TZ_DB_BATCH_TRANSITION.md` (sections 1, 3, 4, 6)
- `docs/reports/DB_TABLES_AND_BATCH_AUDIT.md` (section 2.3 "Hot path, single-row")
- `code_analysis/core/indexing_worker_pkg/processing.py` (full `process_cycle`: from "Start indexing_worker_stats cycle" through "End indexing_worker_stats cycle")
- `code_analysis/core/database_client/client_operations.py` (method `execute_batch` and its parameters)
- `code_analysis/core/database/schema_creation_create.py` (CREATE TABLE indexing_errors)
- `code_analysis/core/database/schema_definition_tables_rest.py` (indexing_worker_stats columns)

---

## Expected file change

- **Initialization (inside the same try block, in the `else:` branch when `project_ids` is non-empty):** Right after `cycle_indexed = 0` and `cycle_had_activity = False`, add five accumulators: `errors_to_clear = []` (list of (project_id, path)); `errors_to_insert = []` (list of (project_id, path, error_type, error_message)); `cycle_files_indexed = 0`; `cycle_files_failed = 0`; `cycle_total_time = 0.0`.
- **Success branch (after `result.get("success")` and `total_indexed += 1`, `logger.debug("Indexed %s", path)`):** Append `(project_id, path)` to `errors_to_clear`. Set `cycle_files_indexed += 1` and `cycle_total_time += elapsed`. Remove the entire `try: database.execute("DELETE FROM indexing_errors ..."); except Exception: pass` block. Remove both `database.execute("UPDATE indexing_worker_stats SET files_indexed = ...")` and `database.execute("UPDATE indexing_worker_stats SET average_processing_time_seconds ...")` for the success path. Keep `cycle_indexed += 1` and `cycle_had_activity = True`.
- **Failure branch (else, index_file returned success=False):** Append `(project_id, path, "index_error", err_msg)` to `errors_to_insert`. Set `cycle_files_failed += 1` and `cycle_total_time += elapsed`. Remove the try/except that does INSERT OR REPLACE INTO indexing_errors. Remove both UPDATE indexing_worker_stats calls. Keep `total_errors += 1`, `logger.warning`, and optional `logger.error` for temp_files. Keep `cycle_indexed += 1` and `cycle_had_activity = True`.
- **Exception branch (except Exception as e around the try that calls index_file):** Append `(project_id, path, "index_exception", str(e))` to `errors_to_insert`. Set `cycle_files_failed += 1` and `cycle_total_time += elapsed`. Remove the try/except that does INSERT OR REPLACE INTO indexing_errors. Remove both database.execute UPDATE indexing_worker_stats blocks. Keep all logging and `total_errors += 1`, `cycle_indexed += 1`, `cycle_had_activity = True`.
- **After the `for project_id in project_ids:` loop, before the comment "# End indexing_worker_stats cycle":** Build `batch_ops` as a list of `(sql, params)` tuples in this order: (1) For each `(p, path)` in `errors_to_clear`, append `("DELETE FROM indexing_errors WHERE project_id = ? AND file_path = ?", (p, path))`. (2) For each `(p, path, typ, msg)` in `errors_to_insert`, append `("INSERT OR REPLACE INTO indexing_errors (project_id, file_path, error_type, error_message, created_at) VALUES (?, ?, ?, ?, julianday('now'))", (p, path, typ, msg))`. (3) One UPDATE: `("UPDATE indexing_worker_stats SET files_indexed = ?, files_failed = ?, total_processing_time_seconds = ?, average_processing_time_seconds = ?, last_updated = julianday('now') WHERE cycle_id = ?", (cycle_files_indexed, cycle_files_failed, cycle_total_time, cycle_total_time / (cycle_files_indexed + cycle_files_failed) if (cycle_files_indexed + cycle_files_failed) > 0 else None, cycle_id))`. If `batch_ops` is non-empty, call `database.execute_batch(batch_ops)`. Do not remove or change the following block: "# End indexing_worker_stats cycle" and the `database.execute("UPDATE indexing_worker_stats SET cycle_end_time = ? ...")`.
- **Non-Python files:** The block that does `database.execute("UPDATE files SET needs_chunking = 0 WHERE id = ?", (row.get("id"),))` for non-.py/.pyi files stays unchanged; it is not part of the batching.
- Ensure no remaining `database.execute` in the file loop for DELETE indexing_errors, INSERT OR REPLACE indexing_errors, or UPDATE indexing_worker_stats (the two UPDATEs that update files_indexed/files_failed/total_processing_time/average_processing_time_seconds).

---

## Forbidden alternatives

- Do not keep any per-file `database.execute` for indexing_errors or for the two UPDATE indexing_worker_stats (files_indexed/files_failed/total_processing_time/average).
- Do not flush the batch inside the loop (e.g. per project); flush only once per cycle, after the entire `for project_id in project_ids` loop.
- Do not change the cycle start logic (UPDATE cycle_end_time WHERE NULL, INSERT INTO indexing_worker_stats with cycle_id) or the cycle end logic (UPDATE cycle_end_time WHERE cycle_id = ?).
- Do not change the signature of process_cycle or add a new module; all changes stay in processing.py.

---

## Atomic operations

1. Add the five accumulator variables at the start of the `else:` block (when project_ids is non-empty).
2. In the success branch: append to errors_to_clear; increment cycle_files_indexed; add elapsed to cycle_total_time; remove the three database.execute calls (one DELETE, two UPDATE).
3. In the failure branch: append to errors_to_insert; increment cycle_files_failed; add elapsed to cycle_total_time; remove the three database.execute calls (one INSERT, two UPDATE).
4. In the exception branch: append to errors_to_insert; increment cycle_files_failed; add elapsed to cycle_total_time; remove the three database.execute calls (one INSERT, two UPDATE).
5. After the `for project_id in project_ids:` loop, build batch_ops in the exact order: all DELETEs, all INSERTs, one UPDATE with (cycle_files_indexed, cycle_files_failed, cycle_total_time, average, cycle_id). If batch_ops is non-empty, call database.execute_batch(batch_ops). Leave the cycle_end_time UPDATE unchanged.

---

## Expected deliverables

- No per-file database.execute for indexing_errors or indexing_worker_stats (files_indexed, files_failed, total_processing_time_seconds, average_processing_time_seconds).
- One execute_batch per cycle, after the file loop, containing all DELETEs, all INSERTs, and one UPDATE for the cycle's aggregated stats.
- Semantics unchanged: successful files clear indexing_errors; failed files insert into indexing_errors; stats row updated once per cycle with correct totals.
- File passes black, flake8, mypy; full test suite passes.

---

## Mandatory validation

- All commands from project root.
- Run `black code_analysis/core/indexing_worker_pkg/processing.py` — no formatting changes left.
- Run `flake8 code_analysis/core/indexing_worker_pkg/processing.py` — zero violations.
- Run `mypy code_analysis/core/indexing_worker_pkg/processing.py` — zero type errors.
- Run `pytest` from project root — all tests must pass. Step is not complete until the test suite is green.

---

## Decision rules

- If the cycle had no files (project_ids empty), the accumulators are never initialized; do not call execute_batch in that case. Only when we entered the `else:` block do we initialize and later possibly flush; if we entered else but batch_ops is empty (e.g. no Python files were processed), still call execute_batch with at least the one UPDATE for indexing_worker_stats so the cycle row has files_indexed=0, files_failed=0, etc. So: when we have project_ids we always have one UPDATE in the batch (the stats row for this cycle_id); build batch_ops and call execute_batch only when we are in the else branch (we always have at least the one UPDATE op for the cycle).
- For the UPDATE params: average_processing_time_seconds = cycle_total_time / (cycle_files_indexed + cycle_files_failed) if denominator > 0 else None. Use the same column names and julianday('now') for last_updated as in the current code.
- Keep all existing logging (logger.debug, logger.warning, logger.error for temp_files) unchanged.

---

## Blackstops

- Stop if you must change any file other than `code_analysis/core/indexing_worker_pkg/processing.py`.
- Stop if any per-file database.execute remains for "DELETE FROM indexing_errors", "INSERT OR REPLACE INTO indexing_errors", or "UPDATE indexing_worker_stats" (the two that set files_indexed/files_failed/total_processing_time/average).
- Stop if the batch is flushed inside the inner loop (for row in files_data) or per project; it must be flushed once per cycle after the full project loop.

---

## Handoff package

Return: path of modified file; confirmation that "Read first" files were read; confirmation that accumulators are used and one execute_batch is called after the project loop with the correct op order (DELETEs, INSERTs, one UPDATE); validation evidence (black, flake8, mypy, pytest); any blockers or risks.
