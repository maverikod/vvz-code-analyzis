"""
LUA скрипты для атомарных операций с индексами.

Содержит статические и динамические LUA скрипты для работы с Redis индексами.
Обеспечивает атомарность операций создания, обновления и удаления индексов.

Features:
- Пятичастная структура REPLACE_CHUNK_SCRIPT
- Статические скрипты очистки и удаления
- Динамическая генерация скриптов на основе данных
- Оптимизированные LUA скрипты для производительности
- Обработка ошибок и rollback механизмы

Architecture:
- REPLACE_CHUNK_SCRIPT с 5 частями для атомарной замены
- Статические части для общих операций
- Динамические части генерируются на основе структуры данных
- Интеграция с chunk_metadata_adapter.to_flat_dict

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Created: 2024-01-01
Updated: 2024-01-01
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

# Константы
DEFAULT_TTL_DAYS: int = 30
"""Время жизни индексов по умолчанию в днях."""

# Логгер
logger = logging.getLogger(__name__)

class IndexType(Enum):
    """Типы индексов."""
    SCALAR = "scalar"
    ARRAY_ELEMENT = "array_element"
    ARRAY_EXACT = "array_exact"
    BM25_TOKEN = "bm25_token"
    BM25_DOCUMENT = "bm25_document"

class IndexOperator(Enum):
    """Операторы для индексов."""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"

# Пятичастная структура REPLACE_CHUNK_SCRIPT
REPLACE_CHUNK_SCRIPT = """
-- REPLACE_CHUNK_SCRIPT - пятичастная структура для атомарной замены
-- KEYS[1] = uuid
-- ARGV[1] = uuid, ARGV[2] = key1, ARGV[3] = value1, ARGV[4] = key2, ARGV[5] = value2, ...

local uuid = KEYS[1]
local param_count = #ARGV

-- ЧАСТЬ 1: ОЧИСТКА ДАННЫХ
-- Удаляем все поля из хеша чанка
redis.call('DEL', 'chunk:' .. uuid)

-- ЧАСТЬ 2: ОЧИСТКА ИНДЕКСОВ
-- Удаляем UUID из всех типов индексов
local patterns = {
    "field_index:*",
    "array_element_index:*", 
    "array_exact_index:*",
    "bm25_token_index:*",
    "bm25_document_index:*"
}

for _, pattern in ipairs(patterns) do
    local keys = redis.call('KEYS', pattern)
    for i, key in ipairs(keys) do
        redis.call('SREM', key, uuid)
    end
end

-- ЧАСТЬ 3: ОЧИСТКА ПУСТЫХ ИНДЕКСОВ
-- Удаляем индексы, которые не содержат данных (оптимизация памяти)
for _, pattern in ipairs(patterns) do
    local keys = redis.call('KEYS', pattern)
    for i, key in ipairs(keys) do
        if redis.call('SCARD', key) == 0 then
            redis.call('DEL', key)
        end
    end
end

-- ЧАСТЬ 4: ЗАПИСЬ НОВЫХ ДАННЫХ
-- Записываем все поля в хеш чанка
for i = 2, param_count, 2 do
    local key = ARGV[i]
    local value = ARGV[i + 1]
    redis.call('HSET', 'chunk:' .. uuid, key, value)
end

-- ЧАСТЬ 5: СОЗДАНИЕ НОВЫХ ИНДЕКСОВ
-- Создаем индексы в зависимости от типа данных
for i = 2, param_count, 2 do
    local key = ARGV[i]
    local value = ARGV[i + 1]
    
    -- Пытаемся распарсить как JSON для определения типа
    local success, decoded = pcall(cjson.decode, value)
    
    if success and type(decoded) == "table" then
        -- Это JSON массив/объект
        if #decoded > 0 then
            -- Массив - создаем индексы для элементов и точного совпадения
            for j, element in ipairs(decoded) do
                redis.call('SADD', 'array_element_index:' .. key .. ':' .. element, uuid)
            end
            -- Индекс для точного совпадения массива
            redis.call('SADD', 'array_exact_index:' .. key .. ':' .. value, uuid)
        else
            -- Пустой массив - только индекс точного совпадения
            redis.call('SADD', 'array_exact_index:' .. key .. ':' .. value, uuid)
        end
    else
        -- Скалярное значение - создаем обычный индекс
        redis.call('SADD', 'field_index:' .. key .. ':' .. value, uuid)
    end
end

-- Обновляем метаданные индекса
redis.call('HSET', 'index_meta:' .. uuid, 'updated_at', redis.call('TIME')[1])
redis.call('HSET', 'index_meta:' .. uuid, 'last_operation', 'replace')

