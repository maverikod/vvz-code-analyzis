# Worker Management Commands — Detailed Descriptions

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

Both in `commands/worker_management_mcp_commands.py`. Core: `worker_manager.py`, `worker_lifecycle.py`. Schema from `get_schema()`; metadata from `metadata()`.

---

## start_worker — StartWorkerMCPCommand

**Description:** Start a worker by type (e.g. file_watcher, vectorization).

**Behavior:** Accepts worker_type; starts the corresponding worker process via WorkerManager/WorkerLifecycleManager; returns status or PID.

---

## stop_worker — StopWorkerMCPCommand

**Description:** Stop a worker by type.

**Behavior:** Accepts worker_type; stops the worker process gracefully; returns success/failure.
