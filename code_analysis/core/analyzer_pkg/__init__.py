"""
Package initialization.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .ast_analysis import (
    _analyze_ast,
    _analyze_class,
    _analyze_function,
    _analyze_method,
)
from .base import CodeAnalyzer
from .checks import (
    _ast_to_dict,
    _has_file_docstring,
    _has_not_implemented_error,
    _has_pass_statement,
    _is_abstract_method,
    _save_ast_tree,
)
from .imports import _analyze_import, _analyze_import_from

CodeAnalyzer._analyze_ast = _analyze_ast
CodeAnalyzer._analyze_class = _analyze_class
CodeAnalyzer._analyze_function = _analyze_function
CodeAnalyzer._analyze_method = _analyze_method
CodeAnalyzer._analyze_import = _analyze_import
CodeAnalyzer._analyze_import_from = _analyze_import_from
CodeAnalyzer._has_file_docstring = _has_file_docstring
CodeAnalyzer._has_pass_statement = _has_pass_statement
CodeAnalyzer._has_not_implemented_error = _has_not_implemented_error
CodeAnalyzer._is_abstract_method = _is_abstract_method
CodeAnalyzer._ast_to_dict = _ast_to_dict
CodeAnalyzer._save_ast_tree = _save_ast_tree

__all__ = ["CodeAnalyzer"]
