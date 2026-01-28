# Анализ текущей реализации CST команд

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2026-01-14

## Требования

1. **ВСЕ CST команды должны принимать параметр `project_id`** - идентификатор проекта, к которому принадлежит файл
2. **Проект должен быть привязан к наблюдаемому каталогу** - через `watch_dir_id` в таблице `projects`
3. **В таблице проектов должно быть имя корневого каталога проекта** - поле `name` (например, `code_analysis`)
4. **Абсолютный путь должен формироваться**: `path_to_watched_dir/project_dir_name/relative_file_path`

## Текущая реализация

### 1. Структура базы данных

#### Таблица `projects`
```sql
CREATE TABLE projects (
    id TEXT PRIMARY KEY,              -- UUID4 из projectid файла
    root_path TEXT UNIQUE NOT NULL,   -- Абсолютный путь к корню проекта
    name TEXT,                         -- ✅ ЕСТЬ: Имя корневого каталога проекта
    comment TEXT,
    watch_dir_id TEXT,                 -- ✅ ЕСТЬ: Связь с watch_dir
    created_at REAL,
    updated_at REAL,
    FOREIGN KEY (watch_dir_id) REFERENCES watch_dirs(id) ON DELETE SET NULL
)
```

#### Таблица `watch_dir_paths`
```sql
CREATE TABLE watch_dir_paths (
    watch_dir_id TEXT PRIMARY KEY,    -- UUID4, FK к watch_dirs(id)
    absolute_path TEXT,                -- ✅ ЕСТЬ: Абсолютный путь к watch_dir
    created_at REAL,
    updated_at REAL
)
```

#### Таблица `files`
```sql
CREATE TABLE files (
    ...
    project_id TEXT,                  -- Связь с проектом
    watch_dir_id TEXT,                 -- Связь с watch_dir
    path TEXT,                         -- Абсолютный путь (старый формат)
    relative_path TEXT,                -- Относительный путь от корня проекта
    ...
)
```

### 2. Текущая реализация CST команд

#### `cst_load_file`
- **Параметры**: `root_dir`, `file_path`, `node_types`, `max_depth`, `include_children`
- **НЕ принимает**: `project_id` ❌
- **Формирование пути**: `Path(root_dir) / file_path` (если file_path относительный)

#### Другие CST команды
- `cst_find_node` - принимает `root_dir`, `file_path`, `tree_id`
- `cst_modify_tree` - принимает `root_dir`, `file_path`, `tree_id`
- `cst_save_tree` - принимает `root_dir`, `file_path`, `tree_id`
- **Все НЕ принимают**: `project_id` ❌

### 3. Как сейчас формируются пути

**В `cst_load_file_command.py`:**
```python
root = Path(root_dir).resolve()
target = Path(file_path)
if not target.is_absolute():
    target = (root / target).resolve()
```

**Проблема**: Используется `root_dir` напрямую, без учета `watch_dir` и `project.name`

### 4. Методы в `BaseMCPCommand`

#### `_resolve_project_root(project_id, root_dir)`
- Если передан `project_id` - получает `root_path` из БД через `db.get_project(project_id)`
- Если передан `root_dir` - нормализует его через `normalize_root_dir()`
- **НЕ использует**: `watch_dir_id` и `project.name` для формирования пути

#### `_get_project_id(db, root_path)`
- Получает `project_id` по `root_path` из БД
- **НЕ использует**: `watch_dir_id` и `project.name`

### 5. Что РЕАЛЬНО сделано

✅ **Сделано:**
1. Таблица `projects` имеет поле `name` (имя корневого каталога)
2. Таблица `projects` имеет поле `watch_dir_id` (связь с watch_dir)
3. Таблица `watch_dir_paths` хранит абсолютные пути к watch_dir
4. Метод `_resolve_project_root()` может получать `root_path` по `project_id`

❌ **НЕ сделано:**
1. CST команды НЕ принимают `project_id`
2. Пути НЕ формируются как `watch_dir_path/project_name/relative_path`
3. Не используется `watch_dir_id` и `project.name` для формирования абсолютных путей

### 6. Что "нафантазировано"

1. **Использование `root_dir` напрямую** - команды принимают `root_dir` вместо `project_id`
2. **Прямое формирование путей** - `root_dir / file_path` вместо `watch_dir_path / project_name / relative_path`
3. **Отсутствие связи с watch_dir** - команды не используют `watch_dir_id` для формирования путей

## Правильная реализация (по требованиям)

### Формирование абсолютного пути

```python
# 1. Получить project по project_id
project = db.get_project(project_id)

# 2. Получить watch_dir_path по watch_dir_id
watch_dir_path = db.get_watch_dir_path(project.watch_dir_id)

# 3. Сформировать абсолютный путь
absolute_path = Path(watch_dir_path) / project.name / relative_file_path
```

### Изменения в CST командах

1. **Добавить параметр `project_id`** во все CST команды
2. **Убрать или сделать опциональным `root_dir`** (можно получать из `project_id`)
3. **Использовать `watch_dir_path / project.name / relative_path`** для формирования абсолютного пути

## Выводы

1. ✅ База данных готова: есть `watch_dir_id`, `name`, `watch_dir_paths`
2. ❌ CST команды не используют эту структуру
3. ❌ Пути формируются неправильно (не через watch_dir/project_name)
4. ❌ Команды не принимают `project_id` как обязательный параметр
