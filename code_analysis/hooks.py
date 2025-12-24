"""
Command registration hooks for code-analysis-server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

# Import patch for CommandExecutionJob to support progress tracking
# This must be imported before CommandExecutionJob is used
from .core.command_execution_job_patch import patch_command_execution_job  # noqa: F401

from mcp_proxy_adapter.commands.hooks import register_custom_commands_hook
from mcp_proxy_adapter.commands.command_registry import registry
from mcp_proxy_adapter.commands.hooks import register_auto_import_module


def register_code_analysis_commands(reg: registry) -> None:
    """Register all code analysis commands."""
    from .commands.analyze_project_command import AnalyzeProjectCommand
    from .commands.help_command import HelpCommand
    from .commands.check_vectors_command import CheckVectorsCommand
    from .commands.ast_mcp_commands import (
        GetASTMCPCommand,
        SearchASTNodesMCPCommand,
        ASTStatisticsMCPCommand,
        ListProjectFilesMCPCommand,
        GetCodeEntityInfoMCPCommand,
        ListCodeEntitiesMCPCommand,
        GetImportsMCPCommand,
        FindDependenciesMCPCommand,
        GetClassHierarchyMCPCommand,
    )
    from .commands.vector_commands import RebuildFaissCommand, RevectorizeCommand
    from .commands.semantic_search_mcp import SemanticSearchMCPCommand
    from .commands.watch_dirs_commands import AddWatchDirCommand, RemoveWatchDirCommand

    # Register commands
    reg.register(AnalyzeProjectCommand, "custom")
    reg.register(HelpCommand, "custom")
    reg.register(CheckVectorsCommand, "custom")
    reg.register(GetASTMCPCommand, "custom")
    reg.register(SearchASTNodesMCPCommand, "custom")
    reg.register(ASTStatisticsMCPCommand, "custom")
    reg.register(ListProjectFilesMCPCommand, "custom")
    reg.register(GetCodeEntityInfoMCPCommand, "custom")
    reg.register(ListCodeEntitiesMCPCommand, "custom")
    reg.register(GetImportsMCPCommand, "custom")
    reg.register(FindDependenciesMCPCommand, "custom")
    reg.register(GetClassHierarchyMCPCommand, "custom")
    reg.register(RebuildFaissCommand, "custom")
    reg.register(RevectorizeCommand, "custom")
    reg.register(SemanticSearchMCPCommand, "custom")
    reg.register(AddWatchDirCommand, "custom")
    reg.register(RemoveWatchDirCommand, "custom")


# Register hook
register_custom_commands_hook(register_code_analysis_commands)

# Register modules for auto-import in child processes (spawn mode)
register_auto_import_module("code_analysis.commands.analyze_project_command")
register_auto_import_module("code_analysis.commands.help_command")
register_auto_import_module("code_analysis.commands.check_vectors_command")
register_auto_import_module("code_analysis.commands.ast_mcp_commands")
register_auto_import_module("code_analysis.commands.vector_commands")
register_auto_import_module("code_analysis.commands.semantic_search_mcp")
register_auto_import_module("code_analysis.commands.watch_dirs_commands")
