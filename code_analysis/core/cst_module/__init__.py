"""
CST module tools (package).

This package contains the implementation previously located in `cst_module_tools.py`.
The legacy module remains as a compatibility shim.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .errors import CSTModulePatchError
from .models import BlockInfo, ReplaceOp, Selector
from .blocks import list_cst_blocks
from .patcher import apply_replace_ops
from .utils import (
    compile_module,
    move_module_imports_to_top,
    unified_diff,
    write_with_backup,
)

__all__ = [
    "CSTModulePatchError",
    "Selector",
    "ReplaceOp",
    "BlockInfo",
    "list_cst_blocks",
    "apply_replace_ops",
    "move_module_imports_to_top",
    "compile_module",
    "unified_diff",
    "write_with_backup",
]