return "OK"
"""

# Полная очистка (части 1-3 пятичастной структуры)
CLEANUP_SCRIPT_PART = """
-- CLEANUP_SCRIPT_PART - полная очистка по UUID (части 1-3)
-- KEYS[1] = uuid

local uuid = KEYS[1]

-- ЧАСТЬ 1: Очистка данных
redis.call('DEL', 'chunk:' .. uuid)

-- ЧАСТЬ 2: Очистка индексов
local patterns = {
    "field_index:*",
    "array_element_index:*", 
    "array_exact_index:*",
    "bm25_token_index:*",
    "bm25_document_index:*"
}

for _, pattern in ipairs(patterns) do
    local keys = redis.call('KEYS', pattern)
    for i, key in ipairs(keys) do
        redis.call('SREM', key, uuid)
    end
end

-- ЧАСТЬ 3: Очистка пустых индексов
for _, pattern in ipairs(patterns) do
    local keys = redis.call('KEYS', pattern)
    for i, key in ipairs(keys) do
        if redis.call('SCARD', key) == 0 then
            redis.call('DEL', key)
        end
    end
end

-- Удаляем метаданные индекса
redis.call('DEL', 'index_meta:' .. uuid)

return "OK"
"""

# Мягкое удаление - пометка удаления
SOFT_DELETE_SCRIPT = """
-- SOFT_DELETE_SCRIPT - пометка удаления без физического удаления
-- KEYS[1] = uuid
-- ARGV[1] = reason (опционально)

local uuid = KEYS[1]
local reason = ARGV[1] or "manual_deletion"
local timestamp = redis.call('TIME')[1]

-- Помечаем чанк как удаленный
redis.call('HSET', 'chunk:' .. uuid, 'deleted', 'true')
redis.call('HSET', 'chunk:' .. uuid, 'deleted_at', timestamp)
redis.call('HSET', 'chunk:' .. uuid, 'deletion_reason', reason)

-- Обновляем метаданные
redis.call('HSET', 'index_meta:' .. uuid, 'deleted', 'true')
redis.call('HSET', 'index_meta:' .. uuid, 'deleted_at', timestamp)
redis.call('HSET', 'index_meta:' .. uuid, 'deletion_reason', reason)

-- Логируем операцию
redis.call('LPUSH', 'deletion_log', cjson.encode({
    uuid = uuid,
    reason = reason,
    timestamp = timestamp,
    type = "soft_delete"
}))

return "OK"
"""

# Жесткое удаление - полное удаление с сортировкой Faiss
HARD_DELETE_SCRIPT = """
-- HARD_DELETE_SCRIPT - полное удаление с сортировкой Faiss
-- KEYS[1] = uuid

local uuid = KEYS[1]
local timestamp = redis.call('TIME')[1]

-- Выполняем полную очистку (части 1-3)
local cleanup_result = redis.call('EVAL', CLEANUP_SCRIPT_PART, 1, uuid)
if cleanup_result ~= "OK" then
    return {err = "CLEANUP_FAILED", details = cleanup_result}
end

-- Удаляем векторные данные
redis.call('DEL', 'vector:' .. uuid)
redis.call('DEL', 'vector_data:' .. uuid)

-- Удаляем из Faiss индекса (если есть)
local faiss_idx = redis.call('HGET', 'vector:' .. uuid, 'faiss_idx')
if faiss_idx then
    redis.call('DEL', 'faiss_idx:' .. faiss_idx)
end

-- Удаляем BM25 данные
redis.call('DEL', 'bm25_document_index:' .. uuid)

-- Логируем операцию
redis.call('LPUSH', 'deletion_log', cjson.encode({
    uuid = uuid,
    timestamp = timestamp,
    type = "hard_delete"
}))

return "OK"
"""

# Дополнительные утилитарные скрипты

# Проверка существования чанка
CHECK_CHUNK_EXISTS_SCRIPT = """
-- CHECK_CHUNK_EXISTS_SCRIPT - проверка существования чанка
-- KEYS[1] = uuid

local uuid = KEYS[1]

-- Проверяем существование основных данных
local exists = redis.call('EXISTS', 'chunk:' .. uuid)

if exists == 1 then
    -- Проверяем, не удален ли чанк
    local deleted = redis.call('HGET', 'chunk:' .. uuid, 'deleted')
    if deleted == 'true' then
        return {exists = false, deleted = true}
    else
        return {exists = true, deleted = false}
    end
else
    return {exists = false, deleted = false}
end
"""

# Получение статистики индексов
GET_INDEX_STATS_SCRIPT = """
-- GET_INDEX_STATS_SCRIPT - получение статистики индексов
-- KEYS[1] = uuid

local uuid = KEYS[1]

local stats = {}

