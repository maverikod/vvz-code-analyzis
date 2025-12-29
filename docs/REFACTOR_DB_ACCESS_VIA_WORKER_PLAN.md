## Refactor Plan: Database access only via DB worker + driver

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

### Goal / Non‑negotiable rules

- **Rule 1**: Only the **DB worker** may access SQLite directly (`sqlite3.connect`, cursors, commits).
- **Rule 2**: Only the **database driver** may talk to the DB worker (IPC/queue/RPC).
- **Rule 3**: **All** DB calls in the codebase must go through the **driver API** only (no `db.conn`, no `cursor = ...`).
- **Rule 4**: Errors must be **logged** with enough context and be **handled** consistently (typed errors, no silent failures).
- **Rule 5**: Any database driver MUST be a subclass of **`BaseDatabaseDriver` (ABC)** and implement a stable set of **abstract methods**. All call sites MUST depend on the **base type** (e.g., `BaseDatabaseDriver`) in signatures/DI to enable transparent future databases.
- **Rule 6**: **CRITICAL**: All driver operations with DB worker MUST use **async/await** (async methods). No synchronous queue access. Polling MUST use `await asyncio.sleep(poll_interval)`. RPC calls MUST use `await`. All queue operations MUST be async.

### Driver interface requirement (for future DB backends)

- The driver is a **polymorphic boundary**. It MUST:
  - Inherit from `code_analysis/core/db_driver/base.py:BaseDatabaseDriver`
  - Implement the abstract API (execute/fetchone/fetchall/commit/rollback/lastrowid/create_schema/get_table_info/connect/disconnect).
  - **CRITICAL**: For proxy drivers (sqlite_proxy), all operations with worker MUST use async/await internally.
- The rest of the codebase MUST:
  - Type against `BaseDatabaseDriver` (or an even narrower protocol if introduced later).
  - Avoid driver-specific types (`SQLiteDriver`, `SQLiteDriverProxy`) in signatures.
  - Use explicit driver selection via configuration (so PostgreSQL/MySQL/etc. can be plugged in later).
- **Rule 5 (Extensibility)**:
  - All database drivers **must be subclasses** of the shared abstract base class `BaseDatabaseDriver`
    (`code_analysis/core/db_driver/base.py`) and implement its **abstract method set**.
  - All higher-level code (server commands, workers, database facade) must depend on the **base type**
    (`BaseDatabaseDriver`) in signatures/attributes where applicable, so that other databases can be
    plugged in transparently later (PostgreSQL, DuckDB, etc.) without changing call sites.

### Current state (baseline)

- There is a driver abstraction (`code_analysis/core/db_driver/base.py`) with two implementations:
  - **`sqlite`** direct driver: `code_analysis/core/db_driver/sqlite.py` (uses `sqlite3.connect`).
  - **`sqlite_proxy`** driver: `code_analysis/core/db_driver/sqlite_proxy.py` (uses queuemgr and executes `SQLiteDatabaseJob`).
- Most DB operations are currently implemented in the `code_analysis/core/database/*` facade modules and use **raw DB-API** (`self.conn.cursor()`, `self.conn.commit()`), which violates rules 1–3.
- Workers (`file_watcher`, `vectorization`, `repair`) open `CodeDatabase(self.db_path)` and therefore access DB directly, violating rule 1.

### Target architecture

