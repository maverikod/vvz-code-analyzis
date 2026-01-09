# Review Summary: PLAN_AUTO_START_VECTORIZATION_WORKER.md

**Author**: Vasiliy Zdanovskiy  
**email**: vasilyvz@gmail.com  
**Date**: 2026-01-09

## Executive Summary

План в целом **корректный и полный**, но есть **несколько критических упущений**, которые нужно добавить перед началом реализации. Основная архитектура правильная, но детали реализации некоторых компонентов требуют уточнения.

## ✅ Что учтено правильно

1. ✅ Удаление зависимости от `project_id` при старте воркера
2. ✅ Удаление зависимости от `watch_dirs` в воркере
3. ✅ Работа только с базой данных (без файловой системы)
4. ✅ Последовательная обработка проектов
5. ✅ Автоматическое обнаружение новых проектов через запросы к БД
6. ✅ Независимость file watcher и vectorization worker
7. ✅ Project-scoped FAISS индексы (решение принято в Step 0)
8. ✅ Удаление dataset_id из worker кода

## 🔴 Критические упущения (добавить обязательно)

### 1. Worker Manager Registration (Step 6)

**Проблема**: Не упомянуто обновление регистрации воркера в `WorkerManager`.

**Текущее состояние**:
- `main.py`: `f"vectorization_{project_id}_{dataset_id[:8]}"`
- `worker_launcher.py`: `f"vectorization_{project_id}"`

**Что добавить в Step 6**:
```markdown
- Update worker registration name to `"vectorization_universal"` in `main.py`
- Update `worker_launcher.py` function `start_vectorization_worker()` to register with name `"vectorization_universal"`
- Update restart function (if exists) to work without project_id/dataset_id
```

**Файлы**:
- `code_analysis/core/worker_launcher.py` - добавить в список файлов для модификации
- `code_analysis/main.py` - уточнить в Step 6

### 2. Worker Launcher Function (Files to Modify)

**Проблема**: `worker_launcher.py` не упомянут в списке файлов для модификации.

**Что добавить**:
```markdown
7. `code_analysis/core/worker_launcher.py` - Update `start_vectorization_worker()` function:
   - Remove `project_id`, `faiss_index_path`, `dataset_id` parameters
   - Add `faiss_dir` parameter
   - Update worker registration name to `"vectorization_universal"`
   - Update function call to `run_vectorization_worker()` without project_id/dataset_id
```

### 3. SQL Query Example (Step 1)

**Проблема**: Нет примера SQL запроса для `get_projects_with_vectorization_count()`.

**Что добавить в Step 1 Details**:
```markdown
**SQL Query Example**:
```sql
SELECT 
    p.id AS project_id,
    p.root_path,
    (
        -- Count files needing chunking (all datasets in project)
        (SELECT COUNT(DISTINCT f.id)
         FROM files f
         WHERE f.project_id = p.id
           AND (f.deleted = 0 OR f.deleted IS NULL)
           AND (f.has_docstring = 1 
                OR EXISTS (SELECT 1 FROM classes c WHERE c.file_id = f.id AND c.docstring IS NOT NULL AND c.docstring != '')
                OR EXISTS (SELECT 1 FROM functions fn WHERE fn.file_id = f.id AND fn.docstring IS NOT NULL AND fn.docstring != '')
                OR EXISTS (SELECT 1 FROM methods m JOIN classes c ON m.class_id = c.id WHERE c.file_id = f.id AND m.docstring IS NOT NULL AND m.docstring != ''))
           AND NOT EXISTS (SELECT 1 FROM code_chunks cc WHERE cc.file_id = f.id))
        +
        -- Count chunks needing vectorization (all datasets in project)
        (SELECT COUNT(cc.id)
         FROM code_chunks cc
         INNER JOIN files f ON cc.file_id = f.id
         WHERE cc.project_id = p.id
           AND (f.deleted = 0 OR f.deleted IS NULL)
           AND cc.embedding_vector IS NOT NULL
           AND cc.vector_id IS NULL)
    ) AS pending_count
FROM projects p
WHERE pending_count > 0
ORDER BY pending_count ASC
```
```

