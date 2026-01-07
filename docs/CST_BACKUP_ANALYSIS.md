# Анализ механизма создания backup файлов при CST операциях

**Автор**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Дата**: 2026-01-07

## Обзор

При выполнении операций через `compose_cst_module` создаются backup копии файлов для возможности отката изменений. В текущей реализации используются **ДВА различных механизма backup**, что может вызывать путаницу.

## Механизмы backup

### 1. BackupManager (новый, основной)

**Расположение**: `code_analysis/core/backup_manager.py`

**Характеристики**:
- **Директория**: `{root_dir}/old_code/`
- **Индекс**: `old_code/index.txt` (текстовый файл с метаданными)
- **Формат имени файла**: `путь_к_файлу_с_подчеркиваниями-UUID4`
  - Пример: `code_analysis_core_database_base_py-a1b2c3d4-e5f6-7890-abcd-ef1234567890`
  - **Важно**: Полный относительный путь включается в имя, поэтому файлы с одинаковыми именами в разных каталогах имеют разные backup имена
    - `code_analysis/core/base.py` → `code_analysis_core_base.py-UUID`
    - `test_data/vast_srv/base.py` → `test_data_vast_srv_base.py-UUID`
- **Метаданные в индексе**: `UUID|File Path|Timestamp|Command|Related Files|Comment`
- **UUID**: Уникальный идентификатор для каждого backup

**Использование**:
- Используется в `compose_cst_module_command.py` (строки 412-433)
- Создается **ПЕРЕД** применением изменений
- Сохраняет метаданные: команда, связанные файлы, комментарий

**Код создания**:
```python
if apply and target.exists():
    backup_manager = BackupManager(root_path)
    backup_uuid = backup_manager.create_backup(
        target,
        command="compose_cst_module",
        related_files=related_files if related_files else None,
        comment=commit_message or "",
    )
```

**Преимущества**:
- ✅ Централизованное хранение всех backup
- ✅ UUID-идентификация для точного восстановления
- ✅ Метаданные (команда, комментарий, связанные файлы)
- ✅ Индекс для быстрого поиска версий
- ✅ API для управления backup (list, restore, delete)

**Недостатки**:
- ⚠️ Имена файлов могут быть длинными (путь с подчеркиваниями)
- ⚠️ Нужно парсить индекс для поиска backup

### 2. write_with_backup (старый, простой)

**Расположение**: `code_analysis/core/cst_module/utils.py` (строки 85-99)

**Характеристики**:
- **Директория**: `{file_dir}/.code_mapper_backups/` (рядом с файлом)
- **Индекс**: Нет
- **Формат имени файла**: `{filename}.backup`
  - Пример: `base.py.backup`
- **Метаданные**: Нет (только файл)

**Использование**:
- Используется в `compose_cst_module_command.py` (строки 436-438)
- Вызывается **ПОСЛЕ** создания BackupManager backup
- Параметр `create_backup` контролирует создание

**Код создания**:
```python
if apply:
    backup_path = write_with_backup(
        target, new_source, create_backup=create_backup
    )
```

**Преимущества**:
- ✅ Простота (backup рядом с файлом)
- ✅ Легко найти backup для конкретного файла

**Недостатки**:
- ❌ Перезаписывается при каждом backup (только последняя версия)
- ❌ Нет метаданных
- ❌ Нет UUID для идентификации
- ❌ Нет истории версий
- ❌ Засоряет директории backup-файлами

## Проблема: Двойное создание backup

**Текущая ситуация**:
При `apply=True` и `create_backup=True` создаются **ОБА** backup:
1. BackupManager создает backup в `old_code/` с UUID
2. `write_with_backup` создает backup в `.code_mapper_backups/` рядом с файлом

**Код в `compose_cst_module_command.py`**:
```python
# Строка 412-433: BackupManager создает backup
if apply and target.exists():
    backup_manager = BackupManager(root_path)
    backup_uuid = backup_manager.create_backup(...)

# Строка 436-438: write_with_backup создает backup
if apply:
    backup_path = write_with_backup(
        target, new_source, create_backup=create_backup
    )
```

**Последствия**:
- ⚠️ Избыточное дублирование backup
- ⚠️ Путаница: какой backup использовать для восстановления?
- ⚠️ Два разных формата хранения
- ⚠️ Два разных API для восстановления

## Рекомендации

### Вариант 1: Использовать только BackupManager (рекомендуется)

**Действия**:
1. Удалить вызов `write_with_backup` из `compose_cst_module_command.py`
2. Использовать только `BackupManager.create_backup()`
3. Удалить функцию `write_with_backup` (или оставить для обратной совместимости)

**Преимущества**:
- ✅ Единый механизм backup
- ✅ Полная история версий
- ✅ Метаданные и UUID
- ✅ Централизованное управление

### Вариант 2: Использовать только write_with_backup

**Действия**:
1. Удалить вызов `BackupManager.create_backup()` из `compose_cst_module_command.py`
2. Использовать только `write_with_backup`