```
┌──────────────────────────┐
│  code_analysis server     │
│  (commands, workers, etc) │
└─────────────┬────────────┘
              │ 1. DB operation request
              │ driver_config required
              ▼
┌──────────────────────────┐
│       CodeDatabase        │   (NO .conn, NO db_path)
│  uses BaseDatabaseDriver  │   (driver can be any type)
└─────────────┬────────────┘
              │ 2. Driver API call
              ▼
┌──────────────────────────┐
│   DatabaseDriver          │   (sqlite_proxy, mysql, postgres, etc.)
│   (polymorphic boundary)  │
└─────────────┬────────────┘
              │ 3. RPC call to separate process
              ▼
┌──────────────────────────┐
│   DB Worker Process       │   (separate process)
│   - Receives RPC request  │
│   - Creates job in queue  │
│   - Returns job ID        │
└─────────────┬────────────┘
              │ 4. Job ID returned to driver
              ▼
┌──────────────────────────┐
│   DatabaseDriver          │
│   - Polls job status      │   (async/await, poll_interval from config)
│   - Waits for completion  │   (await asyncio.sleep(poll_interval))
└─────────────┬────────────┘
              │ 5. Result/error returned
              ▼
┌──────────────────────────┐
│   CodeDatabase            │
│   - Returns to client     │   (transparent for client)
└──────────────────────────┘
```

**Architecture flow (for sqlite_proxy):**
1. **Client** → sends DB operation request to `CodeDatabase`
2. **CodeDatabase** → calls driver API method (execute, fetchone, etc.)
3. **Driver** → makes RPC call (**async/await**) to separate DB worker process
4. **DB Worker Process** → creates job in queue (**async/await**), returns job ID to driver
5. **Driver** → polls job status periodically (**async/await** with `await asyncio.sleep(poll_interval)`, poll_interval from config)
6. **Driver** → receives result/error, returns to CodeDatabase
7. **CodeDatabase** → returns result to client (entire async chain is transparent for client)

**CRITICAL**: All operations in steps 3-5 MUST use async/await. No synchronous queue access.

**Key points:**
- Driver can be ANY type (sqlite_proxy, mysql, postgres, etc.) - not tied to SQLite.
- For SQLite: driver → RPC (async/await) → worker process → queue → SQLite file.
- For MySQL/PostgreSQL: driver → remote server → database.
- **CRITICAL**: All driver operations with worker MUST use async/await (async methods).
- Polling interval (poll_interval) MUST be in config (generator + validator).
- NO backward compatibility, NO fallbacks, NO configuration switches.

### Implementation plan (step-by-step)

> Notes:
> - Each step is intended to be a small reviewable diff and should be committed separately.
> - After each code step: run format/lint/mypy and update code_mapper indexes.
> - Avoid files > 350–400 lines; if a file grows, split via MCP split tools.

---

## Step 0 — Remove all backward compatibility and configuration switches

### Objective
**NO configuration switches, NO fallbacks, NO backward compatibility.**
All database access MUST go through driver → worker → database.
Driver can be any type (sqlite, mysql, postgres, etc.) - not tied to specific database.

### Changes
- **File**: `code_analysis/core/config.py`
  - Remove `DatabaseAccessConfig` class completely.
  - Remove `db_access` field from `ServerConfig`.
  - Remove any `worker_only` or `use_proxy` flags.
- **File**: `config.json`
  - Remove `db_access` section completely.

### Acceptance criteria
- No configuration switches for database access mode.
- No fallback mechanisms.
- Driver type is specified explicitly in `driver_config` when creating `CodeDatabase`.

---

## Step 1 — Make `CodeDatabase` driver-only (remove `.conn` contract)

### Objective
Stop exposing raw connection/cursor API. Everything must use driver methods.
**NO backward compatibility, NO fallbacks.**

### Changes
- **File**: `code_analysis/core/database/base.py`
  - **Class**: `CodeDatabase`
    - Remove `self.conn` property completely.
    - Remove `db_path` parameter - only accept `driver_config` (required).
    - Ensure all internal helpers (`_execute`, `_fetchone`, `_fetchall`, `_commit`, `_rollback`)
      are the only allowed query primitives.
- **File**: `code_analysis/core/database/driver_compat.py`
  - **DELETE** this file completely - no compatibility layer needed.

### Acceptance criteria
- `CodeDatabase` accepts only `driver_config` parameter (required).
- No `.conn` property exists.
- Any attempt to access `.conn` raises `AttributeError`.

---

## Step 2 — Migrate `code_analysis/core/database/*` modules to use driver helpers

