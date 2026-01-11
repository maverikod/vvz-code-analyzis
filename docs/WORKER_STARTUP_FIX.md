# Worker Startup Fix

**Generated**: 2026-01-11 10:00  
**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com

## Problem

Workers were not starting after server restart due to `asyncio.run()` conflict in background thread.

## Root Cause

1. **asyncio.run() conflict**:
   - Workers were started in background thread using `asyncio.run()`
   - This created a new event loop that conflicted with Hypercorn's event loop
   - Error: "Unhandled exception in event loop: unhandled exception during asyncio.run() shutdown"

2. **Unnecessary async/await**:
   - Workers are separate processes (`multiprocessing.Process`)
   - They don't require async/await - they're independent processes
   - Using async functions was unnecessary complexity

## Solution

### 1. Changed worker startup functions from async to sync

**Before**:
```python
async def startup_vectorization_worker() -> None:
    ...
    await startup_vectorization_worker()

async def startup_file_watcher_worker() -> None:
    ...
    await startup_file_watcher_worker()

async def _start_non_db_workers() -> None:
    await startup_vectorization_worker()
    await startup_file_watcher_worker()

def _start_non_db_workers_thread() -> None:
    asyncio.run(_start_non_db_workers())  # <-- PROBLEM
```

**After**:
```python
def startup_vectorization_worker() -> None:
    ...
    startup_vectorization_worker()  # Direct call

def startup_file_watcher_worker() -> None:
    ...
    startup_file_watcher_worker()  # Direct call

# Workers start synchronously before server starts
startup_vectorization_worker()
startup_file_watcher_worker()
```

### 2. Ensured all processes are killed with SIGKILL on timeout

**Updated**:
- `worker_manager.py`: All `proc.wait(timeout=timeout)` now catch `psutil.TimeoutExpired` and call `proc.kill()`
- `db_worker_manager.py`: DB worker now explicitly kills with SIGKILL after 5s timeout
- All processes (workers and main server) are killed with SIGKILL if they don't stop gracefully

## Benefits

1. **No event loop conflicts**: Workers start synchronously, no asyncio.run() needed
2. **Simpler code**: No async/await for process-based workers
3. **Reliable startup**: Workers start before server, ensuring they're ready
4. **Consistent process termination**: All processes killed with SIGKILL on timeout

## Files Changed

- `code_analysis/main.py`: Removed asyncio.run(), changed async functions to sync
- `code_analysis/core/worker_manager.py`: Improved timeout handling with explicit SIGKILL
- `code_analysis/core/db_worker_manager.py`: Explicit SIGKILL after timeout

## Testing

After restart, workers should:
1. Start successfully (no asyncio conflicts)
2. Register in WorkerManager
3. Be visible via `get_worker_status` MCP command
4. Stop gracefully or be killed with SIGKILL if they don't stop within timeout
