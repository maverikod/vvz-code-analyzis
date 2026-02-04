# Step C.3 — WorkerRegistry and stop

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Requirement

Ensure `WorkerRegistry` and `WorkerLifecycleManager.stop_worker_type` support `worker_type == "indexing"` (same as `"file_watcher"` and `"vectorization"`):

- Stop by PID.
- Wait with timeout.
- Remove PID file if ours.
