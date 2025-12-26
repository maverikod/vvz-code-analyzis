# Сравнительный анализ команд

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-12-26

## Проблема

Команды `fulltext_search` и `semantic_search` регистрируются на сервере, но не видны через MCP Proxy в help.

## Сравнение команд

### Видимые команды (работают через прокси)

#### 1. `get_worker_status` (GetWorkerStatusMCPCommand)

```python
class GetWorkerStatusMCPCommand(BaseMCPCommand):
    name = "get_worker_status"
    version = "1.0.0"
    descr = "Get worker process status, resource usage, and recent activity"
    category = "monitoring"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {...},
            "required": ["worker_type"],
            "additionalProperties": False,
        }

    async def execute(self, ...) -> SuccessResult | ErrorResult:
        ...
```

**Наследование**: `BaseMCPCommand` → `Command`  
**Схема**: имеет `additionalProperties: False`  
**Статус**: ✅ Видна в help

#### 2. `format_code` (FormatCodeCommand)

```python
class FormatCodeCommand(Command):
    name = "format_code"
    version = "1.0.0"
    descr = "Format Python code using black formatter"
    category = "code_quality"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {...},
            "required": ["file_path"],
            # НЕТ additionalProperties: False
        }

    async def execute(self, ...) -> SuccessResult | ErrorResult:
        ...
```

**Наследование**: `Command` (напрямую)  
**Схема**: НЕТ `additionalProperties: False`  
**Статус**: ✅ Видна в help

### Невидимые команды (не видны через прокси)

#### 1. `fulltext_search` (FulltextSearchMCPCommand)

```python
class FulltextSearchMCPCommand(BaseMCPCommand):
    name = "fulltext_search"
    version = "1.0.0"
    descr = "Perform full-text search in code content and docstrings"
    category = "search"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {...},
                "query": {...},
                "entity_type": {...},
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 20,  # ← ЕСТЬ default
                },
                "project_id": {...},
            },
            "required": ["root_dir", "query"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        query: str,
        entity_type: Optional[str] = None,
        limit: int = 20,  # ← default в параметре
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        ...
```

**Наследование**: `BaseMCPCommand` → `Command`  
**Схема**: имеет `additionalProperties: False`  
**Особенность**: параметр `limit` имеет `default: 20` в схеме И в сигнатуре метода  
**Статус**: ❌ НЕ видна в help

#### 2. `semantic_search` (SemanticSearchMCPCommand)

```python
class SemanticSearchMCPCommand(BaseMCPCommand):
    name = "semantic_search"
    version = "1.0.0"
    descr = "Perform semantic search using embeddings and FAISS vectors"
    category = "search"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "root_dir": {...},
                "query": {...},
                "k": {
                    "type": "integer",
                    "description": "Number of results to return",
                    "default": 10,  # ← ЕСТЬ default
                    "minimum": 1,
                    "maximum": 100,
                },
                "min_score": {
                    "type": "number",
                    "description": "Minimum similarity score (0.0-1.0)",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    # ← НЕТ default, но есть minimum/maximum
                },
                "project_id": {...},
            },
            "required": ["root_dir", "query"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        root_dir: str,
        query: str,
        k: int = 10,  # ← default в параметре
        min_score: Optional[float] = None,
        project_id: Optional[str] = None,
        **kwargs,
    ) -> SuccessResult | ErrorResult:
        ...
```

**Наследование**: `BaseMCPCommand` → `Command`  
**Схема**: имеет `additionalProperties: False`  
**Особенность**: параметр `k` имеет `default: 10` в схеме И в сигнатуре метода  
**Статус**: ❌ НЕ видна в help

## Выявленные различия

### 1. Наследование
- ✅ Видимые: `BaseMCPCommand` или `Command`
- ❌ Невидимые: `BaseMCPCommand` (одинаково)

### 2. Схема
- ✅ Видимые: могут иметь или не иметь `additionalProperties: False`
- ❌ Невидимые: имеют `additionalProperties: False` (одинаково)

### 3. Параметры с default
- ✅ Видимые: НЕТ параметров с `default` в схеме
- ❌ Невидимые: ЕСТЬ параметры с `default` в схеме (`limit: 20`, `k: 10`)

### 4. Минимальные/максимальные значения
- ✅ Видимые: НЕТ `minimum`/`maximum` в схеме
- ❌ Невидимые: ЕСТЬ `minimum`/`maximum` в схеме (`k: minimum: 1, maximum: 100`)

## Гипотеза

Проблема может быть в том, что:
1. Параметры с `default` в схеме могут вызывать проблемы при валидации
2. Параметры с `minimum`/`maximum` могут вызывать проблемы при валидации
3. Комбинация `default` + `minimum`/`maximum` может вызывать проблемы

## Решение

Убрал `default` из схемы для параметров `limit` и `k`. Дефолтные значения должны быть только в сигнатуре метода `execute()`, а не в JSON схеме.

### Изменения:

1. **FulltextSearchMCPCommand**: Убран `default: 20` из схемы для параметра `limit`
2. **SemanticSearchMCPCommand**: Убран `default: 10` из схемы для параметра `k`

Дефолтные значения остаются в сигнатуре метода:
- `limit: int = 20` в `execute()`
- `k: int = 10` в `execute()`

Это соответствует структуре рабочей команды `GetWorkerStatusMCPCommand`, где опциональные параметры не имеют `default` в схеме.

