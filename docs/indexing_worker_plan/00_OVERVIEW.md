# Indexing Worker Plan — Overview

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Goal

Add a background **indexing worker** (by analogy with the vectorization worker) so that **fulltext search** (and AST/CST/entities) is updated automatically when files change on disk. Manual `update_indexes` remains an emergency/full-refresh tool.

---

## 1. Current State (Brief)

- **Vectorization worker**: separate process; polls DB every `poll_interval` (e.g. 30s); finds projects with files that have `needs_chunking = 1` or no rows in `code_chunks`; requests chunking, assigns `vector_id`, updates FAISS. Uses `DatabaseClient` (RPC) only; no filesystem access in the worker (chunking service reads content).
- **File watcher**: sets `needs_chunking = 1` and updates `files` for new/changed files; does **not** call `update_file_data`, so `code_content` / `code_content_fts` are not filled.
- **update_file_data** (in `core/database/files.py`): full refresh for one file (clear old data → `UpdateIndexesMCPCommand._analyze_file` → AST, CST, entities, **code_content** → fulltext). Used by refactor commands, file_management, splitter, extractor; **not** by file watcher or any background worker.
- **DatabaseClient** does not expose `update_file_data`. The **driver** (database_driver_pkg) holds the real DB connection; it does not expose an RPC for `update_file_data` or `update_file_data_atomic`.

---

## 2. High-Level Design

- New worker: **indexing worker**.
- Runs in a **separate process** (like vectorization), so it does not block the server and survives restarts independently.
- Each cycle:
  - Query DB (via `DatabaseClient`) for projects that have at least one file with `needs_chunking = 1`.
  - For each such project, take a **batch** of files with `needs_chunking = 1` (e.g. limit 5 per project per cycle).
  - For each file: trigger a **full file index** (AST, CST, entities, code_content → fulltext). After success, set `needs_chunking = 0` for that file so we do not re-index it every cycle (vectorization worker still picks it up via “no code_chunks”).
- Worker uses **only** `DatabaseClient` (RPC); the **driver** reads files from disk when handling the index RPC. No direct SQLite in the worker process.
- The **driver** exposes an RPC “index this file” (same effect as `update_file_data` for one file). The worker calls it via `DatabaseClient.index_file(file_path, project_id)`. There is **no** `root_dir` parameter: project root comes from the DB (`projects.root_path`); watch directories and projects define the structure.
- **Interaction with the main code**: the indexer is implemented in the same way as the vectorization worker (package layout, lifecycle, discovery via client, stats table, MCP status/start/stop).
- **Single flag**: Only one flag is used for "file needs work" — `needs_chunking`. Both indexer and vectorization read/clear it. To avoid conflicts, the indexer must run **before** the vectorization worker (startup/cycle order). See [99_ORDER_RISKS_CRITERIA.md](99_ORDER_RISKS_CRITERIA.md) §0.

---

## 3. Plan Structure (Step Files)

| Phase | Step | File |
|-------|------|------|
| A | A.1 Driver: expose "index_file" RPC | [01_A1_driver_rpc.md](01_A1_driver_rpc.md) |
| A | A.2 DatabaseClient: add index_file method | [02_A2_client_method.md](02_A2_client_method.md) |
| A | A.3 Optional: clear needs_chunking after success | [03_A3_needs_chunking.md](03_A3_needs_chunking.md) |
| B | B.1 Package layout | [04_B1_package_layout.md](04_B1_package_layout.md) |
| B | B.2 Discovery query | [05_B2_discovery_query.md](05_B2_discovery_query.md) |
| B | B.3 Backoff and DB availability | [06_B3_backoff.md](06_B3_backoff.md) |
| B | B.4 Logging and PID file | [07_B4_logging_pid.md](07_B4_logging_pid.md) |
| C | C.1 WorkerLifecycleManager | [08_C1_lifecycle.md](08_C1_lifecycle.md) |
| C | C.2 WorkerManager | [09_C2_worker_manager.md](09_C2_worker_manager.md) |
| C | C.3 WorkerRegistry and stop | [10_C3_registry_stop.md](10_C3_registry_stop.md) |
| C | C.4 main.py startup | [11_C4_main_startup.md](11_C4_main_startup.md) |
| C | C.5 Optional: config | [12_C5_config.md](12_C5_config.md) |
| D | D.1 get_worker_status | [13_D1_worker_status.md](13_D1_worker_status.md) |
| D | D.2 start_worker / stop_worker | [14_D2_start_stop.md](14_D2_start_stop.md) |
| E | E.1 Docs | [15_E1_docs.md](15_E1_docs.md) |
| E | E.2 Tests | [16_E2_tests.md](16_E2_tests.md) |

Order of implementation, risks, and success criteria: [99_ORDER_RISKS_CRITERIA.md](99_ORDER_RISKS_CRITERIA.md).
