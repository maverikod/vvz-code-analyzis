"""
MCP command wrappers for AST operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# NOTE:
# This module is kept as a backwards-compatible shim. The implementation was
# split into `code_analysis/commands/ast/` to keep files under the 400-line
# limit. Import paths used by hooks and external integrations remain stable.

from .ast import (  # noqa: F401
    ASTStatisticsMCPCommand,
    ExportGraphMCPCommand,
    FindDependenciesMCPCommand,
    FindUsagesMCPCommand,
    GetASTMCPCommand,
    GetClassHierarchyMCPCommand,
    GetCodeEntityInfoMCPCommand,
    GetEntityDependenciesMCPCommand,
    GetEntityDependentsMCPCommand,
    GetImportsMCPCommand,
    ListCodeEntitiesMCPCommand,
    ListProjectFilesMCPCommand,
    SearchASTNodesMCPCommand,
)

__all__ = [
    "GetASTMCPCommand",
    "SearchASTNodesMCPCommand",
    "ASTStatisticsMCPCommand",
    "ListProjectFilesMCPCommand",
    "GetCodeEntityInfoMCPCommand",
    "ListCodeEntitiesMCPCommand",
    "GetImportsMCPCommand",
    "FindDependenciesMCPCommand",
    "GetEntityDependenciesMCPCommand",
    "GetEntityDependentsMCPCommand",
    "GetClassHierarchyMCPCommand",
    "FindUsagesMCPCommand",
    "ExportGraphMCPCommand",
]
