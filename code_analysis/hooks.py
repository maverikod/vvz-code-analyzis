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
    """Register all code analysis commands.

    Args:
        reg: MCP command registry instance.

    Returns:
        None
    """
    # Import commands that exist (with try/except for missing ones)
    # Note: Some commands may be in different locations or not exist yet

    # Try to import existing commands
    try:
        from .commands.analyze_project_command import AnalyzeProjectCommand  # type: ignore[import-not-found]

        reg.register(AnalyzeProjectCommand, "custom")
    except ImportError:
        pass

    try:
        from .commands.analyze_file_command import AnalyzeFileCommand  # type: ignore[import-not-found]

        reg.register(AnalyzeFileCommand, "custom")
    except ImportError:
        pass

    try:
        from .commands.help_command import HelpCommand  # type: ignore[import-not-found]

        reg.register(HelpCommand, "custom")
    except ImportError:
        pass

    try:
        from .commands.check_vectors_command import CheckVectorsCommand  # type: ignore[import-not-found]

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

    # New CST tree commands
    try:
        from .commands.cst_load_file_command import CSTLoadFileCommand
        from .commands.cst_modify_tree_command import CSTModifyTreeCommand
        from .commands.cst_save_tree_command import CSTSaveTreeCommand
        from .commands.cst_reload_tree_command import CSTReloadTreeCommand
        from .commands.cst_find_node_command import CSTFindNodeCommand
        from .commands.cst_get_node_info_command import CSTGetNodeInfoCommand
        from .commands.cst_get_node_by_range_command import CSTGetNodeByRangeCommand
        from .commands.cst_create_file_command import CSTCreateFileCommand
        from .commands.cst_convert_and_save_command import CSTConvertAndSaveCommand

        reg.register(CSTLoadFileCommand, "custom")
        reg.register(CSTModifyTreeCommand, "custom")
        reg.register(CSTSaveTreeCommand, "custom")
        reg.register(CSTReloadTreeCommand, "custom")
        reg.register(CSTFindNodeCommand, "custom")
        reg.register(CSTGetNodeInfoCommand, "custom")
        reg.register(CSTGetNodeByRangeCommand, "custom")
        reg.register(CSTCreateFileCommand, "custom")
        reg.register(CSTConvertAndSaveCommand, "custom")
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            "✅ Registered CST tree commands: "
            "cst_load_file, cst_modify_tree, cst_save_tree, cst_reload_tree, "
            "cst_find_node, cst_get_node_info, cst_get_node_by_range, "
            "cst_create_file, cst_convert_and_save"
        )
    except ImportError as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to import CST tree commands: {e}")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to register CST tree commands: {e}", exc_info=True)

    try:
        from .commands.ast_mcp_commands import (
            ASTStatisticsMCPCommand,
            ExportGraphMCPCommand,
            FindDependenciesMCPCommand,
            FindUsagesMCPCommand,
            GetASTMCPCommand,
            GetClassHierarchyMCPCommand,
            GetCodeEntityInfoMCPCommand,
            GetImportsMCPCommand,
            ListCodeEntitiesMCPCommand,
            ListProjectFilesMCPCommand,
            SearchASTNodesMCPCommand,
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
        from .commands.watch_dirs_commands import (  # type: ignore[import-not-found]
            AddWatchDirCommand,
            RemoveWatchDirCommand,
        )

        reg.register(AddWatchDirCommand, "custom")
        reg.register(RemoveWatchDirCommand, "custom")
    except ImportError:
        pass

    try:
        from .commands.refactor_mcp_commands import (
            ExtractSuperclassMCPCommand,
            SplitClassMCPCommand,
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

    # Complexity analysis command
    try:
        from .commands.analyze_complexity_mcp import AnalyzeComplexityMCPCommand

        reg.register(AnalyzeComplexityMCPCommand, "custom")
        import logging

        logger = logging.getLogger(__name__)
        logger.info("✅ Registered analyze_complexity command")
    except ImportError as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to import analyze_complexity command: {e}")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(
            f"Failed to register analyze_complexity command: {e}", exc_info=True
        )

    # Duplicate detection command
    try:
        from .commands.find_duplicates_mcp import FindDuplicatesMCPCommand

        reg.register(FindDuplicatesMCPCommand, "custom")
        import logging

        logger = logging.getLogger(__name__)
        logger.info("✅ Registered find_duplicates command")
    except ImportError as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to import find_duplicates command: {e}")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to register find_duplicates command: {e}", exc_info=True)

    # Comprehensive analysis command
    try:
        from .commands.comprehensive_analysis_mcp import ComprehensiveAnalysisMCPCommand

        reg.register(ComprehensiveAnalysisMCPCommand, "custom")
        import logging

        logger = logging.getLogger(__name__)
        logger.info("✅ Registered comprehensive_analysis command")
    except ImportError as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to import comprehensive_analysis command: {e}")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(
            f"Failed to register comprehensive_analysis command: {e}", exc_info=True
        )

    # Search commands (may have dependencies)
    try:
        from .commands.search_mcp_commands import (
            FindClassesMCPCommand,
            FulltextSearchMCPCommand,
            ListClassMethodsMCPCommand,
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
            ListErrorsByCategoryMCPCommand,
            ListLongFilesMCPCommand,
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
        ClearAllBackupsMCPCommand,
        DeleteBackupMCPCommand,
        ListBackupFilesMCPCommand,
        ListBackupVersionsMCPCommand,
        RestoreBackupFileMCPCommand,
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
            CollapseVersionsMCPCommand,
            RepairDatabaseMCPCommand,
            UnmarkDeletedFileMCPCommand,
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
        ListWorkerLogsMCPCommand,
        ViewWorkerLogsMCPCommand,
    )

    reg.register(ViewWorkerLogsMCPCommand, "custom")
    reg.register(ListWorkerLogsMCPCommand, "custom")

    # Worker status commands (exist)
    from .commands.worker_status_mcp_commands import (
        GetDatabaseStatusMCPCommand,
        GetWorkerStatusMCPCommand,
    )

    reg.register(GetWorkerStatusMCPCommand, "custom")
    reg.register(GetDatabaseStatusMCPCommand, "custom")

    # Repair worker management commands (NEW)
    try:
        from .commands.repair_worker_mcp_commands import (
            RepairWorkerStatusMCPCommand,
            StartRepairWorkerMCPCommand,
            StopRepairWorkerMCPCommand,
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

    # Database integrity / safe-mode commands
    try:
        from .commands.database_integrity_mcp_commands import (
            BackupDatabaseMCPCommand,
            GetDatabaseCorruptionStatusMCPCommand,
            RepairSQLiteDatabaseMCPCommand,
        )

        reg.register(GetDatabaseCorruptionStatusMCPCommand, "custom")
        reg.register(BackupDatabaseMCPCommand, "custom")
        reg.register(RepairSQLiteDatabaseMCPCommand, "custom")
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            "✅ Registered database_integrity commands: get_database_corruption_status, backup_database, repair_sqlite_database"
        )
    except ImportError as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to import database_integrity commands: {e}")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(
            f"Failed to register database_integrity commands: {e}", exc_info=True
        )

    # Database restore command (backup + recreate + sequential indexing from config)
    try:
        from .commands.database_restore_mcp_commands import (
            RestoreDatabaseFromConfigMCPCommand,
        )

        reg.register(RestoreDatabaseFromConfigMCPCommand, "custom")
        import logging

        logger = logging.getLogger(__name__)
        logger.info("✅ Registered restore_database command")
    except ImportError as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to import restore_database command: {e}")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to register restore_database command: {e}", exc_info=True)

    # Project management commands
    try:
        from .commands.project_management_mcp_commands import (
            ChangeProjectIdMCPCommand,
            CreateProjectMCPCommand,
            DeleteProjectMCPCommand,
            DeleteUnwatchedProjectsMCPCommand,
            ListProjectsMCPCommand,
        )

        reg.register(ChangeProjectIdMCPCommand, "custom")
        reg.register(CreateProjectMCPCommand, "custom")
        reg.register(DeleteProjectMCPCommand, "custom")
        reg.register(DeleteUnwatchedProjectsMCPCommand, "custom")
        reg.register(ListProjectsMCPCommand, "custom")
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            "✅ Registered project management commands: "
            "change_project_id, create_project, delete_project, delete_unwatched_projects, list_projects"
        )
    except ImportError as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to import project management commands: {e}")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(
            f"Failed to register project management commands: {e}", exc_info=True
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
register_auto_import_module("code_analysis.commands.cst_load_file_command")
register_auto_import_module("code_analysis.commands.cst_modify_tree_command")
register_auto_import_module("code_analysis.commands.cst_save_tree_command")
register_auto_import_module("code_analysis.commands.cst_reload_tree_command")
register_auto_import_module("code_analysis.commands.cst_find_node_command")
register_auto_import_module("code_analysis.commands.cst_get_node_info_command")
register_auto_import_module("code_analysis.commands.cst_get_node_by_range_command")
register_auto_import_module("code_analysis.commands.cst_create_file_command")
register_auto_import_module("code_analysis.commands.cst_convert_and_save_command")
register_auto_import_module("code_analysis.commands.cst_create_file_command")
register_auto_import_module("code_analysis.commands.ast_mcp_commands")
register_auto_import_module("code_analysis.commands.vector_commands")
register_auto_import_module("code_analysis.commands.semantic_search_mcp")
register_auto_import_module("code_analysis.commands.watch_dirs_commands")
register_auto_import_module("code_analysis.commands.refactor_mcp_commands")
register_auto_import_module("code_analysis.commands.code_quality_commands")
register_auto_import_module("code_analysis.commands.analyze_complexity_mcp")
register_auto_import_module("code_analysis.commands.find_duplicates_mcp")
register_auto_import_module("code_analysis.commands.comprehensive_analysis_mcp")
register_auto_import_module("code_analysis.commands.search_mcp_commands")
register_auto_import_module("code_analysis.commands.code_mapper_mcp_command")
register_auto_import_module("code_analysis.commands.backup_mcp_commands")
register_auto_import_module("code_analysis.commands.file_management_mcp_commands")
register_auto_import_module("code_analysis.commands.log_viewer_mcp_commands")
register_auto_import_module("code_analysis.commands.worker_status_mcp_commands")
register_auto_import_module("code_analysis.commands.repair_worker_mcp_commands")
register_auto_import_module("code_analysis.commands.worker_management_mcp_commands")
register_auto_import_module("code_analysis.commands.database_integrity_mcp_commands")
register_auto_import_module("code_analysis.commands.database_restore_mcp_commands")
register_auto_import_module("code_analysis.commands.project_management_mcp_commands")
