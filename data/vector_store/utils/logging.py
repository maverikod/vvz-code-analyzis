"""
Утилиты для логирования в проекте VectorStore.
"""
import logging
import time
from typing import Any, Dict

# Получаем логгер
logger = logging.getLogger("vector_store_api")

def log_request(message: str, data: Any) -> None:
    """
    Логирует информацию о запросе.

    Args:
        message: Сообщение для логирования
        data: Данные запроса
    """
    logger.info("=" * 50)
    logger.info(f"{message}:")
    logger.info(f"{data}")
    logger.info("=" * 50)

def log_request_to_file(body_str: str, headers: Dict[str, Any]) -> None:
    """
    Логирует запрос в файл.

    Args:
        body_str: Тело запроса
        headers: Заголовки запроса
    """
    try:
        with open("/tmp/vector_store_requests.log", "a") as f:
            f.write(f"\n{'=' * 50}\n")
            f.write(f"ЗАПРОС НА /cmd В {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"ТЕЛО: {body_str}\n")
            f.write(f"HEADERS: {headers}\n")
            f.write(f"{'=' * 50}\n")
    except Exception as e:
        logger.error(f"ОШИБКА ЗАПИСИ В ФАЙЛ: {e}")
        # print(f"ОШИБКА ЗАПИСИ В ФАЙЛ: {e}")
