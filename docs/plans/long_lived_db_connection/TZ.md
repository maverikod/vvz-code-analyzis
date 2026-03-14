# TZ: One Long-Lived Database Connection (Server Process)

**Author:** Vasiliy Zdanovskiy  
**email:** vasilyvz@gmail.com

**Status:** Source of truth for the plan. All steps must comply with this TZ.

---

## 1. Goal

There MUST be **one long-lived connection** to the database (RPC client to the driver process) in the **process that serves MCP commands** (the HTTP server process). It MUST be **opened at process startup** and **closed at process shutdown**. No per-command open/close cycle.

---

## 2. Scope

- **In scope:** The **HTTP server process** (Hypercorn) that runs MCP command handlers. All MCP commands that currently call `_open_database_from_config()`, `_open_database()`, or construct `DatabaseClient(...)` and `.connect()` MUST use the shared long-lived connection instead. Commands MUST NOT call `database.disconnect()` on the shared connection (disconnect MUST be no-op when using the shared client).
- **Out of scope:** Worker processes (file_watcher, indexing, vectorization) run in **separate processes**; they keep their current connect/disconnect behaviour. The **database driver process** is unchanged; only the **client side** in the server process is changed.

---

## 3. Analysis of Current Code

### 3.1 Entry point for opening the database

- **`open_database_from_config_impl()`** in `code_analysis/commands/base_mcp_command_open_db.py` is the single implementation. It is called only via:
  - **`BaseMCPCommand._open_database_from_config()`** in `code_analysis/commands/base_mcp_command.py` (static method).
  - **`BaseMCPCommand._open_database()`** in the same file (instance method that delegates to `_open_database_from_config`).

Each call to `open_database_from_config_impl()` currently does:

1. `resolve_config_path()` → load config, `resolve_storage_paths()` → `db_path`, `ensure_storage_dirs(storage)`.
2. **`ensure_database_integrity(db_path)`** — separate `sqlite3` connection to the file, `PRAGMA quick_check(1)` (timeout up to 2s on lock).
3. **`DatabaseClient(socket_path)`** + **`db.connect()`** — new RPC client, pre-fill socket pool (retries up to `startup_connect_timeout` e.g. 5s).
4. **Probe 1:** `db.select("projects", columns=["id"], limit=1)`; on "no such table" → `sync_schema()` then retry.
5. **Probe 2:** `db.select("code_content_fts", columns=["rowid"], limit=1)`; on "no such table" → `sync_schema()`.
6. Return `db`.

So every command pays: integrity check (up to ~2s), connect (up to ~5s after restart), two probe selects. Then the command uses `db` and typically calls `database.disconnect()` in `finally`.

### 3.2 Call sites (MCP command path only)

All of the following run in the **server process** and MUST use the long-lived connection instead of opening a new one:

- **Via `_open_database_from_config(auto_analyze=False)` or `_open_database()`:**  
  `list_projects`, `create_project`, `delete_unwatched_projects`, `list_deleted_files`, `cleanup_deleted_files`, `collapse_versions`, `restore_deleted_files`, `unmark_deleted_file`, `delete_file`, `repair_database`, `get_database_status`, `list_indexing_errors`, `get_worker_status`, `start_repair_worker`, `update_indexes` (metadata), `code_mapper` (list errors, etc.), `cst_load_file`, `cst_save_tree`, `cst_create_file`, `cst_convert_and_save`, `cst_modify_tree`, `cst_compose_module`, `get_file_lines`, `replace_file_lines`, `format_code`, `get_ast`, `list_files`, `dependencies`, `search_mcp_commands_fulltext`, `search_mcp_commands_find_classes`, `search_mcp_commands_list_class_methods`, `semantic_search_mcp`, `find_duplicates_mcp`, `analyze_complexity_mcp`, `comprehensive_analysis_mcp`, `vector_commands/rebuild_faiss`, `vector_commands/revectorize`, `change_project_id`, `database_restore_mcp_commands`, and all AST/refactor commands that use `_open_database()` or `_open_database_from_config()`.

- **Via direct `DatabaseClient(socket_path)` + `.connect()` (MUST be refactored to use shared connection):**  
  `delete_project.py`, `list_watch_dirs.py`, `permanently_delete_from_trash.py`, `clear_trash.py`, `restore_project_from_trash.py`.  
  (`worker_status.py` and `format_code_command.py` also create or use DB — ensure they use shared connection when run in the server process; if they are only used from CLI/scripts, document that.)

