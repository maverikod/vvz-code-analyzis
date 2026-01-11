# Worker Initialization Chain

**Generated**: 2026-01-11  
**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com

## Overview

This document describes the complete initialization chain for all workers in the system, including when they start, how they start, and through which components.

## Worker Types

1. **Vectorization Worker** - Processes files for vectorization
2. **File Watcher Worker** - Monitors file system for changes
3. **DB Worker** - Handles database operations via IPC

## Initialization Timeline

```
Server Startup Sequence:
├── 1. main() function starts
├── 2. Configuration loading
├── 3. App creation (FastAPI)
├── 4. Shutdown handlers registration (atexit, signals)
├── 5. Worker startup (BEFORE server starts)
│   ├── 5.1. Vectorization Worker (synchronous)
│   └── 5.2. File Watcher Worker (synchronous)
├── 6. Server starts (Hypercorn)
└── 7. DB Worker (lazy, when database connection needed)
```

## Detailed Initialization Chains

### 1. Vectorization Worker

**Startup Moment**: Before server starts (synchronous, in main thread)

**Chain**:
```
main() (line 978)
  └─> startup_vectorization_worker() (line 523)
      ├─> Load config from app_config
      ├─> Validate config (chunker, worker enabled)
      ├─> Resolve storage paths (db_path, faiss_dir)
      ├─> Create database if not exists (optional)
      └─> WorkerManager.start_vectorization_worker() (line 664)
          ├─> Check PID file (prevent duplicates)
          ├─> multiprocessing.Process(
          │       target=run_vectorization_worker,
          │       daemon=True
          │   )
          ├─> process.start() (line 882)
          ├─> Write PID file
          └─> WorkerManager.register_worker() (line 892)
              └─> Store in WorkerManager._workers["vectorization"]
```

**Key Points**:
- ✅ Starts **synchronously** before server
- ✅ Uses `multiprocessing.Process` (separate process)
- ✅ Registered in `WorkerManager`
- ✅ Daemon process (terminates when parent dies)

**Code Locations**:
- `main.py`: 523-691 (startup function)
- `worker_manager.py`: 810-901 (start method)
- `vectorization_worker_pkg/runner.py`: 79-341 (worker process)

---

### 2. File Watcher Worker

**Startup Moment**: Before server starts (synchronous, in main thread)

**Chain**:
```
main() (line 993)
  └─> startup_file_watcher_worker() (line 693)
      ├─> Load config from app_config
      ├─> Validate config (file_watcher enabled, watch_dirs)
      ├─> Resolve storage paths (db_path, locks_dir)
      ├─> Validate watch_dirs exist
      └─> WorkerManager.start_file_watcher_worker() (line 810)
          ├─> multiprocessing.Process(
          │       target=run_file_watcher_worker,
          │       daemon=True
          │   )
          ├─> process.start() (line 795)
          └─> WorkerManager.register_worker() (line 799)
              └─> Store in WorkerManager._workers["file_watcher"]
```

**Key Points**:
- ✅ Starts **synchronously** before server
- ✅ Uses `multiprocessing.Process` (separate process)
- ✅ Registered in `WorkerManager`
- ✅ Daemon process (terminates when parent dies)

**Code Locations**:
- `main.py`: 693-837 (startup function)
- `worker_manager.py`: 748-808 (start method)
- `file_watcher_pkg/runner.py`: (worker process)

---

### 3. DB Worker

**Startup Moment**: Lazy initialization (when database connection is requested)

**Chain**:
```
Any MCP Command
  └─> BaseMCPCommand._open_database() (base_mcp_command.py:210)
      └─> CodeDatabase(driver_config) (database/base.py)
          └─> create_driver() (database/base.py:130)
              └─> SQLiteDriverProxy(driver_config)
                  └─> connect() (sqlite_proxy.py:100)
                      └─> _start_worker() (sqlite_proxy.py:129)
                          └─> DBWorkerManager.get_or_start_worker() (db_worker_manager.py:79)
                              ├─> Check if worker exists for db_path
                              ├─> If not exists:
                              │   ├─> Create socket path
                              │   ├─> multiprocessing.Process(
                              │   │       target=run_db_worker,
                              │   │       daemon=False  # NOT daemon!
                              │   │   )
                              │   ├─> process.start() (db_worker_manager.py:214)
                              │   ├─> Wait for socket creation (0.5s)
                              │   └─> Store in DBWorkerManager._workers[db_path]
                              └─> Return worker_info with socket_path
```

**Key Points**:
- ✅ Starts **lazily** when database connection needed
- ✅ Uses `multiprocessing.Process` (separate process)
- ✅ Registered in `DBWorkerManager` (NOT WorkerManager)
- ✅ **NOT daemon** process (can be started from any process)
- ✅ Managed by SQLiteDriverProxy, not main()

**Code Locations**:
- `sqlite_proxy.py`: 100 (connect), 129 (_start_worker)
- `db_worker_manager.py`: 79 (get_or_start_worker)
- `db_worker_pkg/runner.py`: 645 (worker process)

---

## Process Management

### WorkerManager (for vectorization and file_watcher)

