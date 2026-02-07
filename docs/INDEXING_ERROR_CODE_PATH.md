# Indexing error: when and where the code runs

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Error message

```
Schema synchronization failed: disk I/O error
```

Seen in indexing worker log when handling `index_file` RPC (e.g. for `add_full_queue_support.py`).

---

## Why it fails (root cause)

1. **In the driver process there must be only one connection to the SQLite file.**  
   The RPC server already holds that connection (`self.driver`).

2. **Bug:** For each `index_file` request, the handler created a **new** `CodeDatabase(driver_config)` with `type: "sqlite"`.  
   That creates a **second** driver and calls `connect()` → **second connection** to the same `.db` file in the **same process**.

3. **`CodeDatabase.__init__` always calls `sync_schema()`** after `connect()`.  
   So the second connection immediately runs schema sync (read version, compare schemas, maybe backup, maybe migration).  
   SQLite allows multiple connections, but when one connection does schema/transaction work and another tries to read/write the same file, **lock contention** can occur.

4. **SQLite responds with "disk I/O error"** (often `SQLITE_IOERR_LOCK`): one of the operations inside `sync_schema()` on the second connection fails because of locks held by the first connection (or by the same process’s other connection).

5. **Summary:** The process falls because we open a **second connection** and run **sync_schema()** on it while the **first connection** is still in use. One connection + one queue is the intended design; the second connection breaks that and triggers the error.

---

## Intended chain (single client library, single driver process)

- **Indexing worker** → uses **DatabaseClient** (library) → RPC `index_file` →
- **Driver process** → **one** SQLite driver with **one** connection → **one** request queue.

No second connection to the same DB file in the same process.

---

## What was happening when the error occurred (before fix)

### Call stack (top → bottom)

| Step | Where | What runs |
|------|--------|-----------|
| 1 | Indexing worker process | `database.index_file(path, project_id)` via **DatabaseClient** (library). |
| 2 | Same process | `DatabaseClient.rpc_client.call("index_file", params)` → sends RPC to driver process. |
| 3 | **Driver process** | RPC server receives `index_file` → `rpc_handlers_index_file.handle_index_file()`. |
| 4 | **Driver process** | **Bug:** `CodeDatabase(driver_config)` with `type: "sqlite"` → **new** CodeDatabase instance. |
| 5 | `code_analysis/core/database/base.py` | `CodeDatabase.__init__(driver_config)` |
| 6 | `code_analysis/core/db_driver/__init__.py` | `create_driver("sqlite", config)` → **second** SQLite driver instance (second connection to same `.db` file). |
| 7 | `code_analysis/core/database/base.py` | `self.driver.connect(driver_cfg)` → second connection opened. |
| 8 | `code_analysis/core/database/base.py` | `self.sync_schema()` → called in `__init__` after connect. |
| 9 | `code_analysis/core/db_driver/sqlite.py` | `SQLiteDriver.sync_schema(schema_definition, backup_dir)` (the driver from **core/db_driver**, not database_driver_pkg). |
| 10 | Same file | Lock file acquired; then one of: `_get_schema_version()`, `compare_schemas()`, `validate_data_compatibility()`, `create_database_backup()`, or `test_conn = sqlite3.connect(...)` (line 302), or migration `execute()` / `commit()`. |
| 11 | **Error** | **`code_analysis/core/db_driver/sqlite.py`** around line **390–394**: `except Exception as e:` → `raise RuntimeError(f"Schema synchronization failed: {e}") from e`. The underlying `e` is typically **sqlite3.OperationalError: disk I/O error** (e.g. SQLITE_IOERR_LOCK). |

### Process and connections

- **Driver process** already has:
  - **Connection 1:** `database_driver_pkg` SQLite driver (RPC server’s `self.driver`) used for `execute`, `index_file` entry, etc.
- Then inside `handle_index_file`:
  - **Connection 2:** New `CodeDatabase(driver_config)` → `core.db_driver.sqlite.SQLiteDriver` → `connect()` → second process-level connection to the same DB file.
- Inside `sync_schema()` of that second driver:
  - Optional **connection 3:** `test_conn = sqlite3.connect(str(self.db_path))` in `core/db_driver/sqlite.py` line 302 (when backup failed and we check if DB is empty).

So at least two (and sometimes three) connections to the same file in one process → lock contention → SQLite reports "disk I/O error".

### Exact place the exception is raised

- **File:** `code_analysis/core/db_driver/sqlite.py`
- **Method:** `SQLiteDriver.sync_schema()`
- **Lines:** 390–394 (broad `except Exception as e`, then re-raise as `RuntimeError("Schema synchronization failed: {e}")`).
- **Underlying cause:** SQLite I/O error (e.g. lock) during one of the operations inside `sync_schema()` (e.g. `_get_schema_version()`, `compare_schemas()`, backup/empty-check, or migration).

---

## Fix applied

- In **`code_analysis/core/database_driver_pkg/rpc_handlers_index_file.py`**: stop creating a second `CodeDatabase(driver_config)`. Use **`CodeDatabase.from_existing_driver(self.driver)`** so the same connection (the RPC server’s driver) is reused and **no** second connection is opened and **no** `sync_schema()` is run in this path.
- **`code_analysis/core/database/base.py`**: added **`CodeDatabase.from_existing_driver(driver, driver_config=None)`** to build a CodeDatabase that uses an already-connected driver (no `connect()`, no `sync_schema()`).

After the fix, when `index_file` runs in the driver process, only the single driver connection is used; the error path above is no longer executed.