### Objective
Eliminate all direct cursor/commit calls from the database facade modules.

### Method
For each module: replace `assert self.conn; cursor = self.conn.cursor(); cursor.execute(...); self.conn.commit()`
with calls to `self._execute(...)`, `self._fetchone(...)`, `self._fetchall(...)`, `self._commit()`.

### Files (typical offenders)
- `code_analysis/core/database/projects.py`
- `code_analysis/core/database/files.py`
- `code_analysis/core/database/classes.py`
- `code_analysis/core/database/methods.py`
- `code_analysis/core/database/functions.py`
- `code_analysis/core/database/imports.py`
- `code_analysis/core/database/usages.py`
- `code_analysis/core/database/issues.py`
- `code_analysis/core/database/ast.py`
- `code_analysis/core/database/cst.py`
- `code_analysis/core/database/chunks.py`
- `code_analysis/core/database/content.py`
- `code_analysis/core/database/statistics.py`

### Concrete example (what to change)
- **File**: `code_analysis/core/database/files.py`
  - **Function**: `add_file`
    - Replace cursor+commit usage with:
      - `self._execute("INSERT OR REPLACE ...", params)`
      - then fetch lastrowid via driver primitive:
        - extend `BaseDatabaseDriver.execute` to optionally return metadata
          **OR**
        - add `BaseDatabaseDriver.execute_returning_lastrowid(...)`
      - Standardize across all “insert” helpers.

### Acceptance criteria
- `grep` for `".conn.cursor("` inside `code_analysis/core/database/` returns **zero** matches.
- All unit tests / smoke commands still pass.

---

## Step 3 — Enforce worker-only design: make direct sqlite driver unusable outside worker

### Objective
Guarantee Rule 1 at runtime. **NO configuration switches, NO fallbacks.**

### Changes
- **File**: `code_analysis/core/db_driver/sqlite.py`
  - **Class**: `SQLiteDriver`
    - Add a guard in `connect()`:
      - Check environment variable `CODE_ANALYSIS_DB_WORKER=1`.
      - If not set, raise `RuntimeError` with clear message.
    - DB worker process MUST set env var `CODE_ANALYSIS_DB_WORKER=1`.
- **File**: `code_analysis/core/db_driver/__init__.py`
  - **Function**: `create_driver`
    - If `driver_name == "sqlite"` and not in DB worker (env var check),
      reject creation immediately (log + raise).
    - **NO** configuration checks, **NO** fallbacks.

### Acceptance criteria
- Direct `sqlite` driver can ONLY be created in DB worker process.
- All other code MUST use proxy driver or other database drivers (mysql, postgres, etc.).

---

## Step 4 — Implement RPC-based architecture with polling

