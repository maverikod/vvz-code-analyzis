# Worker Manager - Единый менеджер воркеров

**Автор**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Дата создания**: 2024-12-19

## Обзор

`WorkerManager` - это единый менеджер для управления всеми фоновыми воркерами в системе `code-analysis-server`. Он обеспечивает:

1. **Регистрацию всех воркеров** при их запуске
2. **Отслеживание процессов** по типу и PID
3. **Корректное завершение** всех воркеров при остановке сервера
4. **Предотвращение накопления процессов** при перезапусках

## Проблема

До внедрения `WorkerManager` при остановке сервера дочерние процессы воркеров не завершались автоматически, что приводило к их накоплению. Это создавало проблемы:

- Накопление процессов воркеров при перезапусках
- Утечки ресурсов
- Сложность отладки и мониторинга

## Решение

`WorkerManager` решает эти проблемы, предоставляя единый механизм управления жизненным циклом всех воркеров.

## Архитектура

### Компоненты

1. **WorkerManager** (`code_analysis/core/worker_manager.py`)
   - Singleton для глобального доступа
   - Регистрация и отслеживание воркеров
   - Graceful shutdown всех воркеров

2. **Интеграция с воркерами**:
   - `VectorizationWorker` - регистрируется в `main.py`
   - `FileWatcherWorker` - регистрируется в `main.py`
   - `RepairWorker` - регистрируется в `RepairWorkerManager`
   - `SQLiteDriverProxy` (AsyncQueueSystem) - регистрируется в `sqlite_proxy.py`

3. **Механизмы остановки**:
   - `atexit.register()` - cleanup при завершении процесса
   - Signal handlers (SIGTERM, SIGINT) - graceful shutdown

## Использование

### Регистрация воркера

```python
from code_analysis.core.worker_manager import get_worker_manager

worker_manager = get_worker_manager()

# Регистрация процесса-воркера
process = multiprocessing.Process(target=worker_function)
process.start()

worker_manager.register_worker(
    "vectorization",
    {
        "pid": process.pid,
        "process": process,
        "name": f"vectorization_{project_id}",
    }
)
```

### Регистрация очереди (AsyncQueueSystem)

```python
from code_analysis.core.worker_manager import get_worker_manager

worker_manager = get_worker_manager()

# Регистрация очереди
queue_system = AsyncQueueSystem(...)
await queue_system.start()

worker_manager.register_worker(
    "sqlite_queue",
    {
        "queue_system": queue_system,
        "name": f"sqlite_queue_{id(queue_system)}",
        "db_path": str(db_path),
    }
)
```

### Получение статуса воркеров

```python
from code_analysis.core.worker_manager import get_worker_manager

worker_manager = get_worker_manager()
status = worker_manager.get_worker_status()

print(f"Total workers: {status['total_workers']}")
for worker_type, type_info in status['by_type'].items():
    print(f"{worker_type}: {type_info['count']} workers")
```

### Остановка воркеров

```python
from code_analysis.core.worker_manager import get_worker_manager

worker_manager = get_worker_manager()

# Остановка всех воркеров
result = worker_manager.stop_all_workers(timeout=30.0)

# Остановка воркеров определенного типа
result = worker_manager.stop_worker_type("vectorization", timeout=10.0)
```

## Типы воркеров

Система поддерживает следующие типы воркеров:

1. **`vectorization`** - Воркер векторизации кода
2. **`file_watcher`** - Воркер отслеживания изменений файлов
3. **`repair`** - Воркер восстановления целостности БД
4. **`sqlite_queue`** - Очередь для операций с SQLite БД

## Автоматическая остановка

`WorkerManager` автоматически останавливает все воркеры при:

1. **Завершении процесса сервера** - через `atexit.register()`
2. **Получении сигналов** - SIGTERM, SIGINT
3. **Явном вызове** - `stop_all_workers()`

## Интеграция с сервером

В `code_analysis/main.py`:

