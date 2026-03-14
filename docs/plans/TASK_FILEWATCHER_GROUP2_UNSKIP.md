# Task: Enable TestFileWatcherIntegration (Group 2) — production fix

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Status:** Done. Commit: `49f709d` — feat(db): add CodeDatabase.execute() and unskip TestFileWatcherIntegration. Group 2 `pytest tests/test_file_write_integrations.py -q`: 5 passed, 2 skipped (skips from other tests).

---

**Context:** [FIVE_MODEL_TASKS_TEST_FIXES.md](FIVE_MODEL_TASKS_TEST_FIXES.md) — Model 2 (Group 2) left `TestFileWatcherIntegration` skipped due to Blackstop (no production changes). This task assigns the **production** fix so the tests can be unskipped and run green.

---

## Analysis (orchestrator)

### Current state

- **processor_queue.py** already uses `_db_execute()` everywhere (no direct `self.database.execute()`). `_db_execute()` supports both:
  - `database.execute(sql, params)` (DatabaseClient / RPC)
  - `database._execute()` + `_last_execute_result` / `_fetchone()` (CodeDatabase).
- **CodeDatabase** exposes only `_execute()` (and `_fetchone` / `_fetchall`). It does **not** expose a public `execute()` that returns a dict like `{"data": [...]}`.
- **Other production code** that receives a generic `database` and calls `database.execute()`:
  - `multi_project_worker_init.py` — many `database.execute(...)` and one `database.execute("SELECT id FROM watch_dirs", None)` expecting `result.get("data", [])`.
  - `multi_project_worker_cycle.py`, `multi_project_worker_scan.py`, `batch_processor.py`, `chunking.py`, `processing_cycle.py`, `processing_cycle_projects.py`, `indexing_worker_pkg/processing.py`, etc.
- When the **file watcher** is run with **CodeDatabase** (e.g. in tests: `FileChangeProcessor(database=test_db, ...)` with `test_db` = CodeDatabase), any code path that calls `database.execute()` fails because CodeDatabase has no `execute()`.

### Root cause

- The **skip reason** in the test (“ProcessorQueueOps uses database.execute(); CodeDatabase only has _execute()”) is **partially outdated**: ProcessorQueueOps uses `_db_execute()`, which already supports CodeDatabase. However, **FileChangeProcessor** or the code it uses (e.g. during initialization or in multi_project_worker paths) may still call `database.execute()` somewhere when the processor is created or when queue/cycle runs. So the failure can be either:
  1. In ProcessorQueueOps (unlikely — it uses _db_execute), or  
  2. In another layer (e.g. multi_project_worker_init when watch_dirs are synced) that uses `database.execute()`.

- **Unified fix:** Add a public **`execute(sql, params=None)`** method to **CodeDatabase** that returns the same contract as the RPC/driver client: a dict with key `"data"` (list of rows for SELECT; empty list for writes). Then all callers that use `database.execute()` work with both DatabaseClient and CodeDatabase.

### Scope

- **Production:** `code_analysis/core/database/base.py` (CodeDatabase) — add `execute()`.
- **Tests:** `tests/test_file_write_integrations.py` — remove the `@pytest.mark.skip` from `TestFileWatcherIntegration` and ensure the class runs (no skip decorator, no skip inside tests unless for external service).

---

## Task for executor

**Role:** Implement the production change and unskip the tests so that Group 2’s FileWatcher integration tests run and pass.

### 1. Add `CodeDatabase.execute()`

- **File:** `code_analysis/core/database/base.py`
- **Change:** Add a public method:
  - `execute(self, sql: str, params: Optional[tuple] = None) -> Dict[str, Any]`
  - Behavior:
    - For `sql` that is a SELECT (e.g. `sql.strip().upper().startswith("SELECT")`): run the query using existing `_fetchall` (or equivalent) and return `{"data": list_of_rows}`. If no rows, return `{"data": []}`.
    - For all other SQL (INSERT/UPDATE/DELETE etc.): call `_execute(sql, params)` and return `{"data": []}` so that callers that do `result.get("data", [])` get a list.
  - Use existing `_execute`, `_fetchone`, `_fetchall`; do not duplicate driver logic. Prefer `_fetchall` for SELECT so multiple rows are returned; if the codebase expects a single row, callers can take `data[0]` themselves.
- **Compatibility:** Return type must be a dict with at least key `"data"` (list). No change to method signatures of `_execute` / `_fetchone` / `_fetchall`.

### 2. Unskip `TestFileWatcherIntegration`

- **File:** `tests/test_file_write_integrations.py`
- **Change:**
  - Remove the `@pytest.mark.skip` decorator and the `reason=` string from the class `TestFileWatcherIntegration`.
  - Do not add new skips unless a test genuinely requires an external service (then document the reason).
  - Ensure fixtures used by these tests (e.g. `test_db`, `test_file_with_content`, `temp_dir`) still create a CodeDatabase with full schema (including `needs_chunking` and tables used by the processor). If the test DB is created elsewhere (e.g. in the same file), ensure `db._create_schema()` or equivalent is called if that is the project’s pattern for test DBs.

### 3. Validation

- Run Group 2 tests including FileWatcher:
  - `pytest tests/test_file_write_integrations.py -q`
- All tests in that file must pass (no failures, no errors). If any test is skipped, the skip must have a clear reason (e.g. “requires MCP server”).
- Run `black`, `flake8`, `mypy` on:
  - `code_analysis/core/database/base.py`
  - `tests/test_file_write_integrations.py`

### 4. Completion condition

- `pytest tests/test_file_write_integrations.py -q` is green (only allowed skips are documented).
- Black, flake8, mypy pass on the modified files.

### 5. Blackstops

- Do **not** change `processor_queue.py` for this task (it already uses `_db_execute()`).
- Do **not** change any other production module except `code_analysis/core/database/base.py` (add `execute()` only).
- Do **not** change test logic of `TestFileWatcherIntegration` beyond removing the skip and ensuring fixtures; do not relax assertions to make tests pass.

---

## Summary

| Item | Action |
|------|--------|
| **Root cause** | CodeDatabase has no public `execute()`; callers (file watcher path and others) expect `database.execute()` returning `{"data": [...]}`. |
| **Fix** | Add `CodeDatabase.execute(sql, params=None) -> Dict[str, Any]` returning `{"data": rows}` for SELECT and `{"data": []}` for writes. |
| **Tests** | Remove `@pytest.mark.skip` from `TestFileWatcherIntegration` in `tests/test_file_write_integrations.py`. |
| **Validation** | `pytest tests/test_file_write_integrations.py -q` green; black, flake8, mypy on modified files. |
