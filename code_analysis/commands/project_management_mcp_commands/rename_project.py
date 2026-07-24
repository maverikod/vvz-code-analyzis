"""
MCP command: rename_project.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import os
import uuid
from typing import Final

from ._shared import (
    Any,
    BaseMCPCommand,
    Dict,
    ErrorResult,
    SuccessResult,
    ValidationError,
)

_INVALID_NAME_CHARS: Final[str] = "/\\"


def _validate_new_name(new_name: str) -> str:
    """Validate and normalize the requested target project directory name.

    Args:
        new_name: Raw ``new_name`` parameter as supplied by the caller.

    Returns:
        The stripped, validated name.

    Raises:
        ValidationError: If ``new_name`` is empty, contains a path separator,
            or is the special path segment ``.`` or ``..``.
    """
    stripped = (new_name or "").strip()
    if not stripped:
        raise ValidationError(
            "new_name must not be empty",
            field="new_name",
            details={"new_name": new_name},
        )
    if any(ch in stripped for ch in _INVALID_NAME_CHARS):
        raise ValidationError(
            "new_name must not contain path separators",
            field="new_name",
            details={"new_name": new_name},
        )
    if stripped in (".", ".."):
        raise ValidationError(
            "new_name must not be '.' or '..'",
            field="new_name",
            details={"new_name": new_name},
        )
    return stripped


class RenameProjectMCPCommand(BaseMCPCommand):
    """
    Rename a project's directory on disk and update its DB row atomically-ish.

    Flow: lock -> rename on disk -> update DB -> unlock. A filesystem rename is
    O(1) on the same filesystem, so this runs inline (no queue). If the
    directory rename or the DB update fails after the lock is acquired, the
    lock is deliberately left held (no compensation, no automatic disk
    rollback) so a partially-moved project cannot be operated on further by
    accident; use ``emergency_unlock_project`` after manual/administrative
    reconciliation.

    Attributes:
        name: MCP command name.
        version: Command version.
        descr: Short description.
        category: Command category.
        author: Command author.
        email: Author email.
        use_queue: Whether to run in the background queue (False - O(1) rename).
    """

    name = "rename_project"
    version = "1.0.0"
    descr = (
        "Rename a project's directory on disk and update its DB row. Uses the "
        "whole-project exclusive lock; on failure after acquiring the lock the "
        "project stays locked (no compensation) - use emergency_unlock_project."
    )
    category = "project_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls: type["RenameProjectMCPCommand"]) -> Dict[str, Any]:
        """
        Get JSON schema for command parameters.

        Args:
            cls: Command class.

        Returns:
            JSON schema dict.
        """
        return {
            "type": "object",
            "description": (
                "Rename a project's directory on disk (same watch root, new "
                "folder name) and update its projects.root_path/name row."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID to rename (from create_project or list_projects).",
                },
                "new_name": {
                    "type": "string",
                    "description": (
                        "Target directory/project name. Must not contain path "
                        "separators ('/' or '\\\\') and must not be '.' or '..'."
                    ),
                },
            },
            "required": ["project_id", "new_name"],
            "additionalProperties": False,
        }

    async def execute(
        self: "RenameProjectMCPCommand",
        project_id: str,
        new_name: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute rename_project: lock -> rename on disk -> update DB -> unlock.

        Args:
            self: Command instance.
            project_id: Project UUID to rename.
            new_name: Target directory/project name (validated in Step 0).
            **kwargs: Extra args (unused).

        Returns:
            SuccessResult with the new name/root_path, or ErrorResult on any
            of the documented failure codes.
        """
        from ...core.database_driver_pkg.domain.projects import (
            relocate_project_root_after_disk_move,
        )
        from ...core.project_exclusive_lock import (
            acquire_project_exclusive_lock,
            release_project_exclusive_lock,
        )
        from ...core.project_root_path import (
            is_legacy_projects_root_path_absolute_storage,
        )

        db = self._open_database_from_config()
        lock_acquired = False
        try:
            # Step 0: validate new_name, resolve current root (BEFORE acquiring
            # the lock - a legitimate PROJECT_LOCKED rejection here means
            # someone else is already mid-operation on this project).
            try:
                validated_name = _validate_new_name(new_name)
            except ValidationError as e:
                return self._handle_error(e, "VALIDATION_ERROR", "rename_project")

            try:
                old_root = self._resolve_project_root(project_id)
            except ValidationError as e:
                return self._handle_error(e, e.code or "VALIDATION_ERROR", "rename_project")

            rows = db.select("projects", where={"id": project_id})
            row = dict(rows[0]) if rows else {}
            if is_legacy_projects_root_path_absolute_storage(
                str(row.get("root_path") or "")
            ):
                return ErrorResult(
                    message=(
                        f"Project {project_id!r} uses legacy absolute-path storage "
                        "(not under a single watch catalog); rename_project only "
                        "supports the standard watch-relative layout."
                    ),
                    code="RENAME_LEGACY_PROJECT_NOT_SUPPORTED",
                    details={"project_id": project_id, "root_path": row.get("root_path")},
                )

            # Step 1: acquire the whole-project exclusive lock.
            owner = f"rename_project:{uuid.uuid4().hex}"
            if not acquire_project_exclusive_lock(
                db,
                project_id,
                owner=owner,
                reason=f"rename_project to {validated_name!r}",
            ):
                return ErrorResult(
                    message=(
                        f"Project {project_id!r} is already exclusively locked by "
                        "another operation; rename_project refused."
                    ),
                    code="PROJECT_LOCKED",
                    details={"project_id": project_id},
                )
            lock_acquired = True

            # Step 2: rename on disk.
            new_root = old_root.parent / validated_name
            if new_root.exists():
                return ErrorResult(
                    message=(
                        f"Rename target already exists on disk: {new_root}. "
                        "The project remains locked; use emergency_unlock_project "
                        "after resolving the naming conflict."
                    ),
                    code="RENAME_TARGET_EXISTS",
                    details={"project_id": project_id, "new_root": str(new_root)},
                )
            try:
                os.rename(str(old_root), str(new_root))
            except OSError as exc:
                return ErrorResult(
                    message=(
                        f"Failed to rename project directory {old_root} -> "
                        f"{new_root}: {exc}. The project remains locked; use "
                        "emergency_unlock_project after manual reconciliation."
                    ),
                    code="RENAME_OS_ERROR",
                    details={
                        "project_id": project_id,
                        "old_root": str(old_root),
                        "new_root": str(new_root),
                        "error": str(exc),
                    },
                )

            # Step 3: single DB update.
            ok = relocate_project_root_after_disk_move(
                db, project_id, str(old_root), str(new_root)
            )
            if not ok:
                return ErrorResult(
                    message=(
                        f"Directory was renamed on disk ({old_root} -> {new_root}) "
                        "but the database update failed. The project remains "
                        "locked pending manual/administrative reconciliation; use "
                        "emergency_unlock_project once resolved."
                    ),
                    code="RENAME_DB_UPDATE_FAILED",
                    details={
                        "project_id": project_id,
                        "old_root": str(old_root),
                        "new_root": str(new_root),
                    },
                )

            # Step 4: release the lock - only reached on full success.
            release_project_exclusive_lock(db, project_id)
            lock_acquired = False
            return SuccessResult(
                data={
                    "project_id": project_id,
                    "old_name": old_root.name,
                    "new_name": new_root.name,
                    "root_path": str(new_root),
                },
                message=f"Renamed project {project_id} to {validated_name!r}",
            )
        except Exception as e:
            # Unexpected failure after the lock was taken: leave it held, same
            # no-compensation rule as the explicit Step 2/3 failure branches.
            return self._handle_error(e, "RENAME_PROJECT_ERROR", "rename_project")
        finally:
            db.disconnect()

    @classmethod
    def metadata(cls: type["RenameProjectMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        Args:
            cls: Command class.

        Returns:
            Dictionary with command metadata.
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "rename_project renames a project's directory on disk and updates its "
                "projects.root_path/name row, guarded by the whole-project exclusive "
                "lock (core/project_exclusive_lock.py, bugs 88f06abc, 5da73265).\n\n"
                "Flow:\n"
                "0. Validate new_name (no path separators, not '.'/'..'); resolve the "
                "current project root (legitimately rejected with PROJECT_LOCKED if "
                "another operation already holds the lock); reject legacy "
                "absolute-path-storage projects with RENAME_LEGACY_PROJECT_NOT_SUPPORTED "
                "before touching the lock at all.\n"
                "1. Acquire the exclusive lock (PROJECT_LOCKED if already held - "
                "there is no TTL to steal).\n"
                "2. Rename the directory on disk (os.rename). RENAME_TARGET_EXISTS if "
                "the destination already exists; RENAME_OS_ERROR on any OS-level "
                "rename failure.\n"
                "3. Update the projects row in a single UPDATE "
                "(relocate_project_root_after_disk_move). RENAME_DB_UPDATE_FAILED if "
                "this fails - the directory is already renamed on disk at this point.\n"
                "4. Release the lock - only on full success.\n\n"
                "IMPORTANT: if a rename fails after the lock is acquired (steps 2-3, "
                "or an unexpected exception), the lock is deliberately NOT released and "
                "there is NO automatic rollback of the disk rename. This is by design: "
                "a half-moved project must not be touched by other operations until a "
                "human reconciles disk and DB. Use emergency_unlock_project to inspect "
                "and clear the lock once resolved."
            ),
            "parameters": {
                "project_id": {
                    "description": "Project UUID to rename.",
                    "type": "string",
                    "required": True,
                },
                "new_name": {
                    "description": (
                        "Target directory/project name. Must not contain '/' or "
                        "'\\\\' and must not be '.' or '..'."
                    ),
                    "type": "string",
                    "required": True,
                    "examples": ["my_project_v2", "renamed-project"],
                },
            },
            "usage_examples": [
                {
                    "description": "Rename a project",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "new_name": "my_project_v2",
                    },
                    "explanation": (
                        "Locks the project, renames its directory to "
                        "'my_project_v2' under the same watch root, updates the "
                        "DB row, then releases the lock."
                    ),
                },
            ],
            "error_cases": {
                "RENAME_LEGACY_PROJECT_NOT_SUPPORTED": {
                    "description": "Project uses legacy absolute-path root storage",
                    "example": "Project predates the watch-relative root_path scheme",
                    "solution": "Not supported by this command; no lock is taken.",
                },
                "PROJECT_LOCKED": {
                    "description": "Project is already exclusively locked",
                    "example": "Another rename_project or admin operation is in flight",
                    "solution": "Wait, or use emergency_unlock_project if the lock is stuck.",
                },
                "RENAME_TARGET_EXISTS": {
                    "description": "The target directory name already exists on disk",
                    "example": "new_name collides with an existing sibling directory",
                    "solution": "Choose a different new_name. The project remains locked.",
                },
                "RENAME_OS_ERROR": {
                    "description": "os.rename failed at the OS level",
                    "example": "Permission denied, cross-device link, disk full",
                    "solution": "Fix the underlying OS condition; project remains locked.",
                },
                "RENAME_DB_UPDATE_FAILED": {
                    "description": "Directory renamed on disk but the DB update failed",
                    "example": "root_path collision detected by the DB layer",
                    "solution": (
                        "Directory and DB are now inconsistent; reconcile manually, "
                        "then use emergency_unlock_project."
                    ),
                },
                "RENAME_PROJECT_ERROR": {
                    "description": "Unexpected error during rename",
                    "example": "Any exception not covered by the specific codes above",
                    "solution": "Check server logs; the lock state depends on which step failed.",
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "project_id": "Project UUID (unchanged)",
                        "old_name": "Previous directory/project name",
                        "new_name": "New directory/project name",
                        "root_path": "New absolute root path on disk",
                    },
                    "example": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "old_name": "old_project",
                        "new_name": "my_project_v2",
                        "root_path": "/watch/root/my_project_v2",
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "One of the error_cases codes above",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Check the response for PROJECT_LOCKED before assuming failure means "
                "corruption - it may simply mean another operation is in flight",
                "If a rename fails after the lock is acquired, do not assume the "
                "project is safe to use again until you have inspected/reconciled it",
                "Use emergency_unlock_project (force=false) first to inspect a stuck "
                "lock before force-clearing it",
            ],
        }
