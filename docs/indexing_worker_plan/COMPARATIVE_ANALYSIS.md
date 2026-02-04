# Indexing Worker Plan — Comparative Analysis

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

This document compares the plan (step files in this directory) with the current application structure, database schema, and codebase to ensure the plan is complete and consistent.

---

## 1. Application and database structure vs plan

### 1.1 Database schema (relevant parts)

- **files**: has **one** flag for background work: `needs_chunking` (INTEGER DEFAULT 0); also `path`, `project_id`, `deleted` (soft delete, separate semantics). Indexer and vectorization both use `needs_chunking` (no separate `needs_indexing`); to avoid conflicts, indexer must run before vectorization (see 99_ORDER_RISKS_CRITERIA §0).
- **code_content** and **code_content_fts**: filled by `update_file_data` / `add_code_content`; plan correctly states that the indexing worker will refresh these via the new RPC (same effect as `update_file_data`).
- **projects**: has `root_path`; the driver obtains project root from the DB when needed. There is **no** `root_dir` parameter in the RPC; watch directories and projects define the structure.
- **vectorization_stats** / **file_watcher_stats**: exist for other workers; the plan **mandates** an **indexing_worker_stats** table and defines which commands must use it (get_worker_status when `worker_type == "indexing"`, and any dashboard that shows all workers).

### 1.2 Core package layout

| Plan component | Current codebase | Match |
|----------------|------------------|--------|
| Phase A: driver RPC | `database_driver_pkg`: `rpc_server.py` has `handler_map`; handlers in `rpc_handlers*.py` mixins; no "index_file" yet | Plan is correct; implementation must add a new handler mixin and register `"index_file"` in `handler_map`. |
| Phase A: DatabaseClient | `database_client`: `client.py` composes mixins; `client_api_files.py` for file ops; `client_operations.py` uses `rpc_client.call(method, params)` | Plan is correct; add `index_file()` in a mixin (e.g. `client_api_files` or new `client_api_indexing`) and call `rpc_client.call("index_file", params)`. |
| Phase B: indexing_worker_pkg | `vectorization_worker_pkg` has `base`, `processing`, `runner`; also `batch_processor`, `chunking`, `watch_dirs`. Indexing needs no SVO/FAISS. | Plan correctly limits to `base`, `processing`, `runner`; no extra modules required. |
| Phase C: WorkerLifecycleManager | `worker_lifecycle.py`: has `start_vectorization_worker`, `start_file_watcher_worker`; takes db_path, poll_interval, batch_size, worker_log_path, worker_logs_dir (vectorization also faiss_dir, svo_config). | Plan is correct; `start_indexing_worker` will have a smaller parameter set (no faiss_dir, svo_config). |
| Phase C: WorkerManager | `worker_manager.py` delegates to `_lifecycle.start_*_worker`. | Plan is correct. |
| Phase C: WorkerRegistry / stop | `worker_registry.py`: `get_workers(worker_type)`, `stop_worker_type(worker_type)`; type is a string. | Plan is correct; adding `"indexing"` is just using this string. |
| Phase C: main.py | `main.py`: `startup_vectorization_worker()`, `startup_file_watcher_worker()`; called after driver is ready. | Plan is correct; add `startup_indexing_worker()` in the same startup block. |
| Phase D: MCP | `worker_management_mcp_commands.py`: enum `["file_watcher", "vectorization"]`; `worker_status_mcp_commands.py`: same enum. | Plan is correct; both must be extended with `"indexing"`. |

### 1.3 Data flow (current vs planned)

- **Current**: File watcher sets `needs_chunking = 1` (via raw UPDATE in `file_watcher_pkg/processor.py`); vectorization worker discovers files via `get_files_needing_chunking` (docstrings + no chunks or needs_chunking); `update_file_data` is used only by refactor/file_management/splitter and manual `update_indexes`, not by any background worker.
- **Planned**: Indexing worker discovers files with `needs_chunking = 1` only (simpler query than vectorization); calls driver RPC `index_file`; driver performs same logic as `update_file_data` and clears `needs_chunking` after success. Vectorization continues to use its existing discovery (unchanged).

Structure and data flow in the plan are consistent with the application and database.

---

## 2. Code vs plan

### 2.1 Where `update_file_data` lives and who uses it

