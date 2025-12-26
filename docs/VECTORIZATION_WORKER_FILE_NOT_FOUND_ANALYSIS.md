# Анализ проблемы: FileNotFoundError в воркере векторизации

**Дата**: 2025-12-26  
**Автор**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com

## Проблема

Воркер векторизации генерирует повторяющиеся ошибки `FileNotFoundError` для файлов, которые больше не существуют на диске:

```
FileNotFoundError: [Errno 2] No such file or directory: '/home/vasilyvz/projects/tools/code_analysis/code_analysis/core/analyzer.py'
FileNotFoundError: [Errno 2] No such file or directory: '/home/vasilyvz/projects/tools/code_analysis/code_analysis/core/docstring_chunker.py'
FileNotFoundError: [Errno 2] No such file or directory: '/home/vasilyvz/projects/tools/code_analysis/code_analysis/core/refactorer.py'
```

Эти ошибки повторяются в каждом цикле обработки, засоряя логи и создавая ненужную нагрузку.

## Причина

### Исторический контекст

Файлы `analyzer.py`, `docstring_chunker.py`, и `refactorer.py` были разделены на пакеты:

- `analyzer.py` (653 строки) → `analyzer_pkg/` (package)
- `docstring_chunker.py` (754 строки) → `docstring_chunker_pkg/` (package)
- `refactorer.py` (2604 строки) → `refactorer_pkg/` (package)

Это было сделано для соответствия правилу проекта о максимальном размере файла (400 строк).

### Проблема в базе данных

После разделения файлов:

1. **Старые записи остались в базе данных** с путями к несуществующим файлам:
   - `/home/vasilyvz/projects/tools/code_analysis/code_analysis/core/analyzer.py`
   - `/home/vasilyvz/projects/tools/code_analysis/code_analysis/core/docstring_chunker.py`
   - `/home/vasilyvz/projects/tools/code_analysis/code_analysis/core/refactorer.py`

2. **Эти файлы не имеют docstring chunks** в базе данных (потому что их не удалось обработать).

3. **Воркер пытается обработать их** в функции `_chunk_missing_docstring_files()`, которая ищет файлы без docstring chunks и пытается их обработать.

4. **При попытке чтения файла** возникает `FileNotFoundError`, так как файл не существует на диске.

### Проблемный код

В функции `_chunk_missing_docstring_files()` отсутствовали:

1. **Фильтр для удаленных файлов** в SQL-запросе:
   ```sql
   -- БЫЛО (без фильтра deleted):
   WHERE f.project_id = ?
   
   -- ДОЛЖНО БЫТЬ:
   WHERE f.project_id = ?
   AND (f.deleted = 0 OR f.deleted IS NULL)
   ```

2. **Проверка существования файла** перед попыткой чтения:
   ```python
   # БЫЛО:
   content = Path(file_path).read_text(encoding="utf-8")
   
   # ДОЛЖНО БЫТЬ:
   if not Path(file_path).exists():
       logger.debug(f"Skipping missing file: {file_path}")
       continue
   content = Path(file_path).read_text(encoding="utf-8")
   ```

## Решение

### Изменения в коде

#### 1. Добавлен фильтр для удаленных файлов в SQL-запросе

**Файл**: `code_analysis/core/vectorization_worker_pkg/chunking.py`

```python
# В функции _chunk_missing_docstring_files()
cursor.execute(
    """
    SELECT f.id, f.path, f.project_id
    FROM files f
    LEFT JOIN code_chunks c
      ON f.id = c.file_id AND c.source_type LIKE '%docstring%'
    WHERE f.project_id = ?
    AND (f.deleted = 0 OR f.deleted IS NULL)  # ← ДОБАВЛЕНО
    GROUP BY f.id, f.path, f.project_id
    HAVING COUNT(c.id) = 0
    LIMIT ?
    """,
    (self.project_id, limit),
)
```

#### 2. Добавлена проверка существования файла перед обработкой

**Файл**: `code_analysis/core/vectorization_worker_pkg/chunking.py`

```python
# В функции _chunk_missing_docstring_files()
for row in rows:
    if self._stop_event.is_set():
        break
    file_id = row[0]
    file_path = row[1]
    project_id = row[2]

    # ← ДОБАВЛЕНО: Проверка существования файла
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        logger.debug(
            f"Skipping missing file (may have been split/refactored): {file_path}"
        )
        continue

    try:
        content = file_path_obj.read_text(encoding="utf-8")
        # ... остальной код
    except Exception as e:
        logger.warning(f"Failed fallback chunking for {file_path}: {e}", exc_info=True)
```

