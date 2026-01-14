"""
Tree action types for AST/CST tree modifications.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from enum import Enum


class TreeAction(str, Enum):
    """Tree modification action type.

    Defines the type of operation to perform on tree nodes.
    Used for AST and CST tree modification operations.

    Values:
        REPLACE: Replace matched nodes with new nodes
        DELETE: Delete matched nodes
        INSERT: Insert new nodes (before/after target nodes)
    """

    REPLACE = "replace"
    DELETE = "delete"
    INSERT = "insert"
