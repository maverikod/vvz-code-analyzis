"""
Build skeleton (collapsed) representation of a CST tree.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import libcst as cst

from .models import CSTTree

# Placeholder comment shown instead of callable bodies in skeleton view.
BODY_PLACEHOLDER_COMMENT = "# Call node body to see code"


class _SkeletonTransformer(cst.CSTTransformer):
    """Replaces function/method bodies with a comment and pass."""

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        placeholder = cst.IndentedBlock(
            body=[
                cst.SimpleStatementLine(
                    leading_lines=[
                        cst.EmptyLine(comment=cst.Comment(BODY_PLACEHOLDER_COMMENT))
                    ],
                    body=[cst.Pass()],
                )
            ]
        )
        return updated_node.with_changes(body=placeholder)


def skeleton_from_tree(tree: CSTTree) -> str:
    """
    Build skeleton source code from a CST tree.

    Module-level content (docstring, variables, expressions) is kept full.
    Each function/method body is replaced by a single comment and `pass`,
    so the result looks like collapsed branches in an editor.

    Args:
        tree: CSTTree (must have tree.module set).

    Returns:
        Skeleton source code as string.
    """
    transformed = tree.module.visit(_SkeletonTransformer())
    return transformed.code
