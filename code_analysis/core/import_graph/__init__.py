"""
Shared import-graph primitives: module→path resolution and cycle detection.

These are pure utilities (no DB, no disk) used by both the ``analyze_tree``
command and the comprehensive_analysis project-integrity phase, so the two share
ONE resolution + cycle-detection implementation and cannot diverge. Lives in
``core`` (not under a command package) to respect the command→core layering.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from .cycles import find_cycles
from .resolver import (
    STDLIB_TOP_LEVELS,
    ModulePathResolver,
    ResolvedImport,
    is_stdlib_module,
)

__all__ = [
    "find_cycles",
    "ModulePathResolver",
    "ResolvedImport",
    "is_stdlib_module",
    "STDLIB_TOP_LEVELS",
]