-- Подсчитываем количество индексов каждого типа
local patterns = {
    field_index = "field_index:*",
    array_element_index = "array_element_index:*",
    array_exact_index = "array_exact_index:*",
    bm25_token_index = "bm25_token_index:*",
    bm25_document_index = "bm25_document_index:*"
}

for index_type, pattern in pairs(patterns) do
    local keys = redis.call('KEYS', pattern)
    local count = 0
    
    for i, key in ipairs(keys) do
        if redis.call('SISMEMBER', key, uuid) == 1 then
            count = count + 1
        end
    end
    
    stats[index_type] = count
end

-- Добавляем общую статистику
stats.total_indexes = stats.field_index + stats.array_element_index + 
                     stats.array_exact_index + stats.bm25_token_index + 
                     stats.bm25_document_index

return cjson.encode(stats)
"""

# Восстановление удаленного чанка
RESTORE_CHUNK_SCRIPT = """
-- RESTORE_CHUNK_SCRIPT - восстановление мягко удаленного чанка
-- KEYS[1] = uuid

local uuid = KEYS[1]
local timestamp = redis.call('TIME')[1]

-- Проверяем, существует ли чанк и удален ли он
local exists = redis.call('EXISTS', 'chunk:' .. uuid)
if exists == 0 then
    return {err = "CHUNK_NOT_FOUND"}
end

local deleted = redis.call('HGET', 'chunk:' .. uuid, 'deleted')
if deleted ~= 'true' then
    return {err = "CHUNK_NOT_DELETED"}
end

-- Восстанавливаем чанк
redis.call('HDEL', 'chunk:' .. uuid, 'deleted')
redis.call('HDEL', 'chunk:' .. uuid, 'deleted_at')
redis.call('HDEL', 'chunk:' .. uuid, 'deletion_reason')

-- Обновляем метаданные
redis.call('HSET', 'index_meta:' .. uuid, 'restored_at', timestamp)
redis.call('HSET', 'index_meta:' .. uuid, 'last_operation', 'restore')

-- Логируем операцию
redis.call('LPUSH', 'restoration_log', cjson.encode({
    uuid = uuid,
    timestamp = timestamp,
    type = "restore"
}))

return "OK"
"""

# Утилиты для работы со скриптами
def prepare_chunk_parameters(chunk_data: Dict[str, Any]) -> Tuple[str, List[str]]:
    """
    Подготовка параметров чанка для LUA скрипта.
    
    Args:
        chunk_data: Плоский словарь данных чанка
        
    Returns:
        Tuple[uuid, parameters] - UUID и список параметров для скрипта
    """
    uuid = chunk_data.get('uuid')
    if not uuid:
        raise ValueError("UUID is required in chunk data")
    
    params = [uuid]  # UUID как первый параметр
    
    for key, value in chunk_data.items():
        if key == 'uuid':
            continue  # UUID уже добавлен
        
        params.append(key)  # Ключ
        
        # Преобразуем значение в строку без лишних кавычек
        if isinstance(value, (list, tuple, dict)):
            params.append(json.dumps(value))  # JSON строка для сложных типов
        elif isinstance(value, bool):
            params.append(str(value).lower())  # true/false для булевых
        elif isinstance(value, (int, float)):
            params.append(str(value))  # Числа без кавычек
        else:
            params.append(str(value))  # Строки без дополнительных кавычек
    
    return uuid, params

def validate_script_parameters(params: List[str]) -> bool:
    """
    Валидация параметров для LUA скрипта.
    
    Args:
        params: Список параметров
        
    Returns:
        True если параметры валидны
    """
    if not params or len(params) < 1:
        return False
    
    # Проверяем, что количество параметров четное (ключ-значение)
    if len(params) % 2 != 1:  # +1 для UUID
        return False
    
    return True


# Гибридный поиск: BM25 + семантический
HYBRID_SEARCH_SCRIPT = """
-- HYBRID_SEARCH_SCRIPT - гибридный поиск: BM25 + семантический
-- ARGV[1] = search_text
-- ARGV[2] = search_embedding (JSON string)
-- ARGV[3] = semantic_weight (float)
-- ARGV[4] = bm25_weight (float)
-- ARGV[5] = limit (integer)
-- ARGV[6] = offset (integer)

local search_text = ARGV[1]
local search_embedding_json = ARGV[2]
local semantic_weight = tonumber(ARGV[3]) or 0.5
local bm25_weight = tonumber(ARGV[4]) or 0.5
local limit = tonumber(ARGV[5]) or 10
local offset = tonumber(ARGV[6]) or 0

