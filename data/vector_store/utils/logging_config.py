"""
Конфигурация логирования для Vector Store.

Этот модуль содержит настройки логирования с разными уровнями детализации.
"""

import logging
import sys
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

# Создаем логи в отдельной директории
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Форматы логов
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DETAILED_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"

# Пути к файлам логов
MAIN_LOG_FILE = LOG_DIR / "vector_store.log"
DETAILED_LOG_FILE = LOG_DIR / "vector_store_detailed.log"
ERROR_LOG_FILE = LOG_DIR / "vector_store_errors.log"


def configure_logging(console_level=logging.INFO, file_level=logging.DEBUG):
    """
    Настраивает логирование для всего приложения.

    Args:
        console_level: Уровень логирования для консоли
        file_level: Уровень логирования для файлов
    """
    # Очищаем существующие обработчики
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Устанавливаем базовый уровень логирования
    root_logger.setLevel(logging.DEBUG)

    # Создаем форматтеры
    default_formatter = logging.Formatter(DEFAULT_FORMAT)
    detailed_formatter = logging.Formatter(DETAILED_FORMAT)

    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(default_formatter)
    root_logger.addHandler(console_handler)

    # Основной файловый обработчик с ротацией по размеру (10 МБ)
    main_file_handler = RotatingFileHandler(
        MAIN_LOG_FILE, maxBytes=10*1024*1024, backupCount=5
    )
    main_file_handler.setLevel(file_level)
    main_file_handler.setFormatter(default_formatter)
    root_logger.addHandler(main_file_handler)

    # Детальный файловый обработчик для отслеживания работы с данными
    detailed_file_handler = RotatingFileHandler(
        DETAILED_LOG_FILE, maxBytes=20*1024*1024, backupCount=10
    )
    detailed_file_handler.setLevel(logging.DEBUG)
    detailed_file_handler.setFormatter(detailed_formatter)

    # Настраиваем детальное логирование только для определенных логгеров
    detailed_logger = logging.getLogger("vector_store.detailed")
    detailed_logger.setLevel(logging.DEBUG)
    detailed_logger.addHandler(detailed_file_handler)
    detailed_logger.propagate = False  # Чтобы детальные логи не попадали в основной лог

    # Обработчик ошибок с ежедневной ротацией
    error_file_handler = TimedRotatingFileHandler(
        ERROR_LOG_FILE, when='midnight', interval=1, backupCount=30
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(error_file_handler)

    logging.info("Logging system initialized")
    logging.debug("Debug logging enabled")


def get_detailed_logger(name):
    """
    Получает логгер для детального логирования операций.

    Args:
        name: Имя логгера

    Returns:
        Логгер с детальным форматированием
    """
    logger = logging.getLogger(f"vector_store.detailed.{name}")
    logger.setLevel(logging.DEBUG)
    return logger
