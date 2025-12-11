"""
Модуль команд для работы с индексом векторов.
Включает команды создания и удаления записей.
"""

__all__ = [
    'CreateRecordCommand',
    'CreateTextRecordCommand',
    'DeleteCommand',
    'InitializeWALCommand',
    'make_create_record',
    'make_delete'
]

# Закомментированный код устаревшего формата команд
# Импорт всех команд этой категории
# from commands.index.create_record import COMMAND as create_record
# from commands.index.create_text_record import COMMAND as create_text_record
# from commands.index.delete import COMMAND as delete

# Словарь всех команд индексации с их документацией
# INDEX_COMMANDS = {
#     "create_record": create_record,
#     "create_text_record": create_text_record,
#     "delete": delete
# }

from .count import CountCommand
from .clean_faiss_orphans import CleanFaissOrphansCommand
from .initialize_wal import InitializeWALCommand
