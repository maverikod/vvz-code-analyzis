# Worker Management Architecture Analysis

**Generated**: 2026-01-11  
**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com

## Requirements Check

### 0. ✅ Все воркеры должны запускаться как отдельные процессы (не потоки, не async задачи)

**Current State**:
- ✅ **DB Worker**: Запускается как `multiprocessing.Process` (db_worker_manager.py:204, daemon=False)
- ✅ **Vectorization Worker**: Запускается как `multiprocessing.Process` (worker_manager.py:start_vectorization_worker, daemon=True)
- ✅ **File Watcher Worker**: Запускается как `multiprocessing.Process` (worker_manager.py:start_file_watcher_worker, daemon=True)

**Status**: ✅ **CORRECT** - Все воркеры запускаются как отдельные процессы через `multiprocessing.Process`

**Note**: Внутри воркеров могут использоваться async функции (asyncio.run()), но это нормально - каждый воркер это отдельный процесс со своим event loop, не конфликтует с Hypercorn.

### 1. ✅ ВСЕ операции по старту/останову воркеров должен проводить ТОЛЬКО менеджер воркеров

**Current State**: 
- ✅ `WorkerManager` имеет методы для запуска воркеров:
  - `start_vectorization_worker(...)` - запуск vectorization worker
  - `start_file_watcher_worker(...)` - запуск file watcher worker
  - `stop_worker_type(...)` - остановка воркеров определенного типа
  - `stop_all_workers()` - остановка всех воркеров
  - `register_worker()` - регистрация воркера
- ✅ Все методы используют `multiprocessing.Process` для создания процессов
- ✅ `worker_launcher.py` удален - вся логика перенесена в `WorkerManager`

**Status**: ✅ **CORRECT** - Все операции по старту/останову воркеров проводятся через `WorkerManager`

### 2. ✅ Через менеджер воркеров ВСЕ воркеры КРОМЕ воркера базы данных должны стартовать при старте системы

**Current State**:
- ✅ Воркеры запускаются в `main()` при старте системы (lines 977-1005)
- ✅ Функции `startup_vectorization_worker()` и `startup_file_watcher_worker()` используют `WorkerManager`:
  ```python
  # In startup_vectorization_worker() (line 663)
  worker_manager = get_worker_manager()
  result = worker_manager.start_vectorization_worker(...)
  
  # In startup_file_watcher_worker() (line 808)
  worker_manager = get_worker_manager()
  result = worker_manager.start_file_watcher_worker(...)
  ```
- ✅ Воркеры запускаются синхронно перед запуском сервера (line 1017)
- ✅ DB worker НЕ запускается при старте - запускается лениво через SQLiteDriverProxy.connect()

**Status**: ✅ **CORRECT** - Все не-DB воркеры стартуют при старте системы через `WorkerManager`

### 3. ✅ Воркер базы данных должен запускаться SQLite драйвером

**Current State**:
- ✅ DB worker запускается лениво (lazy initialization) через SQLite драйвер:
  - `SQLiteDriverProxy.connect()` (sqlite_proxy.py:100) - вызывается при подключении к БД
  - `_start_worker()` (sqlite_proxy.py:129) - внутренний метод драйвера
  - `DBWorkerManager.get_or_start_worker()` (db_worker_manager.py:79) - менеджер DB воркеров
- ✅ DB worker НЕ запускается при старте системы - только когда требуется подключение к БД
- ✅ Это правильная архитектура - драйвер управляет своим воркером

**Status**: ✅ **CORRECT** - DB worker запускается SQLite драйвером при необходимости

### 4. ✅ Должна соблюдаться цепочка: Command -> CodeDatabase -> SpecificDriver

**Current State**:
- Commands создают `CodeDatabase`:
  ```python
  # In BaseMCPCommand (line 210)
  db = CodeDatabase(driver_config=driver_config)
  ```
- `CodeDatabase` создает драйвер:
  ```python
  # In CodeDatabase.__init__ (line 130)
  self.driver = create_driver(driver_type, driver_cfg)
  ```
- Драйвер (например, `SQLiteDriverProxy`) запускает DB worker при `connect()`

**Status**: ✅ **CORRECT**

## Worker Process Architecture

### ✅ All Workers Use multiprocessing.Process

**Current Implementation**:
- **DB Worker**: `multiprocessing.Process` with `daemon=False` (db_worker_manager.py:204)
- **Vectorization Worker**: `multiprocessing.Process` with `daemon=True` (worker_manager.py:start_vectorization_worker)
- **File Watcher Worker**: `multiprocessing.Process` with `daemon=True` (worker_manager.py:start_file_watcher_worker)

**Why Separate Processes**:
- Avoids conflicts with Hypercorn's event loop
- Each worker has its own memory space
- Workers can use async internally (asyncio.run()) without affecting main server
- Process isolation prevents crashes from affecting main server

**Note**: Inside workers, async functions (asyncio.run()) are used, but this is safe because each worker is a separate process with its own event loop.

## Current Architecture

