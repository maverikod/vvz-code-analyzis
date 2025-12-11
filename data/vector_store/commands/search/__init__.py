"""
Search commands module.
Includes commands for vector search, text search, and metadata filtering.
"""

from .search_records import SearchCommand

__all__ = [
    'SearchCommand'
]

# Импорт всех команд этой категории
# from commands.search.search_by_vector import COMMAND as search_by_vector
# from commands.search.search_by_text import COMMAND as search_by_text
# from commands.search.search_text_records import COMMAND as search_text_records
# from commands.search.filter_records import COMMAND as filter_records

# Словарь всех команд поиска с их документацией
# SEARCH_COMMANDS = {
#     "search_by_vector": search_by_vector,
#     "search_by_text": search_by_text,
#     "search_text_records": search_text_records,
#     "filter_records": filter_records
# }
