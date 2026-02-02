# compose_cst_module: IPC and latency analysis

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

## Purpose

Explain why `compose_cst_module` can take ~30–35 seconds and where inter-process communication (IPC) and subprocess costs come from. The goal is to identify bottlenecks and suggest improvements.

## Summary

- **Observed:** Command often runs ~33 s (server log), and the MCP proxy may report `SERVER_UNAVAILABLE` because its timeout is shorter than that.
- **Main contributors:**
  1. **Validation (mypy subprocess):** 10–20+ s for a single file, especially cold start.
  2. **Database: 100+ RPC round-trips** over Unix socket to the database driver process; no batching.
  3. **sqlite_proxy path (submit/poll):** Where used, `poll_interval = 0.1` s adds up to **~0.1 s × number of operations** (e.g. 10+ s for 100+ ops).

So the delay is mostly **IPC volume** (many small DB calls) and **heavy validation** (mypy), not a single blocking call.

### Profile logging

To find the bottleneck on your run, the code logs **`[PROFILE]`** lines with elapsed times:

- **Command:** `compose_cst_module` steps 1–15 (resolve_project, get_tree, generate_source, validate_and_write_temp, open_db_and_backup_data, create_file_backup, begin_transaction, apply_changes, total).
- **Validation:** `validate_file_in_temp` — compile, docstrings, flake8, mypy, total.
- **Apply:** `_apply_changes` — delete_file_data, update_file_record, update_file_data_atomic, os_replace, commit_transaction, git_commit.
- **DB helpers:** `_backup_file_data`, `_delete_file_data` (per file_id).

Example: `grep "\[PROFILE\]" logs/mcp_server.log` after a run to see the timeline.

---

## 1. Database access: two IPC paths

The project has two ways for the MCP server to talk to the DB:

| Path | Socket | Protocol | Used by |
|------|--------|-----------|--------|
| **DatabaseClient** | `{db_name}_driver.sock` | Request–response (one RPC per connection) | MCP commands, including `compose_cst_module` |
| **SQLiteDriverProxy** | `{db_name}.sock` (db_worker_manager) | Submit → poll loop → delete | CodeDatabase / sqlite_proxy driver |

`compose_cst_module` uses **DatabaseClient** (`base_mcp_command._open_database` → `DatabaseClient(socket_path)`). So its DB traffic goes over the **driver.sock** RPC path, not the submit/poll path. The submit/poll path still matters for other flows and for understanding overall IPC design.

---

## 2. compose_cst_module DB operation count

Rough count of DB-related calls in one successful run (existing file, with backup and transaction):

- **Resolve project:** `get_project` (RPC).
- **If file exists:**
  - `select("files")` (1).
  - `_backup_file_data`: 9–10 `execute` (SELECT) + 1 optional methods SELECT → **~11**.
- **Backup manager:** file backup (no DB).
- **Transaction:** `begin_transaction` (1).
- **Apply changes:**
  - `_delete_file_data`: 2 SELECT + ~14 DELETE → **~16**.
  - `_update_file_record`: 1 UPDATE or `create_file` (1–2 RPCs).
  - `_update_file_data_atomic`:
    - `save_ast`: `get_file` + `select` + `update` or `insert` → **3**.
    - `save_cst`: same → **3**.
    - Per class: `create_class` → `insert` + `select` → **2** per class.
    - Per method: `create_method` → **2** per method.
    - Per function: `create_function` → **2** per function.
    - Per import: `create_import` → **2** per import.
- **Commit:** `commit_transaction` (1).

Example for a small file (e.g. 5 classes, 25 methods, 3 functions, 10 imports):

- Backup: ~11  
- Begin: 1  
- Delete: ~16  
- Update record: 1–2  
- save_ast + save_cst: 6  
- Entities: 5×2 + 25×2 + 3×2 + 10×2 = 86  
- Commit: 1  

**Total ≈ 122 RPC round-trips** to the driver process for one `compose_cst_module` run.

Each RPC is a new connection (or pool checkout), send, and wait for response. So latency is dominated by **number of round-trips**, not by a single slow query.

---

## 3. DatabaseClient → driver.sock (RPC)

- **Client:** `DatabaseClient` → `RPCClient._send_request`: one TCP (Unix) connection per request (or from pool), send request, receive response, then connection is not reused (server closes after response).
- **Server:** `database_driver_pkg` `RPCServer`: accept connection, enqueue request, worker from pool runs driver (e.g. SQLite), writes response, client gets it.

So each of the ~122 calls is **one RTT**. There is **no batching**: every `insert`/`select`/`execute` is a separate RPC. Worker pool size and SQLite’s single-writer nature can serialize work and add queuing delay, but the main cost is **many small requests**.

---

## 4. sqlite_proxy path (submit / poll / delete)

Used by **CodeDatabase** with driver type `sqlite_proxy` (e.g. init DB, other non-MCP paths). Not used by `compose_cst_module`, but relevant for overall IPC:

- **Protocol:** For each logical operation: **submit** (new connection, send job, get `job_id`) → **poll** in a loop with `time.sleep(poll_interval)` until status is completed/failed → **delete** (new connection, send delete).
- **Default `poll_interval`:** **0.1 s** (e.g. `code_analysis/core/database/base.py`, `config.json`).
- **Effect:** For N operations, in the worst case you get about **N × poll_interval** of sleep (e.g. 100 × 0.1 s = 10 s) plus 3 round-trips per operation (submit, poll(s), delete).

So any code path that uses sqlite_proxy and does many operations will pay this **poll_interval** tax. Reducing `poll_interval` (e.g. to 0.01 s) would cut that sleep time for those paths.

---

## 5. Validation: mypy subprocess

