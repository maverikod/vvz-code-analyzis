# Анализ логов автозапуска воркеров

## Дата анализа: 2025-12-29

## Проблема
Воркеры не запускаются автоматически при старте сервера. Процесс останавливается на этапе создания CodeDatabase.

## Пошаговый анализ логов

### Успешные шаги:
1. ✅ **STEP 1**: Создание конфигурации драйвера - успешно
   ```
   [STEP 1] Creating driver config for db_path=/home/vasilyvz/projects/tools/code_analysis/data/code_analysis.db
   ```

2. ✅ **STEP 2**: Конфигурация драйвера создана - успешно
   ```
   [STEP 2] Driver config created: type=sqlite_proxy
   ```

3. ✅ **STEP 3**: Обновление конфигурации proxy-драйвера - успешно
   ```
   [STEP 3] Proxy driver config updated: timeout=60.0, poll_interval=1.0
   ```

4. ⚠️ **STEP 4**: Создание CodeDatabase - процесс останавливается
   ```
   [STEP 4] Creating CodeDatabase instance with driver_config
   ```
   **Проблема**: После этого шага нет логов из `CodeDatabase.__init__` или `create_driver`.

### Отсутствующие логи:
- Нет логов из `[CodeDatabase] __init__`
- Нет логов из `[create_driver]`
- Нет логов из `[SQLITE_PROXY] connect()`

### Наблюдения:
1. Процесс зависает при создании CodeDatabase
2. В регистре очереди (`queuemgr_registry.jsonl`) задания создаются со статусом 0 (созданы), но не обрабатываются
3. DB worker процесс не запускается автоматически
4. Нет процессов `python.*sqlite|python.*queuemgr|python.*worker`

### Ошибки в логах:
1. **Таймаут БД операций**: `Database operation 'execute' timed out after 60.0s`
2. **Ошибка ProcessControlError**: `cannot schedule new futures after shutdown` (одна попытка)

## Выводы (на основе полного traceback)

### Основная проблема:
**DB worker не запускается автоматически**, что приводит к таймаутам всех операций с БД.

### Детальный анализ:
1. ✅ **CodeDatabase создается успешно** - `CodeDatabase(driver_config=driver_config)` выполняется
2. ✅ **Driver инициализируется** - `driver.connect()` вызывается и завершается
3. ⚠️ **При создании схемы БД операция таймаутит**:
   - `_create_schema()` → `_execute()` → `driver.execute()`
   - `driver.execute()` → `_run_async()` → создается новый event loop в потоке
   - Операция добавляется в очередь (`queuemgr_registry.jsonl`), но **не обрабатывается**
   - Таймаут через 60 секунд: `Database operation 'execute' timed out after 60.0s`

### Корневая причина:
**AsyncQueueSystem не запускает DB worker процесс автоматически**. Задания создаются в очереди (статус 0 - "Job created"), но нет процесса, который их обрабатывает.

### Доказательства:
1. В `queuemgr_registry.jsonl` все задания имеют `"status": 0` (созданы, но не обработаны)
2. Нет процессов `python.*sqlite|python.*queuemgr|python.*worker`
3. Операции таймаутят через 60 секунд

### Рекомендации:
1. **Проверить документацию AsyncQueueSystem** - возможно, нужно явно запустить worker
2. **Добавить явный запуск DB worker** при инициализации proxy-драйвера
3. **Проверить конфигурацию queuemgr** - возможно, требуется дополнительная настройка
4. **Рассмотреть альтернативный подход** - запускать DB worker как отдельный процесс при старте сервера

## Следующие шаги:
1. Исследовать API AsyncQueueSystem для запуска worker
2. Добавить логирование в процесс запуска worker через AsyncQueueSystem
3. Проверить, требуется ли явная регистрация SQLiteDatabaseJob в AsyncQueueSystem
4. Рассмотреть возможность запуска DB worker как отдельного процесса при старте сервера

