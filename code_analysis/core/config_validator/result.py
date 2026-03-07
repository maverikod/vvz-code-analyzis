"""
Validation result type for config validator.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from typing import Optional


class ValidationResult:
    """Validation result with level, message, and optional details."""

    def __init__(
        self,
        level: str,
        message: str,
        section: Optional[str] = None,
        key: Optional[str] = None,
        suggestion: Optional[str] = None,
    ):
        """
        Initialize validation result.

        Args:
            level: Result level (error, warning, info)
            message: Validation message
            section: Configuration section (optional)
            key: Configuration key (optional)
            suggestion: Suggestion for fixing (optional)
        """
        self.level = level
        self.message = message
        self.section = section
        self.key = key
        self.suggestion = suggestion
