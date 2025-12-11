"""
Адаптер для обратной совместимости со старым API.

Предоставляет методы для постепенной миграции существующего кода
с старого API на новый упрощенный API.

Features:
- Конвертация старых методов поиска в новые
- Миграция с search_by_* методов на search(ChunkQuery)
- Конвертация метаданных в выражения фильтров
- Предупреждения об устаревших методах

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Created: 2024-01-01
Updated: 2024-01-01
"""

import warnings
from typing import Dict, List, Any, Optional
from chunk_metadata_adapter import SemanticChunk, ChunkQuery

from vector_store.services.vector_store_service import VectorStoreService


class LegacyAPIMigrationAdapter:
    """
    Адаптер для миграции с старого API на новый.
    
    Предоставляет методы для постепенной миграции существующего кода.
    """
    
    def __init__(self, vector_store_service: VectorStoreService):
        """Инициализация адаптера."""
        self.service = vector_store_service
    
    def convert_metadata_to_filter(self, metadata: Dict[str, Any]) -> str:
        """
        Конвертировать словарь метаданных в выражение фильтра.
        
        Args:
            metadata: Словарь метаданных
            
        Returns:
            Выражение фильтра в формате AST
        """
        conditions = []
        
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool)):
                conditions.append(f"{key} = '{value}'")
            elif isinstance(value, list):
                if value:
                    values_str = ", ".join(f"'{v}'" for v in value)
                    conditions.append(f"{key} IN [{values_str}]")
            elif value is None:
                conditions.append(f"{key} IS NULL")
        
        return " AND ".join(conditions) if conditions else ""
    
    def convert_criteria_to_query(self, criteria: Dict[str, Any]) -> ChunkQuery:
        """
        Конвертировать критерии поиска в ChunkQuery.
        
        Args:
            criteria: Словарь критериев поиска
            
        Returns:
            ChunkQuery объект
        """
        query_params = {}
        
        # Обработка текстового поиска
        if "text" in criteria:
            query_params["search_query"] = criteria["text"]
        
        # Обработка векторного поиска
        if "vector" in criteria:
            query_params["embedding"] = criteria["vector"]
        
        # Обработка метаданных
        if "metadata" in criteria:
            filter_expr = self.convert_metadata_to_filter(criteria["metadata"])
            if filter_expr:
                query_params["filter_expr"] = filter_expr
        
        # Обработка лимитов
        if "limit" in criteria:
            query_params["limit"] = criteria["limit"]
        
        if "offset" in criteria:
            query_params["offset"] = criteria["offset"]
        
        # Обработка гибридного поиска
        if "hybrid" in criteria and criteria["hybrid"]:
            query_params["hybrid_search"] = True
            query_params["bm25_weight"] = criteria.get("bm25_weight", 0.5)
            query_params["semantic_weight"] = criteria.get("semantic_weight", 0.5)
        
        return ChunkQuery(**query_params)
    
    # Методы для миграции
    async def search_by_text(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Миграция search_by_text.
        
        Args:
            query: Текст для поиска
            limit: Лимит результатов
            
        Returns:
            Список результатов
        """
        warnings.warn(
            "search_by_text() устарел, используйте search(ChunkQuery(search_query=query, limit=limit))",
            DeprecationWarning,
            stacklevel=2
        )
        
        chunk_query = ChunkQuery(search_query=query, limit=limit)
        return await self.service.search(chunk_query)
    
    async def search_by_vector(self, vector: List[float], limit: int = 10) -> List[Dict[str, Any]]:
        """
        Миграция search_by_vector.
        
        Args:
            vector: Вектор для поиска
            limit: Лимит результатов
            
        Returns:
            Список результатов
        """
        warnings.warn(
            "search_by_vector() устарел, используйте search(ChunkQuery(embedding=vector, limit=limit))",
            DeprecationWarning,
            stacklevel=2
        )
        
        chunk_query = ChunkQuery(embedding=vector, limit=limit)
        return await self.service.search(chunk_query)
    
    async def search_by_metadata(self, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Миграция search_by_metadata.
        
        Args:
            metadata: Метаданные для фильтрации
            
        Returns:
            Список результатов
        """
        warnings.warn(
            "search_by_metadata() устарел, используйте search(ChunkQuery(filter_expr=...))",
            DeprecationWarning,
            stacklevel=2
        )
        
        filter_expr = self.convert_metadata_to_filter(metadata)
        chunk_query = ChunkQuery(filter_expr=filter_expr)
        return await self.service.search(chunk_query)
    
    async def search_bm25(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Миграция search_bm25.
        
        Args:
            query: Текст для поиска
            limit: Лимит результатов
            
        Returns:
            Список результатов
        """
        warnings.warn(
            "search_bm25() устарел, используйте search(ChunkQuery(search_query=query, hybrid_search=False, limit=limit))",
            DeprecationWarning,
            stacklevel=2
        )
        
        chunk_query = ChunkQuery(
            search_query=query,
            hybrid_search=False,
            limit=limit
        )
        return await self.service.search(chunk_query)
    
    async def hybrid_search(self, query: str, bm25_weight: float = 0.5) -> List[Dict[str, Any]]:
        """
        Миграция hybrid_search.
        
        Args:
            query: Текст для поиска
            bm25_weight: Вес BM25
            
        Returns:
            Список результатов
        """
        warnings.warn(
            "hybrid_search() устарел, используйте search(ChunkQuery(search_query=query, hybrid_search=True, bm25_weight=bm25_weight))",
            DeprecationWarning,
            stacklevel=2
        )
        
        chunk_query = ChunkQuery(
            search_query=query,
            hybrid_search=True,
            bm25_weight=bm25_weight,
            semantic_weight=1.0 - bm25_weight
        )
        return await self.service.search(chunk_query)
    
    async def search_combined(self, criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Миграция search_combined.
        
        Args:
            criteria: Критерии поиска
            
        Returns:
            Список результатов
        """
        warnings.warn(
            "search_combined() устарел, используйте search(ChunkQuery(**convert_criteria(criteria)))",
            DeprecationWarning,
            stacklevel=2
        )
        
        chunk_query = self.convert_criteria_to_query(criteria)
        return await self.service.search(chunk_query)
    
    # Утилиты для миграции
    def get_migration_guide(self) -> str:
        """
        Получить руководство по миграции.
        
        Returns:
            Текст руководства по миграции
        """
        return """
# Руководство по миграции API

## Основные изменения

### 1. Новый упрощенный API
```python
# Старый API
service.search_by_text("query", limit=10)
service.search_by_vector(vector, limit=10)
service.search_by_metadata(metadata)

# Новый API
service.search(ChunkQuery(search_query="query", limit=10))
service.search(ChunkQuery(embedding=vector, limit=10))
service.search(ChunkQuery(filter_expr="field = 'value'"))
```

### 2. Унифицированный поиск
```python
# Комбинированный поиск
query = ChunkQuery(
    search_query="python tutorial",
    filter_expr="difficulty = 'beginner' AND language = 'en'",
    hybrid_search=True,
    bm25_weight=0.6,
    limit=10
)
results = await service.search(query)
```

### 3. CRUD операции
```python
# Сохранение
chunk = SemanticChunk(uuid="123", text="content", embedding=[0.1, 0.2])
uuid = await service.upsert(chunk)

# Удаление
success = await service.delete(ChunkQuery(uuid="123"))

# Поиск
results = await service.search(ChunkQuery(uuid="123"))
```

## План миграции

1. Замените прямые вызовы search_by_* на search(ChunkQuery)
2. Конвертируйте метаданные в выражения фильтров
3. Обновите обработку результатов
4. Удалите устаревшие методы после полной миграции

## Примеры миграции

### Поиск по тексту
```python
# Было
results = await service.search_by_text("machine learning", limit=20)

# Стало
query = ChunkQuery(search_query="machine learning", limit=20)
results = await service.search(query)
```

### Поиск с фильтрацией
```python
# Было
metadata = {"category": "tutorial", "language": "en"}
results = await service.search_by_metadata(metadata)

# Стало
query = ChunkQuery(filter_expr="category = 'tutorial' AND language = 'en'")
results = await service.search(query)
```

### Гибридный поиск
```python
# Было
results = await service.hybrid_search("python", bm25_weight=0.7)

# Стало
query = ChunkQuery(
    search_query="python",
    hybrid_search=True,
    bm25_weight=0.7,
    semantic_weight=0.3
)
results = await service.search(query)
```
"""

    def generate_migration_script(self, old_code: str) -> str:
        """
        Генерировать скрипт миграции для старого кода.
        
        Args:
            old_code: Старый код для миграции
            
        Returns:
            Новый код с мигрированными вызовами
        """
        # Простые замены
        replacements = {
            "service.search_by_text(": "service.search(ChunkQuery(search_query=",
            "service.search_by_vector(": "service.search(ChunkQuery(embedding=",
            "service.search_bm25(": "service.search(ChunkQuery(search_query=",
            "service.hybrid_search(": "service.search(ChunkQuery(search_query=",
        }
        
        new_code = old_code
        for old_pattern, new_pattern in replacements.items():
            new_code = new_code.replace(old_pattern, new_pattern)
        
        # Добавляем закрывающие скобки
        new_code = new_code.replace("limit=10)", "limit=10))")
        new_code = new_code.replace("limit=20)", "limit=20))")
        
        return new_code
