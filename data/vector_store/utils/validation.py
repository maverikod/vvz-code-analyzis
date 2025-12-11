"""
Utilities for data validation in VectorStore project.
"""
import uuid
from typing import Optional, Union, Dict, Any
import re
import datetime
from chunk_metadata_adapter import SemanticChunk

# Custom type for error response
class ValidationResponse:
    """
    Simple validation response.

    Attributes:
        success (bool): Success flag
        error (Optional[Dict[str, Any]]): Error information if validation failed
    """
    def __init__(self, success: bool, error: Optional[Dict[str, Any]] = None):
        self.success = success
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        """
        Converts response to dictionary.

        Returns:
            Dict[str, Any]: Dictionary with validation result information
        """
        if self.success:
            return {"success": True}
        return {"success": False, "error": self.error}

def is_valid_uuid4(value: Optional[Union[str, uuid.UUID]]) -> Optional[str]:
    """
    Universal UUID4 validator and converter.
    If input is None - error (returns None).
    If input is already UUID4 - returns string.
    If string and valid UUID4 - returns string.
    If string and invalid UUID4 - returns None.
    """
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        if value.version == 4:
            return str(value)
        return None
    if isinstance(value, str):
        try:
            # Проверяем наличие символов, отличных от hex-цифр и дефисов
            clean_value = value.replace('-', '')
            if not re.match(r'^[0-9a-fA-F]+$', clean_value):
                return None

            # Пытаемся создать UUID, не обращая внимания на формат
            if len(clean_value) == 32:  # Длина UUID без дефисов
                uuid_str = f"{clean_value[0:8]}-{clean_value[8:12]}-{clean_value[12:16]}-{clean_value[16:20]}-{clean_value[20:32]}"
                uuid_obj = uuid.UUID(uuid_str, version=4)
                return str(uuid_obj)
            else:
                uuid_obj = uuid.UUID(value, version=4)
                return str(uuid_obj)
        except (ValueError, AttributeError, TypeError):
            return None
    return None

def validate_uuid4(param_name: str, value: str) -> Optional[ValidationResponse]:
    """
    Validates that value is a valid UUID4.

    Args:
        param_name: Parameter name for error message
        value: Value to validate

    Returns:
        None if value is valid, otherwise ValidationResponse object with error
    """
    if value is None:
        return None

    try:
        # Используем более гибкую проверку UUID
        clean_value = value.replace('-', '')
        if not re.match(r'^[0-9a-fA-F]+$', clean_value):
            return ValidationResponse(
                success=False,
                error={
                    "code": 400,
                    "message": f"Parameter {param_name} must be in UUID4 format, got: '{value}'"
                }
            )

        # Если длина подходит для UUID (32 hex символа)
        if len(clean_value) == 32:
            try:
                # Формируем стандартную запись UUID
                uuid_str = f"{clean_value[0:8]}-{clean_value[8:12]}-{clean_value[12:16]}-{clean_value[16:20]}-{clean_value[20:32]}"
                uuid_obj = uuid.UUID(uuid_str, version=4)
                # Проверяем версию
                if uuid_obj.version != 4:
                    return ValidationResponse(
                        success=False,
                        error={
                            "code": 400,
                            "message": f"Parameter {param_name} must be in UUID4 format, got: '{value}'"
                        }
                    )
                return None
            except ValueError:
                return ValidationResponse(
                    success=False,
                    error={
                        "code": 400,
                        "message": f"Parameter {param_name} must be in UUID4 format, got: '{value}'"
                    }
                )

        # Стандартная проверка если формат не распознан
        uuid_obj = uuid.UUID(value, version=4)
        return None
    except ValueError:
        return ValidationResponse(
            success=False,
            error={
                "code": 400,
                "message": f"Parameter {param_name} must be in UUID4 format, got: '{value}'"
            }
        )

def validate_optional_uuid4(param_name: str, value: Optional[str]) -> Union[Optional[str], ValidationResponse]:
    """
    Validates that optional value is a valid UUID4.

    Args:
        param_name: Parameter name for error message
        value: Value to validate

    Returns:
        None or UUID4 string if value is valid or not specified,
        otherwise ValidationResponse object with error
    """
    if value is None:
        return None

    validation_result = validate_uuid4(param_name, value)
    return value if validation_result is None else validation_result

def validate_iso8601_timestamp(param_name: str, value: Optional[str]) -> Optional[ValidationResponse]:
    """
    Validates that value is a valid ISO 8601 timestamp.

    Args:
        param_name: Parameter name for error message
        value: Value to validate

    Returns:
        None if value is valid or not specified, otherwise ValidationResponse object with error
    """
    if value is None:
        return None
    try:
        import iso8601
        iso8601.parse_date(value)
        return None
    except Exception:
        return ValidationResponse(
            success=False,
            error={
                "code": 400,
                "message": f"Parameter {param_name} must be a valid ISO 8601 timestamp, got: '{value}'"
            }
        )

def validate_and_autofill_metadata(metadata: dict) -> dict:
    """
    Универсальная функция для валидации и автозаполнения метаданных:
    - Если нет created_at — подставляет текущее время (ISO8601, UTC)
    - Валидирует все присутствующие поля через SemanticChunk.validate_and_fill
    - Возвращает валидированный dict (или выбрасывает ValueError)
    """
    meta = dict(metadata)  # не мутируем исходный dict
    if "created_at" not in meta or not meta["created_at"]:
        meta["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    semantic, err = SemanticChunk.validate_and_fill(meta)
    if semantic is None:
        raise ValueError(f"Metadata validation failed: {err}")
    return semantic.model_dump()

REQUIRED_FIELDS = ["embedding", "uuid", "source_id", "created_at"]

def check_required_fields(meta: dict, required_fields=REQUIRED_FIELDS):
    """
    Проверяет наличие и непустоту обязательных полей в метаданных.
    Если хотя бы одно поле отсутствует или пустое — выбрасывает ValueError.
    Возвращает True если все поля присутствуют и непустые.
    """
    missing = [f for f in required_fields if not meta.get(f)]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")
    return True
