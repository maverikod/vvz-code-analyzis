# Рефакторинг SQLite драйвера: вынос операций БД в отдельный процесс

**Автор**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Дата создания**: 2024-12-19  
**Статус**: Планирование

## Проблема

Текущая реализация SQLite драйвера (`code_analysis/core/db_driver/sqlite.py`) создает соединение с БД в одном потоке, но используется из разных потоков и процессов. Это приводит к ошибкам:

```
sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread.
```

Хотя было добавлено `check_same_thread=False`, это не решает проблему полностью, так как:
1. SQLite не является полностью thread-safe для конкурентных записей
2. При использовании `run_in_executor` соединение может использоваться из разных процессов
3. Блокировки на уровне `CodeDatabase` не гарантируют безопасность при работе из разных процессов

## Решение

Вынести все операции чтения/записи SQLite БД в отдельный процесс, который будет обрабатывать запросы через очередь заданий (queuemgr). Это обеспечит:

1. **Изоляцию соединения**: SQLite соединение будет существовать только в одном процессе
2. **Прозрачность для верхних уровней**: Интерфейс `BaseDatabaseDriver` останется неизменным
3. **Автоматическое решение проблем с потоками**: Все запросы будут сериализованы через очередь
4. **Масштабируемость**: Легко добавить пул процессов для обработки запросов

## Архитектура

### Текущая архитектура

```
┌─────────────────────────────────────┐
│      CodeDatabase                    │
│  ┌───────────────────────────────┐  │
│  │   BaseDatabaseDriver          │  │
│  │   ┌─────────────────────────┐ │
│  │  │   SQLiteDriver           │ │  │
│  │  │   (прямое соединение)    │ │  │
│  │  └─────────────────────────┘ │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
         │
         │ (используется из разных потоков/процессов)
         ▼
    SQLite Database
```

### Новая архитектура

```
┌─────────────────────────────────────┐
│      CodeDatabase                    │
│  ┌───────────────────────────────┐  │
│  │   BaseDatabaseDriver          │  │
│  │   ┌─────────────────────────┐ │  │
│  │  │   SQLiteDriverProxy      │ │  │
│  │  │   (RPC клиент)           │ │  │
│  │  └─────────────────────────┘ │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
         │
         │ (IPC через queuemgr)
         ▼
┌─────────────────────────────────────┐
│      QueueManager                    │
│  ┌───────────────────────────────┐  │
│  │   Job Queue                   │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
         │
         │ (задания)
         ▼
┌─────────────────────────────────────┐
│   SQLiteWorkerProcess               │
│  ┌───────────────────────────────┐  │
│  │   SQLiteDatabaseJob           │  │
│  │   ┌─────────────────────────┐ │  │
│  │  │   SQLiteDriver            │ │  │
│  │  │   (реальное соединение)  │ │  │
│  │  └─────────────────────────┘ │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
         │
         ▼
    SQLite Database
```

## Компоненты

### 1. SQLiteDriverProxy

**Файл**: `code_analysis/core/db_driver/sqlite_proxy.py`

Прокси-драйвер, который реализует интерфейс `BaseDatabaseDriver`, но вместо прямого обращения к БД отправляет задания в очередь.

**Основные методы**:
- `connect(config)` - инициализирует подключение к QueueManager
- `execute(sql, params)` - отправляет задание на выполнение SQL
- `fetchone(sql, params)` - отправляет задание на получение одной строки
- `fetchall(sql, params)` - отправляет задание на получение всех строк
- `commit()` - отправляет задание на коммит транзакции
- `rollback()` - отправляет задание на откат транзакции
- `lastrowid()` - отправляет задание на получение последнего ID
- `get_table_info(table_name)` - отправляет задание на получение информации о таблице

**Особенности**:
- Использует `AsyncQueueSystem` из `queuemgr` для асинхронной работы
- Кэширует соединение с QueueManager
- Обрабатывает ошибки и таймауты
- Поддерживает синхронный и асинхронный интерфейсы

