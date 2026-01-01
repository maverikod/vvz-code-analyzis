"""
Package initialization.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import inspect

from .base import CodeDatabase, create_driver_config_for_worker
from . import ast
from . import chunks
from . import classes
from . import content
from . import cst
from . import files
from . import functions
from . import imports
from . import issues
from . import methods
from . import projects
from . import statistics
from . import usages
from . import duplicates


def _add_functions_as_methods(target_class: type, source_module: object) -> None:
    """Add module-level functions as methods to target class."""
    for name, obj in inspect.getmembers(source_module, predicate=inspect.isfunction):
        if not name.startswith("_"):
            setattr(target_class, name, obj)


_MODULES = [
    projects,
    files,
    classes,
    methods,
    functions,
    imports,
    issues,
    usages,
    ast,
    cst,
    chunks,
    content,
    statistics,
    duplicates,
]

for _m in _MODULES:
    _add_functions_as_methods(CodeDatabase, _m)

__all__ = ["CodeDatabase", "create_driver_config_for_worker"]
