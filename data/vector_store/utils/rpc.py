"""
Утилиты для обработки JSON-RPC запросов.
"""
import json
import logging
from typing import Dict, Any, Tuple, List, Optional
# JsonRpcResponse is a simple dict structure

# Получаем логгер
logger = logging.getLogger("vector_store_api")

def parse_json_rpc_request(body_str: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Парсит JSON-RPC запрос.

    Args:
        body_str: Строка с JSON-RPC запросом

    Returns:
        Кортеж (данные, ошибка). Если ошибок нет, второй элемент будет None.
    """
    try:
        data = json.loads(body_str)
        logger.info(f"[DEBUG-VS] Parsed JSON data: {data}")
        return data, None
    except json.JSONDecodeError as e:
        logger.error(f"[DEBUG-VS] JSON parse error: {str(e)}")
        error = {
            "success": False,
            "error": {
                "code": 1002,
                "message": "Ошибка синтаксиса JSON"
            }
        }
        return None, error

def adapt_mcp_proxy_format(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Адаптирует формат запроса MCP Proxy к формату, ожидаемому обработчиком.

    Args:
        data: Исходные данные запроса

    Returns:
        Адаптированные данные запроса
    """
    # Логируем входные данные на уровне debug для отладки
    logger.debug(f"Adapting request format: {data}")

    # Поддержка стандартного формата JSON-RPC (метод вместо команды)
    if data.get('method') and 'command' not in data:
        # Это уже стандартный JSON-RPC формат, просто преобразуем method в command
        method = data.get('method')
        adapted_data = {
            'command': method,
            'params': data.get('params', {}),
            'jsonrpc': data.get('jsonrpc', '2.0'),
            'id': data.get('id')
        }
        logger.debug(f"Converted JSON-RPC method to command: {adapted_data}")
        return adapted_data

    # Формат MCP Proxy: {"command":"executeCommand","params":{"command":"executeCommand","parameters":{"command":"help","parameters":{}}}}
    if data.get('command') == 'executeCommand' and isinstance(data.get('params'), dict):
        mcp_params = data.get('params', {})

        # Проверяем второй уровень - MCP может отправлять двойную структуру
        if mcp_params.get('command') == 'executeCommand' and isinstance(mcp_params.get('parameters'), dict):
            # Извлекаем фактическую команду и параметры из вложенной структуры
            actual_command = mcp_params.get('parameters', {}).get('command')
            actual_params = mcp_params.get('parameters', {}).get('parameters', {})

            if actual_command:
                # Пересобираем данные в формат, который ожидает наш обработчик
                adapted_data = {
                    'command': actual_command,
                    'params': actual_params,
                    'jsonrpc': data.get('jsonrpc', '2.0'),
                    'id': data.get('id')
                }
                logger.debug(f"Restructured nested MCP request to: {adapted_data}")
                return adapted_data
        # Также поддерживаем стандартный формат MCP Proxy (один уровень вложенности)
        elif mcp_params.get('command'):
            # Извлекаем команду и параметры из структуры первого уровня
            actual_command = mcp_params.get('command')
            actual_params = mcp_params.get('parameters', {})

            if actual_command:
                # Пересобираем данные в формат, который ожидает наш обработчик
                adapted_data = {
                    'command': actual_command,
                    'params': actual_params,
                    'jsonrpc': data.get('jsonrpc', '2.0'),
                    'id': data.get('id')
                }
                logger.debug(f"Restructured standard MCP format to: {adapted_data}")
                return adapted_data

    # Если формат не соответствует ни одному из ожидаемых,
    # но это JSON-RPC формат с методом, адаптируем его
    if 'method' in data and 'params' in data:
        adapted_data = {
            'command': data['method'],
            'params': data['params'],
            'jsonrpc': data.get('jsonrpc', '2.0'),
            'id': data.get('id')
        }
        logger.debug(f"Converted standard JSON-RPC to command format: {adapted_data}")
        return adapted_data

    # Если формат не соответствует MCP Proxy, возвращаем исходные данные
    logger.debug(f"No adaptation needed for: {data}")
    return data

def validate_command(command: str, valid_commands: List[str]) -> Optional[Dict[str, Any]]:
    """
    Проверяет, что команда входит в список доступных команд.

    Args:
        command: Команда для проверки
        valid_commands: Список доступных команд

    Returns:
        None, если команда валидна, иначе объект JsonRpcResponse с ошибкой
    """
    if command not in valid_commands:
        logger.error(f"Invalid command: {command}")
        return {
            "success": False,
            "error": {
                "code": 1002,
                "message": f"Неизвестная команда: {command}. Допустимые команды: {', '.join(valid_commands)}"
            }
        }
    return None

def validate_params(params: Any) -> Optional[Dict[str, Any]]:
    """
    Проверяет, что параметры имеют правильный тип.

    Args:
        params: Параметры для проверки

    Returns:
        None, если параметры валидны, иначе объект JsonRpcResponse с ошибкой
    """
    if params is not None and not isinstance(params, dict):
        logger.error(f"[DEBUG-VS] Invalid params type: {type(params)}")
        return {
            "success": False,
            "error": {
                "code": 1002,
                "message": f"Параметры команды должны быть объектом (словарем), получено: {type(params).__name__}"
            }
        }
    return None