- **Compose/flows that call command’s open and then disconnect:**  
  `compose_cst_tree_flow.py`, `compose_cst_ops_flow.py`, `query_cst_handler.py` — they call `command._open_database_from_config(...)` and later `database.disconnect()`. They MUST receive the shared client from the same mechanism; `disconnect()` on the shared client MUST be a no-op.

### 3.3 Startup / shutdown

- **Startup:** `code_analysis/main_app_events.py` — `register_startup_shutdown_events()` registers `@app.on_event("startup")` which runs `_start_workers_bg()` in a background thread: `startup_database_driver()` then indexing, vectorization, file_watcher. The **database driver process** is started first; the HTTP server process does not open any DB client there.
- **Shutdown:** `@app.on_event("shutdown")` calls `worker_manager.stop_all_workers(timeout=...)`. There is no “close shared DB connection” step today.

So: the **process that serves the DB** (in the sense of “process that serves MCP requests and talks to the DB”) is the **HTTP server process**. That process must get one long-lived `DatabaseClient` (or equivalent) at startup and close it at shutdown.

### 3.4 Where the shared connection must live

- Commands are invoked by the adapter (or HTTP route); the command class does not receive `app` or `request` by default. So the shared client cannot be passed only via `app.state` without also providing a way for command code to access it. The reliable approach is a **dedicated module** in code_analysis that holds the shared client (or a proxy) and is set at startup and cleared at shutdown. Commands (and compose flows) call a function such as **`get_shared_database()`** that returns that client. If the shared client is not initialized (e.g. startup failed or shutdown in progress), `get_shared_database()` MUST raise a defined error (no silent fallback to “open new connection”).
- To avoid changing every command’s `finally: database.disconnect()`, the object returned by `get_shared_database()` MAY be a **proxy** that forwards all methods to the real `DatabaseClient` except **`disconnect()`**, which is a **no-op**. Then existing `database.disconnect()` in command code does not close the shared connection.

### 3.5 Integrity and probe

- **Integrity:** `ensure_database_integrity(db_path)` MUST run **once per server startup** (e.g. when establishing the long-lived connection). If it fails (DB corrupted / safe mode): **log the error and stop** (abort startup; the server MUST NOT continue). No per-command integrity check.
- **Probe selects and sync_schema:** The two probe selects (and any `sync_schema`) MUST run **once** when the long-lived connection is created at startup. They MUST NOT run on every command.

### 3.6 Order of operations

- **Startup:** 1) Start database driver process (existing). 2) Resolve config and paths. 3) `ensure_database_integrity(db_path)`; **if not OK → log and stop** (abort startup). 4) Create `DatabaseClient(socket_path)`, `db.connect()`; **if connect fails → log and stop**. 5) Run probe selects (and `sync_schema` if needed); **if probe fails → log and stop**. 6) Store the client (or a no-op-disconnect proxy) in the shared holder. This MUST happen in the same process as the one that will run MCP commands (e.g. in the startup event, after or together with driver start). **Any error during steps 3–5: write to log and stop (do not continue server startup).** The long-lived connection MUST be set (`set_shared_database`) **before** the server process starts accepting HTTP/MCP requests. If the DB open runs in a background thread, the startup handler MUST wait for that thread to complete (or for a readiness signal) before returning; do not return from startup while shared_database is still unset.
- **Shutdown:** 1) Close the shared connection (disconnect the real client). 2) Clear the holder. Order relative to `stop_all_workers`: close shared DB connection **before** stopping workers so that in-flight command requests can finish using the connection; then stop workers. (If the TZ is updated to close after workers, document the reason.)

---

## 4. Requirements (must)

- One long-lived `DatabaseClient` (or equivalent) in the HTTP server process, opened at startup and closed at shutdown.
- All MCP commands in that process use this connection (via `get_shared_database()` or equivalent); no per-command `open_database_from_config_impl()` and no per-command `DatabaseClient(...).connect()`.
- Commands MUST NOT close the shared connection; any existing `database.disconnect()` in command code MUST become a no-op when the command is using the shared client (e.g. via proxy).
- Integrity check and probe selects run once at startup when creating the long-lived connection; they do not run per command.
- **On startup, if any error is detected** (integrity failure, connect failure, or probe failure): **write to log and stop** (abort startup; the server MUST NOT continue serving).
- No fallback: if the shared connection is not available, `get_shared_database()` MUST raise; no “fallback to opening a new connection” for the command path in the server process.
- Workers (file_watcher, indexing, vectorization) are out of scope: they remain in separate processes with their current connect/disconnect behaviour.

