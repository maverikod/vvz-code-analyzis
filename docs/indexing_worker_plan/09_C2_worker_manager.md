# Step C.2 — WorkerManager

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Where

`code_analysis/core/worker_manager.py`

## Add method

`start_indexing_worker(self, *, db_path, poll_interval=30, batch_size=5, worker_log_path=None, worker_logs_dir=None)` that delegates to `_lifecycle.start_indexing_worker(...)`.
