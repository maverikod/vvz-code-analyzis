# Step B.1 — Package layout

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Directory

`code_analysis/core/indexing_worker_pkg/`

## Files

Mirror vectorization worker where applicable:

| File | Purpose |
|------|---------|
| `__init__.py` | Package init |
| `base.py` | Class `IndexingWorker` with `__init__(self, db_path, socket_path, batch_size, poll_interval, ...)` and `_stop_event`; no SVO/FAISS |
| `processing.py` | Async loop `process_cycle(self, database)` (or similar): query projects with files that have `needs_chunking = 1`, then for each project get a batch of files (e.g. LIMIT 5), for each file call `database.index_file(file_path, project_id)` (no root_dir; paths from DB), handle errors; clear `needs_chunking` is done in driver after success |
| `runner.py` | `run_indexing_worker(db_path, poll_interval=30, worker_log_path=None, pid_file_path=None, socket_path=None, batch_size=5, ...)`: setup logging, resolve `socket_path` from `db_path` if not provided, create `DatabaseClient`, create `IndexingWorker`, run `asyncio.run(worker.process_cycle(...))` in a loop with `poll_interval` and `_stop_event` check; handle KeyboardInterrupt and PID file cleanup (remove only if PID matches) |
