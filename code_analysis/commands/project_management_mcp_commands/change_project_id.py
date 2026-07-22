"""
MCP command: change_project_id.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from ._shared import (
    Any,
    BaseMCPCommand,
    Dict,
    ErrorResult,
    Optional,
    Path,
    SuccessResult,
    ValidationError,
    ProjectIdError,
    load_project_id,
    _get_socket_path_from_db_path,
    logger,
    uuid,
)
from ...core.database_driver_pkg.domain.projects import get_project
from ...core.exceptions import CodeAnalysisError
from ...core.project_root_path import persist_projects_root_path_stored_value
from ...core.sql_portable import sql_julian_timestamp_now_expr
from .change_project_id_schema import get_metadata as _get_metadata
from .change_project_id_schema import get_schema as _get_schema


def _rollback_projectid_file(projectid_path: Path, prior: Optional[bytes]) -> None:
    """Restore previous projectid file contents after a failed database update."""
    try:
        if prior is None:
            if projectid_path.exists():
                projectid_path.unlink()
        else:
            projectid_path.write_bytes(prior)
    except OSError as exc:
        logger.error(
            "Could not rollback projectid file after database error: %s",
            exc,
            exc_info=True,
        )


def _db_row_root_matches_project_root(project_root: Path, row_root: str) -> bool:
    """True if DB root_path refers to the same directory as ``project_root``."""
    from ...core.path_normalization import normalize_path_simple

    try:
        return normalize_path_simple(str(row_root)) == normalize_path_simple(
            str(project_root)
        )
    except Exception:
        return (
            Path(row_root).expanduser().resolve()
            == Path(project_root).expanduser().resolve()
        )


class ChangeProjectIdMCPCommand(BaseMCPCommand):
    """
    Change project identifier in projectid file and database.

    This command updates the project identifier for a project:
    1. Validates the new project_id (must be UUID v4)
    2. Updates the projectid file in the project root
    3. Updates the project record in the database (if exists)

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue.
    """

    name = "change_project_id"
    version = "1.2.0"
    descr = (
        "Change project identifier and/or description: update projectid file and database record. "
        "New project_id must be a valid UUID v4. Description is optional."
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(
        cls: type["ChangeProjectIdMCPCommand"],
    ) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        This schema is used by MCP Proxy for request validation.
        Keep it strict and deterministic.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return _get_schema()

    @classmethod
    def metadata(cls: type["ChangeProjectIdMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return _get_metadata(
            cls.name,
            cls.version,
            cls.descr,
            cls.category,
            cls.author,
            cls.email,
        )

    def validate_params(
        self: "ChangeProjectIdMCPCommand", params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate params and reject unknown project_id before execution."""
        params = super().validate_params(params)
        BaseMCPCommand._validate_project_id_exists(params["project_id"])
        return params

    async def execute(
        self: "ChangeProjectIdMCPCommand",
        project_id: str,
        new_project_id: str,
        old_project_id: Optional[str] = None,
        description: Optional[str] = None,
        update_database: bool = True,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute change project ID and/or description command.

        Args:
            self: Command instance.
            project_id: Current project identifier (root path resolved from database).
            new_project_id: New project identifier (UUID v4).
            old_project_id: Optional current project_id for validation.
            description: Optional new project description.
            update_database: Whether to update database (default: True).
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with change summary or ErrorResult on failure.
        """
        try:
            root_path = self._resolve_project_root(project_id)
            projectid_path = root_path / "projectid"

            # Step 2: Validate new_project_id format (must be UUID v4)
            try:
                new_uuid = uuid.UUID(new_project_id)
                if new_uuid.version != 4:
                    return self._handle_error(
                        ValidationError(
                            f"Invalid UUID version: expected v4, got v{new_uuid.version}",
                            field="new_project_id",
                            details={"new_project_id": new_project_id},
                        ),
                        "VALIDATION_ERROR",
                        "change_project_id",
                    )
            except ValueError as e:
                return self._handle_error(
                    ValidationError(
                        f"Invalid UUID format: {str(e)}",
                        field="new_project_id",
                        details={"new_project_id": new_project_id},
                    ),
                    "VALIDATION_ERROR",
                    "change_project_id",
                )

            # Step 3: Load current project information from file
            current_description = ""
            if not projectid_path.exists():
                # If file doesn't exist, we'll create it
                current_project_id = None
            else:
                try:
                    from ...core.project_resolution import load_project_info

                    project_info = load_project_info(root_path)
                    current_project_id = project_info.project_id
                    current_description = project_info.description
                except ProjectIdError as e:
                    # File exists but is invalid - we'll recreate it
                    logger.warning(
                        f"Invalid projectid file at {projectid_path}, will recreate: {e}"
                    )
                    current_project_id = None
                    current_description = ""
                except Exception as e:
                    # Try to load just the ID if description loading fails
                    try:
                        current_project_id = load_project_id(root_path)
                        current_description = ""
                    except Exception:
                        return self._handle_error(
                            ValidationError(
                                f"Failed to load current project_id: {str(e)}",
                                field="project_id",
                                details={"project_id": project_id, "error": str(e)},
                            ),
                            "PROJECTID_LOAD_ERROR",
                            "change_project_id",
                        )

            # Step 4: Validate old_project_id if provided
            if old_project_id is not None:
                if current_project_id is None:
                    return self._handle_error(
                        ValidationError(
                            "old_project_id provided but projectid file doesn't exist",
                            field="old_project_id",
                            details={
                                "old_project_id": old_project_id,
                                "projectid_path": str(projectid_path),
                            },
                        ),
                        "PROJECTID_FILE_NOT_FOUND",
                        "change_project_id",
                    )
                if old_project_id != current_project_id:
                    return self._handle_error(
                        ValidationError(
                            f"old_project_id mismatch: expected {current_project_id}, got {old_project_id}",
                            field="old_project_id",
                            details={
                                "old_project_id": old_project_id,
                                "current_project_id": current_project_id,
                            },
                        ),
                        "OLD_PROJECT_ID_MISMATCH",
                        "change_project_id",
                    )

            # Step 5: Determine new description
            new_description = (
                description if description is not None else current_description
            )

            # Step 5b: Before any filesystem or DB mutation, reject duplicate new id
            if str(new_project_id).lower() != str(project_id).lower():
                pre_db = self._open_database_from_config(auto_analyze=False)
                try:
                    existing_new = get_project(pre_db, new_project_id)
                    if (
                        existing_new is not None
                        and not _db_row_root_matches_project_root(
                            root_path, str(existing_new.root_path)
                        )
                    ):
                        return self._handle_error(
                            CodeAnalysisError(
                                "new_project_id is already registered for a different "
                                "project root in the database",
                                code="DUPLICATE_PROJECT_ID",
                                details={
                                    "new_project_id": new_project_id,
                                    "existing_root_path": str(existing_new.root_path),
                                    "this_root_path": str(root_path),
                                },
                            ),
                            "DUPLICATE_PROJECT_ID",
                            "change_project_id",
                        )
                finally:
                    pre_db.disconnect()

            # Step 6: Update projectid file in JSON format (backup for DB rollback)
            import json

            projectid_prior: Optional[bytes] = (
                projectid_path.read_bytes() if projectid_path.exists() else None
            )
            try:
                project_data = {
                    "id": new_project_id,
                    "description": new_description,
                }
                projectid_path.write_text(
                    json.dumps(project_data, indent=4, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                logger.info(
                    f"Updated projectid file: {projectid_path} "
                    f"(old_id: {current_project_id}, new_id: {new_project_id}, "
                    f"old_desc: {current_description}, new_desc: {new_description})"
                )
            except Exception as e:
                return self._handle_error(
                    ValidationError(
                        f"Failed to write projectid file: {str(e)}",
                        field="project_id",
                        details={
                            "projectid_path": str(projectid_path),
                            "error": str(e),
                        },
                    ),
                    "PROJECTID_WRITE_ERROR",
                    "change_project_id",
                )

            # Step 7: Update database if requested (on failure rollback projectid file)
            database_updated = False
            database_project_id = None
            if update_database:
                try:
                    config_path = self._resolve_config_path()
                    from ...core.storage_paths import (
                        load_raw_config,
                        resolve_storage_paths,
                    )

                    config_data = load_raw_config(config_path)
                    resolve_storage_paths(
                        config_data=config_data, config_path=config_path
                    )

                    database = self._open_database_from_config(auto_analyze=False)
                    try:
                        _now = sql_julian_timestamp_now_expr(database)
                        existing_project_id = (
                            BaseMCPCommand._get_project_id_by_root_path(
                                database, str(root_path)
                            )
                        )
                        if existing_project_id:
                            if (
                                current_project_id
                                and existing_project_id == current_project_id
                            ):
                                # Update project record (both ID and description if changed)
                                if description is not None:
                                    # Update both ID and description
                                    database.execute(
                                        f"""
                                        UPDATE projects 
                                        SET id = ?, comment = ?, updated_at = {_now}
                                        WHERE id = ?
                                        """,
                                        (
                                            new_project_id,
                                            new_description,
                                            current_project_id,
                                        ),
                                    )
                                else:
                                    # Update only ID
                                    database.execute(
                                        f"""
                                        UPDATE projects 
                                        SET id = ?, updated_at = {_now}
                                        WHERE id = ?
                                        """,
                                        (new_project_id, current_project_id),
                                    )
                                database_updated = True
                                database_project_id = new_project_id
                                logger.info(
                                    f"Updated project record in database: "
                                    f"{current_project_id} -> {new_project_id}"
                                    + (
                                        f", description: {new_description}"
                                        if description
                                        else ""
                                    )
                                )
                            elif existing_project_id != new_project_id:
                                # Update existing project with different ID
                                if description is not None:
                                    database.execute(
                                        f"""
                                        UPDATE projects 
                                        SET id = ?, comment = ?, updated_at = {_now}
                                        WHERE id = ?
                                        """,
                                        (
                                            new_project_id,
                                            new_description,
                                            existing_project_id,
                                        ),
                                    )
                                else:
                                    database.execute(
                                        f"""
                                        UPDATE projects 
                                        SET id = ?, updated_at = {_now}
                                        WHERE id = ?
                                        """,
                                        (new_project_id, existing_project_id),
                                    )
                                database_updated = True
                                database_project_id = new_project_id
                                logger.info(
                                    f"Updated project record in database: "
                                    f"{existing_project_id} -> {new_project_id}"
                                    + (
                                        f", description: {new_description}"
                                        if description
                                        else ""
                                    )
                                )
                            else:
                                # Same ID, only update description if provided
                                if description is not None:
                                    database.execute(
                                        f"""
                                        UPDATE projects 
                                        SET comment = ?, updated_at = {_now}
                                        WHERE id = ?
                                        """,
                                        (new_description, existing_project_id),
                                    )
                                    database_updated = True
                                    logger.info(
                                        f"Updated project description in database: {new_description}"
                                    )
                        else:
                            # Project doesn't exist in database, create it with new ID and description
                            root_stored = persist_projects_root_path_stored_value(
                                project_root_absolute=root_path,
                                watch_dir_id=None,
                                database=database,
                            )
                            database.execute(
                                f"""
                                INSERT INTO projects (id, root_path, name, comment, updated_at)
                                VALUES (?, ?, ?, ?, {_now})
                                """,
                                (
                                    new_project_id,
                                    root_stored,
                                    root_path.name,
                                    new_description,
                                ),
                            )
                            database_updated = True
                            database_project_id = new_project_id
                            logger.info(
                                f"Created new project record in database with ID: {new_project_id}, "
                                f"description: {new_description}"
                            )
                    finally:
                        database.disconnect()
                except Exception as e:
                    _rollback_projectid_file(projectid_path, projectid_prior)
                    return self._handle_error(
                        e,
                        "CHANGE_PROJECT_ID_DB_ERROR",
                        "change_project_id",
                    )

            # Build result message
            message_parts = []
            if current_project_id != new_project_id:
                message_parts.append(
                    f"Project ID: {current_project_id or 'none'} -> {new_project_id}"
                )
            if description is not None and current_description != new_description:
                message_parts.append(
                    f"Description: '{current_description}' -> '{new_description}'"
                )
            if not message_parts:
                message_parts.append("Project updated (no changes detected)")

            return SuccessResult(
                data={
                    "old_project_id": current_project_id,
                    "new_project_id": new_project_id,
                    "old_description": current_description,
                    "new_description": new_description,
                    "projectid_file_path": str(projectid_path),
                    "database_updated": database_updated,
                    "database_project_id": database_project_id,
                },
                message="; ".join(message_parts),
            )
        except Exception as e:
            return self._handle_error(e, "CHANGE_PROJECT_ID_ERROR", "change_project_id")
