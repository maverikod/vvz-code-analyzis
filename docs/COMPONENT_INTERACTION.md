# Component Interaction

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

This document describes how the main components of the code-analysis server interact: MCP entry point, command registration, database driver, workers, and core services.

---

## 1. Entry and Configuration

- **Entry**: `code_analysis/main.py` parses CLI (e.g. `--config`, `--daemon`, `--host`, `--port`), loads and validates config via `CodeAnalysisConfigValidator`, then uses `AppFactory` / `ServerEngineFactory` from `mcp_proxy_adapter` to run the server.
- **Config**: Paths and settings come from config file and `SettingsManager` (`core/settings_manager.py`); storage paths from `core/storage_paths.py` (e.g. DB, FAISS, logs).
- **Hooks**: `code_analysis/hooks.py` is imported from `main`; it registers all commands with the MCP proxy’s registry via `register_code_analysis_commands(reg)` and registers auto-import modules for spawn mode.

---

## 2. MCP Request → Command Execution

1. **MCP proxy** receives a tool call and dispatches it to the code-analysis server.
2. **Registry**: The server uses the registry populated by `register_code_analysis_commands`. Each command class (e.g. `GetASTMCPCommand`) is registered under a name (e.g. `get_ast`).
3. **Command instance**: The framework instantiates the command class and invokes its execution (e.g. run with params from the tool call).
4. **BaseMCPCommand**: Most commands extend `BaseMCPCommand` (`commands/base_mcp_command.py`), which:
   - Resolves config path and opens/checks DB (including SQLite integrity check),
   - Resolves project_id / project root (e.g. from `project_id` or `root_path`),
   - Validates paths and files,
   - Handles errors and returns a consistent response shape.
5. **Database access**: Commands that need DB either use a **direct** `CodeDatabase` (when server and DB run in the same process) or a **DatabaseClient** (RPC) when the DB runs in a separate driver process.
6. **Response**: Command returns a result (e.g. success + data or error); the MCP layer serializes it back to the client.

---

## 3. Database and Driver

- **CodeDatabase** (`core/database/`): Central DB abstraction. Methods are attached from modules (projects, files, ast, cst, entities, chunks, etc.). Used when the server process holds the SQLite DB.
- **Database driver process**: When enabled, the DB runs in a separate process. `DatabaseDriverManager` / `db_worker_pkg` start and stop this process. The driver runs an RPC server (`database_driver_pkg/rpc_server.py`) that handles:
   - Schema (create_table, sync_schema, get_table_info),
   - Transactions (begin, commit, rollback),
   - CRUD (insert, update, delete, select, execute),
   - AST/CST query and modify (handlers in `rpc_handlers_*.py`).
- **DatabaseClient** (`core/database_client/`): RPC client that sends requests to the driver and parses responses. Command code uses this client when the driver is in use, so that all DB access goes over RPC.
- **Integrity**: Before opening DB, `BaseMCPCommand` (or startup) can run `_ensure_database_integrity` (backed by `core/db_integrity.py`); on corruption, DB may be backed up and recreated.

---

## 4. Workers

- **WorkerManager** (`core/worker_manager.py`): Single point to start/stop workers and the database driver. It uses:
  - **WorkerRegistry**: Registers worker types (e.g. file_watcher, vectorization), PID/lock files, status.
  - **WorkerLifecycleManager**: Starts/stops specific worker types (e.g. file_watcher_worker, vectorization_worker).
  - **DatabaseDriverManager**: Starts/stops the DB driver process.
- **Worker monitor**: `WorkerMonitor` periodically checks worker health and can restart them; started/stopped via WorkerManager.
- **File watcher**: Scans registered project roots, detects file changes, and enqueues work (e.g. re-indexing). Can call `UpdateIndexesMCPCommand` or equivalent after changes.
- **Vectorization worker**: Processes chunks (e.g. from `chunks` table), computes embeddings, updates FAISS index and DB (vector_id, embedding_model).
- **Repair worker**: Separate process for repair tasks; controlled by repair_worker MCP commands (start/stop/status) and repair worker management in core.

Interaction: **Project management commands** (e.g. create_project) register projects and watch dirs; **worker_management** commands (start_worker/stop_worker) start/stop file_watcher and vectorization; **worker_status** and **log_viewer** commands report status and logs.

---

## 5. Command → Core Dependencies

- **AST commands**: Use `CodeDatabase` or client methods for AST (query, get, list); some use core analyzers (e.g. usage_tracker, complexity_analyzer).
- **CST commands**: Use `core/cst_tree/` and `core/cst_module/` for build/save/load/modify; DB access for CST via database/cst or client.
- **Project management**: Use `ProjectManager`, `CreateProjectCommand`/`DeleteProjectCommand` (in commands), and DB projects/watch_dirs.
- **Backup**: Use `BackupManager` (`core/backup_manager.py`) for file backup/restore.
- **Code quality**: Use `core/code_quality/` (formatter, linter, type_checker).
- **Refactor**: Use `core/refactorer_pkg/` (extractor, splitter, file_splitter, validators).
- **Vector**: Use `FaissIndexManager`, `vectorization_helper`, and DB chunks; revectorize/rebuild_faiss commands drive re-indexing and FAISS rebuild.
- **Analysis**: Complexity, duplicates, and comprehensive analysis use `ComplexityAnalyzer`, `DuplicateDetector`, `ComprehensiveAnalyzer`; semantic search uses vector index and optional SVO client.

---

## 6. Data Flow Summary

- **Client (MCP)** → **Server (main)** → **Registry** → **Command (e.g. BaseMCPCommand)** → **CodeDatabase or DatabaseClient** → **SQLite / driver process**.
- **File watcher** → file change → **UpdateIndexes** (or similar) → **CodeDatabase** (files, AST, entities, chunks).
- **Vectorization worker** → chunks without vectors → embeddings → **FaissIndexManager** + DB update.
- **Repair worker** → started/stopped by repair_worker commands; may run DB repair or other maintenance.

For per-command behavior and parameters, see `docs/commands/<block>/COMMANDS.md` and the schema returned by each command’s `get_schema()` (and `metadata()`).
