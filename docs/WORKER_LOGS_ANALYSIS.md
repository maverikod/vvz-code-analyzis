# Worker logs: analysis and tools

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## 1. One log per worker

Each worker has its own log file. Paths are resolved from server config: `config_dir` is the directory containing `config.json`; worker logs live under `config_dir/logs/` (or paths set in config for each worker).

| Worker            | Default log file              | Config key (if any)                    |
|-------------------|-------------------------------|----------------------------------------|
| file_watcher      | file_watcher.log              | code_analysis.file_watcher.log_path    |
| vectorization     | vectorization_worker.log     | code_analysis.worker.log_path          |
| indexing          | indexing_worker.log          | code_analysis.indexing_worker.log_path |
| database_driver   | database_driver.log          | (driver log_path from startup)         |
| server (main)     | mcp_server.log               | server.log_dir                          |
| repair_worker     | repair_worker.log            | (per root_dir in command)              |
| analysis          | comprehensive_analysis.log  | (analysis-specific)                     |

All of these (except repair_worker, which is per root_dir) use the same base directory when not overridden: `config_dir/logs/`. So a single `logs/` directory (relative to config or explicitly set) contains one log file per worker type.

## 2. Current layout (example)

With config at project root (`config.json`), `config_dir` is the project root and logs typically are:

- `logs/file_watcher.log` (and rotated .log.1, .log.2, …)
- `logs/vectorization_worker.log` (and rotated)
- `logs/indexing_worker.log` (created when indexing worker runs and sets up logging)
- `logs/database_driver.log` (created by driver process)
- `logs/mcp_server.log` or `logs/mcp_proxy_adapter.log` (server/main process)

If `code_analysis.file_watcher.log_path` (or other worker log_path) is set to an absolute path, that worker’s log is written there instead.

## 3. Server tools for viewing and searching worker logs

Two MCP commands provide viewing and search over worker logs.

### 3.1 list_worker_logs

- **Purpose**: List available worker log files (discovery).
- **Parameters**:
  - `log_dirs` (optional): Directories to scan. If omitted, the server uses **config-based default**: `[config_dir/logs, "logs"]`, so the canonical worker log directory is always scanned.
  - `worker_type` (optional): Filter by worker type: `file_watcher`, `vectorization`, `indexing`, `database_driver`, `analysis`, `server`.
- **Returns**: List of log files with path, size, modified time, and detected `worker_type`.
- **Use case**: Discover which worker logs exist and their paths before viewing or searching.

### 3.2 view_worker_logs

- **Purpose**: View and search inside a worker log with filters. One analyzer for all worker logs; supports unified and legacy log formats (see UNIFIED_LOG_FORMAT.md, LOG_IMPORTANCE_CRITERIA.md).
- **Parameters**:
  - `log_path` (optional): Path to the log file. If omitted, the server **resolves the default** for the given `worker_type` from config: `config_dir/logs/<worker_log_filename>` (see table in §1).
  - `worker_type` (optional): `file_watcher`, `vectorization`, `indexing`, `database_driver`, `analysis`. Used for default path resolution and for event-type patterns when filtering.
  - **Time interval** (partial or full): `from_time`, `to_time` — ISO or `YYYY-MM-DD HH:MM:SS` or date-only `YYYY-MM-DD`. You can set only `from_time`, only `to_time`, or both.
  - `event_types`: Filter by event type (e.g. `new_file`, `changed_file`, `cycle`, `error`); patterns depend on `worker_type`.
  - `log_levels`: Filter by level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.
  - **Importance**: `importance_min`, `importance_max` (0–10) — filter by message importance; see LOG_IMPORTANCE_CRITERIA.md.
  - **Search**: `search_pattern` — **regex** on the message part (case-insensitive).
  - `tail`: Return only the last N lines (time filters ignored).
  - `limit`: Max number of lines to return (default 1000).
- **Returns**: Structured log entries: `timestamp` (ISO), `level`, **`importance`** (0–10), `message`, `raw`; plus total/filtered counts and applied filters.
- **Use case**: Inspect recent activity, find errors, or search by text/regex or time or importance in any worker log.

**Rule**: Either provide `log_path` or rely on `worker_type` with config available; if neither gives a path, the command returns an error.

### 3.3 rotate_worker_logs

- **Purpose**: Manually rotate a worker log file (same scheme as `RotatingFileHandler`: current → .1, .1 → .2, … then new empty log).
- **Parameters**:
  - `log_path` (optional): Path to the log file. If omitted, resolved from `worker_type` and config.
  - `worker_type` (optional): `file_watcher`, `vectorization`, `indexing`, `database_driver`, `analysis`, `server` — to resolve default log path.
  - `backup_count` (optional): Number of backup files to keep (1–99; default 5).
- **Returns**: `log_path`, `backup_count`, `rotated_paths` (e.g. `["path.log.1", "path.log.2"]`), `message`.
- **Note**: The running worker may continue writing to the previous file (now .1) until it restarts or reopens the log.

## 4. Event patterns by worker type

Used by `view_worker_logs` when filtering by `event_types`:

- **file_watcher**: new_file, changed_file, deleted_file, cycle, scan_start, scan_end, queue, error, info, warning.
- **vectorization**: cycle, processed, error, info, warning, circuit_breaker.
- **indexing**: cycle, indexed, error, info, warning, database.
- **database_driver**: rpc, execute, error, info, warning.

## 5. Summary

- **One log per worker**: Each worker type writes to its own file under `config_dir/logs/` (or configured path).
- **Discovery**: `list_worker_logs` lists worker log files; without `log_dirs` it uses config to scan the canonical logs directory and optionally `"logs"`.
- **View and search**: `view_worker_logs` views/filters by time (partial interval), level, importance (0–10), event type, and **regex** on message; one analyzer for all logs; `log_path` can be omitted and resolved from `worker_type` and server config.
- **Manual rotation**: `rotate_worker_logs` rotates a log file (current → .1, .1 → .2, … new empty log); specify `log_path` or `worker_type`.
