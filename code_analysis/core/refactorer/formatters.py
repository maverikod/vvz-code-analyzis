"""
Module formatters.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Optional
import logging

from ..code_quality import format_code_with_black  # noqa: F401

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
__all__ = ["format_code_with_black", "format_error_message"]


def format_error_message(
    error_type: str, error_details: str, file_path: Optional[Path] = None
) -> str:
    """
    Format error message in a user-friendly way.

    Args:
        error_type: Type of error (validation, syntax, completeness, etc.)
        error_details: Detailed error message
        file_path: Optional file path for context

    Returns:
        Formatted error message
    """
    file_info = f" in {file_path.name}" if file_path else ""
    if error_type == "python_syntax":
        if "IndentationError" in error_details:
            if "expected an indented block" in error_details:
                return f"Рефакторинг не выполнен{file_info}: ошибка форматирования кода.\nПричина: отсутствует отступ после определения функции или класса.\nФайл восстановлен из резервной копии."
            return f"Рефакторинг не выполнен{file_info}: ошибка отступов в коде.\nФайл восстановлен из резервной копии."
        elif "SyntaxError" in error_details:
            return f"Рефакторинг не выполнен{file_info}: синтаксическая ошибка в результате.\nФайл восстановлен из резервной копии."
        return f"Рефакторинг не выполнен{file_info}: ошибка валидации Python синтаксиса.\nДетали: {error_details}\nФайл восстановлен из резервной копии."
    elif error_type == "config_validation":
        return f"Ошибка конфигурации{file_info}:\n{error_details}\nПроверьте, что все свойства и методы указаны в конфигурации."
    elif error_type == "completeness":
        return f"Рефакторинг не выполнен{file_info}: потеря данных при рефакторинге.\nДетали: {error_details}\nФайл восстановлен из резервной копии."
    elif error_type == "docstring":
        return f"Рефакторинг не выполнен{file_info}: потеря докстрингов.\nДетали: {error_details}\nФайл восстановлен из резервной копии."
    else:
        return f"Рефакторинг не выполнен{file_info}: {error_details}"
