"""
Module imports.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Optional


def add_import(
    self, file_id: int, name: str, module: Optional[str], import_type: str, line: int
) -> int:
    """Add import record. Returns import_id."""
    self._execute(
        "\n            INSERT INTO imports (file_id, name, module, import_type, line)\n            VALUES (?, ?, ?, ?, ?)\n        ",
        (file_id, name, module, import_type, line),
    )
    self._commit()
    result = self._lastrowid()
    assert result is not None
    return result
