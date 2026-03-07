"""
Configuration validator for code-analysis-server.

Validates configuration files for compatibility with mcp-proxy-adapter.
Based on SimpleConfigValidator from mcp-proxy-adapter with code_analysis specific extensions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .constants import ALLOWED_CODE_ANALYSIS_KEYS
from .result import ValidationResult
from .validator import CodeAnalysisConfigValidator

__all__ = [
    "ALLOWED_CODE_ANALYSIS_KEYS",
    "CodeAnalysisConfigValidator",
    "ValidationResult",
]
