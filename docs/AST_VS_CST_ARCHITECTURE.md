# AST vs CST: Архитектура и использование

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-12-26

## Текущая ситуация

В проекте используются **оба** подхода, но для разных целей:

### AST (Abstract Syntax Tree) - для анализа

**Использование:**
- ✅ Сохранение в БД (`ast_trees` таблица)
- ✅ Команды анализа: `get_ast`, `search_ast_nodes`, `ast_statistics`
- ✅ Извлечение структуры: классы, функции, методы, импорты
- ✅ Векторизация: привязка чанков к AST узлам

**Ограничения:**
- ❌ Не сохраняет форматирование
- ❌ Не сохраняет комментарии
- ❌ Нельзя восстановить исходный код из AST

**Где используется:**
- `code_analysis/commands/code_mapper_mcp_command.py` - `update_indexes` сохраняет AST
- `code_analysis/core/database/ast.py` - методы работы с AST
- `code_analysis/commands/ast/*` - все команды анализа AST

### CST (Concrete Syntax Tree) - для манипуляций

**Использование:**
- ✅ Манипуляции с кодом: `compose_cst_module`
- ✅ Сохранение форматирования и комментариев
- ✅ Восстановление исходного кода: `cst.Module.code`

**Ограничения:**
- ❌ Не сохраняется в БД
- ❌ Используется только для операций, не для хранения

**Где используется:**
- `code_analysis/core/cst_module/*` - все операции с CST
- `code_analysis/commands/cst_compose_module_command.py` - команда манипуляций
- `code_analysis/commands/list_cst_blocks_command.py` - список блоков
- `code_analysis/commands/query_cst_command.py` - запросы к CST

## Проблема

В `repair_database` есть TODO для восстановления файлов из CST узлов:

```python
async def _restore_file_from_cst(self, file_id: int, file_path: str, file_record: Dict[str, Any]) -> bool:
    # TODO: Restore file content from AST tree
    # This requires converting AST back to source code
```

Но:
1. В БД сохраняется только AST (не CST)
2. Из AST нельзя восстановить исходный код
3. Нужен CST для восстановления

## Решения

### Вариант 1: Сохранять и AST, и CST (РЕКОМЕНДУЕТСЯ)

**Преимущества:**
- ✅ AST для анализа (быстрый, легкий)
- ✅ CST для восстановления (полный исходный код)
- ✅ Обратная совместимость
- ✅ Гибкость

**Реализация:**
1. Добавить таблицу `cst_trees` в БД
2. Сохранять CST в `update_indexes`
3. Использовать CST для восстановления в `repair_database`

**Схема БД:**
```sql
CREATE TABLE IF NOT EXISTS cst_trees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    project_id TEXT NOT NULL,
    cst_code TEXT NOT NULL,  -- Исходный код файла (можно восстановить через cst.Module.code)
    cst_hash TEXT NOT NULL,
    file_mtime REAL NOT NULL,
    created_at REAL DEFAULT (julianday('now')),
    updated_at REAL DEFAULT (julianday('now')),
    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(file_id, cst_hash)
)
```

### Вариант 2: Сохранять исходный код файла

**Преимущества:**
- ✅ Простота
- ✅ Можно восстановить файл напрямую

**Недостатки:**
- ❌ Дублирование данных (код уже в файловой системе)
- ❌ Больше места в БД

**Реализация:**
Добавить поле `source_code TEXT` в таблицу `files` или создать отдельную таблицу.

### Вариант 3: Заменить AST на CST

**Преимущества:**
- ✅ Один формат для всего
- ✅ Можно восстановить код

**Недостатки:**
- ❌ Потеря обратной совместимости
- ❌ CST тяжелее AST
- ❌ Нужно переписать все команды анализа

## Рекомендация

**Использовать Вариант 1**: Сохранять и AST, и CST.

**Причины:**
1. AST легкий и быстрый для анализа
2. CST нужен для восстановления и манипуляций
3. Обратная совместимость сохраняется
4. Гибкость использования

**План реализации:**
1. Добавить таблицу `cst_trees` в `code_analysis/core/database/base.py`
2. Добавить методы `save_cst_tree`, `get_cst_tree` в `code_analysis/core/database/`
3. Обновить `update_indexes` для сохранения CST
4. Реализовать восстановление из CST в `repair_database`

## Текущее состояние

- ✅ AST сохраняется и используется для анализа
- ✅ CST используется для манипуляций
- ❌ CST не сохраняется в БД
- ❌ Восстановление файлов не реализовано

## Вывод

**Нет конфликта** между AST и CST - они дополняют друг друга:
- **AST** - для анализа структуры кода
- **CST** - для манипуляций и восстановления

Нужно добавить сохранение CST в БД для возможности восстановления файлов.