#### 3. Добавлена проверка существования файла в `_request_chunking_for_files()`

**Файл**: `code_analysis/core/vectorization_worker_pkg/chunking.py`

```python
# В функции _request_chunking_for_files()
file_path = file_record["path"]

# ← ДОБАВЛЕНО: Проверка существования файла
file_path_obj = Path(file_path)
if not file_path_obj.exists():
    logger.debug(
        f"Skipping missing file (may have been split/refactored): {file_path}"
    )
    continue

try:
    file_content = file_path_obj.read_text(encoding="utf-8")
    # ... остальной код
```

#### 4. Улучшена функция `_log_missing_docstring_files()`

**Файл**: `code_analysis/core/vectorization_worker_pkg/chunking.py`

```python
# Добавлен фильтр для удаленных файлов в SQL-запросе
cursor.execute(
    """
    SELECT f.path
    FROM files f
    LEFT JOIN code_chunks c
      ON f.id = c.file_id AND c.source_type LIKE '%docstring%'
    WHERE f.project_id = ?
    AND (f.deleted = 0 OR f.deleted IS NULL)  # ← ДОБАВЛЕНО
    GROUP BY f.id, f.path
    HAVING COUNT(c.id) = 0
    LIMIT ?
    """,
    (self.project_id, sample),
)

# Фильтрация несуществующих файлов из логов
if rows:
    paths = [row[0] for row in rows]
    # ← ДОБАВЛЕНО: Фильтр несуществующих файлов
    existing_paths = [p for p in paths if Path(p).exists()]
    if existing_paths:
        logger.warning(
            f"⚠️  Files with no docstring chunks in DB (sample {len(existing_paths)}/{sample}): {existing_paths}"
        )
    if len(existing_paths) < len(paths):
        missing_count = len(paths) - len(existing_paths)
        logger.debug(
            f"Skipped {missing_count} missing file(s) in log (may have been split/refactored)"
        )
```

## Результаты

### До исправления

- ❌ Повторяющиеся ошибки `FileNotFoundError` в каждом цикле обработки
- ❌ Засорение логов предупреждениями о несуществующих файлах
- ❌ Попытки обработки файлов, которые были разделены на пакеты
- ❌ Отсутствие фильтрации удаленных файлов в SQL-запросах

### После исправления

- ✅ Проверка существования файла перед обработкой
- ✅ Фильтрация удаленных файлов в SQL-запросах
- ✅ Пропуск несуществующих файлов с информативным сообщением на уровне DEBUG
- ✅ Чистые логи без повторяющихся ошибок

## Рекомендации

### Краткосрочные

1. ✅ **Исправлено**: Добавлена проверка существования файла перед обработкой
2. ✅ **Исправлено**: Добавлен фильтр для удаленных файлов в SQL-запросах
3. ⚠️ **Рекомендуется**: Пометить несуществующие файлы как удаленные (soft delete) в базе данных

### Долгосрочные

1. **Миграция базы данных**: Создать скрипт миграции, который:
   - Находит файлы в базе данных, которых нет на диске
   - Помечает их как удаленные (soft delete)
   - Или удаляет их записи из базы данных (hard delete), если они не нужны

2. **Валидация при добавлении файлов**: При добавлении файлов в базу данных проверять их существование на диске.

3. **Периодическая очистка**: Регулярно проверять базу данных на наличие записей о несуществующих файлах и очищать их.

## Связанные файлы

- `code_analysis/core/vectorization_worker_pkg/chunking.py` - Основной файл с исправлениями
- `code_analysis/core/database/files.py` - Методы работы с файлами в базе данных
- `code_analysis/core/database/chunks.py` - Методы работы с чанками

## Выводы

Проблема была вызвана тем, что после разделения больших файлов на пакеты старые записи в базе данных остались с путями к несуществующим файлам. Воркер векторизации пытался обработать эти файлы, что приводило к повторяющимся ошибкам `FileNotFoundError`.

Исправление включает:
1. Добавление проверки существования файла перед обработкой
2. Фильтрацию удаленных файлов в SQL-запросах
3. Улучшение логирования для пропуска несуществующих файлов

Эти изменения предотвращают повторяющиеся ошибки и улучшают стабильность воркера векторизации.

