# Why the indexing worker appears dead

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Summary

The indexing worker is started as a **separate process** (`multiprocessing.Process`, `daemon=True`) and is **not** configured for auto-restart. When it exits (crash or exception), the monitor does not restart it, so it stays "dead" until the server is restarted.

---

## 1. How the indexing worker runs

- **Start**: `main.py` → `startup_indexing_worker()` → `worker_manager.start_indexing_worker(...)` → `worker_lifecycle.start_indexing_worker()`.
- **Process**: `multiprocessing.Process(target=run_indexing_worker, ..., daemon=True)`. So it is a **child process**, not a thread.
- **Registry**: On start, the process is registered with `WorkerRegistry` (PID + process object). `get_worker_status(worker_type="indexing")` reads from this registry and then checks if the PID is still alive via `psutil`. If the process has exited, `processes` is empty and `is_running` is false.

So "indexing is dead" means: the indexing **process** that was started at server startup has **exited**.

---

## 2. Why it might have exited

### 2.1 No auto-restart

- In `worker_lifecycle.start_indexing_worker()` the worker is registered with only `{"pid": ..., "process": ..., "name": "indexing_universal"}`.
- **No `restart_func`** (and no `restart_args` / `restart_kwargs`) is passed, unlike the database driver, which registers `restart_func=self.start_database_driver`.
- In `worker_monitor._check_and_restart_workers()`, when a worker is detected dead, it tries to call `restart_func` if present. For indexing there is none, so the log would say: *"Cannot restart indexing worker ... no restart function provided"*.
- So once the indexing process exits, nothing restarts it.

### 2.2 Possible causes of exit

1. **Unhandled exception**  
   The worker loop is `process_cycle()` in `indexing_worker_pkg/processing.py` (async, run with `asyncio.run(worker.process_cycle(...))` in `runner.run_indexing_worker()`).  
   - Exceptions inside the cycle are caught and lead to `database = None`, backoff, and `continue`.  
   - If an exception escapes the loop or happens in a code path that doesn’t catch it, it will propagate to `run_indexing_worker`, which catches `Exception` and returns `{"indexed": 0, "errors": 1, "cycles": 0}`. So the **process exits normally** (return from `run_indexing_worker`), and the OS process ends.

2. **Startup log shows it did run**  
   Server startup log contained: *"Created project 928bcf10... vast_srv"*. That comes from the indexing worker’s cycle (discovery + indexing). So the worker **did run at least one cycle** and then exited later (next cycle or during teardown).

3. **No indexing log file**  
   A search for `**/indexing_worker*.log*` found **no** indexing worker log.  
   - Logging is set in `runner.run_indexing_worker()` via `_setup_worker_logging(worker_log_path, ...)` at the start.  
   - So either: the process exited **before** that line (e.g. import/runtime error very early), or the log is written to a path outside the searched tree (e.g. under `config_dir` or `/tmp`).  
   - If the worker ran one full cycle (as above), logging was likely set; then the log might be in a different directory (e.g. `config_dir/logs/` or path from config). Without that log, the exact exception or reason for exit is unknown.

4. **daemon=True**  
   If the **parent** (main server) exits, the OS kills daemon children. Here the parent is still running, so this does not explain the current death; it only means that after a server restart, the old indexing process is gone.

---

## 3. Conclusions

| Finding | Detail |
|--------|--------|
| **Why status shows "dead"** | The indexing **process** started at startup has exited; the registry still had its PID, but `psutil` shows the process no longer exists. |
| **Why it doesn’t come back** | Indexing worker is **not** registered with a `restart_func`, so the worker monitor does not restart it when it detects the process is dead. |
| **Why we don’t see the reason** | No indexing worker log file was found; the process either exited before opening the log or wrote it elsewhere. So the root cause (exception, OOM, etc.) is not visible from the repo. |
| **Evidence it ran** | Server log shows the indexing worker created project `vast_srv` in one cycle; it exited sometime after that. |

---

## 4. Recommendations

1. **Add auto-restart for the indexing worker**  
   When registering the indexing worker, pass a `restart_func` (and `restart_args` / `restart_kwargs`) so that `WorkerMonitor` can restart it when it detects the process has exited (same idea as for the database driver). The restart function should be the same startup logic used in `startup_indexing_worker()` (with config/code_analysis section and storage paths resolved again, or a thin wrapper that calls the same code).

2. **Ensure a log file is always created**  
   - Use a fixed, well-known path for the indexing worker log (e.g. under `storage.config_dir` or a single `logs/` directory) and document it.  
   - Optionally, set up logging as early as possible in the child (e.g. right at the top of `run_indexing_worker`) so that any later exception is recorded.

3. **Reproduce and capture the error**  
   - Run the indexing worker **manually** in a terminal (same config and paths as the server) to see if it exits with an exception: e.g. call `run_indexing_worker(db_path=..., worker_log_path=..., pid_file_path=None)` from a small script.  
   - Or temporarily add a `restart_func` and check server/monitor logs when the monitor restarts the worker; if the worker crashes again, ensure its log path is correct and inspect that log.

After implementing (1) and (2), the indexing worker will restart when it dies, and future deaths will be easier to diagnose from logs.