- **Location:** `compose_cst_module` → `_validate_and_write_temp` → `validate_file_in_temp` → `type_check_with_mypy` (in `core/cst_module/validation.py`).
- **Implementation:** `type_checker.type_check_with_mypy` runs **mypy in a subprocess** (see `_type_check_with_subprocess`). This avoids in-process import/ast conflicts but adds process start and mypy startup cost.
- **Typical cost:** **10–20+ seconds** for one file (cold start, imports, type checking). This is often the **largest single contributor** to the ~33 s total.

So the “compilation” step is cheap; **mypy** is the heavy part of validation.

---

## 6. Other costs

- **Flake8:** Usually 1–3 s for one file.
- **Backup (file copy), git, temp file I/O:** Usually under a couple of seconds.
- **CST/tree work:** In-memory; negligible compared to IPC and mypy.

---

## 7. Rough time breakdown (33 s example)

| Phase | Estimated share | Notes |
|-------|-----------------|--------|
| mypy (subprocess) | 10–20 s | Dominant; cold start and type checking |
| DB (122 RPCs) | 5–12 s | Many round-trips; queuing and SQLite serialization |
| Flake8 + docstrings + compile | 1–3 s | Single file |
| Backup, git, I/O | 1–2 s | |

So the total is consistent with **~30–35 s**, and the main levers are **mypy** and **number of DB round-trips**.

---

## 8. Recommendations

### 8.1 Validation (mypy)

- **Option A:** Make type-check validation **optional** for `compose_cst_module` (e.g. parameter `validate_type_checker: bool = False` or config), so fast edits don’t pay 10–20 s.
- **Option B:** Run mypy with a **timeout** (e.g. 5–10 s) and treat timeout as “skipped” or “warning” instead of hard failure.
- **Option C:** Run mypy **asynchronously** (e.g. in background) and return success immediately, with type errors reported later or in a follow-up call (requires API/UX design).

### 8.2 Database IPC

- **Batch operations:** Introduce an RPC that runs a **batch** of statements in one transaction (e.g. “execute_batch” with a list of SQL + params). Then `_delete_file_data` and `_update_file_data_atomic` could send one or a few batched RPCs instead of dozens of single-shot RPCs.
- **Keep connection / session:** If the driver protocol is extended to allow multiple requests over one connection (or a session), round-trips and connection churn would drop.
- **Transaction scope:** Ensure all operations inside the command use a single transaction and minimal number of RPCs (batch or multi-statement RPC) so that the driver process does one commit at the end.

### 8.3 sqlite_proxy (for other commands)

- **Reduce `poll_interval`** for the sqlite_proxy driver (e.g. from 0.1 s to 0.01 s or 0.005 s) in config/defaults. This cuts the sleep overhead for any flow that does many submit/poll/delete cycles (e.g. 100+ ops: from ~10 s to ~1 s of sleep).
- **Optional:** Add a “sync” mode where the worker sends the result back on the **same** connection (request–response) instead of submit → poll → delete, so each operation is one RTT and no poll sleep.

### 8.4 Observability

- Add **timing** (e.g. log or return) for: validation (mypy vs flake8 vs compile), DB phase (backup + delete + update + commit), and file I/O. That will confirm which phase dominates in production and after changes.

---

## 9. Batch RPC (implemented)

To reduce the number of RPC round-trips, **execute_batch** was added:

- **Driver:** `BaseDatabaseDriver.execute_batch(operations, transaction_id)` runs a list of `(sql, params)` in one RPC; default implementation loops `execute()` so all drivers work without change.
- **RPC:** `handle_execute_batch` in `rpc_handlers_base.py`; registered in `rpc_server.py` as `execute_batch`.
- **Client:** `DatabaseClient.execute_batch(operations, transaction_id)` sends one RPC and returns a list of result dicts (same shape as `execute()`).

**compose_cst_module** uses batching:

- **\_backup_file_data:** One batch of 9 SELECTs (files, classes, functions, imports, usages, issues, code_content, ast_trees, cst_trees); then optionally one batch of 1 SELECT for methods. So **2 RPCs** instead of ~11.
- **\_delete_file_data:** One batch of 2 SELECTs (class_ids, content_ids); then one batch of all DELETEs (FTS, methods, entities, vector_index). So **2 RPCs** instead of ~16. Uses the same `transaction_id` as the command transaction.

**Expected effect:** Backup + delete go from ~27 single-shot RPCs to **4** batched RPCs. Remaining DB cost is mainly `_update_file_data_atomic` (per-entity inserts) and validation (mypy). To measure: run `compose_cst_module`, then `grep "\[PROFILE\]" logs/…` and compare `_backup_file_data` and `_delete_file_data` elapsed times before/after.

---

## 10. References

- `code_analysis/commands/cst_compose_module_command.py` — command flow, DB and validation calls.
- `code_analysis/core/database_client/rpc_client.py` — RPC client (request–response).
- `code_analysis/core/database_driver_pkg/rpc_server.py` — RPC server (driver.sock).
- `code_analysis/core/db_driver/sqlite_proxy.py` — submit/poll/delete protocol, `poll_interval`.
- `code_analysis/core/db_worker_pkg/runner.py` — DB worker (submit/poll/delete).
- `code_analysis/core/cst_module/validation.py` — validation and mypy.
- `code_analysis/core/code_quality/type_checker.py` — mypy subprocess.
- `docs/commands/cst/compose_cst_module.md` — user-facing docs and timeout note (e.g. 40–60 s for proxy).
- `code_analysis/core/database_client/client_operations.py` — `execute_batch` client method.
- `code_analysis/core/database_driver_pkg/rpc_handlers_base.py` — `handle_execute_batch`.
