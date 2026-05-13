"""
PreviewBudget (C-013) — response size caps for universal_file_preview.

Two caps:
  preview_lines     — max blocks returned when selector is omitted.
  value_preview_len — max length of any inline scalar value or name.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PreviewBudget:
    """
    Resolved size caps for one preview request (C-013).

    Both values are resolved from caller input or from implementation
    defaults before the NavigationProcedure runs.

    Attributes:
        preview_lines: Max blocks returned when selector is omitted.
                       Must be >= 1.
        value_preview_len: Max characters for any inline scalar or name.
                          Must be >= 1.
    """

    preview_lines: int
    value_preview_len: int

    def __post_init__(self) -> None:
        """Validate that both caps are positive integers."""
        if self.preview_lines < 1:
            raise ValueError(f"preview_lines must be >= 1, got {self.preview_lines}")
        if self.value_preview_len < 1:
            raise ValueError(
                f"value_preview_len must be >= 1, got {self.value_preview_len}"
            )
