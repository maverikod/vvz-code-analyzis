## Refactor Plan: Database access only via DB worker + driver

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

### Goal / Non‑negotiable rules

- **Rule 1**: Only the **DB worker** may access SQLite directly (`sqlite3.connect`, cursors, commits).
- **Rule 2**: Only the **database driver** may talk to the DB worker (IPC/queue/RPC).
- **Rule 3**: **All** DB calls in the codebase must go through the **driver API** only (no `db.conn`, no `cursor = ...`).
- **Rule 4**: Errors must be **logged** with enough context and be **handled** consistently (typed errors, safe fallbacks, no silent failures).
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
              │ DB operations (ALL)
              ▼
┌──────────────────────────┐
│       CodeDatabase        │   (no .conn exposure)
│  uses BaseDatabaseDriver  │
└─────────────┬────────────┘
              │ IPC only (driver ↔ worker)
              ▼
┌──────────────────────────┐
│     SQLiteDriverProxy     │   (ONLY component that talks to worker)
└─────────────┬────────────┘
              │ jobs/messages
              ▼
┌──────────────────────────┐
│     DB Worker process     │   (ONLY component that touches sqlite3)
│  owns sqlite3 connection  │
└─────────────┬────────────┘
              ▼
          SQLite file
```

### Implementation plan (step-by-step)

> Notes:
> - Each step is intended to be a small reviewable diff and should be committed separately.
> - After each code step: run format/lint/mypy and update code_mapper indexes.
> - Avoid files > 350–400 lines; if a file grows, split via MCP split tools.

---

## Step 0 — Lock in “strict mode” configuration (scaffolding)

### Objective
Introduce an explicit server setting that enables the strict model:
**no direct sqlite connections anywhere except DB worker**.

### Changes
- **File**: `code_analysis/core/config.py` (or wherever ServerConfig lives)
  - Add a boolean flag, e.g. `db_access.worker_only: bool = True`.
  - Document defaults in docstring.
- **File**: `config.json`
  - Add:
    - `code_analysis.db_access.worker_only = true`
    - (optional) `code_analysis.db_access.driver = "sqlite_proxy"`

### Acceptance criteria
- Config loads with defaults.
- Flag is accessible from runtime (server + workers).

---

## Step 1 — Make `CodeDatabase` driver-only (remove `.conn` contract)

### Objective
Stop exposing raw connection/cursor API. Everything must use driver methods.

### Changes
- **File**: `code_analysis/core/database/base.py`
  - **Class**: `CodeDatabase`
    - Remove `self.conn` exposure (or keep it only during transition behind feature flag).
    - Ensure all internal helpers (`_execute`, `_fetchone`, `_fetchall`, `_commit`, `_rollback`)
      are the only allowed query primitives.
    - Add explicit logging when legacy `.conn` is accessed (temporary) to find offenders.
- **File**: `code_analysis/core/database/driver_compat.py`
  - Mark as **temporary** and plan deletion once migration completes.
  - Do not use it in production strict mode.

### Acceptance criteria
- In strict mode, any access to `db.conn` fails fast with a clear error.
- In non-strict mode, existing code still runs while we migrate modules.

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

## Step 3 — Enforce “worker_only” by design: make direct sqlite driver unusable outside worker

### Objective
Guarantee Rule 1 at runtime.

### Changes
- **File**: `code_analysis/core/db_driver/sqlite.py`
  - **Class**: `SQLiteDriver`
    - Add a guard in `connect()`:
      - if strict mode is enabled and environment does not indicate DB worker context,
        raise a `DatabaseError` (or `RuntimeError`) with guidance.
    - DB worker process should set an env var, e.g. `CODE_ANALYSIS_DB_WORKER=1`.
- **File**: `code_analysis/core/db_driver/__init__.py`
  - **Function**: `create_driver`
    - If strict mode enabled and driver_name resolves to `"sqlite"` without proxy,
      reject creation (log + raise).

### Acceptance criteria
- Starting server in strict mode cannot open direct sqlite connections.
- DB worker can (has env var).

---

## Step 4 — Replace current queuemgr usage with a server-safe synchronous driver client

### Objective
Make the proxy driver safe in sync contexts (server request handlers) without event-loop hacks.

### Rationale
The current `SQLiteDriverProxy` uses `AsyncQueueSystem` and creates/joins event loops/threads.
This is fragile inside a web server and previously caused timeouts.

### Changes
- **File**: `code_analysis/core/db_driver/sqlite_proxy.py`
  - **Class**: `SQLiteDriverProxy`
    - Replace `AsyncQueueSystem` usage with a **synchronous queue client** (from queuemgr’s sync API),
      or implement a single long-lived background queue controller created once at startup.
    - Ensure:
      - no per-call event loop creation;
      - driver methods are pure sync;
      - timeouts are configurable and logged.
- **File**: `code_analysis/core/worker_manager.py`
  - Register DB worker (and queue system if applicable) as a managed worker type, e.g. `db_worker`.

### Acceptance criteria
- `get_database_status` and other non-queued MCP commands work reliably under load.
- Proxy driver logs: operation name, duration, timeout, and root_dir/db_path.

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
Workers must not touch sqlite3 directly; they must use proxy driver.

### Changes
- **File**: `code_analysis/core/file_watcher_pkg/base.py`
  - **Class**: `FileWatcherWorker.run`
    - Replace `database = CodeDatabase(self.db_path)` with:
      - `CodeDatabase(driver_config={"type": "sqlite", "config": {"path": str(self.db_path), "use_proxy": True, ...}})`
- **File**: `code_analysis/core/vectorization_worker_pkg/processing.py`
  - Replace `CodeDatabase(self.db_path)` similarly.
- **File**: `code_analysis/core/repair_worker_pkg/base.py`
  - Replace `CodeDatabase(self.db_path)` similarly.

### Acceptance criteria
- Workers run with strict mode enabled.
- No worker imports `sqlite3` or uses `.conn.cursor()`.

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
Prevent regressions: no direct DB access.

### Changes
- **New tests**: `tests/test_db_worker_only.py`
  - Assert that in strict mode:
    - creating `SQLiteDriver` outside worker raises;
    - `CodeDatabase(db_path)` uses proxy (or is forbidden if direct);
    - core commands can run basic SELECT via proxy.
- Add a CI-style grep test:
  - Fail if `.conn.cursor(` exists outside DB worker and test helpers.
  - Fail if `sqlite3.connect(` exists outside DB worker and db_integrity.

### Acceptance criteria
- Tests cover the “worker-only” invariant.
- Lint/mypy/black are clean.

---

## Step 10 — Cleanup / removal of transitional compatibility

### Objective
Remove remaining legacy paths.

### Changes
- Delete `code_analysis/core/database/driver_compat.py` (or keep only for tests).
- Remove any `db.conn` usage in codebase.
- Make `worker_only` mode the default.

### Acceptance criteria
- Only DB worker owns sqlite3 connection.
- All code calls DB through driver API only.


