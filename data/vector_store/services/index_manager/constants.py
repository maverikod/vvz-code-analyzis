"""
Константы для AtomicIndexManager.

Содержит все константы и лимиты для работы с индексами.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
Created: 2024-01-01
Updated: 2024-01-01
"""

# Лимиты для данных чанков
MAX_CHUNK_SIZE = 1024 * 1024  # 1MB - максимальный размер данных чанка
MAX_TEXT_LENGTH = 100  # Порог для определения текстового поля
MAX_OBJECT_SIZE = 10000  # Лимит размера объекта для индексации
MAX_FIELD_NAME_LENGTH = 255  # Максимальная длина имени поля

# Типы индексов
INDEX_TYPE_SCALAR = "scalar"
INDEX_TYPE_ARRAY_ELEMENT = "array_element"
INDEX_TYPE_BM25 = "bm25"
INDEX_TYPE_NUMERIC = "numeric"
INDEX_TYPE_DATE = "date"

# Паттерны для определения дат
DATE_PATTERNS = [
    r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
    r'\d{2}/\d{2}/\d{4}',  # MM/DD/YYYY
    r'\d{2}-\d{2}-\d{4}',  # MM-DD-YYYY
]

# Префиксы для системных полей
SYSTEM_FIELD_PREFIX = "_"

# Операции с индексами
OPERATION_INDEX = "index"
OPERATION_DELETE = "delete"
OPERATION_CLEANUP = "cleanup"
OPERATION_RESTORE = "restore"

# Сообщения об ошибках
ERROR_UUID_EMPTY = "UUID must be a non-empty string"
ERROR_CHUNK_DATA_EMPTY = "Chunk data must be a non-empty dictionary"
ERROR_CHUNK_TOO_LARGE = "Chunk data too large: {} bytes"
ERROR_INVALID_FIELD_NAME = "Invalid field name: {}"
ERROR_FIELD_NAME_TOO_LONG = "Field name too long: {}"
ERROR_ADAPTER_NOT_SET = "Chunk metadata adapter not set"
ERROR_INVALID_SCRIPT_PARAMS = "Invalid script parameters"

# Логирование
LOG_INDEX_START = "Starting index operation for chunk {} with {} fields"
LOG_INDEX_SUCCESS = "Successfully indexed chunk {}"
LOG_INDEX_FAILED = "Failed to index chunk {}: {}"
LOG_ROLLBACK_COMPLETED = "Rollback completed for chunk {}"
LOG_ROLLBACK_FAILED = "Rollback failed for chunk {}: {}"
LOG_CACHE_CLEARED = "Caches cleared"
