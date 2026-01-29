# Worker Status Commands — Detailed Descriptions

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Both in `commands/worker_status_mcp_commands.py`. Internal: `WorkerStatusCommand`, `DatabaseStatusCommand` in `commands/worker_status.py`. Schema from `get_schema()`; metadata from `metadata()`.

---

## get_worker_status — GetWorkerStatusMCPCommand

**Description:** Get status of workers (file_watcher, vectorization, etc.): running/stopped, PID, last activity.

**Behavior:** Returns status per worker type (and optionally per project) from WorkerRegistry/WorkerManager.

---

## get_database_status — GetDatabaseStatusMCPCommand

**Description:** Get database driver status: connected, process PID, health.

**Behavior:** Returns whether the DB driver process is running and reachable, and optional connection info.
