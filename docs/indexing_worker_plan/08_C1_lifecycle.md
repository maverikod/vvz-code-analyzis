# Step C.1 — WorkerLifecycleManager

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Where

`code_analysis/core/worker_lifecycle.py`

## Add method

`start_indexing_worker(self, *, db_path, poll_interval=30, batch_size=5, worker_log_path=None, worker_logs_dir=None) -> WorkerStartResult`

## Behaviour

1. Resolve `socket_path` from `db_path` (same as vectorization).
2. Resolve PID file path (e.g. `worker_logs_dir / "indexing_worker.pid"` or `logs / "indexing_worker.pid"`).
3. Check PID file; if already running, return "already running".
4. Start `multiprocessing.Process(target=run_indexing_worker, args=(db_path,), kwargs={...}, daemon=True)`.
5. Write PID to PID file, register worker with type `"indexing"`.