### 2. SQLiteDatabaseJob

**Файл**: `code_analysis/core/db_driver/sqlite_worker_job.py`

Job для queuemgr, который выполняет операции с БД в отдельном процессе.

**Параметры задания**:
```python
{
    "operation": "execute" | "fetchone" | "fetchall" | "commit" | "rollback" | "lastrowid" | "get_table_info",
    "db_path": str,  # путь к БД
    "sql": str,  # SQL запрос (для execute, fetchone, fetchall)
    "params": tuple,  # параметры запроса (опционально)
    "table_name": str,  # имя таблицы (для get_table_info)
}
```

**Результат задания**:
```python
{
    "success": bool,
    "result": Any,  # результат операции
    "error": str | None,  # сообщение об ошибке (если есть)
}
```

**Особенности**:
- Создает SQLite соединение при старте job'а
- Выполняет операцию с БД
- Возвращает результат или ошибку
- Закрывает соединение при завершении

### 3. SQLiteWorkerProcess

**Файл**: `code_analysis/core/db_driver/sqlite_worker.py`

Процесс-воркер, который управляет жизненным циклом SQLiteDatabaseJob.

**Функциональность**:
- Запускает QueueManager с SQLiteDatabaseJob
- Управляет пулом процессов для обработки запросов
- Обеспечивает graceful shutdown
- Логирует операции

### 4. Конфигурация

**Файл**: `code_analysis/core/db_driver/config.py`

Конфигурация для SQLite драйвера с поддержкой прокси-режима.

```python
{
    "type": "sqlite",
    "config": {
        "path": str,  # путь к БД
        "use_proxy": bool,  # использовать прокси-режим (по умолчанию False для обратной совместимости)
        "worker_config": {
            "registry_path": str,  # путь к реестру queuemgr
            "max_workers": int,  # максимальное количество воркеров
            "command_timeout": float,  # таймаут для команд
        }
    }
}
```

## План реализации

### Этап 1: Создание SQLiteDatabaseJob

1. Создать `code_analysis/core/db_driver/sqlite_worker_job.py`
2. Реализовать класс `SQLiteDatabaseJob(QueueJobBase)`
3. Реализовать метод `execute()` с обработкой всех типов операций
4. Добавить обработку ошибок и валидацию параметров
5. Написать тесты для job'а

**Критерии готовности**:
- Job успешно выполняет все типы операций с БД
- Обрабатывает ошибки корректно
- Возвращает результаты в правильном формате
- Тесты покрывают все операции

**Статус**: ✅ Выполнено

### Этап 2: Создание SQLiteDriverProxy

1. Создать `code_analysis/core/db_driver/sqlite_proxy.py`
2. Реализовать класс `SQLiteDriverProxy(BaseDatabaseDriver)`
3. Реализовать все методы интерфейса через отправку заданий
4. Добавить кэширование соединения с QueueManager
5. Реализовать обработку таймаутов и ошибок
6. Написать тесты для прокси-драйвера

**Критерии готовности**:
- Все методы интерфейса реализованы
- Прокси корректно отправляет задания в очередь
- Обрабатывает результаты и ошибки
- Тесты покрывают все методы

**Статус**: ✅ Выполнено

### Этап 3: Создание единого менеджера воркеров

**КРИТИЧЕСКИ ВАЖНО**: Все воркеры должны регистрироваться в едином менеджере и корректно завершаться при остановке сервера.

1. Создать `code_analysis/core/worker_manager.py`:
   - Класс `WorkerManager` для управления всеми воркерами
   - Регистрация воркеров по типам
   - Отслеживание процессов (PID)
   - Graceful shutdown всех воркеров
   - Интеграция с lifespan функциями сервера

2. Типы воркеров для управления:
   - `vectorization` - VectorizationWorker
   - `file_watcher` - FileWatcherWorker
   - `repair` - RepairWorker
   - `sqlite_queue` - AsyncQueueSystem (для SQLiteDatabaseJob)

