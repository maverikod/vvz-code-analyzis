# Error Analysis: Server Test Session

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Summary

During the server tools test (delete projects, create project, create CLI app, edit/move node, search, worker status), two errors occurred:

1. **SERVER_UNAVAILABLE** — after `cst_save_tree` for cli.py, the third `cst_save_tree` (utils.py) failed with "Server code-analysis-server_1 is unavailable".
2. **NOT NULL constraint failed: files.dataset_id** — when creating `greeting.py` via `cst_create_file`, the RPC/driver reported "Failed to insert row: NOT NULL constraint failed: files.dataset_id".

---

## 1. SERVER_UNAVAILABLE (Why the server “fell”)

### What happened

- `cst_save_tree` for main.py and cli.py succeeded.
- The third call (`cst_save_tree` for utils.py) returned SERVER_UNAVAILABLE (or a retry failed with it).
- Later, after restarting the server, `cst_create_file` for greeting.py failed with the dataset_id error.

### Possible causes (no server log was inspected)

1. **Crash in server or driver**  
   An unhandled exception in the server process or in the database driver process could terminate the process. The MCP proxy would then report the server as unavailable.

2. **Driver process died on a later request**  
   If the driver hit the NOT NULL constraint (e.g. on another code path that inserts into `files`), it might raise and crash the driver process. Subsequent requests would then fail with SERVER_UNAVAILABLE until the server (and driver) are restarted.

3. **Connection/timeout**  
   Long-running `cst_save_tree` (e.g. heavy DB/disk work) could cause the MCP proxy or client to time out and close the connection, leading to “unavailable” on the next request.

4. **Resource exhaustion**  
   Memory or file descriptors could have been exhausted during multiple save operations.

### Recommendations

- **Always check logs after a failure**  
  Daemon log: `{config_dir}/logs/mcp_server.log` (from config `server.log_dir`).  
  Driver log: `logs/database_driver.log.*` if the driver writes there.  
  Inspect stack traces and the last operations before SERVER_UNAVAILABLE.

- **Do not restart the server before collecting logs**  
  Restarting loses the failing process state and tracebacks. Prefer: reproduce once, then inspect logs and fix the root cause (e.g. dataset_id below).

---

## 2. NOT NULL constraint failed: files.dataset_id

### What happened

- `cst_create_file` for greeting.py calls `save_tree_to_file` → `database.create_file(file_obj)`.
- The server uses **DatabaseClient** (RPC), which sends `insert("files", data)` to the database driver.
- `data` comes from `object_to_db_row(file)` → `File.to_db_row()`. The **File** model has **no `dataset_id`**.
- The driver runs `INSERT INTO files (project_id, path, ...) VALUES (?, ?, ...)` with only the columns present in `data`.
- The **actual SQLite database** has a column `files.dataset_id` that is **NOT NULL** and has no default.
- SQLite therefore rejects the insert: "NOT NULL constraint failed: files.dataset_id".

### Root cause

- The **current codebase** no longer has datasets:
  - `code_analysis/core/database/datasets.py` is **deleted** (D in git status).
  - `_get_schema_definition()` in `code_analysis/core/database/base.py` defines the **files** table **without** `dataset_id` (lines 1539–1596).
  - `File` in `code_analysis/core/database_client/objects/file.py` has no `dataset_id`.
  - Direct `add_file` in `code_analysis/core/database/files.py` does not use `dataset_id`.
- So the **database file on disk** was created or altered by an **older version** that added `dataset_id` to `files` (when datasets existed). After removing the datasets feature, **no migration was added** to drop or relax `dataset_id`. The live DB still has NOT NULL `dataset_id`, so inserts that omit it fail.

### Evidence

- Tests still reference datasets: `tests/test_vectorization_integration.py` calls `temp_db.add_file(..., dataset_id=...)` and `temp_db.get_or_create_dataset(project_id)`, but `core/database/files.py` `add_file()` has **no** `dataset_id` parameter — tests are outdated or use a different DB fixture.
- No `dataset_id` in: `base.py` CREATE TABLE files, `_get_schema_definition()` "files", `File.to_db_row()`, or driver schema. So the only source of `files.dataset_id` is an **existing DB** created by old code.

### Fix (optional)

Project is in development stage; migration was not added. If the DB has `dataset_id` in `files`, either recreate the DB from the current schema or add a one-off migration to drop the column when needed.

---

## 3. Why the server was restarted (and why that was wrong)

The server was restarted without:

1. Checking `logs/mcp_server.log` (or the configured daemon log) for the crash/exception.
2. Checking driver logs for the NOT NULL error or driver crash.
3. Fixing the dataset_id schema so that the next run would not hit the same insert error.

Correct approach:

1. On SERVER_UNAVAILABLE: **do not restart** until logs are read and the cause is identified.
2. On dataset_id: **add the migration** and, if needed, fix tests that still pass `dataset_id` to `add_file` so they match the current API and schema.

---

## 4. Action items

| # | Action |
|---|--------|
| 1 | After any SERVER_UNAVAILABLE, inspect `server.log_dir/mcp_server.log` and driver logs before restarting. |
| 2 | Align tests: remove or update `dataset_id` / `get_or_create_dataset` usage in `test_vectorization_integration.py` to match the current schema and `add_file()` signature. |

---

## 5. Session 2026-01-30: cst_create_file x3 and SERVER_UNAVAILABLE (root cause found)

### What happened

- After create_project, three `cst_create_file` calls: main.py (OK), cli.py (OK), utils.py (client got SERVER_UNAVAILABLE).
- Agent retried utils.py and got "All connection attempts failed"; no restart was done in this session before investigating.

### Investigation (logs/mcp_server.log)

1. **Third cst_create_file (utils.py) completed on the server**  
   Log shows: `Command 'cst_create_file' executed in 10.426s` at 23:49:06. So the server did **not** crash on the third call; it finished successfully.

2. **Cause of SERVER_UNAVAILABLE: server was stopped**  
   At 23:49:15 the log shows: `Received signal 15, stopping all workers...` (SIGTERM). So the process was **terminated from outside** (e.g. manual restart, IDE, or another script). The client/proxy saw SERVER_UNAVAILABLE because the server was shutting down or already down when the next request (or retry) was made.

3. **Conclusion**  
   - Do **not** restart without checking logs; this time the logs showed the server was killed by SIGTERM, not by an internal error.  
   - The third file (utils.py) may have been created on disk before shutdown; after a new server start, the project may already contain main.py, cli.py, and possibly utils.py.

### Other errors in the same log (fixed)

| Error | Location / context |
|-------|---------------------|
| `RuntimeError: Event loop is closed` | Vectorization worker calling chunker service (svo_client async) after event loop closed. |
| `unsupported operand type(s) for -: 'float' and 'datetime.datetime'` | File watcher “computing delta” for main.py and cli.py. |
| `'DatabaseClient' object has no attribute '_fetchall'` | File watcher checking database projects for deleted directories. |

**Fixes applied:** (1) **Event loop**: `runner.py` — SVO init and `process_chunks` now run in one event loop (`_run_worker_with_svo()`), so the chunker client is not bound to a closed loop. (2) **float vs datetime**: `processor.py` — convert `db_mtime` to timestamp when it has `.timestamp()` (datetime) before comparing with filesystem mtime. (3) **_fetchall**: `processor.py` — use `database.select("projects", columns=["id", "root_path"])` when client has `select`, else `database.execute("SELECT ...").get("data", [])`.
