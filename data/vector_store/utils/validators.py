"""
Модуль-обертка для обратной совместимости.
Реэкспортирует функции из validation.py для поддержания старого имени модуля.
"""

from vector_store.utils.validation import is_valid_uuid4, validate_uuid4, validate_optional_uuid4

# Другие функции валидации могут быть добавлены по мере необходимости
