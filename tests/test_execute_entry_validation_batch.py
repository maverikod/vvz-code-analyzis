"""Execute-entry validate_params tests for wave-6 and wave-7 commands."""

from __future__ import annotations

import uuid

import pytest

from code_analysis.commands.analyze_complexity_mcp import AnalyzeComplexityMCPCommand
from code_analysis.commands.ast.dependencies import FindDependenciesMCPCommand
from code_analysis.commands.ast.entity_info import GetCodeEntityInfoMCPCommand
from code_analysis.commands.ast.get_ast import GetASTMCPCommand
from code_analysis.commands.ast.hierarchy import GetClassHierarchyMCPCommand
from code_analysis.commands.ast.list_entities import ListCodeEntitiesMCPCommand
from code_analysis.commands.ast.statistics import ASTStatisticsMCPCommand
from code_analysis.commands.ast.usages import FindUsagesMCPCommand
from code_analysis.commands.backup_mcp_commands.restore_backup_file import (
    RestoreBackupFileMCPCommand,
)
from code_analysis.commands.check_vectors_command import CheckVectorsCommand
from code_analysis.commands.code_mapper_mcp_command import UpdateIndexesMCPCommand
from code_analysis.commands.comprehensive_analysis_mcp.command import (
    ComprehensiveAnalysisMCPCommand,
)
from code_analysis.commands.database_integrity_mcp_commands.get_corruption_status import (
    GetDatabaseCorruptionStatusMCPCommand,
)
from code_analysis.commands.project_management_mcp_commands.delete_project import (
    DeleteProjectMCPCommand,
)
from code_analysis.commands.refactor_extract_superclass import (
    ExtractSuperclassMCPCommand,
)
from code_analysis.commands.search_mcp_commands_find_classes import (
    FindClassesMCPCommand,
)
from code_analysis.commands.search_mcp_commands_fulltext import FulltextSearchMCPCommand
from code_analysis.commands.vector_commands.revectorize import RevectorizeCommand
from mcp_proxy_adapter.commands.result import ErrorResult

_VALID_PROJECT_ID = str(uuid.uuid4())


@pytest.mark.parametrize(
    ("command_cls", "execute_kwargs"),
    [
        (ComprehensiveAnalysisMCPCommand, {"project_id": _VALID_PROJECT_ID}),
        (AnalyzeComplexityMCPCommand, {"project_id": _VALID_PROJECT_ID}),
        (FindClassesMCPCommand, {"project_id": _VALID_PROJECT_ID}),
        (
            FindUsagesMCPCommand,
            {"project_id": _VALID_PROJECT_ID, "target_name": "foo"},
        ),
        (
            FindDependenciesMCPCommand,
            {"project_id": _VALID_PROJECT_ID, "entity_name": "Bar"},
        ),
        (
            GetASTMCPCommand,
            {"project_id": _VALID_PROJECT_ID, "file_path": "src/main.py"},
        ),
        (CheckVectorsCommand, {"project_id": _VALID_PROJECT_ID}),
        (RevectorizeCommand, {"project_id": _VALID_PROJECT_ID}),
        (
            GetCodeEntityInfoMCPCommand,
            {
                "project_id": _VALID_PROJECT_ID,
                "entity_type": "class",
                "entity_name": "Foo",
            },
        ),
        (ListCodeEntitiesMCPCommand, {"project_id": _VALID_PROJECT_ID}),
        (GetClassHierarchyMCPCommand, {"project_id": _VALID_PROJECT_ID}),
        (ASTStatisticsMCPCommand, {"project_id": _VALID_PROJECT_ID}),
        (GetDatabaseCorruptionStatusMCPCommand, {}),
        (UpdateIndexesMCPCommand, {"project_id": _VALID_PROJECT_ID}),
        (DeleteProjectMCPCommand, {"project_id": _VALID_PROJECT_ID}),
        (
            RestoreBackupFileMCPCommand,
            {"project_id": _VALID_PROJECT_ID, "file_path": "src/main.py"},
        ),
        (
            ExtractSuperclassMCPCommand,
            {
                "project_id": _VALID_PROJECT_ID,
                "file_path": "src/models.py",
                "config": {"child_classes": ["A", "B"], "base_class_name": "Base"},
            },
        ),
        (
            FulltextSearchMCPCommand,
            {"project_id": _VALID_PROJECT_ID, "query": "search term"},
        ),
    ],
)
@pytest.mark.asyncio
async def test_execute_rejects_unknown_param(
    command_cls: type,
    execute_kwargs: dict[str, object],
) -> None:
    """Verify test execute rejects unknown param."""
    cmd = command_cls()
    result = await cmd.execute(**execute_kwargs, __unknown_param__="x")
    assert isinstance(result, ErrorResult)
    assert result.code == "VALIDATION_ERROR"
    assert "unknown parameter" in result.message.lower()
