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
    # Import commands that exist (with try/except for missing ones)
    # Note: Some commands may be in different locations or not exist yet

    # Try to import existing commands
    try:
        from .commands.analyze_project_command import AnalyzeProjectCommand

        reg.register(AnalyzeProjectCommand, "custom")
    except ImportError:
        pass

    try:
        from .commands.analyze_file_command import AnalyzeFileCommand

        reg.register(AnalyzeFileCommand, "custom")
    except ImportError:
        pass

    try:
        from .commands.help_command import HelpCommand

        reg.register(HelpCommand, "custom")
    except ImportError:
        pass

    try:
        from .commands.check_vectors_command import CheckVectorsCommand

        reg.register(CheckVectorsCommand, "custom")
    except ImportError:
        pass

    try:
        from .commands.cst_compose_module_command import ComposeCSTModuleCommand

        reg.register(ComposeCSTModuleCommand, "custom")
    except ImportError:
        pass

    try:
        from .commands.list_cst_blocks_command import ListCSTBlocksCommand

        reg.register(ListCSTBlocksCommand, "custom")
    except ImportError:
        pass

    try:
        from .commands.query_cst_command import QueryCSTCommand

        reg.register(QueryCSTCommand, "custom")
    except ImportError:
        pass

    try:
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
    except ImportError:
        pass

    try:
        from .commands.code_mapper_mcp_command import UpdateIndexesMCPCommand

        reg.register(UpdateIndexesMCPCommand, "custom")
    except ImportError:
        pass

    try:
        from .commands.vector_commands import RebuildFaissCommand, RevectorizeCommand

        reg.register(RebuildFaissCommand, "custom")
        reg.register(RevectorizeCommand, "custom")
    except ImportError:
        pass

    try:
        from .commands.semantic_search_mcp import SemanticSearchMCPCommand

        reg.register(SemanticSearchMCPCommand, "custom")
        import logging

        logger = logging.getLogger(__name__)
        logger.info("✅ Registered semantic_search command")
    except ImportError as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to import semantic_search command: {e}")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to register semantic_search command: {e}", exc_info=True)

    try:
        from .commands.watch_dirs_commands import (
            AddWatchDirCommand,
            RemoveWatchDirCommand,
        )

        reg.register(AddWatchDirCommand, "custom")
        reg.register(RemoveWatchDirCommand, "custom")
    except ImportError:
        pass

    try:
        from .commands.refactor_mcp_commands import (
            SplitClassMCPCommand,
            ExtractSuperclassMCPCommand,
            SplitFileToPackageMCPCommand,
        )

        reg.register(SplitClassMCPCommand, "custom")
        reg.register(ExtractSuperclassMCPCommand, "custom")
        reg.register(SplitFileToPackageMCPCommand, "custom")
    except ImportError:
        pass

    # Code quality commands (exist)
    from .commands.code_quality_commands import (
        FormatCodeCommand,
        LintCodeCommand,
        TypeCheckCodeCommand,
    )

    reg.register(FormatCodeCommand, "custom")
    reg.register(LintCodeCommand, "custom")
    reg.register(TypeCheckCodeCommand, "custom")

    # Search commands (may have dependencies)
    try:
        from .commands.search_mcp_commands import (
            FulltextSearchMCPCommand,
            ListClassMethodsMCPCommand,
            FindClassesMCPCommand,
        )

        reg.register(FulltextSearchMCPCommand, "custom")
        reg.register(ListClassMethodsMCPCommand, "custom")
        reg.register(FindClassesMCPCommand, "custom")
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            "✅ Registered search commands: fulltext_search, list_class_methods, find_classes"
        )
    except ImportError as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to import search commands: {e}")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to register search commands: {e}", exc_info=True)

    # Code mapper commands (may have dependencies)
    try:
        from .commands.code_mapper_mcp_command import UpdateIndexesMCPCommand

        reg.register(UpdateIndexesMCPCommand, "custom")
    except ImportError:
        pass

    try:
        from .commands.code_mapper_mcp_commands import (
            ListLongFilesMCPCommand,
            ListErrorsByCategoryMCPCommand,
        )

        reg.register(ListLongFilesMCPCommand, "custom")
        reg.register(ListErrorsByCategoryMCPCommand, "custom")
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            "✅ Registered code_mapper commands: list_long_files, list_errors_by_category"
        )
    except ImportError as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to import code_mapper commands: {e}")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to register code_mapper commands: {e}", exc_info=True)

    # Backup commands (exist)
    from .commands.backup_mcp_commands import (
        ListBackupFilesMCPCommand,
        ListBackupVersionsMCPCommand,
        RestoreBackupFileMCPCommand,
        DeleteBackupMCPCommand,
        ClearAllBackupsMCPCommand,
    )

    reg.register(ListBackupFilesMCPCommand, "custom")
    reg.register(ListBackupVersionsMCPCommand, "custom")
    reg.register(RestoreBackupFileMCPCommand, "custom")
    reg.register(DeleteBackupMCPCommand, "custom")
    reg.register(ClearAllBackupsMCPCommand, "custom")

    # File management commands (exist)
    try:
        from .commands.file_management_mcp_commands import (
            CleanupDeletedFilesMCPCommand,
            UnmarkDeletedFileMCPCommand,
            CollapseVersionsMCPCommand,
            RepairDatabaseMCPCommand,
        )

        reg.register(CleanupDeletedFilesMCPCommand, "custom")
        reg.register(UnmarkDeletedFileMCPCommand, "custom")
        reg.register(CollapseVersionsMCPCommand, "custom")
        reg.register(RepairDatabaseMCPCommand, "custom")
        import logging

        logger = logging.getLogger(__name__)
        logger.info("✅ Registered repair_database command")
    except ImportError as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to import file management commands: {e}")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to register file management commands: {e}", exc_info=True)

    # Log viewer commands (exist)
    from .commands.log_viewer_mcp_commands import (
        ViewWorkerLogsMCPCommand,
        ListWorkerLogsMCPCommand,
    )

    reg.register(ViewWorkerLogsMCPCommand, "custom")
    reg.register(ListWorkerLogsMCPCommand, "custom")

    # Worker status commands (exist)
    from .commands.worker_status_mcp_commands import (
        GetWorkerStatusMCPCommand,
        GetDatabaseStatusMCPCommand,
    )

    reg.register(GetWorkerStatusMCPCommand, "custom")
    reg.register(GetDatabaseStatusMCPCommand, "custom")

    # Repair worker management commands (NEW)
    try:
        from .commands.repair_worker_mcp_commands import (
            StartRepairWorkerMCPCommand,
            StopRepairWorkerMCPCommand,
            RepairWorkerStatusMCPCommand,
        )

        reg.register(StartRepairWorkerMCPCommand, "custom")
        reg.register(StopRepairWorkerMCPCommand, "custom")
        reg.register(RepairWorkerStatusMCPCommand, "custom")
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            "✅ Registered repair worker commands: start_repair_worker, stop_repair_worker, repair_worker_status"
        )
    except ImportError as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to import repair worker commands: {e}")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to register repair worker commands: {e}", exc_info=True)

    # Worker management commands (start/stop file_watcher/vectorization)
    try:
        from .commands.worker_management_mcp_commands import (
            StartWorkerMCPCommand,
            StopWorkerMCPCommand,
        )

        reg.register(StartWorkerMCPCommand, "custom")
        reg.register(StopWorkerMCPCommand, "custom")
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            "✅ Registered worker management commands: start_worker, stop_worker"
        )
    except ImportError as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to import worker management commands: {e}")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(
            f"Failed to register worker management commands: {e}", exc_info=True
        )


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
register_auto_import_module("code_analysis.commands.backup_mcp_commands")
register_auto_import_module("code_analysis.commands.file_management_mcp_commands")
register_auto_import_module("code_analysis.commands.log_viewer_mcp_commands")
register_auto_import_module("code_analysis.commands.worker_status_mcp_commands")
register_auto_import_module("code_analysis.commands.repair_worker_mcp_commands")
register_auto_import_module("code_analysis.commands.worker_management_mcp_commands")
