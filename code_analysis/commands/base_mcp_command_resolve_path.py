"""
Resolve file path from project_id and relative path for BaseMCPCommand.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path

from ..core.database_client.client import DatabaseClient
from ..core.exceptions import ValidationError


def resolve_file_path_from_project(
    database: DatabaseClient,
    project_id: str,
    relative_file_path: str,
) -> Path:
    """
    Resolve absolute file path from project_id and relative path.

    Path formation: watch_dir_path / project_name / relative_file_path.

    Args:
        database: DatabaseClient instance.
        project_id: Project identifier (UUID4).
        relative_file_path: File path relative to project root.

    Returns:
        Resolved absolute Path object.

    Raises:
        ValidationError: If project not found, watch_dir not found, or path invalid.
    """
    project = database.get_project(project_id)
    if not project:
        raise ValidationError(
            f"Project with ID {project_id} not found in database",
            field="project_id",
            details={"project_id": project_id},
        )

    if not project.watch_dir_id:
        raise ValidationError(
            f"Project {project_id} is not linked to a watch directory",
            field="project_id",
            details={
                "project_id": project_id,
                "project_name": project.name,
            },
        )

    if not project.name:
        raise ValidationError(
            f"Project {project_id} does not have a name",
            field="project_id",
            details={"project_id": project_id},
        )

    watch_dir_path_result = database.execute(
        "SELECT absolute_path FROM watch_dir_paths WHERE watch_dir_id = ?",
        (project.watch_dir_id,),
    )
    if isinstance(watch_dir_path_result, list):
        watch_dir_paths = watch_dir_path_result
    else:
        watch_dir_paths = watch_dir_path_result.get("data", [])

    if not watch_dir_paths:
        raise ValidationError(
            f"Watch directory path not found for watch_dir_id {project.watch_dir_id}",
            field="project_id",
            details={
                "project_id": project_id,
                "watch_dir_id": project.watch_dir_id,
            },
        )

    watch_dir_path = watch_dir_paths[0].get("absolute_path")
    if not watch_dir_path:
        raise ValidationError(
            f"Watch directory path is NULL for watch_dir_id {project.watch_dir_id}",
            field="project_id",
            details={
                "project_id": project_id,
                "watch_dir_id": project.watch_dir_id,
            },
        )

    absolute_path = Path(watch_dir_path) / project.name / relative_file_path
    resolved_path = absolute_path.resolve()

    if not resolved_path.exists():
        raise ValidationError(
            f"File does not exist: {resolved_path}",
            field="file_path",
            details={
                "relative_file_path": relative_file_path,
                "absolute_path": str(resolved_path),
                "watch_dir_path": watch_dir_path,
                "project_name": project.name,
            },
        )

    return resolved_path
