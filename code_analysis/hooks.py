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
    from .commands.analyze_file_command import AnalyzeFileCommand
    from .commands.help_command import HelpCommand
    from .commands.check_vectors_command import CheckVectorsCommand
    from .commands.cst_compose_module_command import ComposeCSTModuleCommand
    from .commands.list_cst_blocks_command import ListCSTBlocksCommand
    from .commands.query_cst_command import QueryCSTCommand
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
        FindUsagesMCPCommand,
        ExportGraphMCPCommand,
    )
    from .commands.vector_commands import RebuildFaissCommand, RevectorizeCommand
    from .commands.semantic_search_mcp import SemanticSearchMCPCommand
    from .commands.watch_dirs_commands import AddWatchDirCommand, RemoveWatchDirCommand
    from .commands.refactor_mcp_commands import (
        SplitClassMCPCommand,
        ExtractSuperclassMCPCommand,
        SplitFileToPackageMCPCommand,
    )
    from .commands.code_quality_commands import (
        FormatCodeCommand,
        LintCodeCommand,
        TypeCheckCodeCommand,
    )
    from .commands.search_mcp_commands import (
        FulltextSearchMCPCommand,
        ListClassMethodsMCPCommand,
        FindClassesMCPCommand,
    )
    from .commands.code_mapper_mcp_command import UpdateIndexesMCPCommand

    # Register commands
    reg.register(AnalyzeProjectCommand, "custom")
    reg.register(AnalyzeFileCommand, "custom")
    reg.register(HelpCommand, "custom")
    reg.register(CheckVectorsCommand, "custom")
    reg.register(ComposeCSTModuleCommand, "custom")
    reg.register(ListCSTBlocksCommand, "custom")
    reg.register(QueryCSTCommand, "custom")
    reg.register(GetASTMCPCommand, "custom")
    reg.register(SearchASTNodesMCPCommand, "custom")
    reg.register(ASTStatisticsMCPCommand, "custom")
    reg.register(ListProjectFilesMCPCommand, "custom")
    reg.register(GetCodeEntityInfoMCPCommand, "custom")
    reg.register(ListCodeEntitiesMCPCommand, "custom")
    reg.register(GetImportsMCPCommand, "custom")
    reg.register(FindDependenciesMCPCommand, "custom")
    reg.register(GetClassHierarchyMCPCommand, "custom")
    reg.register(FindUsagesMCPCommand, "custom")
    reg.register(ExportGraphMCPCommand, "custom")
    reg.register(RebuildFaissCommand, "custom")
    reg.register(RevectorizeCommand, "custom")
    reg.register(SemanticSearchMCPCommand, "custom")
    reg.register(AddWatchDirCommand, "custom")
    reg.register(RemoveWatchDirCommand, "custom")
    reg.register(SplitClassMCPCommand, "custom")
    reg.register(ExtractSuperclassMCPCommand, "custom")
    reg.register(SplitFileToPackageMCPCommand, "custom")
    reg.register(FormatCodeCommand, "custom")
    reg.register(LintCodeCommand, "custom")
    reg.register(TypeCheckCodeCommand, "custom")
    reg.register(FulltextSearchMCPCommand, "custom")
    reg.register(ListClassMethodsMCPCommand, "custom")
    reg.register(FindClassesMCPCommand, "custom")
    reg.register(UpdateIndexesMCPCommand, "custom")


# Register hook
register_custom_commands_hook(register_code_analysis_commands)

# Register modules for auto-import in child processes (spawn mode)
register_auto_import_module("code_analysis.commands.analyze_project_command")
register_auto_import_module("code_analysis.commands.analyze_file_command")
register_auto_import_module("code_analysis.commands.help_command")
register_auto_import_module("code_analysis.commands.check_vectors_command")
register_auto_import_module("code_analysis.commands.cst_compose_module_command")
register_auto_import_module("code_analysis.commands.list_cst_blocks_command")
register_auto_import_module("code_analysis.commands.query_cst_command")
register_auto_import_module("code_analysis.commands.ast_mcp_commands")
register_auto_import_module("code_analysis.commands.vector_commands")
register_auto_import_module("code_analysis.commands.semantic_search_mcp")
register_auto_import_module("code_analysis.commands.watch_dirs_commands")
register_auto_import_module("code_analysis.commands.refactor_mcp_commands")
register_auto_import_module("code_analysis.commands.code_quality_commands")
register_auto_import_module("code_analysis.commands.search_mcp_commands")
register_auto_import_module("code_analysis.commands.code_mapper_mcp_command")
