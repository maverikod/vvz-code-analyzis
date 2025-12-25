"""
Errors for CST module patching tools.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""


class CSTModulePatchError(Exception):
    """Raised when a CST patch cannot be applied safely."""