**Недостатки**:
- ❌ Теряется история версий
- ❌ Нет метаданных
- ❌ Нет UUID

### Вариант 3: Гибридный подход

**Действия**:
1. BackupManager для основной backup (с историей)
2. `write_with_backup` только для быстрого доступа к последней версии
3. Параметр `create_backup` контролирует только `write_with_backup`

**Недостатки**:
- ⚠️ Все еще два механизма
- ⚠️ Путаница в использовании

## Структура BackupManager

### Директория old_code/

```
old_code/
├── index.txt                    # Индекс всех backup
├── code_analysis_core_base_py-uuid1
├── code_analysis_core_base_py-uuid2
└── test_data_vast_srv_file_py-uuid3
```

### Обработка файлов с одинаковыми именами

**Механизм**: Полный относительный путь от `root_dir` включается в имя backup файла.

**Алгоритм генерации имени** (метод `_generate_backup_filename`):
1. Конвертирует абсолютный путь в относительный от `root_dir`
2. Заменяет все `/` и `\` на `_` (подчеркивания)
3. Удаляет ведущие подчеркивания
4. Добавляет UUID в конец

**Примеры**:
- Файл: `code_analysis/core/base.py`
  - Backup: `code_analysis_core_base.py-a1b2c3d4-...`
  
- Файл: `test_data/vast_srv/base.py` (то же имя, другой каталог)
  - Backup: `test_data_vast_srv_base.py-b2c3d4e5-...`

**Результат**: Файлы с одинаковыми именами в разных каталогах имеют **разные** имена backup файлов, что исключает конфликты.

**Реальные примеры из индекса**:
- `code_analysis/core/database/base.py` → `code_analysis_core_database_base.py-UUID`
- `code_analysis/core/file_watcher_pkg/base.py` → `code_analysis_core_file_watcher_pkg_base.py-UUID`

Оба файла называются `base.py`, но backup имена различаются благодаря полному пути.

### Формат index.txt

```
# UUID|File Path|Timestamp|Command|Related Files|Comment
a1b2c3d4-...|code_analysis/core/base.py|2026-01-07T10-30-45|compose_cst_module||Fixed bug
e5f6g7h8-...|test_data/vast_srv/file.py|2026-01-07T11-00-00|split_file|new_file1.py,new_file2.py|Split large file
```

### API BackupManager

```python
backup_manager = BackupManager(root_dir)

# Создать backup
backup_uuid = backup_manager.create_backup(
    file_path,
    command="compose_cst_module",
    related_files=["file1.py", "file2.py"],
    comment="Fixed bug"
)

# Список всех файлов с backup
files = backup_manager.list_files()

# Список версий файла
versions = backup_manager.list_versions("code_analysis/core/base.py")

# Восстановить файл
success, message = backup_manager.restore_file(
    "code_analysis/core/base.py",
    backup_uuid="a1b2c3d4-..."  # или None для последней версии
)

# Удалить backup
success, message = backup_manager.delete_backup("a1b2c3d4-...")

# Очистить все backup
success, message = backup_manager.clear_all()
```

## Текущее использование в коде

### compose_cst_module_command.py

**Строки 412-433**: Создание backup через BackupManager
```python
if apply and target.exists():
    backup_manager = BackupManager(root_path)
    backup_uuid = backup_manager.create_backup(
        target,
        command="compose_cst_module",
        related_files=related_files if related_files else None,
        comment=commit_message or "",
    )
```

**Строки 436-438**: Создание backup через write_with_backup
```python
if apply:
    backup_path = write_with_backup(
        target, new_source, create_backup=create_backup
    )
```

**Проблема**: Оба backup создаются одновременно, если `create_backup=True`.

## Выводы

1. **Два механизма backup** работают параллельно, что избыточно
2. **BackupManager** - более продвинутый механизм с историей версий
3. **write_with_backup** - простой механизм, но без истории
4. **Рекомендация**: Использовать только BackupManager, удалить write_with_backup из compose_cst_module

## Возвращаемые значения

### В ответе команды compose_cst_module

**Поля в ответе**:
- `backup_path`: Путь к backup файлу от `write_with_backup` (если `create_backup=True`)
- `backup_uuid`: UUID backup от `BackupManager` (если `apply=True` и файл существует)

**Проблема**: 
- `backup_path` указывает на backup в `.code_mapper_backups/`, который перезаписывается
- `backup_uuid` указывает на backup в `old_code/` с полной историей
- Пользователь может запутаться, какой backup использовать

## Статистика backup

### BackupManager (old_code/)
- **Всего backup файлов**: ~94 (по индексу)
- **Формат**: `путь_к_файлу-UUID`
- **Индекс**: `old_code/index.txt` (94 строки)

### write_with_backup (.code_mapper_backups/)
- **Найдено директорий**: 5
- **Формат**: `filename.backup`
- **Проблема**: Перезаписывается при каждом backup

## Следующие шаги

1. ✅ Анализ завершен
2. ⏳ Решение: какой механизм использовать
3. ⏳ Рефакторинг: удалить избыточный механизм
4. ⏳ Обновление документации

