# План реализации repair_database с воркером

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-12-26

## Цель

Создать систему восстановления целостности базы данных с отдельным воркер-процессом и командами управления.

## Требования

1. ✅ Команда `repair_database` для восстановления целостности БД
2. ✅ Отдельный воркер-процесс для автоматического восстановления
3. ✅ Команды управления воркером (start/stop/status)
4. ✅ Автоматическая остановка всех воркеров перед восстановлением
5. ✅ Graceful shutdown для воркера
6. ✅ Регистрация команд через MCP

## Пошаговый план

### Этап 1: Базовая команда repair_database

- [x] **1.1** Создать `RepairDatabaseCommand` в `file_management.py`
  - Логика восстановления на основе реального наличия файлов
  - Обработка трех случаев: файл в проекте, файл в версиях, файл отсутствует
  - Статус: ✅ Выполнено

- [x] **1.2** Создать `RepairDatabaseMCPCommand` в `file_management_mcp_commands.py`
  - MCP обертка для команды
  - Параметры: root_dir, project_id, version_dir, dry_run
  - Статус: ✅ Выполнено

- [x] **1.3** Удалить старую команду `fix_deleted_files`
  - Удалить `FixDeletedFilesCommand`
  - Удалить `FixDeletedFilesMCPCommand`
  - Статус: ✅ Выполнено

### Этап 2: Остановка воркеров перед восстановлением

- [x] **2.1** Добавить метод `_stop_all_workers()` в `RepairDatabaseCommand`
  - Поиск всех воркеров (file_watcher, vectorization, repair)
  - Отправка SIGTERM для graceful shutdown
  - Force kill после timeout (10 сек)
  - Статус: ✅ Выполнено

- [x] **2.2** Вызывать `_stop_all_workers()` перед восстановлением
  - Вызов в начале `execute()` метода
  - Логирование остановленных воркеров
  - Статус: ✅ Выполнено

### Этап 3: Воркер-процесс для автоматического восстановления

- [x] **3.1** Создать пакет `repair_worker_pkg`
  - Создать директорию `code_analysis/core/repair_worker_pkg/`
  - Создать `__init__.py`
  - Статус: ✅ Выполнено

- [x] **3.2** Создать `base.py` с классом `RepairWorker`
  - Основной класс воркера
  - Метод `run()` с основным циклом
  - Graceful shutdown через сигналы (SIGTERM, SIGINT)
  - Обработка `_stop_event` для корректной остановки
  - Статус: ✅ Выполнено

- [x] **3.3** Создать `runner.py` с функцией `run_repair_worker()`
  - Функция для запуска в отдельном процессе
  - Настройка логирования с ротацией
  - Обработка KeyboardInterrupt и исключений
  - Статус: ✅ Выполнено

### Этап 4: Команды управления воркером

- [x] **4.1** Создать `RepairWorkerManager` в `repair_worker_management.py`
  - Методы: `start()`, `stop()`, `status()`
  - Поиск процессов воркера
  - Graceful shutdown с timeout
  - Статус: ✅ Выполнено

- [x] **4.2** Создать MCP команды управления в `repair_worker_mcp_commands.py`
  - `StartRepairWorkerMCPCommand` - запуск воркера
  - `StopRepairWorkerMCPCommand` - остановка воркера
  - `RepairWorkerStatusMCPCommand` - статус воркера
  - Статус: ✅ Выполнено

### Этап 5: Интеграция и тестирование

- [x] **5.1** Создать все команды и воркер
  - Все файлы созданы и готовы к использованию
  - Команды будут автоматически зарегистрированы при перезапуске сервера
  - Статус: ✅ Выполнено

- [x] **5.2** Перезапустить сервер для регистрации команд
  - Восстановлен hooks.py с регистрацией новых команд
  - Восстановлены недостающие модули (main.py, command_execution_job_patch.py, code_quality, database, db_driver, exceptions, progress_tracker)
  - Остановлен старый сервер
  - Запущен новый сервер
  - Проверена регистрация всех команд через MCP Proxy
  - ✅ Все команды repair доступны: repair_database, start_repair_worker, stop_repair_worker, repair_worker_status
  - Статус: ✅ Выполнено

