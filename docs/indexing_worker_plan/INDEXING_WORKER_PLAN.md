# Indexing Worker: Plan Index

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

The detailed step-by-step plan for the **indexing worker** is split into a dedicated directory. Each step is in its own file for easier navigation and tracking.

## Plan location

**Directory**: [docs/indexing_worker_plan/](indexing_worker_plan/)

## Entry point

Start from the overview and step index:

- **[00_OVERVIEW.md](indexing_worker_plan/00_OVERVIEW.md)** — Goal, current state, high-level design, and table of all step files.

## Phases and steps (file list)

| Phase | Description | Step files |
|-------|--------------|------------|
| **A** | RPC for "index one file" | [01_A1_driver_rpc](indexing_worker_plan/01_A1_driver_rpc.md), [02_A2_client_method](indexing_worker_plan/02_A2_client_method.md), [03_A3_needs_chunking](indexing_worker_plan/03_A3_needs_chunking.md) |
| **B** | Indexing worker package | [04_B1_package_layout](indexing_worker_plan/04_B1_package_layout.md) … [07_B4_logging_pid](indexing_worker_plan/07_B4_logging_pid.md) |
| **C** | Integration (lifecycle, main, config) | [08_C1_lifecycle](indexing_worker_plan/08_C1_lifecycle.md) … [12_C5_config](indexing_worker_plan/12_C5_config.md) |
| **D** | MCP / CLI (status, start/stop) | [13_D1_worker_status](indexing_worker_plan/13_D1_worker_status.md), [14_D2_start_stop](indexing_worker_plan/14_D2_start_stop.md) |
| **E** | Documentation and tests | [15_E1_docs](indexing_worker_plan/15_E1_docs.md), [16_E2_tests](indexing_worker_plan/16_E2_tests.md) |
| — | Order, risks, success criteria | [99_ORDER_RISKS_CRITERIA](indexing_worker_plan/99_ORDER_RISKS_CRITERIA.md) |

## Implementation order

1. Phase A → Phase B → Phase C → Phase D → Phase E (see [99_ORDER_RISKS_CRITERIA.md](indexing_worker_plan/99_ORDER_RISKS_CRITERIA.md)).

---

## Principles

- **Same interaction as vectorizer**: The indexer is implemented like the vectorization worker: same package layout (base, processing, runner), same lifecycle (WorkerLifecycleManager, WorkerManager, main startup), same discovery pattern (query DB via DatabaseClient), same stats table pattern and MCP (get_worker_status, start_worker, stop_worker). No `root_dir`: project root comes from the database (`projects.root_path`); watch directories and projects define the structure.
- **Flag process**: The indexer selects only records with **needs_chunking = 1** (flag set = needs indexing). After a successful index, the flag is **reset** to 0 so the file is not reprocessed. See [05_B2_discovery_query.md](indexing_worker_plan/05_B2_discovery_query.md).
- **Single flag, no zoo**: There is only one flag for "file needs work": **needs_chunking**. It is used by both the indexer and the vectorization worker. To avoid conflicts (vectorization clearing the flag before the indexer runs), the **indexer must run before vectorization** (startup/cycle order). See [99_ORDER_RISKS_CRITERIA.md](indexing_worker_plan/99_ORDER_RISKS_CRITERIA.md) §0.

---

## Comparative analysis

A detailed comparison of the plan with the current application structure, database, and code is in **[COMPARATIVE_ANALYSIS.md](indexing_worker_plan/COMPARATIVE_ANALYSIS.md)**. It covers:

- Application and database structure vs plan (schema, packages, data flow).
- Code vs plan (where `update_file_data` lives, driver capabilities, discovery query, clearing `needs_chunking`, worker status).

---

## Unaccounted nuances (from comparative analysis)

These points should be reflected in the step files or accepted explicitly before implementation.

1. **RPC server registration (A.1)**  
   Add `"index_file"` to the `handler_map` in `rpc_server._process_request` and implement a handler mixin (e.g. `_RPCHandlersIndexFileMixin`) with `handle_index_file(self, params)` returning `SuccessResult`/`ErrorResult`. Params: `file_path`, `project_id` (no `root_dir`).

2. **Discovery: projects with work (B.2)**  
   First run `execute("SELECT DISTINCT project_id FROM files WHERE (deleted = 0 OR deleted IS NULL) AND needs_chunking = 1")`, then for each `project_id` get the file batch. Step B.2 already describes this.

3. **Statistics table and commands (D.1)**  
   Add table **indexing_worker_stats** and methods in `worker_stats.py` (`start_indexing_cycle`, `update_indexing_stats`, `end_indexing_cycle`, `get_indexing_stats`). Commands that **must** use it: **get_worker_status** when `worker_type == "indexing"`; any dashboard or summary that shows all workers must include indexing and use the same stats.

4. **Path and filesystem**  
   The driver process must have read access to file paths (paths are absolute, from `files.path`). Project root is taken from `projects.root_path` in the DB when needed.

5. **Startup order (C.4)**  
   Add `startup_indexing_worker()` in the same startup block, **before** vectorization (after the database driver is ready). Order: driver → **indexing** → vectorization → file_watcher (so the indexer clears `needs_chunking` before vectorization; see §0 in 99_ORDER_RISKS_CRITERIA).

6. **Config key (C.5)**  
   Define the config section for the indexing worker (e.g. `indexing_worker`) so `main.py` and startup know where to read `poll_interval`, `batch_size`, `log_path`.
