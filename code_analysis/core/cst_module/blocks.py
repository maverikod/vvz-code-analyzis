"""
Logical block listing for CST module tools.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import libcst as cst
from libcst.metadata import MetadataWrapper, PositionProvider

from .models import BlockInfo


def _block_id(kind: str, qualname: str, start_line: int, end_line: int) -> str:
    # Stable enough for edit workflows; if code moves, user refreshes via list_cst_blocks.
    return f"{kind}:{qualname}:{start_line}-{end_line}"


def list_cst_blocks(source: str) -> list[BlockInfo]:
    """
    List replaceable statement blocks with stable ids.

    We focus on *logical blocks*:
    - top-level classes/functions
    - class methods
    - any statement by line-range selector (still supported via range)
    """
    module = cst.parse_module(source)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)

    blocks: list[BlockInfo] = []

    for stmt in module.body:
        pos = positions.get(stmt)
        if pos is None:
            continue
        if isinstance(stmt, cst.FunctionDef):
            qual = stmt.name.value
            blocks.append(
                BlockInfo(
                    block_id=_block_id("function", qual, pos.start.line, pos.end.line),
                    kind="function",
                    qualname=qual,
                    start_line=pos.start.line,
                    end_line=pos.end.line,
                )
            )
        elif isinstance(stmt, cst.ClassDef):
            class_name = stmt.name.value
            blocks.append(
                BlockInfo(
                    block_id=_block_id(
                        "class", class_name, pos.start.line, pos.end.line
                    ),
                    kind="class",
                    qualname=class_name,
                    start_line=pos.start.line,
                    end_line=pos.end.line,
                )
            )
            # Methods
            for cstmt in stmt.body.body:
                if not isinstance(cstmt, cst.FunctionDef):
                    continue
                mpos = positions.get(cstmt)
                if mpos is None:
                    continue
                qual = f"{class_name}.{cstmt.name.value}"
                blocks.append(
                    BlockInfo(
                        block_id=_block_id(
                            "method", qual, mpos.start.line, mpos.end.line
                        ),
                        kind="method",
                        qualname=qual,
                        start_line=mpos.start.line,
                        end_line=mpos.end.line,
                    )
                )

    return blocks
