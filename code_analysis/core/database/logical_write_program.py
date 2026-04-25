"""
Logical write program types for composite SQLite RPC transactions.

Defines TypedDict payloads for execute_logical_write_operation (one RPC, full transaction).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Literal, Sequence, Tuple, TypedDict

DEFAULT_DEFER_CONSTRAINTS: bool = False

SqlParamPair = Tuple[str, Sequence[Any]]


class LogicalWriteProgramV1(TypedDict, total=False):
    batches: list[list[SqlParamPair]]
    defer_constraints: bool
    operation_name: str
    project_id: str
    lock_scope: Literal["none", "project_write", "project_read"]
