# Why the indexing worker stopped when disk was full

Author: Vasiliy Zdanovskiy  
email: vasilyvz@gmail.com

## Observed in logs

```
Failed to write worker status file logs/indexing_worker.status.json: [Errno 28] No space left on device
[CYCLE #164] Starting indexing cycle
```

After that, the worker no longer appeared in `get_worker_status` (process_count: 0). So the process (or the indexing loop) exited.

---

## Root cause (exact chain)

1. **Disk full.** Any write to the project/logs directory can fail with `OSError(28, "No space left on device")`.

2. **First failure: status file.**  
   In the indexing cycle, `write_worker_status(status_file_path, ...)` is called (`processing.py`).  
   It does `open(path, "w")` and `json.dump(...)` → write to `logs/indexing_worker.status.json`.  
   That write raises **OSError(28)** (no space).

3. **Exception is caught in `write_worker_status`.**  
   In `worker_status_file.py` the `except Exception as e:` block runs. The code then calls:
   ```python
   logger.debug("Failed to write worker status file %s: %s", status_file_path, e)
   ```

4. **Second failure: log file.**  
   The logger is configured to write to a file (e.g. `logs/indexing_worker.log`).  
   The logging handler (e.g. `FileHandler`) tries to write the message to that file.  
   The disk is still full → the **same OSError(28)** is raised inside the logging machinery.

5. **That second exception is not caught.**  
   The `except` block in `write_worker_status` did not wrap the `logger.debug(...)` call in `try/except`.  
   So the OSError from the logger propagates **out of** `write_worker_status()`.

6. **Caller had no try/except.**  
   In `processing.py`, `write_worker_status(...)` was called without a surrounding try/except.  
   So the exception propagated out of the `while not self._stop_event.is_set():` loop.  
   The loop exited → `finally` ran (disconnect) → the coroutine/thread ended → the worker “crashed” (stopped).

So the **immediate** reason the worker stopped was: **the exception that escaped was the one from logging** (writing to the log file on a full disk), not the one from writing the status file. The status write failed first and was caught; the attempt to log that failure failed too and was not caught, so it killed the loop.

---

## Summary

| Step | Where | What happens |
|------|--------|--------------|
| 1 | `worker_status_file.write_worker_status` | `open(path,"w")` or `json.dump` → **OSError(28)** (no space). |
| 2 | Same function, `except` block | Calls `logger.debug("Failed to write worker status file ...")`. |
| 3 | Logging (e.g. FileHandler) | Writes to `indexing_worker.log` → same disk full → **OSError(28)** again. |
| 4 | `write_worker_status` | Does not catch this second exception → **exception propagates**. |
| 5 | `processing.process_cycle` | No try/except around `write_worker_status(...)` → exception leaves the `while` loop → loop exits → worker stops. |

So the cause of the crash was: **reporting the status-file error via the logger on a full disk caused a second OSError that was not swallowed, so it propagated and stopped the indexing worker.**

---

## Fixes applied

1. **`worker_status_file.write_worker_status` (and `read_worker_status`)**  
   In the `except` block, the call to `logger.debug(...)` is wrapped in `try/except Exception: pass`.  
   So even if logging fails (e.g. disk full), no exception leaves `write_worker_status` → the worker does not crash because of a failed status write or failed log write.

2. **`indexing_worker_pkg/processing.py`**  
   - The call to `write_worker_status` + `logger.info` at the start of the cycle is wrapped in try/except: on any exception, backoff and `continue` (no exit from the loop).  
   - The whole cycle body (all `database.execute`, project/file loop, stats, sleep) is wrapped in an outer try/except: on any exception (no space, DB unavailable, service error), log (with guarded logger), disconnect, backoff, `continue`.  
   So failures like “no space”, “DB unavailable”, or “service unavailable” no longer terminate the worker; it retries after backoff.

With these changes, a full disk may prevent writing the status file (and possibly the log), but the indexing worker loop no longer exits because of an uncaught exception from logging or status write.
