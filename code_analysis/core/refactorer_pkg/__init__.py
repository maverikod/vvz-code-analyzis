"""
Package initialization.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .base import BaseRefactorer
try:
    from .formatters import format_code_with_black, format_error_message
except ImportError:
    from .utils import format_code_with_black, format_error_message

__all__ = [
    "BaseRefactorer",
    "format_code_with_black",
    "format_error_message",
]
