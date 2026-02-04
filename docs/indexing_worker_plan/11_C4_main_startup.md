# Step C.4 — main.py startup

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Where

`code_analysis/main.py` (next to `startup_vectorization_worker`).

## Add

- **Function**: `startup_indexing_worker()`: read config (db path, logs dir, poll_interval, batch_size), resolve paths, call `worker_manager.start_indexing_worker(...)`.
- **When**: Call it after the database driver is ready and **before** the vectorization worker. This ordering avoids flag conflicts: the indexer processes files with `needs_chunking = 1` first and clears the flag; then vectorization still sees the file via "no code_chunks" and chunks it (see 99_ORDER_RISKS_CRITERIA §0).