### Worker Startup Flow (Current - CORRECT)

```
main() - System Startup
  ↓
startup_vectorization_worker()  # Function in main.py (line 523)
  ↓
WorkerManager.get_instance()  # Get singleton
  ↓
WorkerManager.start_vectorization_worker()  # Full management
  ↓
multiprocessing.Process.start()  # Internal to WorkerManager
  ↓
WorkerManager.register_worker()  # Automatic registration

main() - System Startup
  ↓
startup_file_watcher_worker()  # Function in main.py (line 692)
  ↓
WorkerManager.get_instance()  # Get singleton
  ↓
WorkerManager.start_file_watcher_worker()  # Full management
  ↓
multiprocessing.Process.start()  # Internal to WorkerManager
  ↓
WorkerManager.register_worker()  # Automatic registration

Command -> CodeDatabase -> SQLiteDriverProxy.connect()
  ↓
SQLiteDriverProxy._start_worker()  # Internal method
  ↓
DBWorkerManager.get_or_start_worker()  # DB worker manager
  ↓
multiprocessing.Process.start()  # DB worker process
```

## Implementation Details

### WorkerManager Methods

**File**: `code_analysis/core/worker_manager.py`

**Implemented Methods**:
- `start_vectorization_worker(...)` - Starts vectorization worker as separate process
- `start_file_watcher_worker(...)` - Starts file watcher worker as separate process
- `stop_worker_type(...)` - Stops all workers of specific type with timeout
- `stop_all_workers(...)` - Stops all registered workers
- `register_worker(...)` - Registers worker in manager
- `get_worker_status()` - Returns status of all workers

**All methods use `multiprocessing.Process`** to ensure workers don't conflict with Hypercorn's event loop.

### System Startup Flow

**File**: `code_analysis/main.py`

**Implementation**:
- Workers start synchronously in `main()` before server starts (lines 977-1005)
- `startup_vectorization_worker()` function calls `WorkerManager.get_instance().start_vectorization_worker(...)`
- `startup_file_watcher_worker()` function calls `WorkerManager.get_instance().start_file_watcher_worker(...)`
- DB worker is NOT started at system startup - it starts lazily when database connection is needed

## Code Locations

### Current Worker Startup
- **main.py**: Lines 523-835 (startup functions that call WorkerManager)
- **worker_manager.py**: Lines 748-898 (start_file_watcher_worker, start_vectorization_worker)
- **worker_manager.py**: Lines 95-117 (register_worker - automatic registration)

### DB Worker Startup (Correct)
- **sqlite_proxy.py**: Line 129 (`_start_worker()`)
- **db_worker_manager.py**: Line 79 (`get_or_start_worker()`)

### Command -> Database Chain (Correct)
- **base_mcp_command.py**: Line 210 (`CodeDatabase(driver_config)`)
- **database/base.py**: Line 130 (`create_driver()`)
- **db_driver/sqlite_proxy.py**: Line 100 (`connect()`)

## Summary

| Requirement | Status | Implementation |
|------------|--------|----------------|
| 0. All workers as separate processes | ✅ | All workers use multiprocessing.Process |
| 1. All worker operations via WorkerManager | ✅ | All start/stop operations through WorkerManager methods |
| 2. All non-DB workers start via WorkerManager at system startup | ✅ | Workers start in main() before server via WorkerManager |
| 3. DB worker started by SQLite driver | ✅ | DB worker started lazily by SQLiteDriverProxy.connect() |
| 4. Chain: Command -> CodeDatabase -> Driver | ✅ | Correct architecture chain |

## Implementation Status

### ✅ Completed

1. ✅ **Workers as separate processes**: All workers use `multiprocessing.Process`
2. ✅ **WorkerManager has full control**: All start/stop operations through WorkerManager
3. ✅ **Workers start at system startup**: Non-DB workers start in `main()` before server via WorkerManager
4. ✅ **DB Worker**: Started lazily by SQLiteDriverProxy driver
5. ✅ **Command -> CodeDatabase -> Driver**: Correct architecture chain
6. ✅ **worker_launcher.py removed**: All logic moved to WorkerManager
7. ✅ **Process termination guarantee**: WorkerManager forcefully kills processes that don't stop after timeout

### Key Requirements

1. ✅ **Воркеры должны стартовать при старте системы (через менеджер)**
   - Реализовано: Воркеры запускаются в `main()` при старте системы через `WorkerManager`
   - Location: `main.py` lines 977-1005
   - Method: `startup_vectorization_worker()` и `startup_file_watcher_worker()` используют `WorkerManager.get_instance().start_*_worker()`

2. ✅ **Воркер базы должен запускаться SQLite драйвером**
   - Реализовано: DB worker запускается лениво через `SQLiteDriverProxy.connect()`
   - Location: `sqlite_proxy.py` line 100 (`connect()`) -> line 129 (`_start_worker()`) -> `db_worker_manager.py` line 79
   - Method: Драйвер управляет своим воркером через `DBWorkerManager`