```python
from code_analysis.core.worker_manager import get_worker_manager

# Инициализация
worker_manager = get_worker_manager()
app.state.worker_manager = worker_manager

# Регистрация shutdown handlers
import atexit
import signal

def cleanup_workers():
    worker_manager.stop_all_workers(timeout=30.0)

atexit.register(cleanup_workers)
signal.signal(signal.SIGTERM, lambda s, f: cleanup_workers())
signal.signal(signal.SIGINT, lambda s, f: cleanup_workers())
```

## API Reference

### WorkerManager

#### `get_instance() -> WorkerManager`
Получить singleton экземпляр менеджера.

#### `register_worker(worker_type: str, process_info: Dict[str, Any]) -> None`
Зарегистрировать воркер.

**Параметры**:
- `worker_type`: Тип воркера (например, 'vectorization')
- `process_info`: Словарь с информацией о воркере:
  - `pid`: Process ID (для процессов)
  - `process`: multiprocessing.Process (опционально)
  - `queue_system`: AsyncQueueSystem (опционально)
  - `worker`: Экземпляр воркера (опционально)
  - `name`: Человекочитаемое имя (опционально)

#### `unregister_worker(worker_type: str, pid: Optional[int] = None) -> None`
Удалить воркер из реестра.

#### `get_worker_status() -> Dict[str, Any]`
Получить статус всех воркеров.

**Возвращает**:
```python
{
    "total_workers": int,
    "by_type": {
        "worker_type": {
            "count": int,
            "pids": List[int],
            "names": List[str],
        }
    },
    "workers": [
        {
            "type": str,
            "pid": int,
            "name": str,
            "alive": bool,
            "registered_at": float,
        }
    ]
}
```

#### `stop_worker_type(worker_type: str, timeout: float = 10.0) -> Dict[str, Any]`
Остановить все воркеры определенного типа.

**Возвращает**:
```python
{
    "success": bool,
    "stopped": int,
    "failed": int,
    "errors": List[str],
    "message": str,
}
```

#### `stop_all_workers(timeout: float = 30.0) -> Dict[str, Any]`
Остановить все зарегистрированные воркеры.

**Возвращает**:
```python
{
    "success": bool,
    "total_stopped": int,
    "total_failed": int,
    "by_type": Dict[str, Dict],
    "errors": List[str],
    "message": str,
}
```

#### `stop_all_workers_async(timeout: float = 30.0) -> Dict[str, Any]`
Асинхронная версия `stop_all_workers()`.

## Тестирование

Тесты находятся в `tests/test_worker_manager.py`:

```bash
pytest tests/test_worker_manager.py -v
```

## Лучшие практики

1. **Всегда регистрируйте воркеры** при их запуске
2. **Используйте уникальные имена** для воркеров
3. **Обрабатывайте ошибки** при регистрации/остановке
4. **Используйте таймауты** для graceful shutdown
5. **Мониторьте статус** воркеров через `get_worker_status()`

## Примеры

### Пример: Регистрация воркера векторизации

```python
from code_analysis.core.worker_manager import get_worker_manager
import multiprocessing

def start_vectorization_worker():
    worker_manager = get_worker_manager()
    
    process = multiprocessing.Process(
        target=run_vectorization_worker,
        args=(db_path, project_id, ...),
        daemon=True,
    )
    process.start()
    
    worker_manager.register_worker(
        "vectorization",
        {
            "pid": process.pid,
            "process": process,
            "name": f"vectorization_{project_id}",
        }
    )
```

### Пример: Регистрация очереди SQLite

```python
from code_analysis.core.worker_manager import get_worker_manager
from queuemgr.async_simple_api import AsyncQueueSystem

async def initialize_sqlite_queue():
    worker_manager = get_worker_manager()
    
    queue_system = AsyncQueueSystem(
        registry_path="data/queuemgr_registry.jsonl",
        shutdown_timeout=30.0,
    )
    await queue_system.start()
    
    worker_manager.register_worker(
        "sqlite_queue",
        {
            "queue_system": queue_system,
            "name": f"sqlite_queue_{id(queue_system)}",
            "db_path": str(db_path),
        }
    )
```

## Заключение

`WorkerManager` обеспечивает единообразный механизм управления всеми фоновыми воркерами, предотвращая накопление процессов и обеспечивая корректное завершение при остановке сервера.