-- Функция для вычисления косинусного сходства
local function calculate_cosine_similarity(vec1, vec2)
    if not vec1 or not vec2 or #vec1 ~= #vec2 then
        return 0.0
    end
    
    local dot_product = 0.0
    local norm1 = 0.0
    local norm2 = 0.0
    
    for i = 1, #vec1 do
        local v1 = tonumber(vec1[i]) or 0.0
        local v2 = tonumber(vec2[i]) or 0.0
        dot_product = dot_product + v1 * v2
        norm1 = norm1 + v1 * v1
        norm2 = norm2 + v2 * v2
    end
    
    if norm1 == 0.0 or norm2 == 0.0 then
        return 0.0
    end
    
    return dot_product / (math.sqrt(norm1) * math.sqrt(norm2))
end

-- BM25 поиск
local bm25_results = {}
if search_text and search_text ~= "" then
    local tokens = {}
    for token in string.gmatch(search_text:lower(), "%w+") do
        if #token > 2 then
            table.insert(tokens, token)
        end
    end
    
    for _, token in ipairs(tokens) do
        local token_key = "bm25_token_index:" .. token
        local uuids = redis.call('SMEMBERS', token_key)
        for _, uuid in ipairs(uuids) do
            bm25_results[uuid] = (bm25_results[uuid] or 0) + 1
        end
    end
end

-- Семантический поиск
local semantic_results = {}
if search_embedding_json and search_embedding_json ~= "" then
    local search_embedding = cjson.decode(search_embedding_json)
    if search_embedding then
        local vector_keys = redis.call('KEYS', 'vector_data:*')
        for _, key in ipairs(vector_keys) do
            local uuid = string.sub(key, 13)  -- Убираем 'vector_data:' префикс
            local vector_data = redis.call('GET', key)
            if vector_data then
                local vector = cjson.decode(vector_data)
                if vector then
                    local similarity = calculate_cosine_similarity(search_embedding, vector)
                    semantic_results[uuid] = similarity
                end
            end
        end
    end
end

-- Комбинирование результатов
local combined_results = {}
local all_uuids = {}

-- Собираем все UUIDs
for uuid in pairs(bm25_results) do 
    all_uuids[uuid] = true 
end
for uuid in pairs(semantic_results) do 
    all_uuids[uuid] = true 
end

-- Вычисляем комбинированные скоры
for uuid in pairs(all_uuids) do
    local bm25_score = bm25_results[uuid] or 0
    local semantic_score = semantic_results[uuid] or 0
    local combined_score = bm25_weight * bm25_score + semantic_weight * semantic_score
    table.insert(combined_results, {uuid = uuid, score = combined_score})
end

-- Сортировка по убыванию скора
table.sort(combined_results, function(a, b) 
    return a.score > b.score 
end)

-- Применяем пагинацию
local final_results = {}
for i = offset + 1, math.min(offset + limit, #combined_results) do
    table.insert(final_results, combined_results[i])
end

return cjson.encode(final_results)
"""

# Фильтрация по метаданным
METADATA_FILTER_SCRIPT = """
-- METADATA_FILTER_SCRIPT - фильтрация по метаданным
-- ARGV[1] = metadata_filters (JSON string)
-- ARGV[2] = limit (integer)
-- ARGV[3] = offset (integer)

local metadata_filters_json = ARGV[1]
local limit = tonumber(ARGV[2]) or 10
local offset = tonumber(ARGV[3]) or 0

local metadata_filters = cjson.decode(metadata_filters_json)
if not metadata_filters then
    return cjson.encode({})
end

local results = {}
local candidate_uuids = {}

-- Сбор кандидатов по всем фильтрам
for field, value in pairs(metadata_filters) do
    if type(value) == "table" then
        -- Массив значений (IN оператор)
        for _, item in ipairs(value) do
            local index_key = "array_element_index:" .. field .. ":" .. tostring(item)
            local uuids = redis.call('SMEMBERS', index_key)
            for _, uuid in ipairs(uuids) do
                candidate_uuids[uuid] = (candidate_uuids[uuid] or 0) + 1
            end
        end
    else
        -- Скалярное значение (EQUALS оператор)
        local index_key = "field_index:" .. field .. ":" .. tostring(value)
        local uuids = redis.call('SMEMBERS', index_key)
        for _, uuid in ipairs(uuids) do
            candidate_uuids[uuid] = (candidate_uuids[uuid] or 0) + 1
        end
    end
end

-- Фильтрация и ранжирование
local required_filters = 0
for _ in pairs(metadata_filters) do 
    required_filters = required_filters + 1 
end

for uuid, match_count in pairs(candidate_uuids) do
    if match_count >= required_filters then
        table.insert(results, {uuid = uuid, score = match_count / required_filters})
    end
end

-- Сортировка по убыванию скора
table.sort(results, function(a, b) 
    return a.score > b.score 
end)

-- Применяем пагинацию
local final_results = {}
for i = offset + 1, math.min(offset + limit, #results) do
    table.insert(final_results, results[i])
end

return cjson.encode(final_results)
"""