3. Методы WorkerManager:
   - `register_worker(worker_type: str, process_info: Dict)` - регистрация воркера
   - `unregister_worker(worker_type: str, pid: int)` - удаление из реестра
   - `stop_all_workers(timeout: float = 30.0)` - остановка всех воркеров
   - `stop_worker_type(worker_type: str, timeout: float = 10.0)` - остановка воркеров типа
   - `get_worker_status()` - статус всех воркеров
   - `cleanup_on_shutdown()` - очистка при завершении

4. Интеграция с lifespan:
   - В `code_analysis/main.py` добавить lifespan функцию
   - При startup: инициализация WorkerManager
   - При shutdown: вызов `stop_all_workers()`

**Критерии готовности**:
- WorkerManager создан и работает
- Все воркеры регистрируются при запуске
- Все воркеры корректно завершаются при остановке сервера
- Нет накопления процессов воркеров
- Интеграция с lifespan выполнена

**Статус**: ⏳ В процессе

### Этап 4: Интеграция воркеров с WorkerManager

1. Обновить VectorizationWorker:
   - Регистрация в WorkerManager при запуске
   - Удаление из реестра при остановке
   - Обработка сигналов для graceful shutdown

2. Обновить FileWatcherWorker:
   - Регистрация в WorkerManager при запуске
   - Удаление из реестра при остановке
   - Обработка сигналов для graceful shutdown

3. Обновить RepairWorker:
   - Регистрация в WorkerManager при запуске
   - Удаление из реестра при остановке
   - Обработка сигналов для graceful shutdown

4. Обновить SQLiteDriverProxy:
   - Регистрация AsyncQueueSystem в WorkerManager при connect()
   - Остановка очереди при disconnect()
   - Обработка shutdown через WorkerManager

**Критерии готовности**:
- Все воркеры интегрированы с WorkerManager
- Нет дублирования логики остановки
- Единообразный механизм управления жизненным циклом
- Тесты проверяют корректное завершение всех воркеров

**Статус**: ⏳ Ожидает выполнения

### Этап 5: Интеграция с CodeDatabase

1. Модифицировать `code_analysis/core/db_driver/__init__.py` для поддержки прокси-режима
2. Добавить конфигурацию `use_proxy` в драйвер
3. Обновить `CodeDatabase` для использования прокси при необходимости
4. Добавить автоматический запуск QueueManager при использовании прокси
5. Обновить документацию

**Критерии готовности**:
- CodeDatabase может работать с прокси-драйвером
- Автоматический запуск/остановка QueueManager через WorkerManager
- Обратная совместимость сохранена (по умолчанию используется прямой драйвер)
- Документация обновлена

**Статус**: ✅ Выполнено (прокси-драйвер зарегистрирован и интегрирован)

### Этап 6: Тестирование и оптимизация

1. Написать интеграционные тесты
2. Протестировать работу из разных потоков/процессов
3. Измерить производительность
4. Оптимизировать при необходимости
5. Обновить документацию

**Критерии готовности**:
- Все тесты проходят
- Работа из разных потоков/процессов работает корректно
- Производительность приемлема
- Документация полная

**Статус**: ✅ Частично выполнено (созданы базовые тесты для WorkerManager)

1. Написать интеграционные тесты
2. Протестировать работу из разных потоков/процессов
3. Измерить производительность
4. Оптимизировать при необходимости
5. Обновить документацию

**Критерии готовности**:
- Все тесты проходят
- Работа из разных потоков/процессов работает корректно
- Производительность приемлема
- Документация полная

### Этап 7: Миграция и деплой

1. Обновить конфигурацию по умолчанию для использования прокси
2. Обновить документацию по миграции
3. Протестировать на реальных данных
4. Выполнить миграцию

**Критерии готовности**:
- Миграция выполнена успешно
- Все команды работают корректно
- Документация обновлена

## Детали реализации

### SQLiteDatabaseJob.execute()

