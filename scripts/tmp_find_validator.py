"""Inspect validator helpers during temporary schema debugging."""

import inspect
from code_analysis.core.config_validator import CodeAnalysisConfigValidator

print(inspect.getfile(CodeAnalysisConfigValidator))
