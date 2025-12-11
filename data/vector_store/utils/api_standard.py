"""
Утилита для стандартизации API ответов.

Предоставляет простую функцию для преобразования результатов команд
в единый стандартизированный формат API.
"""
from typing import Dict, Any, Optional, Union


def standard_response(data: Any) -> Dict[str, Any]:
    """
    Создает стандартизированный ответ API.

    Args:
        data: Данные ответа или исключение

    Returns:
        Стандартизированный ответ API в формате:
        - В случае успеха: {"success": True, "result": data}
        - В случае ошибки: {"success": False, "error": {"code": code, "message": message}}
    """
    # Проверяем, является ли результат ошибкой или исключением
    if isinstance(data, Exception):
        return {
            "success": False,
            "error": {
                "code": getattr(data, "code", 500),
                "message": str(data)
            }
        }

    # Если это объект с методом to_dict, вызываем его
    if hasattr(data, "to_dict") and callable(getattr(data, "to_dict")):
        data = data.to_dict()

    # Проверяем, является ли ответ уже стандартизированным
    if isinstance(data, dict) and 'success' in data and ('result' in data or 'error' in data):
        return data

    # Оборачиваем результат в стандартизированный формат
    return {
        "success": True,
        "result": data
    }
