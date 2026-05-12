"""
MCP AST command wrappers split into dedicated modules.

This package holds the MCP-facing command classes (Command subclasses) that
wrap internal code-analysis commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from .get_ast import GetASTMCPCommand
from .search_nodes import SearchASTNodesMCPCommand
from .statistics import ASTStatisticsMCPCommand
from .list_files import ListProjectFilesMCPCommand
from .entity_info import GetCodeEntityInfoMCPCommand
from .list_entities import ListCodeEntitiesMCPCommand
from .imports import GetImportsMCPCommand
from .dependencies import FindDependenciesMCPCommand
from .entity_dependencies import (
    GetEntityDependenciesMCPCommand,
    GetEntityDependentsMCPCommand,
)
from .hierarchy import GetClassHierarchyMCPCommand
from .usages import FindUsagesMCPCommand
from .graph import ExportGraphMCPCommand

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
