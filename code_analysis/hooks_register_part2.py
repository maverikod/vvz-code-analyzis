"""
Register second part of code analysis commands (backup, file, log, workers, DB, projects).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging

from mcp_proxy_adapter.commands.command_registry import registry

logger = logging.getLogger(__name__)


def register_commands_part2(reg: registry) -> None:
    """Register backup, file management, log viewer, workers, DB integrity, restore, projects."""
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

    try:
        from .commands.file_management_mcp_commands import (
            CleanupDeletedFilesMCPCommand,
            CollapseVersionsMCPCommand,
            CreateTextFileMCPCommand,
            DeleteFileMCPCommand,
            DeleteFilesByMaskMCPCommand,
            ListDeletedFilesMCPCommand,
            RepairDatabaseMCPCommand,
            RunUuidIdentityMigrationMCPCommand,
            RestoreDeletedFilesMCPCommand,
            UnmarkDeletedFileMCPCommand,
        )

        reg.register(CleanupDeletedFilesMCPCommand, "custom")
        reg.register(CreateTextFileMCPCommand, "custom")
        reg.register(DeleteFileMCPCommand, "custom")
        reg.register(DeleteFilesByMaskMCPCommand, "custom")
        reg.register(ListDeletedFilesMCPCommand, "custom")
        reg.register(UnmarkDeletedFileMCPCommand, "custom")
        reg.register(RestoreDeletedFilesMCPCommand, "custom")
        reg.register(CollapseVersionsMCPCommand, "custom")
        reg.register(RepairDatabaseMCPCommand, "custom")
        reg.register(RunUuidIdentityMigrationMCPCommand, "custom")
        logger.info("✅ Registered repair_database command")
        logger.info("✅ Registered run_uuid_identity_migration command")
    except ImportError as e:
        logger.warning("Failed to import file management commands: %s", e)
    except Exception as e:
        logger.error(
            "Failed to register file management commands: %s", e, exc_info=True
        )

    from .commands.log_viewer_mcp_commands import (
        AnalyzeTimingBottlenecksMCPCommand,
        ListLogsMCPCommand,
        ListWorkerLogsMCPCommand,
        RotateAllLogsMCPCommand,
        RotateWorkerLogsMCPCommand,
        ViewWorkerLogsMCPCommand,
    )

    reg.register(ViewWorkerLogsMCPCommand, "custom")
    reg.register(ListLogsMCPCommand, "custom")
    reg.register(ListWorkerLogsMCPCommand, "custom")
    reg.register(RotateWorkerLogsMCPCommand, "custom")
    reg.register(RotateAllLogsMCPCommand, "custom")
    reg.register(AnalyzeTimingBottlenecksMCPCommand, "custom")

    from .commands.worker_status_mcp_commands import (
        GetDatabaseStatusMCPCommand,
        GetWorkerStatusMCPCommand,
        ListIndexingErrorsMCPCommand,
    )

    reg.register(GetWorkerStatusMCPCommand, "custom")
    reg.register(GetDatabaseStatusMCPCommand, "custom")
    reg.register(ListIndexingErrorsMCPCommand, "custom")

    try:
        from .commands.repair_worker_mcp_commands import (
            RepairWorkerStatusMCPCommand,
            StartRepairWorkerMCPCommand,
            StopRepairWorkerMCPCommand,
        )

        reg.register(StartRepairWorkerMCPCommand, "custom")
        reg.register(StopRepairWorkerMCPCommand, "custom")
        reg.register(RepairWorkerStatusMCPCommand, "custom")
        logger.info("✅ Registered repair worker commands")
    except ImportError as e:
        logger.warning("Failed to import repair worker commands: %s", e)
    except Exception as e:
        logger.error("Failed to register repair worker commands: %s", e, exc_info=True)

    try:
        from .commands.worker_management_mcp_commands import (
            StartWorkerMCPCommand,
            StopWorkerMCPCommand,
        )

        reg.register(StartWorkerMCPCommand, "custom")
        reg.register(StopWorkerMCPCommand, "custom")
        logger.info("✅ Registered worker management commands")
    except ImportError as e:
        logger.warning("Failed to import worker management commands: %s", e)
    except Exception as e:
        logger.error(
            "Failed to register worker management commands: %s", e, exc_info=True
        )

    try:
        from .commands.database_integrity_mcp_commands import (
            BackupDatabaseMCPCommand,
            GetDatabaseCorruptionStatusMCPCommand,
            RepairSQLiteDatabaseMCPCommand,
        )

        reg.register(GetDatabaseCorruptionStatusMCPCommand, "custom")
        reg.register(BackupDatabaseMCPCommand, "custom")
        reg.register(RepairSQLiteDatabaseMCPCommand, "custom")
        logger.info("✅ Registered database_integrity commands")
    except ImportError as e:
        logger.warning("Failed to import database_integrity commands: %s", e)
    except Exception as e:
        logger.error(
            "Failed to register database_integrity commands: %s", e, exc_info=True
        )

    try:
        from .commands.database_restore_mcp_commands import (
            RestoreDatabaseFromConfigMCPCommand,
        )

        reg.register(RestoreDatabaseFromConfigMCPCommand, "custom")
        logger.info("✅ Registered restore_database command")
    except ImportError as e:
        logger.warning("Failed to import restore_database command: %s", e)
    except Exception as e:
        logger.error(
            "Failed to register restore_database command: %s", e, exc_info=True
        )

    try:
        from .commands.project_management_mcp_commands import (
            ChangeProjectIdMCPCommand,
            ClearTrashMCPCommand,
            CreateProjectMCPCommand,
            DeleteProjectMCPCommand,
            DeleteUnwatchedProjectsMCPCommand,
            ListProjectsMCPCommand,
            ListTrashedProjectsMCPCommand,
            ListWatchDirsMCPCommand,
            PermanentlyDeleteFromTrashMCPCommand,
            RestoreProjectFromTrashMCPCommand,
            SetProjectProcessingPausedMCPCommand,
        )
        from .commands.run_project_script_command import RunProjectScriptCommand
        from .commands.run_project_module_command import RunProjectModuleCommand
        from .commands.project_pip_commands import (
            ProjectPipCheckCommand,
            ProjectPipInstallCommand,
            ProjectPipListCommand,
            ProjectPipSearchCommand,
            ProjectPipShowCommand,
            ProjectPipUninstallCommand,
        )

        reg.register(ChangeProjectIdMCPCommand, "custom")
        reg.register(CreateProjectMCPCommand, "custom")
        reg.register(ListWatchDirsMCPCommand, "custom")
        reg.register(DeleteProjectMCPCommand, "custom")
        reg.register(DeleteUnwatchedProjectsMCPCommand, "custom")
        reg.register(ListProjectsMCPCommand, "custom")
        reg.register(ListTrashedProjectsMCPCommand, "custom")
        reg.register(PermanentlyDeleteFromTrashMCPCommand, "custom")
        reg.register(RestoreProjectFromTrashMCPCommand, "custom")
        reg.register(SetProjectProcessingPausedMCPCommand, "custom")
        reg.register(ClearTrashMCPCommand, "custom")
        reg.register(RunProjectScriptCommand, "custom")
        reg.register(RunProjectModuleCommand, "custom")
        reg.register(ProjectPipInstallCommand, "custom")
        reg.register(ProjectPipListCommand, "custom")
        reg.register(ProjectPipShowCommand, "custom")
        reg.register(ProjectPipUninstallCommand, "custom")
        reg.register(ProjectPipCheckCommand, "custom")
        reg.register(ProjectPipSearchCommand, "custom")
        logger.info("✅ Registered project management commands")
    except ImportError as e:
        logger.warning("Failed to import project management commands: %s", e)
    except Exception as e:
        logger.error(
            "Failed to register project management commands: %s", e, exc_info=True
        )

    try:
        from .commands.universal_file_preview_command import (
            UniversalFilePreviewCommand,
        )

        reg.register(UniversalFilePreviewCommand, "custom")
        logger.info("✅ Registered universal_file_preview command")
    except ImportError as e:
        logger.warning("Failed to import universal_file_preview command: %s", e)
    except Exception as e:
        logger.error(
            "Failed to register universal_file_preview command: %s",
            e,
            exc_info=True,
        )
    try:
        from .commands.universal_file_edit.open_command import UniversalFileOpenCommand
        from .commands.universal_file_edit.edit_command import UniversalFileEditCommand
        from .commands.universal_file_edit.write_command import (
            UniversalFileWriteCommand,
        )
        from .commands.universal_file_edit.close_command import (
            UniversalFileCloseCommand,
        )
        from .commands.universal_file_edit.move_nodes_command import (
            UniversalFileMoveNodesCommand,
        )
        from .commands.universal_file_edit.search_command import (
            UniversalFileSearchCommand,
        )
        from .commands.universal_file_edit.session_git_log_command import (
            SessionGitLogCommand,
        )
        from .commands.universal_file_edit.session_git_diff_command import (
            SessionGitDiffCommand,
        )
        from .commands.universal_file_edit.session_git_show_command import (
            SessionGitShowCommand,
        )
        from .commands.universal_file_edit.session_git_status_command import (
            SessionGitStatusCommand,
        )
        from .commands.universal_file_edit.session_git_revert_command import (
            SessionGitRevertCommand,
        )
        from .commands.universal_file_edit.session_write_command import (
            SessionWriteCommand,
        )

        reg.register(UniversalFileOpenCommand, "custom")
        reg.register(UniversalFileEditCommand, "custom")
        reg.register(UniversalFileWriteCommand, "custom")
        reg.register(UniversalFileCloseCommand, "custom")
        reg.register(UniversalFileMoveNodesCommand, "custom")
        reg.register(UniversalFileSearchCommand, "custom")
        reg.register(SessionGitLogCommand, "custom")
        reg.register(SessionGitDiffCommand, "custom")
        reg.register(SessionGitShowCommand, "custom")
        reg.register(SessionGitStatusCommand, "custom")
        reg.register(SessionGitRevertCommand, "custom")
        reg.register(SessionWriteCommand, "custom")
        logger.info("Registered universal_file_edit commands")
    except ImportError as e:
        logger.warning("Failed to import universal_file_edit commands: %s", e)
    except Exception as e:
        logger.error(
            "Failed to register universal_file_edit commands: %s",
            e,
            exc_info=True,
        )

    try:
        from .commands.sessions.session_create_command import SessionCreateCommand
        from .commands.sessions.session_delete_command import SessionDeleteCommand
        from .commands.sessions.session_list_command import SessionListCommand
        from .commands.sessions.session_view_command import SessionViewCommand
        from .commands.sessions.session_open_file_command import SessionOpenFileCommand
        from .commands.sessions.session_close_file_command import (
            SessionCloseFileCommand,
        )
        from .commands.sessions.session_list_file_locks_command import (
            SessionListFileLocksCommand,
        )
        from .commands.sessions.subordinate_session_commands import (
            SubordinateSessionCreateCommand,
            SubordinateSessionDeleteCommand,
            SubordinateSessionGetCommand,
            SubordinateSessionListCommand,
            SubordinateSessionUpdateCommand,
        )

        reg.register(SessionCreateCommand, "custom")
        reg.register(SessionDeleteCommand, "custom")
        reg.register(SessionListCommand, "custom")
        reg.register(SessionViewCommand, "custom")
        reg.register(SessionOpenFileCommand, "custom")
        reg.register(SessionCloseFileCommand, "custom")
        reg.register(SessionListFileLocksCommand, "custom")
        reg.register(SubordinateSessionCreateCommand, "custom")
        reg.register(SubordinateSessionGetCommand, "custom")
        reg.register(SubordinateSessionUpdateCommand, "custom")
        reg.register(SubordinateSessionDeleteCommand, "custom")
        reg.register(SubordinateSessionListCommand, "custom")
        logger.info("Registered session_management commands")
    except ImportError as e:
        logger.warning("Failed to import session_management commands: %s", e)
    except Exception as e:
        logger.error(
            "Failed to register session_management commands: %s",
            e,
            exc_info=True,
        )