```python
def execute(self) -> None:
    """Execute database operation based on params."""
    operation = self.params.get("operation")
    db_path = self.params.get("db_path")
    
    if not operation or not db_path:
        raise ValidationError("operation and db_path are required")
    
    # Create connection
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    
    try:
        if operation == "execute":
            sql = self.params.get("sql")
            params = self.params.get("params")
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            result = None
            
        elif operation == "fetchone":
            sql = self.params.get("sql")
            params = self.params.get("params")
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            row = cursor.fetchone()
            result = dict(row) if row else None
            
        elif operation == "fetchall":
            sql = self.params.get("sql")
            params = self.params.get("params")
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            rows = cursor.fetchall()
            result = [dict(row) for row in rows]
            
        elif operation == "commit":
            conn.commit()
            result = None
            
        elif operation == "rollback":
            conn.rollback()
            result = None
            
        elif operation == "lastrowid":
            cursor = conn.cursor()
            result = cursor.lastrowid
            
        elif operation == "get_table_info":
            table_name = self.params.get("table_name")
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            rows = cursor.fetchall()
            columns = ["cid", "name", "type", "notnull", "dflt_value", "pk"]
            result = [dict(zip(columns, row)) for row in rows]
            
        else:
            raise ValueError(f"Unknown operation: {operation}")
        
        self.set_result({
            "success": True,
            "result": result,
            "error": None
        })
        
    except Exception as e:
        self.set_result({
            "success": False,
            "result": None,
            "error": str(e)
        })
    finally:
        conn.close()
```

### SQLiteDriverProxy.execute()

```python
async def _execute_operation(self, operation: str, **kwargs) -> Any:
    """Execute database operation via queue."""
    if not self._queue_system:
        raise RuntimeError("Queue system not initialized")
    
    # Generate unique job ID
    job_id = f"sqlite_{operation}_{uuid.uuid4().hex[:8]}"
    
    # Prepare job params
    params = {
        "operation": operation,
        "db_path": str(self.db_path),
        **kwargs
    }
    
    # Add job to queue
    await self._queue_system.add_job(SQLiteDatabaseJob, job_id, params)
    
    # Start job
    await self._queue_system.start_job(job_id)
    
    # Wait for completion
    max_wait = self.command_timeout or 30.0
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        status = await self._queue_system.get_job_status(job_id)
        
        if status["status"] == "completed":
            result = status.get("result", {})
            if result.get("success"):
                return result.get("result")
            else:
                error = result.get("error", "Unknown error")
                raise RuntimeError(f"Database operation failed: {error}")
        elif status["status"] == "error":
            raise RuntimeError(f"Job failed: {status.get('error', 'Unknown error')}")
        
        await asyncio.sleep(0.1)
    
    # Timeout
    await self._queue_system.stop_job(job_id)
    raise TimeoutError(f"Database operation timed out after {max_wait}s")

def execute(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> None:
    """Execute SQL statement."""
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        self._execute_operation("execute", sql=sql, params=params)
    )
```

## Обратная совместимость

Для обеспечения обратной совместимости:

1. По умолчанию используется прямой `SQLiteDriver` (без прокси)
2. Прокси-режим включается только при явном указании `use_proxy=True` в конфигурации
3. Существующий код продолжает работать без изменений
4. Миграция на прокси-режим выполняется постепенно

## Производительность

Ожидаемые изменения производительности:

1. **Задержка**: Каждая операция будет иметь дополнительную задержку из-за IPC (~1-10ms)
2. **Пропускная способность**: Может быть ниже из-за сериализации через очередь
3. **Параллелизм**: Улучшится за счет изоляции соединений

Для оптимизации:
- Использовать пул воркеров для параллельной обработки
- Батчинг операций (группировка нескольких операций в одно задание)
- Кэширование часто используемых запросов

## Безопасность

1. **Изоляция**: Каждое задание выполняется в отдельном процессе
2. **Валидация**: Все параметры валидируются перед выполнением
3. **Таймауты**: Операции имеют таймауты для предотвращения зависаний
4. **Очистка**: Соединения закрываются после выполнения задания

