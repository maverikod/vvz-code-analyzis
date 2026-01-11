"""
Package initialization.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import inspect

from .base import CodeDatabase, create_driver_config_for_worker
from . import files
from . import cst
from . import ast
from . import entities

# Try to import optional modules
try:
    from . import projects
except ImportError:
    projects = None

from . import datasets
from . import chunks
from . import comprehensive_analysis
from . import watch_dirs
from . import worker_stats


def _add_functions_as_methods(target_class: type, source_module: object) -> None:
    """Add module-level functions as methods to target class."""
    if source_module is None:
        return
    for name, obj in inspect.getmembers(source_module, predicate=inspect.isfunction):
        if not name.startswith("_"):
            setattr(target_class, name, obj)


_MODULES = [
    projects,
    datasets,
    files,
    cst,
    ast,
    watch_dirs,
    entities,
    chunks,
    comprehensive_analysis,
    worker_stats,
]

for _m in _MODULES:
    _add_functions_as_methods(CodeDatabase, _m)

__all__ = ["CodeDatabase", "create_driver_config_for_worker"]