**Responsibilities**:
- Start workers as separate processes
- Register workers (PID, process handle, name)
- Stop workers gracefully (SIGTERM → SIGKILL)
- Monitor workers (optional restart on death)
- Stop all workers on server shutdown

**Methods**:
- `start_vectorization_worker()` - Start vectorization worker
- `start_file_watcher_worker()` - Start file watcher worker
- `register_worker()` - Register worker in manager
- `stop_worker_type()` - Stop all workers of a type
- `stop_all_workers()` - Stop all registered workers

**Process Control**:
- All workers use `multiprocessing.Process` with `daemon=True`
- Processes are forcefully killed (SIGKILL) if they don't stop within timeout
- Multiple fallback mechanisms ensure process termination

### DBWorkerManager (for DB worker)

**Responsibilities**:
- Start DB worker for specific database path
- Manage socket-based IPC communication
- Reuse existing workers for same database path
- Stop workers on shutdown

**Methods**:
- `get_or_start_worker()` - Get existing or start new DB worker
- `stop_worker()` - Stop worker for specific database
- `stop_all_workers()` - Stop all DB workers

**Process Control**:
- DB worker uses `multiprocessing.Process` with `daemon=False`
- Can be started from any process (not just main)
- Managed separately from other workers

---

## Shutdown Sequence

```
Server Shutdown:
├── 1. Signal received (SIGTERM/SIGINT) or atexit
├── 2. signal_handler() or cleanup_workers() called
├── 3. WorkerManager.stop_all_workers(timeout=30.0)
│   ├── 3.1. Stop vectorization workers
│   │   ├── SIGTERM (graceful)
│   │   ├── Wait timeout
│   │   └── SIGKILL (force if still alive)
│   └── 3.2. Stop file_watcher workers
│       ├── SIGTERM (graceful)
│       ├── Wait timeout
│       └── SIGKILL (force if still alive)
└── 4. DBWorkerManager.stop_all_workers() (if called)
    └── Stop all DB workers
```

---

## Key Architecture Decisions

### 1. Separate Processes (Not Threads, Not Async)

**Why**: 
- Prevents conflicts with Hypercorn's event loop
- True process isolation
- Can be forcefully killed if needed

**Implementation**:
- All workers use `multiprocessing.Process`
- Vectorization/File Watcher: `daemon=True`
- DB Worker: `daemon=False` (can be started from any process)

### 2. WorkerManager for Non-DB Workers

**Why**:
- Centralized management
- Consistent startup/shutdown
- Process monitoring and restart capability

**Implementation**:
- `WorkerManager` singleton
- Methods: `start_*_worker()`, `stop_*_worker()`, `register_worker()`
- All non-DB workers registered here

### 3. DBWorkerManager for DB Worker

**Why**:
- DB worker has different lifecycle (lazy, per-database)
- Socket-based IPC requires different management
- Can be started from any process (not just main)

**Implementation**:
- `DBWorkerManager` singleton
- Method: `get_or_start_worker(db_path)`
- Separate from WorkerManager

### 4. Synchronous Startup (No asyncio.run())

**Why**:
- Workers are separate processes, no need for async
- Avoids event loop conflicts
- Simpler code

**Implementation**:
- Workers start synchronously in `main()` before server
- No `asyncio.run()` or background threads
- Direct function calls

---

## Verification Checklist

- ✅ All workers use `multiprocessing.Process` (separate processes)
- ✅ Vectorization worker starts before server via WorkerManager
- ✅ File watcher worker starts before server via WorkerManager
- ✅ DB worker starts lazily via SQLiteDriverProxy
- ✅ All non-DB workers registered in WorkerManager
- ✅ DB worker registered in DBWorkerManager
- ✅ Workers can be forcefully killed (SIGKILL) if they don't stop
- ✅ No asyncio.run() conflicts
- ✅ No direct process creation in main.py (all through WorkerManager)

---

## Code Flow Diagrams

### Vectorization Worker Startup
```
main()
  └─> startup_vectorization_worker()
      └─> WorkerManager.start_vectorization_worker()
          └─> multiprocessing.Process.start()
              └─> WorkerManager.register_worker()
```

### File Watcher Worker Startup
```
main()
  └─> startup_file_watcher_worker()
      └─> WorkerManager.start_file_watcher_worker()
          └─> multiprocessing.Process.start()
              └─> WorkerManager.register_worker()
```

### DB Worker Startup (Lazy)
```
MCP Command
  └─> CodeDatabase()
      └─> SQLiteDriverProxy.connect()
          └─> DBWorkerManager.get_or_start_worker()
              └─> multiprocessing.Process.start()
                  └─> Store in DBWorkerManager._workers
```

---

## Summary

| Worker | Startup Moment | Manager | Process Type | Daemon |
|--------|---------------|---------|--------------|--------|
| Vectorization | Before server (sync) | WorkerManager | multiprocessing.Process | Yes |
| File Watcher | Before server (sync) | WorkerManager | multiprocessing.Process | Yes |
| DB Worker | Lazy (on DB connect) | DBWorkerManager | multiprocessing.Process | No |

**All workers are separate processes, managed through their respective managers, with guaranteed termination (SIGKILL if needed).**
