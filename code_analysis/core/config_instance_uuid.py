"""
Ensure ``registration.instance_uuid`` is a valid UUID4 in config files.

Used at package install time when the template placeholder or an invalid value
is still present in ``/etc/casmgr/config.json``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Optional, Union

from code_analysis.core.config_json import load_config_json_text
from code_analysis.core.config_validator.helpers import is_valid_uuid4

_INSTANCE_UUID_PATTERN = re.compile(
    r'("instance_uuid"\s*:\s*")([^"]*)(")',
    re.MULTILINE,
)


def registration_instance_uuid_value(config: dict[str, Any]) -> str:
    """Return stripped ``registration.instance_uuid`` or empty string."""
    registration = config.get("registration")
    if not isinstance(registration, dict):
        return ""
    value = registration.get("instance_uuid")
    if value is None:
        return ""
    return str(value).strip()


def needs_instance_uuid_fix(config: dict[str, Any]) -> bool:
    """True when instance_uuid is missing, empty, or not a valid UUID4."""
    value = registration_instance_uuid_value(config)
    if not value:
        return True
    return not is_valid_uuid4(value)


def replace_instance_uuid_in_text(text: str, new_uuid: str) -> tuple[str, bool]:
    """Replace the first ``instance_uuid`` JSON string value, preserving comments."""
    if not _INSTANCE_UUID_PATTERN.search(text):
        return text, False
    new_text, count = _INSTANCE_UUID_PATTERN.subn(rf"\g<1>{new_uuid}\3", text, count=1)
    return new_text, count > 0


def ensure_instance_uuid_in_config(
    config_path: Union[str, Path],
    *,
    dry_run: bool = False,
) -> Optional[str]:
    """
    Replace invalid ``registration.instance_uuid`` with a new UUID4.

    Returns the new UUID when the file was (or would be) updated, else ``None``.
    """
    path = Path(config_path)
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    try:
        config = load_config_json_text(text)
    except Exception:
        return None
    if not needs_instance_uuid_fix(config):
        return None
    new_uuid = str(uuid.uuid4())
    new_text, replaced = replace_instance_uuid_in_text(text, new_uuid)
    if not replaced:
        return None
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return new_uuid