- **Definition**: `code_analysis/core/database/files.py` — `update_file_data(self, file_path, project_id, root_dir)`. It is attached to `CodeDatabase` via `_add_functions_as_methods` in `database/__init__.py`. (When called from the driver, `root_dir` is derived from `projects.root_path` in the DB; the RPC does not take `root_dir`.)
- **Callers**: refactorer (file_splitter, splitter, extractor), tree_saver (via `update_file_data_atomic`), manual update_indexes path, and the new driver RPC `index_file`. The driver reuses the same app logic (same interaction pattern as the vectorization worker’s use of the driver).

### 2.2 Driver process capabilities

- **RPC server** (`rpc_server.py`): dispatches by `request.method`; uses `handler_map` for methods that do not use Request classes (e.g. `query_ast`, `execute`). Handler receives `params` dict and returns a `BaseResult` (e.g. `SuccessResult`, `ErrorResult`).
- **Handlers**: Implemented as mixins in `rpc_handlers_*.py`; composed in `rpc_handlers.py` as `RPCHandlers`. Adding `index_file` requires a new mixin (e.g. `_RPCHandlersIndexFileMixin`) with `handle_index_file(self, params)` and registering `"index_file": self.handlers.handle_index_file` in `rpc_server._process_request`.
- **Driver**: `SQLiteDriver` in `drivers/sqlite.py` has `self.conn` and low-level operations. The new handler implements `index_file` in the same way as other driver RPCs: reuses existing app logic so behaviour is identical to the rest of the application. No `root_dir` is passed; project root comes from `projects.root_path` in the DB.

### 2.3 Discovery query (B.2) and client API

- **Plan B.2**: Projects with at least one file with `needs_chunking = 1`; per project, `SELECT id, path, project_id FROM files ... needs_chunking = 1 ...`; call `index_file(path, project_id)` with no `root_dir` (path from `files.path`, project root from DB when needed). Flag process: select files with `needs_chunking = 1`, process, then reset flag to 0 on success.
- **Code**: `DatabaseClient` has `execute(sql, params)` and `get_project(project_id)`. Efficient discovery: first `execute("SELECT DISTINCT project_id FROM files WHERE (deleted = 0 OR deleted IS NULL) AND needs_chunking = 1")`, then for each `project_id` get the file batch. B.2 describes this two-step sequence.

### 2.4 Clearing `needs_chunking` (A.3)

- **Plan**: Prefer clearing in the driver after a successful index.
- **Code**: `update_file_data` in `files.py` does **not** set `needs_chunking = 0` at the end. So the driver’s `handle_index_file` (or the code it calls) must run `UPDATE files SET needs_chunking = 0 WHERE id = ?` after a successful update. This is consistent with the plan.

### 2.5 Vectorization worker pattern (backoff, DB availability, runner)

- **Code**: `vectorization_worker_pkg/processing.py` uses a backoff (1–60 s), checks DB availability (e.g. `list_projects()`), resets backoff when DB is available, and uses `DatabaseClient` from `socket_path` derived from `db_path`. Runner sets up logging, PID file, and `asyncio.run(worker.process_cycle(...))` in a loop with `poll_interval` and `_stop_event`.
- **Plan**: B.3 and B.4 mirror this (backoff, DB availability, logging, PID). The plan is aligned with the code.

### 2.6 Worker status and stats (D.1)

- **Code**: `worker_status_mcp_commands.py` uses `worker_type` and for `file_watcher` / `vectorization` uses `get_file_watcher_stats`, `get_vectorization_stats` (tables `file_watcher_stats`, `vectorization_stats`). The plan **mandates** table **indexing_worker_stats** and methods in `worker_stats.py` (`start_indexing_cycle`, `update_indexing_stats`, `end_indexing_cycle`, `get_indexing_stats`). Commands that **must** use it: **get_worker_status** when `worker_type == "indexing"`; any dashboard or summary that shows all workers.

---

## 3. Summary

- **Structure**: The plan matches the existing layout; the indexer is implemented in the same way as the vectorization worker (same interaction with the main code).
- **Database**: Correct use of `needs_chunking`, `code_content`, `code_content_fts`, and `projects.root_path`. No `root_dir` parameter: project root comes from the DB; watch directories and projects define the structure.
- **Code vs plan**: Driver reuses existing app logic for `index_file` (same pattern as other RPCs). Discovery is two-step (projects with work, then file batch); B.2 describes it. **indexing_worker_stats** table and commands that use it are defined in D.1.

The unaccounted nuances derived from this analysis are listed in [INDEXING_WORKER_PLAN.md](INDEXING_WORKER_PLAN.md#unaccounted-nuances).
