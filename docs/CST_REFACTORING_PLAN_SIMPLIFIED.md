# Plan: CST Tools Refactoring (Simplified)

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-01-12  
**Status**: ✅ Большая часть уже реализована!

---

## 🎯 Ключевое открытие

**Большая часть функциональности УЖЕ ЕСТЬ в проекте!**

### ✅ Что уже есть:

1. **Lark parser для грамматики** (`cst_query/parser.py`)
   - Грамматика CSTQuery уже определена
   - Парсер уже создан и работает
   - Transformer уже реализован

2. **Executor для поиска узлов** (`cst_query/executor.py`)
   - Функция `query_source(source: str, selector: str)` уже работает
   - Логика поиска по CST дереву уже реализована
   - Нужно только добавить `query_tree(module: cst.Module, selector: str)`

3. **XPath-подобный синтаксис** (`cst_query/`)
   - Все возможности уже реализованы
   - Combinators, predicates, pseudos - все работает

### 🔧 Что нужно сделать:

1. **Добавить функцию `query_tree()` в `cst_query/executor.py`**
   - Взять логику из `query_source()` (строки 88-112)
   - Убрать `cst.parse_module(source)` - дерево уже есть
   - Остальная логика остается той же

2. **Создать простую инфраструктуру для tree_id**
   - In-memory хранилище деревьев
   - Модели данных для tree_id и метаданных

3. **Создать команды с правильными метаданными**
   - `cst_load_file` - загрузка файла в дерево
   - `cst_modify_tree` - модификация дерева
   - `cst_save_tree` - сохранение дерева
   - `cst_find_node` - поиск узлов (простой + XPath)

4. **Написать хорошие метаданные и help**
   - Подробные описания команд
   - Примеры использования
   - Обработка ошибок

---

## 📋 Упрощенный план реализации

### Step 1: Адаптация executor (5 минут)

**Файл**: `code_analysis/cst_query/executor.py`

Добавить функцию:
```python
def query_tree(
    module: cst.Module, selector: str, *, include_code: bool = False
) -> list[Match]:
    """
    Query CST module tree using CSTQuery selectors.
    
    Args:
        module: Already parsed CST module
        selector: selector string
        include_code: include code snippet for each match
    """
    q = parse_selector(selector)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    parents = wrapper.resolve(ParentNodeProvider)
    positions = wrapper.resolve(PositionProvider)
    
    nodes = _build_index(module, parents=parents, positions=positions)
    matched = _eval_query(nodes, q)
    
    out: list[Match] = []
    for info in matched:
        code = module.code_for_node(info.node) if include_code else None
        out.append(
            Match(
                node_id=info.to_id(),
                kind=info.kind,
                node_type=info.node_type,
                name=info.name,
                qualname=info.qualname,
                start_line=info.start_line,
                start_col=info.start_col,
                end_line=info.end_line,
                end_col=info.end_col,
                code=code,
            )
        )
    return out
```

**Изменения**: Убрали `cst.parse_module(source)` - дерево уже есть.

---

### Step 2: Простая инфраструктура tree_id (30 минут)

**Файл**: `code_analysis/core/cst_tree/__init__.py`
```python
from .models import CSTTree, TreeNodeMetadata, TreeOperation
from .tree_store import get_tree, store_tree, remove_tree

__all__ = [
    "CSTTree",
    "TreeNodeMetadata", 
    "TreeOperation",
    "get_tree",
    "store_tree",
    "remove_tree",
]
```

**Файл**: `code_analysis/core/cst_tree/models.py`
```python
from dataclasses import dataclass
from typing import Optional
import libcst as cst

@dataclass
class CSTTree:
    tree_id: str
    file_path: str
    module: cst.Module  # Полное дерево на сервере

@dataclass
class TreeNodeMetadata:
    node_id: str
    type: str
    name: Optional[str]
    start_line: int
    end_line: int
    children_count: int
    children: list[str]  # Только ID детей
```