---

## 5. Constraints

- Do not change the database driver process or RPC protocol.
- Do not change the signature of command `execute()`/`run()` in a way that breaks the adapter (e.g. do not require new parameters for “get DB”); commands obtain the DB via a shared accessor (e.g. `get_shared_database()` or `BaseMCPCommand._open_database_from_config()` delegating to it).
- Preserve safe-mode behaviour: if integrity fails at startup, **log and stop** (abort startup); the server MUST NOT run with a corrupted or unavailable DB.

---

## 6. Forbidden alternatives

- Do not add a “per-request” or “per-command” connection pool that opens/closes connections for each command. Requirement is exactly one long-lived connection.
- Do not leave any MCP command in the server process opening its own connection via `open_database_from_config_impl()` or `DatabaseClient(...).connect()` for normal execution.
- Do not run `ensure_database_integrity()` or the two probe selects on every command.
- Do not add backward-compatibility fallback “if shared not set, open new connection” for the MCP command path in the server process.

---

## 7. Validation (definition of done)

- After implementation, a single server startup MUST create exactly one RPC client connection to the driver (one `DatabaseClient` and one `connect()` in the server process for the shared connection).
- Each MCP command execution in that process MUST use that same client (no new `connect()` per command).
- Server shutdown MUST close that client exactly once (`disconnect()` on the real client).
- Full test suite (e.g. `pytest`) MUST pass. Step/plan completion is valid only when the test suite is green.

---

## 8. References

- Entry: `code_analysis/commands/base_mcp_command_open_db.py` — `open_database_from_config_impl`
- Entry: `code_analysis/commands/base_mcp_command.py` — `_open_database_from_config`, `_open_database`
- Startup: `code_analysis/main_app_events.py` — `register_startup_shutdown_events`
- Config/paths: `code_analysis/core/storage_paths.py`, `code_analysis/commands/base_mcp_command.py` — `_resolve_config_path`
- Client: `code_analysis/core/database_client/client.py` — `DatabaseClient`
- Integrity: `code_analysis/commands/base_mcp_command_open_db.py` — `ensure_database_integrity`; `code_analysis/core/db_integrity.py` — `check_sqlite_integrity`

---

## 9. Decision rules (if X then Y)

- If the executor is unsure whether to open a new connection or use shared → use shared only; never open a new connection for the MCP command path in the server process.
- If integrity fails at startup → log (logging.error or equivalent) and abort (raise exception or sys.exit so the server process does not serve requests); do not set shared_database.
- If connect() or probe fails at startup → same: log and abort; do not set shared_database.
- If a test runs in isolation and fails because get_shared_database() is not set → the test must set up shared_database in setup/fixture or be skipped for that context; do not add a fallback "open new connection" in production code.
- If Step 04 (extract open once) is not yet implemented when doing Step 02 → call existing open_database_from_config_impl() from base_mcp_command_open_db with BaseMCPCommand._resolve_config_path and _get_socket_path_from_db_path to obtain the client, then set_shared_database(that_client_or_proxy). On any exception from that call → log and abort.

---

## 10. Executor handoff (instructions for Llama-level model)

1. **Before writing any code:** Read this TZ in full, then [PLAN.md](PLAN.md), then [PARALLEL_CHAINS.md](PARALLEL_CHAINS.md). Then open the step file for the step you are executing (e.g. `steps/step_01_shared_database_module.md`) and read every file listed in that step’s "Read first" in full.
2. **Order of execution:** Execute steps **01, 02, 03, 04** in that order. Then execute steps **05, 06, 07, 08, 09** in any order (they are independent). Do not skip steps. Do not change the target file of a step to a different file.
3. **Per step:** Implement only what is written in the step’s "Expected file change" and "Atomic operations". Do not add features not listed. Respect "Forbidden alternatives" and "Blackstops". If a blackstop condition is met, stop and report.
4. **After each step:** Run the step’s "Mandatory validation" exactly: from the **project root** (repository root), activate `.venv` if present, then run `black <target_file>`, `flake8 <target_file>`, `mypy <target_file>`, and `pytest`. The step is **not complete** until all tests pass. Fix any failures before proceeding.
5. **No alternatives:** Do not implement a connection pool, per-command open, or fallback "if shared not set then open new connection". The architecture is fixed by this TZ.