### Objective
Implement proper RPC-based architecture with exact flow:
1. **Client** → sends DB operation request to driver
2. **Driver** → makes RPC call (**async/await**) to separate DB worker process
3. **DB Worker Process** → creates job in queue (**async/await**), returns job ID to driver
4. **Driver** → polls job status periodically using job ID (**async/await** with `await asyncio.sleep(poll_interval)`, poll_interval from config)
5. **Driver** → receives result/error, returns to client (transparent chain - client doesn't see async)

**CRITICAL**: Steps 2-4 MUST use async/await. All queue operations MUST be async methods.

### Rationale
Current implementation uses `AsyncQueueSystem` directly, which is fragile.
Proper architecture requires:
- Separate DB worker process (RPC server)
- Driver as RPC client (**MUST use async/await internally**)
- Job ID returned from worker to driver
- Polling with configurable interval (**async/await** with `await asyncio.sleep(poll_interval)`, poll_interval in config)
- Transparent operation for client code (async chain hidden from client)
- **CRITICAL**: All queue operations MUST be async methods: `await add_job()`, `await start_job()`, `await get_job_status()`

### Changes
- **File**: `code_analysis/core/db_driver/sqlite_proxy.py`
  - **Class**: `SQLiteDriverProxy`
    - **CRITICAL**: All driver methods MUST use async/await internally
    - Implement RPC client to communicate with DB worker process
    - RPC call: send operation request → receive job ID (async/await, not direct queue access)
    - Polling: periodically check job status using job ID (async/await with `await asyncio.sleep(poll_interval)`)
    - Return result/error when job completes
    - **All internal operations MUST be async**: `await add_job()`, `await start_job()`, `await get_job_status()`, `await asyncio.sleep(poll_interval)`
    - API is transparent for client (client doesn't need to know about async - wrapped via `_run_async`)
    - Use `poll_interval` from `worker_config` (default: 0.1 seconds = 100ms)
- **File**: `code_analysis/core/db_driver/sqlite_worker.py` (create if missing)
  - Implement RPC server (DB worker process)
  - **CRITICAL**: All RPC handlers MUST be async methods (async/await)
  - Receive RPC requests from driver (async/await)
  - Create job in queue using queuemgr (async/await)
  - Return job ID to driver (not result directly)
- **File**: `code_analysis/core/database/base.py`
  - **Function**: `create_driver_config_for_worker`
    - Add `poll_interval` to `worker_config` (default: 0.1 seconds = 100ms)
    - Document that poll_interval is in seconds
- **File**: `code_analysis/core/config_generator.py`
  - Note: `poll_interval` is set dynamically via `create_driver_config_for_worker()` function
  - If config generator creates example driver configs, include `poll_interval` in `worker_config`
  - Default value: 0.1 seconds (100ms)
- **File**: `code_analysis/core/config.py` (if needed for validation)
  - Document poll_interval in driver worker config structure
  - Validate poll_interval > 0 if present

### Acceptance criteria
- **CRITICAL**: All driver methods use async/await internally (no synchronous queue access)
- Driver makes RPC call to separate process (async/await, not direct queue access)
- DB worker process creates job in queue and returns job ID (async/await, not result)
- Driver polls job status using job ID with configurable interval (async/await with `await asyncio.sleep(poll_interval)`, poll_interval from config)
- All queue operations use async/await: `await add_job()`, `await start_job()`, `await get_job_status()`
- `poll_interval` is included in config generator (default: 0.1 seconds)
- `poll_interval` is validated in config validator (must be > 0)
- Client code sees transparent API (entire async chain is hidden from client via `_run_async` wrapper)
- All operations work reliably under load.

---

## Step 5 — Introduce a dedicated DB worker process (single writer) and route all DB ops through it

### Objective
Make DB worker the only owner of sqlite3 connection.

### Changes
- **File**: `code_analysis/core/db_driver/sqlite_worker_job.py`
  - Keep as job executor OR evolve to persistent-connection worker (recommended for performance).
  - Ensure structured error results:
    - `{"success": False, "error": {"type": "...", "message": "...", "sql": "...", "params": ...}}`
- **File**: `code_analysis/core/db_driver/sqlite_worker.py` (create if missing)
  - Create DB worker process entrypoint.
  - Set env `CODE_ANALYSIS_DB_WORKER=1`.
  - Own sqlite3 connection.
  - Serialize all operations from queue.

### Acceptance criteria
- `grep` for `sqlite3.connect(` in `code_analysis/` yields only:
  - DB worker implementation + db_integrity checker.

---

## Step 6 — Migrate all workers to driver-only access (no `CodeDatabase(db_path)` with direct sqlite)

### Objective
Workers must not touch sqlite3 directly; they must use proxy driver or other database drivers.
**NO backward compatibility, NO fallbacks.**

### Changes
- **File**: `code_analysis/core/file_watcher_pkg/base.py`
  - **Class**: `FileWatcherWorker.run`
    - Replace `database = CodeDatabase(self.db_path)` with:
      - `CodeDatabase(driver_config=create_driver_config_for_worker(self.db_path))`
      - Use `create_driver_config_for_worker()` helper function.
- **File**: `code_analysis/core/vectorization_worker_pkg/processing.py`
  - Replace `CodeDatabase(self.db_path)` with `CodeDatabase(driver_config=create_driver_config_for_worker(self.db_path))`.
- **File**: `code_analysis/core/repair_worker_pkg/base.py`
  - Replace `CodeDatabase(self.db_path)` with `CodeDatabase(driver_config=create_driver_config_for_worker(self.db_path))`.

### Acceptance criteria
- All workers use `driver_config` parameter only.
- No worker imports `sqlite3` or uses `.conn.cursor()`.
- Workers can use any database driver type (sqlite_proxy, mysql, postgres, etc.).

---

## Step 7 — Migrate server commands to driver-only access

### Objective
MCP commands must only use driver API and must not access `.conn`.

### Changes
- **File**: `code_analysis/commands/base_mcp_command.py`
  - Replace any `.conn.cursor()` usage for “empty DB checks” with driver `_fetchone`.
- **Files**: `code_analysis/commands/ast/*`, `code_analysis/commands/search_mcp_commands.py`, etc.
  - Remove `.conn` usage (if any) and use `CodeDatabase` methods (which are driver-backed after Step 2).

### Acceptance criteria
- `grep` for `.conn.cursor(` under `code_analysis/commands/` returns **zero** matches.

---

## Step 8 — Error model & logging standardization

### Objective
All driver/worker errors are logged and surfaced consistently.

### Changes
- **File**: `code_analysis/core/exceptions.py`
  - Add `DatabaseOperationError` with fields:
    - `operation`, `db_path`, `sql`, `params`, `root_dir`, `timeout`, `cause`.
- **File**: `code_analysis/core/db_driver/sqlite_proxy.py`
  - Catch:
    - queuemgr control errors/timeouts,
    - worker errors,
    - decode/serialization errors,
  - Log at appropriate levels with structured context.
- **File**: `code_analysis/core/db_driver/sqlite_worker_job.py` / `sqlite_worker.py`
  - Log SQL/operation with safe truncation (avoid logging huge payloads).
  - Return structured error to proxy driver.

### Acceptance criteria
- One consistent error format across MCP responses (ErrorResult details include operation + db_path).
- “database is locked” and other temporary errors are handled without corrupting marker state.

---

## Step 9 — Tests + enforcement checks

### Objective
Prevent regressions: no direct DB access, no backward compatibility.

### Changes
- **New tests**: `tests/test_db_worker_only.py`
  - Assert that:
    - creating `SQLiteDriver` outside worker raises `RuntimeError`;
    - `CodeDatabase(db_path)` is forbidden (only `driver_config` allowed);
    - `CodeDatabase` without `driver_config` raises `ValueError`;
    - core commands can run basic SELECT via proxy driver;
    - other database drivers (mysql, postgres) can be used.
- Add a CI-style grep test:
  - Fail if `.conn.cursor(` exists anywhere (except DB worker).
  - Fail if `sqlite3.connect(` exists outside DB worker and db_integrity.
  - Fail if `CodeDatabase(db_path=` exists (must use `driver_config`).

### Acceptance criteria
- Tests cover the "worker-only" invariant.
- Tests verify no backward compatibility exists.
- Lint/mypy/black are clean.

---

## Step 10 — Cleanup / removal of all compatibility

### Objective
Remove ALL legacy paths, ALL compatibility layers, ALL fallbacks.

### Changes
- Delete `code_analysis/core/database/driver_compat.py` completely.
- Remove any `db.conn` usage in codebase.
- Remove `DatabaseAccessConfig` from config.
- Remove all `worker_only` and `use_proxy` flags.
- Ensure `CodeDatabase` accepts ONLY `driver_config` parameter.

### Acceptance criteria
- Only DB worker owns sqlite3 connection (for sqlite driver).
- All code calls DB through driver API only.
- No configuration switches for database access.
- Any database driver type can be used (sqlite, mysql, postgres, etc.).
- Driver is not tied to specific database implementation.


