"""
Docstring chunker package.

This package provides `DocstringChunker`, used by the vectorization worker to
extract docstrings from Python files and store them as `code_chunks`.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .docstring_chunker import DocstringChunker

__all__ = ["DocstringChunker"]