- [x] **5.3** Создать тестовый скрипт для test_data
  - Скрипт копирует test_data/bhlff в test_data/test_bhlff_repair
  - Создает тестовую базу данных
  - Тестирует repair_database на копии
  - Статус: ✅ Выполнено (скрипт создан: scripts/test_repair_database_full.py)

- [ ] **5.4** Протестировать на копии test_data
  - Запустить scripts/test_repair_database_full.py
  - Проверить восстановление файлов
  - Проверить остановку воркеров
  - Статус: ⏳ Ожидает (требует восстановления файлов database)

- [ ] **5.5** Протестировать воркер
  - Запустить воркер через start_repair_worker
  - Проверить статус через repair_worker_status
  - Остановить через stop_repair_worker
  - Проверить graceful shutdown
  - Статус: ⏳ Ожидает

- [ ] **5.6** Протестировать остановку всех воркеров
  - Запустить file_watcher и vectorization воркеры
  - Запустить repair_database
  - Проверить, что все воркеры остановлены
  - Статус: ⏳ Ожидает

### Этап 6: Восстановление из CST (опционально, требует доработки)

- [ ] **6.1** Реализовать восстановление файла из AST дерева
  - Получить AST tree из базы
  - Конвертировать AST обратно в исходный код
  - Сохранить файл в версии и проекте
  - Статус: ⏳ Требует реализации

- [ ] **6.2** Протестировать восстановление из CST
  - Создать тестовый файл с AST в базе
  - Удалить файл из файловой системы
  - Запустить repair_database
  - Проверить восстановление файла
  - Статус: ⏳ Ожидает

## Текущий статус

### ✅ Выполнено

1. Базовая команда `repair_database` создана
2. MCP обертка создана
3. Старая команда `fix_deleted_files` удалена
4. Остановка всех воркеров перед восстановлением реализована
5. Воркер-процесс создан (base.py, runner.py)
6. Команды управления воркером созданы (start/stop/status)
7. MCP команды управления созданы

### ⏳ В процессе

1. Перезапуск сервера для регистрации команд
2. Тестирование на test_data

### ⏳ Ожидает

1. Полное тестирование функциональности
2. Реализация восстановления из CST

## Следующие шаги

1. ✅ Перезапустить сервер для регистрации новых команд
2. ⏳ Проверить доступность команд через MCP Proxy
3. ⏳ Протестировать на копии test_data
4. ⏳ Протестировать воркер и graceful shutdown
5. ⏳ Протестировать остановку всех воркеров перед восстановлением

## Файлы

### Созданные файлы

- `code_analysis/commands/file_management.py` - `RepairDatabaseCommand`
- `code_analysis/commands/file_management_mcp_commands.py` - `RepairDatabaseMCPCommand`
- `code_analysis/core/repair_worker_pkg/base.py` - `RepairWorker`
- `code_analysis/core/repair_worker_pkg/runner.py` - `run_repair_worker()`
- `code_analysis/commands/repair_worker_management.py` - `RepairWorkerManager`
- `code_analysis/commands/repair_worker_mcp_commands.py` - MCP команды управления
- `scripts/test_repair_database_full.py` - полный тест на копии test_data
- `docs/REPAIR_DATABASE_IMPLEMENTATION_PLAN.md` - этот файл
- `docs/REPAIR_DATABASE_COMMAND.md` - документация команды

### Удаленные файлы

- `FixDeletedFilesCommand` (заменен на `RepairDatabaseCommand`)
- `FixDeletedFilesMCPCommand` (заменен на `RepairDatabaseMCPCommand`)

## Команды

### MCP команды

1. `repair_database` - восстановление целостности БД
2. `start_repair_worker` - запуск воркера восстановления
3. `stop_repair_worker` - остановка воркера
4. `repair_worker_status` - статус воркера

### Использование

```python
# Восстановление БД
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="repair_database",
    params={
        "root_dir": "/path/to/project",
        "version_dir": "data/versions",
        "dry_run": False
    }
)

# Запуск воркера
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="start_repair_worker",
    params={
        "root_dir": "/path/to/project",
        "batch_size": 10,
        "poll_interval": 30
    }
)

# Статус воркера
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="repair_worker_status",
    params={"root_dir": "/path/to/project"}
)

# Остановка воркера
mcp_MCP-Proxy-2_call_server(
    server_id="code-analysis-server",
    command="stop_repair_worker",
    params={"timeout": 10, "force": False}
)
```

