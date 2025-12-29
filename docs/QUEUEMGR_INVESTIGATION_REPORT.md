# Исследование queuemgr и проблемы с DB worker

## Дата: 2025-12-29

## Архитектура queuemgr

### Компоненты:
1. **AsyncQueueSystem** - высокоуровневый API для работы с очередью
2. **AsyncProcessManager** - управляет процессом менеджера очереди
3. **run_async_process_manager** - точка входа в процесс менеджера
4. **JobQueue** - управляет жизненным циклом заданий
5. **QueueJobBase** - базовый класс для заданий, запускает их в отдельных процессах

### Поток выполнения:

```
AsyncQueueSystem.start()
  → AsyncProcessManager.start()
    → Process(target=run_async_process_manager) ✅ (должен запуститься)
      → JobQueue создается
      → response_queue.put({"status": "ready"}) ✅
      → Цикл ожидания команд из control_queue
        → process_command(job_queue, command, params)
          → job_queue.start_job(job_id)
            → job.start_process()
              → Process(target=_job_loop_static) ✅ (должен запуститься для каждого задания)
                → job.execute() ✅ (выполняется в дочернем процессе)
```

## Проблема

### Наблюдения из логов:
1. ✅ **AsyncQueueSystem.start() вызывается** - есть логи `[SQLITE_PROXY] Calling AsyncQueueSystem.start()`
2. ❓ **Нет логов о завершении start()** - нет логов `[SQLITE_PROXY] AsyncQueueSystem.start() completed`
3. ❌ **Нет процесса AsyncQueueManager** - `ps aux | grep AsyncQueueManager` не находит процесс
4. ❌ **Задания создаются, но не обрабатываются** - в `queuemgr_registry.jsonl` все задания со статусом 0

### Возможные причины:
1. **AsyncProcessManager.start() падает с ошибкой** - процесс не успевает запуститься
2. **Таймаут инициализации** - процесс запускается, но не успевает отправить "ready" за 10 секунд
3. **Проблема с multiprocessing в daemon потоке** - возможно, daemon поток не может создавать дочерние процессы
4. **Ошибка в run_async_process_manager** - процесс падает при инициализации

## Следующие шаги для диагностики:

1. ✅ Добавить логирование в AsyncProcessManager.start() для отслеживания запуска процесса
2. ✅ Проверить, не блокируется ли вызов await self._manager.start()
3. ✅ Добавить обработку исключений в _initialize_queue_async() для выявления ошибок
4. ⚠️ Проверить, можно ли создавать процессы из daemon потока

## Наблюдения после добавления логирования:

1. **Логи из SQLITE_PROXY не появляются** - даже через print()
2. **Логи из CodeDatabase и create_driver не появляются** - даже через print()
3. **Процесс останавливается на STEP 4** - создание CodeDatabase
4. **Из traceback видно, что execute() вызывается** - значит connect() был вызван
5. **Нет процесса AsyncQueueManager** - процесс менеджера не запускается

## Выводы:

### Проблема с логированием:
- Логи из `code_analysis.core.db_driver.sqlite_proxy` не выводятся (logger не имеет handlers)
- Логи из `code_analysis.core.database.base` не выводятся
- Даже print() не работает - возможно, вывод перенаправлен или процесс зависает

### Проблема с AsyncQueueSystem:
- `AsyncQueueSystem.start()` вызывается, но процесс менеджера не запускается
- Возможные причины:
  1. **Daemon поток не может создавать дочерние процессы** - Python multiprocessing ограничение
  2. **Таймаут инициализации** - процесс не успевает отправить "ready" за 10 секунд
  3. **Ошибка в run_async_process_manager** - процесс падает при инициализации

### Рекомендации:

1. **Проверить, можно ли создавать процессы из daemon потока** - возможно, нужно использовать обычный поток
2. **Добавить логирование в файл напрямую** - обойти проблему с logger handlers
3. **Проверить, не блокируется ли await self._queue_system.start()** - возможно, процесс зависает
4. **Рассмотреть альтернативный подход** - запускать DB worker как отдельный процесс при старте сервера, а не через AsyncQueueSystem

