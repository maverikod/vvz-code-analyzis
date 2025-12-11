"""
ChunkQuerySearchManager - единый менеджер поиска с ChunkQuery.

Единый метод поиска, объединяющий семантический поиск, BM25 и фильтрацию
с автоматическим определением типов поиска и объединением по пересечению.

Features:
- Единый метод search_by_chunk_query()
- Автоматическое определение типов поиска
- Семантический поиск с настраиваемыми весами
- BM25 поиск с настраиваемыми весами
- Фильтрация по метаданным SemanticChunk
- Объединение результатов по пересечению
- Фильтрация удаленных записей по умолчанию
- LUA скрипты для эффективного поиска

Architecture:
- Единый интерфейс для всех типов поиска
- Стратегии поиска с весами
- Пересечение результатов
- Интеграция с Redis и LUA скриптами

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Created: 2024-01-01
Updated: 2024-01-01
"""

import json
import logging
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass

import redis.asyncio as redis
from chunk_metadata_adapter import ChunkQuery

# Логгер
logger = logging.getLogger(__name__)

@dataclass
class SearchResult:
    """Результат поиска."""
    uuid: str
    score: float
    metadata: Dict[str, Any]
    search_type: str

class ChunkQuerySearchManager:
    """
    Единый менеджер поиска с поддержкой ChunkQuery.
    
    Обеспечивает универсальный поиск, объединяющий семантический поиск,
    BM25 и фильтрацию по метаданным с пересечением результатов.
    """
    
    def __init__(self, redis_client: redis.Redis, embedding_service=None) -> None:
        """
        Инициализация менеджера поиска.
        
        Args:
            redis_client: Redis клиент
            embedding_service: Сервис для получения эмбеддингов
        """
        self.redis_client = redis_client
        """Redis клиент для выполнения операций."""
        
        self.embedding_service = embedding_service
        """Сервис для получения эмбеддингов."""
    
    async def search_by_chunk_query(
        self,
        chunk_query: ChunkQuery,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[SearchResult]:
        """
        Единый метод поиска с поддержкой всех типов поиска.
        
        Логика поиска:
        1. Если есть строка поиска + семантический коэффициент ≠ 0 → семантический поиск
        2. Если есть строка поиска + BM25 коэффициент ≠ 0 → BM25 поиск  
        3. Если есть фильтры → фильтрация по метаданным
        4. По умолчанию фильтрация по is_deleted = false
        5. Объединение результатов по пересечению
        
        Args:
            chunk_query: Запрос для поиска
            limit: Максимальное количество результатов
            offset: Смещение результатов
            
        Returns:
            Список результатов поиска
            
        Raises:
            ValueError: При невалидном запросе
            RedisError: При ошибках Redis
        """
        try:
            # Валидация запроса
            self._validate_chunk_query(chunk_query)
            
            # Анализ типов поиска
            search_types = self._analyze_search_types(chunk_query)
            
            logger.info(f"Executing search with types: {search_types}")
            
            # Выполнение поисков
            all_results: Dict[str, Set[str]] = {}
            
            # 1. Семантический поиск
            if "semantic" in search_types:
                semantic_results = await self._semantic_search(chunk_query, limit, offset)
                all_results["semantic"] = {r.uuid for r in semantic_results}
            
            # 2. BM25 поиск
            if "bm25" in search_types:
                bm25_results = await self._bm25_search(chunk_query, limit, offset)
                all_results["bm25"] = {r.uuid for r in bm25_results}
            
            # 3. Фильтрация метаданных
            if "metadata" in search_types:
                metadata_results = await self._metadata_filter(chunk_query, limit, offset)
                all_results["metadata"] = {r.uuid for r in metadata_results}
            
            # 4. Фильтрация по умолчанию (is_deleted = false)
            # Применяем фильтр по умолчанию только если нет явного фильтра по удалению
            if not self._has_deletion_filter(chunk_query):
                default_filter_results = await self._default_deletion_filter()
                all_results["default"] = {r.uuid for r in default_filter_results}
            
            # Объединение результатов по пересечению
            final_uuids = self._intersect_results(all_results)
            
            # Получение финальных результатов с метаданными
            final_results = await self._get_final_results(final_uuids, limit, offset)
            
            return final_results
            
        except Exception as e:
            logger.error(f"Search by ChunkQuery failed: {e}")
            raise
    
    def _validate_chunk_query(self, chunk_query: ChunkQuery) -> None:
        """
        Валидация ChunkQuery.
        
        Args:
            chunk_query: Запрос для валидации
            
        Raises:
            ValueError: При невалидном запросе
        """
        if not isinstance(chunk_query, ChunkQuery):
            raise ValueError("chunk_query must be an instance of ChunkQuery")
        
        # Проверка наличия хотя бы одного критерия поиска
        has_search_text = bool(chunk_query.search_query or chunk_query.text)
        has_filters = bool(self._extract_metadata_filters(chunk_query))
        has_embedding = bool(chunk_query.embedding)
        
        if not any([has_search_text, has_filters, has_embedding]):
            raise ValueError("ChunkQuery must have at least one search criterion")
    
    def _analyze_search_types(self, chunk_query: ChunkQuery) -> List[str]:
        """
        Анализ типов поиска на основе ChunkQuery.
        
        Args:
            chunk_query: Запрос для анализа
            
        Returns:
            Список типов поиска для выполнения
        """
        search_types = []
        
        # Проверка семантического поиска
        has_search_text = bool(chunk_query.search_query or chunk_query.text)
        semantic_weight = getattr(chunk_query, 'semantic_weight', 0.0)
        
        if has_search_text and semantic_weight > 0:
            search_types.append("semantic")
        
        # Проверка BM25 поиска
        bm25_weight = getattr(chunk_query, 'bm25_weight', 0.0)
        
        if has_search_text and bm25_weight > 0:
            search_types.append("bm25")
        
        # Проверка фильтрации метаданных
        if self._extract_metadata_filters(chunk_query):
            search_types.append("metadata")
        
        return search_types
    
    def _extract_metadata_filters(self, chunk_query: ChunkQuery) -> Dict[str, Any]:
        """
        Извлечение фильтров метаданных из ChunkQuery.
        
        Args:
            chunk_query: Запрос для анализа
            
        Returns:
            Словарь фильтров метаданных
        """
        filters = {}
        
        # Отдельные поля метаданных
        if chunk_query.category:
            filters['category'] = chunk_query.category
        
        if chunk_query.tags:
            filters['tags'] = chunk_query.tags
        
        if chunk_query.type:
            filters['type'] = chunk_query.type
        
        if chunk_query.is_deleted is not None:
            filters['is_deleted'] = chunk_query.is_deleted
        
        if chunk_query.language:
            filters['language'] = chunk_query.language
        
        if chunk_query.status:
            filters['status'] = chunk_query.status
        
        if chunk_query.quality_score:
            filters['quality_score'] = chunk_query.quality_score
        
        if chunk_query.source_id:
            filters['source_id'] = chunk_query.source_id
        
        if chunk_query.project:
            filters['project'] = chunk_query.project
        
        if chunk_query.task_id:
            filters['task_id'] = chunk_query.task_id
        
        if chunk_query.subtask_id:
            filters['subtask_id'] = chunk_query.subtask_id
        
        if chunk_query.unit_id:
            filters['unit_id'] = chunk_query.unit_id
        
        if chunk_query.role:
            filters['role'] = chunk_query.role
        
        if chunk_query.year:
            filters['year'] = chunk_query.year
        
        if chunk_query.is_public is not None:
            filters['is_public'] = chunk_query.is_public
        
        if chunk_query.source:
            filters['source'] = chunk_query.source
        
        if chunk_query.block_type:
            filters['block_type'] = chunk_query.block_type
        
        if chunk_query.chunking_version:
            filters['chunking_version'] = chunk_query.chunking_version
        
        if chunk_query.block_id:
            filters['block_id'] = chunk_query.block_id
        
        if chunk_query.block_index is not None:
            filters['block_index'] = chunk_query.block_index
        
        if chunk_query.source_lines_start is not None:
            filters['source_lines_start'] = chunk_query.source_lines_start
        
        if chunk_query.source_lines_end is not None:
            filters['source_lines_end'] = chunk_query.source_lines_end
        
        if chunk_query.links:
            filters['links'] = chunk_query.links
        
        if chunk_query.block_meta:
            filters['block_meta'] = chunk_query.block_meta
        
        if chunk_query.tags_flat:
            filters['tags_flat'] = chunk_query.tags_flat
        
        if chunk_query.link_related:
            filters['link_related'] = chunk_query.link_related
        
        if chunk_query.link_parent:
            filters['link_parent'] = chunk_query.link_parent
        
        # Удаление поисковых полей
        search_fields = ['search_query', 'text', 'embedding', 'bm25_k1', 'bm25_b', 
                        'hybrid_search', 'bm25_weight', 'semantic_weight', 
                        'min_score', 'max_results', 'search_fields', 'created_at',
                        'uuid', 'body', 'summary', 'ordinal', 'sha256', 'source_path',
                        'coverage', 'cohesion', 'boundary_prev', 'boundary_next',
                        'used_in_generation', 'feedback_accepted', 'feedback_rejected',
                        'start', 'end', 'title', 'filter_expr']
        
        for field in search_fields:
            filters.pop(field, None)
        
        return filters
    
    def _has_deletion_filter(self, chunk_query: ChunkQuery) -> bool:
        """
        Проверка наличия фильтра по удалению.
        
        Args:
            chunk_query: Запрос для проверки
            
        Returns:
            True если есть фильтр по удалению
        """
        # Проверка прямого фильтра
        if chunk_query.is_deleted is not None:
            return True
        
        return False
    
    async def _semantic_search(
        self,
        chunk_query: ChunkQuery,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[SearchResult]:
        """
        Семантический поиск по векторам.
        
        Args:
            chunk_query: Запрос для поиска
            limit: Максимальное количество результатов
            offset: Смещение результатов
            
        Returns:
            Список результатов семантического поиска
        """
        search_text = chunk_query.search_query or chunk_query.text
        if not search_text:
            return []
        
        # Получение эмбеддинга
        if self.embedding_service:
            try:
                embedding = await self.embedding_service.get_embedding(search_text)
            except Exception as e:
                logger.error(f"Failed to get embedding: {e}")
                return []
        else:
            embedding = chunk_query.embedding
        
        if not embedding:
            return []
        
        # Генерация LUA скрипта для семантического поиска
        script = self._generate_semantic_search_script(embedding, limit, offset)
        
        try:
            result = await self.redis_client.eval(script, 0)
            return self._parse_search_results(result, "semantic")
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []
    
    async def _bm25_search(
        self,
        chunk_query: ChunkQuery,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[SearchResult]:
        """
        BM25 поиск по тексту.
        
        Args:
            chunk_query: Запрос для поиска
            limit: Максимальное количество результатов
            offset: Смещение результатов
            
        Returns:
            Список результатов BM25 поиска
        """
        search_text = chunk_query.search_query or chunk_query.text
        if not search_text:
            return []
        
        # Генерация LUA скрипта для BM25 поиска
        script = self._generate_bm25_search_script(search_text, limit, offset)
        
        try:
            result = await self.redis_client.eval(script, 0)
            return self._parse_search_results(result, "bm25")
        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []
    
    async def _metadata_filter(
        self,
        chunk_query: ChunkQuery,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[SearchResult]:
        """
        Фильтрация по метаданным.
        
        Args:
            chunk_query: Запрос для фильтрации
            limit: Максимальное количество результатов
            offset: Смещение результатов
            
        Returns:
            Список результатов фильтрации
        """
        filters = self._extract_metadata_filters(chunk_query)
        if not filters:
            return []
        
        # Генерация LUA скрипта для фильтрации метаданных
        script = self._generate_metadata_filter_script(filters, limit, offset)
        
        try:
            result = await self.redis_client.eval(script, 0)
            return self._parse_search_results(result, "metadata")
        except Exception as e:
            logger.error(f"Metadata filter failed: {e}")
            return []
    
    async def _default_deletion_filter(self) -> List[SearchResult]:
        """
        Фильтрация по умолчанию (is_deleted = false).
        
        Returns:
            Список результатов фильтрации
        """
        filters = {"is_deleted": False}
        script = self._generate_metadata_filter_script(filters, None, None)
        
        try:
            result = await self.redis_client.eval(script, 0)
            return self._parse_search_results(result, "default")
        except Exception as e:
            logger.error(f"Default deletion filter failed: {e}")
            return []
    
    def _intersect_results(self, all_results: Dict[str, Set[str]]) -> Set[str]:
        """
        Объединение результатов по пересечению.
        
        Args:
            all_results: Словарь результатов по типам поиска
            
        Returns:
            Множество UUID, прошедших все фильтры
        """
        if not all_results:
            return set()
        
        # Начинаем с первого множества
        result_sets = list(all_results.values())
        intersection = result_sets[0]
        
        # Пересекаем со всеми остальными
        for result_set in result_sets[1:]:
            intersection = intersection.intersection(result_set)
        
        return intersection
    
    async def _get_final_results(
        self,
        uuids: Set[str],
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[SearchResult]:
        """
        Получение финальных результатов с метаданными.
        
        Args:
            uuids: Множество UUID для получения
            limit: Максимальное количество результатов
            offset: Смещение результатов
            
        Returns:
            Список финальных результатов
        """
        results = []
        
        for uuid in list(uuids)[offset or 0:offset or 0 + (limit or len(uuids))]:
            try:
                # Получение метаданных чанка
                chunk_key = f"chunk:{uuid}"
                metadata = await self.redis_client.hgetall(chunk_key)
                
                if metadata:
                    result = SearchResult(
                        uuid=uuid,
                        score=1.0,  # Базовый скор для пересечения
                        metadata=metadata,
                        search_type="intersection"
                    )
                    results.append(result)
            except Exception as e:
                logger.error(f"Failed to get metadata for {uuid}: {e}")
        
        return results
    
    def _generate_semantic_search_script(
        self,
        embedding: List[float],
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> str:
        """
        Генерация LUA скрипта для семантического поиска.
        
        Args:
            embedding: Вектор для поиска
            limit: Максимальное количество результатов
            offset: Смещение результатов
            
        Returns:
            LUA скрипт для семантического поиска
        """
        embedding_json = json.dumps(embedding)
        
        return f"""
-- Semantic Search Script
local search_embedding = cjson.decode('{embedding_json}')
local limit = {limit or 100}
local offset = {offset or 0}

-- Получение всех векторов
local vector_keys = redis.call('KEYS', 'vector_data:*')
local results = {{}}

for _, key in ipairs(vector_keys) do
    local uuid = string.sub(key, 13)  -- Remove 'vector_data:' prefix
    local vector_data = redis.call('GET', key)
    
    if vector_data then
        local vector = cjson.decode(vector_data)
        local similarity = calculate_cosine_similarity(search_embedding, vector)
        
        table.insert(results, {{uuid = uuid, score = similarity}})
    end
end

-- Сортировка по сходству
table.sort(results, function(a, b) return a.score > b.score end)

-- Применение лимитов
local final_results = {{}}
for i = offset + 1, math.min(offset + limit, #results) do
    table.insert(final_results, results[i])
end

return cjson.encode(final_results)

function calculate_cosine_similarity(vec1, vec2)
    local dot_product = 0
    local norm1 = 0
    local norm2 = 0
    
    for i = 1, #vec1 do
        dot_product = dot_product + vec1[i] * vec2[i]
        norm1 = norm1 + vec1[i] * vec1[i]
        norm2 = norm2 + vec2[i] * vec2[i]
    end
    
    if norm1 == 0 or norm2 == 0 then
        return 0
    end
    
    return dot_product / (math.sqrt(norm1) * math.sqrt(norm2))
end
"""
    
    def _generate_bm25_search_script(
        self,
        search_text: str,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> str:
        """
        Генерация LUA скрипта для BM25 поиска.
        
        Args:
            search_text: Текст для поиска
            limit: Максимальное количество результатов
            offset: Смещение результатов
            
        Returns:
            LUA скрипт для BM25 поиска
        """
        return f"""
-- BM25 Search Script
local search_text = "{search_text}"
local limit = {limit or 100}
local offset = {offset or 0}

-- Токенизация текста
local tokens = {{}}
for token in string.gmatch(search_text:lower(), "%w+") do
    if #token > 2 then  -- Skip very short tokens
        table.insert(tokens, token)
    end
end

-- Поиск по токенам
local results = {{}}
local doc_scores = {{}}

for _, token in ipairs(tokens) do
    local token_key = "bm25_token_index:" .. token
    local uuids = redis.call('SMEMBERS', token_key)
    
    for _, uuid in ipairs(uuids) do
        if not doc_scores[uuid] then
            doc_scores[uuid] = 0
        end
        doc_scores[uuid] = doc_scores[uuid] + 1
    end
end

-- Сортировка по релевантности
local sorted_results = {{}}
for uuid, score in pairs(doc_scores) do
    table.insert(sorted_results, {{uuid = uuid, score = score}})
end

table.sort(sorted_results, function(a, b) return a.score > b.score end)

-- Применение лимитов
local final_results = {{}}
for i = offset + 1, math.min(offset + limit, #sorted_results) do
    table.insert(final_results, sorted_results[i])
end

return cjson.encode(final_results)
"""
    
    def _generate_metadata_filter_script(
        self,
        metadata_filters: Dict[str, Any],
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> str:
        """
        Генерация LUA скрипта для фильтрации метаданных.
        
        Args:
            metadata_filters: Фильтры метаданных
            limit: Максимальное количество результатов
            offset: Смещение результатов
            
        Returns:
            LUA скрипт для фильтрации метаданных
        """
        filters_json = json.dumps(metadata_filters)
        
        return f"""
-- Metadata Filter Script
local metadata_filters = cjson.decode('{filters_json}')
local limit = {limit or 1000}
local offset = {offset or 0}

local results = {{}}
local candidate_uuids = {{}}

-- Сбор кандидатов по каждому фильтру
for field, value in pairs(metadata_filters) do
    if type(value) == "table" then
        -- Массив значений
        for _, item in ipairs(value) do
            local index_key = "array_element_index:" .. field .. ":" .. tostring(item)
            local uuids = redis.call('SMEMBERS', index_key)
            for _, uuid in ipairs(uuids) do
                candidate_uuids[uuid] = (candidate_uuids[uuid] or 0) + 1
            end
        end
    else
        -- Скалярное значение
        local index_key = "field_index:" .. field .. ":" .. tostring(value)
        local uuids = redis.call('SMEMBERS', index_key)
        for _, uuid in ipairs(uuids) do
            candidate_uuids[uuid] = (candidate_uuids[uuid] or 0) + 1
        end
    end
end

-- Фильтрация по количеству совпадений
local required_filters = 0
for _ in pairs(metadata_filters) do
    required_filters = required_filters + 1
end

for uuid, match_count in pairs(candidate_uuids) do
    if match_count >= required_filters then
        table.insert(results, {{uuid = uuid, score = match_count / required_filters}})
    end
end

-- Сортировка по релевантности
table.sort(results, function(a, b) return a.score > b.score end)

-- Применение лимитов
local final_results = {{}}
for i = offset + 1, math.min(offset + limit, #results) do
    table.insert(final_results, results[i])
end

return cjson.encode(final_results)
"""
    
    def _parse_search_results(
        self,
        redis_result: Any,
        search_type: str
    ) -> List[SearchResult]:
        """
        Парсинг результатов поиска из Redis.
        
        Args:
            redis_result: Результат из Redis
            search_type: Тип поиска
            
        Returns:
            Список результатов поиска
        """
        if not redis_result:
            return []
        
        try:
            results_data = json.loads(redis_result)
            search_results = []
            
            for item in results_data:
                search_result = SearchResult(
                    uuid=item['uuid'],
                    score=item['score'],
                    metadata={},
                    search_type=search_type
                )
                search_results.append(search_result)
            
            return search_results
            
        except Exception as e:
            logger.error(f"Failed to parse search results: {e}")
            return []
