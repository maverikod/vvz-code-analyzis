"""
Module formatters.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import subprocess
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def format_code_with_black(file_path: Path) -> tuple[bool, Optional[str]]:
    """
    Format Python code using black formatter.

    Args:
        file_path: Path to Python file to format

    Returns:
        Tuple of (success, error_message)
    """
    try:
        result = subprocess.run(
            ["black", "--quiet", str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            logger.info(f"Code formatted successfully with black: {file_path}")
            return (True, None)
        else:
            error_msg = result.stderr or result.stdout or "Unknown error"
            logger.warning(f"Black formatting failed: {error_msg}")
            return (False, error_msg)
    except subprocess.TimeoutExpired:
        logger.warning("Black formatting timed out")
        return (False, "Formatting timed out")
    except FileNotFoundError:
        logger.warning("Black formatter not found, skipping formatting")
        return (False, "Black formatter not installed")
    except Exception as e:
        logger.warning(f"Error during formatting: {e}")
        return (False, str(e))


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
