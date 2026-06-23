"""
Module → project file path resolution for analyze_tree.

The implementation now lives in ``core.import_graph.resolver`` so the
comprehensive_analysis circular-import detector shares exactly one resolution
implementation with analyze_tree (TZ-CA-INDEX-INTEGRITY-001 C-3). This module
re-exports it for backward compatibility.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from ...core.import_graph.resolver import (
    STDLIB_TOP_LEVELS,
    ModulePathResolver,
    ResolvedImport,
    is_stdlib_module,
)

__all__ = [
    "ModulePathResolver",
    "ResolvedImport",
    "is_stdlib_module",
    "STDLIB_TOP_LEVELS",
]
