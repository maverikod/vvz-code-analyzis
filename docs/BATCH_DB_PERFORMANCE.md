# Batch DB performance (cst_save_tree / compose_cst_module)

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Purpose

After refactoring file-data writes from per-row calls (save_ast, save_cst, create_class, create_method, create_function, create_import in loops) to batch operations (execute_batch), this doc describes how to measure performance and correctness.

## What changed

- **Before:** One DB round-trip per entity (AST, CST, each class, method, function, import). For a file with many entities this produced many round-trips and high latency (e.g. ~6s for `update_file_data_atomic` on a small file over RPC).
- **After:** Three `execute_batch` calls: (1) clear + insert AST + insert CST, (2) insert all classes, (3) insert all methods + functions + imports. Same data, fewer round-trips.
- **Typical effect:** `update_file_data_atomic` dropped from ~6s to ~1s for the same file (server with RPC driver). Exact numbers depend on DB location and load.

## How to measure performance

### 1. Via server (real usage)

1. Restart server: `python -m code_analysis.cli.server_manager_cli --config config.json restart`
2. Run the real workflow (e.g. `/realusecmd` in chat): load file → modify → save.
3. In the `cst_save_tree` response, use the `timings` object:
   - `update_file_data_atomic` — time for the batch file-data update (AST, CST, entities).
   - `db_file_record` — time for file record create/update.
   - `commit_transaction` — commit time.
4. Optionally run the same save several times and compare min/mean/max of `update_file_data_atomic`.

### 2. Automated performance tests

Run the batch performance tests (mock DB; checks that timings are present and within threshold):

```bash
pytest tests/performance/test_cst_save_batch_performance.py -v
```

With printed timings:

```bash
pytest tests/performance/test_cst_save_batch_performance.py -v -s
```

Tests assert that `update_file_data_atomic` is under 5s; if it grows (e.g. someone re-introduces per-row calls in a loop), the test fails.

## Correctness

- **Batch DB contents (known result):** `tests/test_file_data_batch_integration.py` — real CodeDatabase, `update_file_data_atomic_batch`, then asserts exact counts and content in `classes`, `methods`, `functions`, `imports`, `ast_trees`, `cst_trees`. Uses fixed source code and expected entity names/counts.
- **Unit:** `tests/test_cst_tree_saver.py` — tree_saver with mock that has `execute_batch`.
- **Batch driver:** `tests/test_sqlite_batch.py` — SQLite batch execution.
- **File data atomic (legacy path):** `tests/test_update_file_data_atomic.py` — CodeDatabase atomic update.
- **Entity cross-ref:** `tests/test_entity_cross_ref_integration.py` — entity dependencies after update.

After changing batch or file-data logic, run:

```bash
pytest tests/test_cst_tree_saver.py tests/test_sqlite_batch.py tests/test_update_file_data_atomic.py tests/performance/test_cst_save_batch_performance.py -v
```

## Baseline (reference)

- **Environment:** code-analysis-server over MCP, SQLite via RPC, test_data project.
- **Before batch refactor:** `update_file_data_atomic` ~6.3s for a small file (single save).
- **After batch refactor:** `update_file_data_atomic` ~1.0–1.2s for the same file.
- **Commands affected:** `cst_save_tree`, `compose_cst_module` (the path that writes file data in one transaction).