### 4. Log File Path (Step 6)

**Проблема**: Не упомянуто обновление пути к лог-файлу.

**Текущее состояние**:
- `main.py`: `f"{log_path_obj.stem}_{project_id[:8]}_{dataset_id[:8]}{log_path_obj.suffix}"`

**Что добавить в Step 6**:
```markdown
- Update log file path generation: use `vectorization_worker.log` or `vectorization_universal.log` (no project_id/dataset_id in name)
```

### 5. Restart Function (Step 6)

**Проблема**: Если есть restart функция в `main.py`, она не упомянута.

**Что добавить в Step 6**:
```markdown
- Update restart function (if exists) to start universal worker without project_id/dataset_id
- Remove project_id/dataset_id from restart function closure
```

## ⚠️ Важные уточнения (рекомендуется добавить)

### 6. MCP Command Decision

**Проблема**: MCP команда `start_worker` не упомянута.

**Рекомендация**: Добавить в Notes или отдельный раздел:
```markdown
**MCP Command `start_worker`**:
- MCP command can still support manual start with project_id/dataset_id for backward compatibility
- Or update to universal mode only (decision needed)
- Document behavior in command help
```

### 7. Edge Case: Multiple Workers

**Проблема**: Не упомянуто, что делать, если запущено несколько воркеров.

**Что добавить в Edge Cases**:
```markdown
8. **Multiple vectorization workers**: If universal worker is running, prevent starting project-specific workers
   - Solution: Worker manager should check if universal worker exists before allowing project-specific workers
   - Or: Allow multiple workers but document behavior
```

### 8. Configuration watch_dirs

**Проблема**: Не упомянуто, что делать с `watch_dirs` в конфигурации.

**Рекомендация**: Добавить в Notes:
```markdown
- **watch_dirs in config**: Keep `watch_dirs` in config file (file watcher needs them), but vectorization worker ignores them
- No need to remove from config schema
```

## 📝 Дополнительные улучшения (можно сделать во время реализации)

### 9. Chunking Request Clarification

**Уточнение**: В Step 2 упомянуто `get_files_needing_chunking()`, но не детализировано, что происходит с файлами.

**Рекомендация**: Добавить в Step 2 Details:
```markdown
- Files are processed using `_request_chunking_for_files()` method (already exists, no changes needed)
- Method uses `DocstringChunker` to chunk files
- Works with project_id from file record (no changes needed)
```

### 10. Type Hints and Docstrings

**Рекомендация**: Добавить в Code Cleanup Checklist:
```markdown
- [ ] Update type hints for all modified functions
- [ ] Update docstrings to reflect universal mode
- [ ] Remove references to "single project" or "dataset-scoped" from docstrings
```

## 📋 Чеклист перед началом реализации

- [x] План создан и структурирован
- [ ] Добавлен SQL query example в Step 1
- [ ] Добавлено обновление worker registration в Step 6
- [ ] Добавлен `worker_launcher.py` в список файлов для модификации
- [ ] Добавлено обновление log file path в Step 6
- [ ] Добавлено обновление restart function в Step 6 (если существует)
- [ ] Добавлен edge case для multiple workers
- [ ] Добавлено уточнение по watch_dirs в config
- [ ] Решено, как обрабатывать MCP command `start_worker`

## 🎯 Приоритеты

**Критично (перед началом реализации)**:
1. SQL query example (Step 1)
2. Worker registration update (Step 6)
3. Worker launcher update (Files to Modify)
4. Log file path update (Step 6)

**Важно (во время реализации)**:
5. Restart function update (Step 6)
6. Edge case: multiple workers
7. MCP command decision

**Можно сделать позже**:
8. Type hints update
9. Docstring updates
10. Configuration clarification

## ✅ Итоговая оценка

**План готов к реализации на 85%**. Основная архитектура правильная, но нужно добавить:

1. **5 критических упущений** (добавить обязательно)
2. **3 важных уточнения** (рекомендуется добавить)
3. **3 дополнительных улучшения** (можно сделать во время реализации)

После добавления этих пунктов план будет **полностью готов** к реализации.