**Файл**: `code_analysis/core/cst_tree/tree_store.py`
```python
from typing import Dict, Optional
import uuid
from .models import CSTTree

_trees: Dict[str, CSTTree] = {}

def store_tree(tree: CSTTree) -> str:
    _trees[tree.tree_id] = tree
    return tree.tree_id

def get_tree(tree_id: str) -> Optional[CSTTree]:
    return _trees.get(tree_id)

def remove_tree(tree_id: str) -> None:
    _trees.pop(tree_id, None)
```

---

### Step 3: Команды с метаданными (2-3 часа)

#### 3.1. `cst_load_file`

**Простая реализация**:
- Читать файл
- Парсить в `cst.Module`
- Сохранить в tree_store
- Вернуть tree_id и метаданные узлов

**Метаданные**: Подробное описание, примеры, ошибки

#### 3.2. `cst_find_node`

**Простая реализация**:
- Получить дерево по tree_id
- Если простой поиск → фильтровать узлы
- Если XPath → использовать `query_tree(module, selector)`
- Вернуть метаданные найденных узлов

**Метаданные**: Примеры XPath запросов, описание синтаксиса

#### 3.3. `cst_modify_tree`

**Простая реализация**:
- Получить дерево по tree_id
- Валидировать все операции
- Применить операции (использовать существующие патчеры)
- Сохранить обновленное дерево

**Метаданные**: Примеры операций, атомарность

#### 3.4. `cst_save_tree`

**Простая реализация**:
- Получить дерево по tree_id
- Валидация → Backup → Temp file → Atomic replace → DB → Commit
- Использовать существующую логику из `cst_compose_module_command.py`

**Метаданные**: Атомарность, rollback, примеры

---

### Step 4: Метаданные и help (1-2 часа)

**Приоритет**: Хорошие метаданные важнее, чем сложная реализация!

**Что включить в метаданные**:
- Подробное описание команды
- Примеры использования (реальные кейсы)
- Описание параметров
- Обработка ошибок
- Best practices
- Связанные команды

**Пример структуры** (как в `cst_compose_module_command.py`):
```python
@classmethod
def metadata(cls) -> Dict[str, Any]:
    return {
        "name": cls.name,
        "version": cls.version,
        "description": cls.descr,
        "detailed_description": "...",
        "parameters": {...},
        "usage_examples": [...],
        "error_cases": {...},
        "return_value": {...},
        "best_practices": [...],
    }
```

---

## 🎯 Итоговый план (упрощенный)

### Phase 1: Минимальная инфраструктура (1 час)
- [ ] Добавить `query_tree()` в `cst_query/executor.py`
- [ ] Создать простые модели (`CSTTree`, `TreeNodeMetadata`)
- [ ] Создать простой tree_store (in-memory dict)

### Phase 2: Команды (2-3 часа)
- [ ] `cst_load_file` - загрузка файла
- [ ] `cst_find_node` - поиск узлов (простой + XPath)
- [ ] `cst_modify_tree` - модификация дерева
- [ ] `cst_save_tree` - сохранение дерева

### Phase 3: Метаданные и help (1-2 часа)
- [ ] Подробные метаданные для всех команд
- [ ] Примеры использования
- [ ] Обработка ошибок
- [ ] Best practices

### Phase 4: Удаление старого (30 минут)
- [ ] Удалить `cst_compose_module_command.py`
- [ ] Удалить `list_cst_blocks_command.py`
- [ ] Удалить `query_cst_command.py`
- [ ] Обновить `hooks.py`

---

## ✅ Преимущества упрощенного подхода

1. **Минимальные изменения** - используем существующий код
2. **Быстрая реализация** - 4-6 часов вместо дней
3. **Меньше багов** - переиспользуем проверенный код
4. **Проще тестировать** - меньше нового кода

---

## 📝 Вывод

**Большая часть уже есть!** Нужно только:
1. Добавить `query_tree()` в executor (5 минут)
2. Создать простую инфраструктуру tree_id (30 минут)
3. Создать команды с хорошими метаданными (2-3 часа)
4. Удалить старые команды (30 минут)

**Итого**: 4-6 часов работы вместо полного рефакторинга!
