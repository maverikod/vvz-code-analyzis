"""
Compatibility shim for CST module tools.

The implementation lives in `code_analysis.core.cst_module`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .cst_module import (  # noqa: F401
    BlockInfo,
    CSTModulePatchError,
    DocstringValidationError,
    ReplaceOp,
    Selector,
    apply_replace_ops,
    compile_module,
    list_cst_blocks,
    move_module_imports_to_top,
    unified_diff,
    validate_module_docstrings,
    write_with_backup,
)