## Тестирование

Необходимые тесты:

1. **Unit тесты**:
   - SQLiteDatabaseJob для всех типов операций
   - SQLiteDriverProxy для всех методов интерфейса
   - Обработка ошибок и таймаутов

2. **Интеграционные тесты**:
   - Работа из разных потоков
   - Работа из разных процессов
   - Параллельные запросы
   - Обработка ошибок

3. **Нагрузочные тесты**:
   - Производительность при высокой нагрузке
   - Масштабируемость
   - Устойчивость к сбоям

## Документация

Необходимо обновить:

1. `docs/AI_TOOL_USAGE_RULES.md` - добавить информацию о прокси-режиме
2. `docs/COMMAND_ARCHITECTURE.md` - описать новую архитектуру
3. `README.md` - добавить информацию о конфигурации
4. Примеры использования прокси-драйвера

## Управление жизненным циклом воркеров

### Проблема

При остановке сервера дочерние процессы воркеров не завершаются автоматически, что приводит к их накоплению. Необходим единообразный механизм управления всеми воркерами.

### Решение: WorkerManager

Создается единый менеджер воркеров, который:

1. **Регистрирует все воркеры** при их запуске
2. **Отслеживает процессы** по PID и типу
3. **Корректно завершает** все воркеры при остановке сервера
4. **Интегрируется с lifespan** функциями сервера

### Архитектура WorkerManager

```python
class WorkerManager:
    """Единый менеджер для всех воркеров системы."""
    
    def __init__(self):
        self._workers: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.Lock()
    
    def register_worker(
        self, 
        worker_type: str, 
        process_info: Dict[str, Any]
    ) -> None:
        """Зарегистрировать воркер."""
        
    def stop_all_workers(self, timeout: float = 30.0) -> Dict[str, Any]:
        """Остановить все воркеры."""
        
    def stop_worker_type(
        self, 
        worker_type: str, 
        timeout: float = 10.0
    ) -> Dict[str, Any]:
        """Остановить воркеры определенного типа."""
```

### Интеграция с воркерами

Все воркеры должны:

1. **Регистрироваться** в WorkerManager при запуске:
   ```python
   worker_manager.register_worker("vectorization", {
       "pid": process.pid,
       "type": "vectorization",
       "process": process,
       "worker": worker_instance
   })
   ```

2. **Удаляться** из реестра при остановке:
   ```python
   worker_manager.unregister_worker("vectorization", process.pid)
   ```

3. **Обрабатывать сигналы** для graceful shutdown:
   ```python
   signal.signal(signal.SIGTERM, lambda s, f: worker.stop())
   signal.signal(signal.SIGINT, lambda s, f: worker.stop())
   ```

### Интеграция с lifespan

В `code_analysis/main.py`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    worker_manager = WorkerManager.get_instance()
    app.state.worker_manager = worker_manager
    
    yield
    
    # Shutdown
    await worker_manager.stop_all_workers_async()
```

## Риски

1. **Производительность**: Дополнительная задержка из-за IPC
2. **Сложность**: Увеличение сложности системы
3. **Отладка**: Сложнее отлаживать проблемы в отдельном процессе
4. **Зависимости**: Зависимость от queuemgr
5. **Управление процессами**: Необходимость корректного завершения всех воркеров при остановке сервера

## Альтернативы

1. **Использование SQLite в WAL режиме**: Может улучшить параллелизм, но не решает проблему с потоками
2. **Использование connection pool**: Сложнее реализовать и не решает проблему с процессами
3. **Переход на другую БД**: PostgreSQL, MySQL - но это требует миграции данных

## Заключение

Рефакторинг SQLite драйвера с выносом операций в отдельный процесс решит проблемы с доступом из разных потоков/процессов и обеспечит масштабируемость системы. Реализация должна быть поэтапной с сохранением обратной совместимости.

