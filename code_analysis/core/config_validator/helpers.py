"""
Helper functions for config validation (field type, URL, port, UUID).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import re
import urllib.parse
from typing import Any, List, Tuple, Type, Union

from .result import ValidationResult


def validate_field_type(
    results: List[ValidationResult],
    section: str,
    key: str,
    value: Any,
    expected_type: Union[Type[Any], Tuple[Type[Any], ...]],
) -> bool:
    """
    Validate field type and append error to results if invalid.

    Args:
        results: List to append validation results to.
        section: Configuration section name.
        key: Field key.
        value: Field value.
        expected_type: Expected type.

    Returns:
        True if type is valid, False otherwise.
    """
    if value is None:
        return True

    if not isinstance(value, expected_type):
        if isinstance(expected_type, tuple):
            type_names = [t.__name__ for t in expected_type]
            expected_type_str = " or ".join(type_names)
        else:
            expected_type_str = expected_type.__name__

        results.append(
            ValidationResult(
                level="error",
                message=f"Field '{section}.{key}' must be {expected_type_str}, got {type(value).__name__}",
                section=section,
                key=key,
                suggestion=f"Change '{section}.{key}' to {expected_type_str} type",
            )
        )
        return False
    return True


def validate_url_format(url: str) -> bool:
    """
    Validate URL format.

    Args:
        url: URL string to validate.

    Returns:
        True if URL is valid, False otherwise.
    """
    try:
        result = urllib.parse.urlparse(url)
        return bool(result.scheme and result.netloc)
    except Exception:
        return False


def validate_port_range(port: int) -> bool:
    """
    Validate port number range.

    Args:
        port: Port number.

    Returns:
        True if port is in valid range (1-65535), False otherwise.
    """
    return 1 <= port <= 65535


def is_valid_uuid4(uuid_str: str) -> bool:
    """Check if string is a valid UUID4."""
    uuid_pattern = (
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    return bool(re.match(uuid_pattern, uuid_str, re.IGNORECASE))
