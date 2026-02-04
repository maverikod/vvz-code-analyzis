# Step D.1 — get_worker_status and indexing stats

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Where

Commands that report worker status (e.g. `worker_status_mcp_commands.py`) and the database module that provides stats (e.g. `core/database/worker_stats.py`).

## Statistics table

Add **indexing_worker_stats** (same pattern as `file_watcher_stats` and `vectorization_stats`):

- Table in schema (e.g. in `core/database/base.py`): cycle_id, cycle_start_time, cycle_end_time, files_total_at_start, files_indexed, files_failed, total_processing_time_seconds, average_processing_time_seconds, last_updated (and any columns needed for "last cycle" reporting).
- Add to `worker_stats.py`: `start_indexing_cycle`, `update_indexing_stats`, `end_indexing_cycle`, `get_indexing_stats()` (same style as file_watcher/vectorization).
- Indexing worker updates this table each cycle (via `DatabaseClient.execute` or dedicated RPC if needed).

## Commands that use the stats

- **get_worker_status** (e.g. `worker_status_mcp_commands.py`): when `worker_type == "indexing"`, report PID, log path, running/not running, and **last cycle stats** from `get_indexing_stats()` (same pattern as `file_watcher` / `vectorization`).
- Any other command that shows worker status or dashboard (e.g. a summary of all workers) must include indexing worker and use the same stats source.

## Change to get_worker_status

Extend allowed `worker_type` to include `"indexing"`.

When `worker_type == "indexing"`, report:

- Status (PID, log path, "running" / "not running").
- Last cycle stats from `indexing_worker_stats` (files indexed, etc.), using `get_indexing_stats()`.

Reuse the same pattern as for `file_watcher` and `vectorization`.
