"""
Data models for CST module patching tools.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Selector:
    """
    Selector for statement blocks.

    Supported kinds:
    - module: create module from scratch (new_code becomes entire module body)
    - function: match top-level FunctionDef by name
    - class: match top-level ClassDef by name
    - method: match class method FunctionDef by qualified name "ClassName.method"
    - range: match statement by exact (start_line, end_line) anywhere in the module
    - block_id: match statement by stable id returned by list_cst_blocks
    - node_id: match statement/smallstmt by node_id returned by query_cst
    - cst_query: match statement/smallstmt by CSTQuery selector string
    """

    kind: str
    name: Optional[str] = None
    start_line: Optional[int] = None
    start_col: Optional[int] = None
    end_line: Optional[int] = None
    end_col: Optional[int] = None
    block_id: Optional[str] = None
    node_id: Optional[str] = None
    query: Optional[str] = None
    match_index: Optional[int] = None


@dataclass(frozen=True)
class ReplaceOp:
    """
    Replace operation for module-level blocks.

    If new_code is empty string, the target block is removed.
    For kind='module', file_docstring is required.
    """

    selector: Selector
    new_code: str
    file_docstring: Optional[str] = None


@dataclass(frozen=True)
class InsertOp:
    """
    Insert operation for adding new nodes.

    Inserts new_code before or after the node matched by selector.
    If selector is None or empty, inserts at the end of module/class/function body.
    """

    selector: Optional[Selector]
    new_code: str
    position: str = "after"  # "before" or "after" or "end"
    file_docstring: Optional[str] = None


@dataclass(frozen=True)
class CreateOp:
    """
    Create operation for creating new nodes.

    Creates a new node from new_code at the specified position.
    Position can be:
    - "end_of_module": at the end of module body
    - "after_selector": after the node matched by selector
    - "before_selector": before the node matched by selector
    - "end_of_class": at the end of class body (requires selector pointing to class)
    - "end_of_function": at the end of function body (requires selector pointing to function)
    """

    selector: Optional[Selector]
    new_code: str
    position: str = "end_of_module"  # "end_of_module", "after_selector", "before_selector", "end_of_class", "end_of_function"
    file_docstring: Optional[str] = None


@dataclass(frozen=True)
class BlockInfo:
    """Index entry for replaceable statement blocks."""

    block_id: str
    kind: str
    qualname: str
    start_line: int
    end_line: int
