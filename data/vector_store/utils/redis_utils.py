import json
import enum
import math


def ensure_str_key(key):
    """
    Ensure Redis key is a string (decode bytes if needed).
    Гарантирует, что ключ Redis — строка (декодирует bytes при необходимости).
    """
    if isinstance(key, bytes):
        key = key.decode()
    assert isinstance(key, str), f"Redis key must be str, got {type(key)}: {key}"
    return key


def check_redis_mapping_types(mapping: dict) -> list:
    """
    Проверяет, что все значения в mapping подходят для записи в Redis (str, int, float, bytes).
    Возвращает список ошибок: [(key, type, value), ...] для неподдерживаемых типов.
    """
    errors = []
    allowed_types = (str, int, float, bytes)
    for k, v in mapping.items():
        # None запрещён
        if v is None:
            errors.append((k, type(v).__name__, v))
            continue
        # bool запрещён (Redis не принимает)
        if isinstance(v, bool):
            errors.append((k, 'bool', v))
            continue
        # dict/list/tuple запрещены
        if isinstance(v, (dict, list, tuple, set)):
            errors.append((k, type(v).__name__, v))
            continue
        # complex запрещён
        if isinstance(v, complex):
            errors.append((k, 'complex', v))
            continue
        # float('nan'), float('inf') запрещены
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            errors.append((k, 'float_nan_or_inf', v))
            continue
        # bytes — ОК
        # str/int/float — ОК
        # Остальные типы запрещены
        if not isinstance(v, allowed_types):
            errors.append((k, type(v).__name__, v))
    return errors


async def get_id_to_idx_mapping(redis_instance) -> dict:
    """
    Возвращает отображение record_id -> idx для всех ключей vector:*
    Args:
        redis_instance: Redis client
    Returns:
        Dict[str, int]: Словарь record_id -> FAISS idx
    """
    keys = await redis_instance.keys("vector:*")
    id_to_idx = {}
    for key in keys:
        key = ensure_str_key(key)
        record_id = key.replace("vector:", "")
        try:
            idx = await redis_instance.hget(key, 'idx')
            if idx is not None:
                if isinstance(idx, bytes):
                    idx = idx.decode('utf-8')
                try:
                    id_to_idx[record_id] = int(idx)
                except Exception:
                    continue
        except Exception:
            # Skip this key if hget fails
            continue
    return id_to_idx
