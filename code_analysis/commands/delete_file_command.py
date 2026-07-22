"""
MCP command: delete_file

Legacy soft-delete (trash) aligned with universal ordering: ``resolve_handler`` runs
before opening the database or moving files. Venv, ``site-packages``, and
indexer-allowlisted installed paths are rejected before trash or DB updates.
Structured or partial deletes belong to ``universal_file_delete`` with an explicit
``delete_mode``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Type

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..core.database_driver_pkg.domain.projects import get_project
from ..core.file_handlers.registry import HANDLER_TEXT, RegistryError, resolve_handler
from ..core.git_integration import commit_after_write
from ..core.venv_path_policy import (
    build_allowlisted_site_packages_py_files,
    load_venv_site_packages_index_allowlist_from_config,
)
from .base_mcp_command import BaseMCPCommand
from .file_management.mark_file_deleted import MarkFileDeletedCommand
from .project_text_file_guard import reject_if_write_under_project_venv

logger = logging.getLogger(__name__)

_REGISTRY_NOTE_NON_TEXT = (
    "Partial or structured deletes for this file type require universal_file_delete "
    "with an explicit delete_mode (range, yaml_path, node, cst_selector, etc.). "
    "delete_file always performs a full-file soft delete to trash."
)


def _reject_legacy_delete_blocked_paths(
    absolute_path: Path, project_root: Path
) -> Optional[ErrorResult]:
    """Reject .venv/venv writes, site-packages paths, and allowlisted installed files."""
    blocked = reject_if_write_under_project_venv(absolute_path, project_root)
    if blocked is not None:
        return blocked

    try:
        resolved = absolute_path.resolve()
        root = project_root.resolve()
        rel = resolved.relative_to(root)
    except OSError as e:
        return ErrorResult(
            message=f"Cannot resolve paths for delete guard: {e}",
            code="INVALID_FILE_PATH",
            details={"resolved_path": str(absolute_path)},
        )
    except ValueError:
        return ErrorResult(
            message="Resolved file path is outside the project root.",
            code="INVALID_FILE_PATH",
            details={"resolved_path": str(absolute_path)},
        )

    if "site-packages" in rel.parts:
        return ErrorResult(
            message=(
                "Deleting paths under a site-packages directory is not allowed via delete_file."
            ),
            code="SITE_PACKAGES_DELETE_FORBIDDEN",
            details={
                "relative_path": rel.as_posix(),
                "resolved_path": str(resolved),
            },
        )

    allow_list = load_venv_site_packages_index_allowlist_from_config()
    allowlisted = build_allowlisted_site_packages_py_files(project_root, allow_list)
    if resolved in allowlisted:
        return ErrorResult(
            message=(
                "Deleting indexer-visible installed-package files is not allowed "
                "via delete_file."
            ),
            code="INSTALLED_PACKAGE_PATH_DELETE_FORBIDDEN",
            details={"resolved_path": str(resolved)},
        )

    return None


class DeleteFileMCPCommand(BaseMCPCommand):
    """Mark a file as deleted and move it to file trash (soft delete)."""

    name = "delete_file"
    version = "1.2.0"
    descr = (
        "Move file to trash (recycle bin): soft-delete — mark in DB and store under "
        "trash_dir; original path is not kept in the project tree. Registry validation "
        "runs before DB or filesystem effects; use universal_file_delete for structured deletes."
    )
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "description": (
                "Soft-delete to file trash: the file is moved under the configured "
                "trash_dir (recycle bin) and marked deleted in the DB — not shredded in "
                "place. Restore with unmark_deleted_file when possible. Unsupported "
                "extensions fail with UNSUPPORTED_FILE_EXTENSION before side effects."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects).",
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Single literal file path relative to project root "
                        "(e.g. ai_admin/commands/foo.py; no globs — use delete_files_by_mask for masks). "
                        "Content is relocated into trash_dir for this project."
                    ),
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["DeleteFileMCPCommand"]) -> Dict[str, Any]:
        """Rich metadata emphasizing trash / recycle-bin semantics."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "**Trash / recycle bin:** `delete_file` does **not** erase bytes in the "
                "project tree immediately. It runs a **soft delete**: the file is recorded "
                "as deleted in the database and its contents are moved under "
                "`code_analysis.storage.trash_dir` (per-project layout), analogous to a "
                "recycle bin.\n\n"
                "**Recovery:** use `unmark_deleted_file` to move the file back from the "
                "version/trash flow when supported. Permanent removal from disk is a "
                "separate trash-maintenance concern (see file trash docs / related "
                "commands).\n\n"
                "**Requirements:** `trash_dir` must be configured; otherwise the command "
                "returns DELETE_FILE_CONFIG_ERROR.\n\n"
                "**Permanent removal:** this command only **moves** to trash. To purge those "
                "file rows and bytes afterward, use ``cleanup_deleted_files`` with "
                "``hard_delete=True`` (and optionally ``older_than_days``).\n\n"
                "**Registry:** handler routing is validated before DB/trash (same suffix "
                "map as universal file commands). Use ``universal_file_delete`` with "
                "explicit ``delete_mode`` for partial or structured deletes."
            ),
            "parameters": {
                "project_id": {
                    "description": "Project UUID the file belongs to.",
                    "type": "string",
                    "required": True,
                },
                "file_path": {
                    "description": "Path relative to project root; file ends up under trash.",
                    "type": "string",
                    "required": True,
                },
            },
            "best_practices": [
                "Treat this as “move to trash”, not “secure wipe”.",
                "Use unmark_deleted_file to undo when the trashed copy still exists.",
                "Use universal_file_delete when you need delete_mode (range, CST, JSON ops).",
            ],
            "usage_examples": [],
            "error_cases": {},
            "return_value": {},
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute delete file command (mark as deleted, move to trash).

        Ordering: resolve_handler(delete) → DB open → path guards → trash move.

        Args:
            project_id: Project UUID (from create_project or list_projects).
            file_path: File path relative to project root.

        Returns:
            SuccessResult with success and message, or ErrorResult on failure.
        """
        try:
            try:
                handler_id = resolve_handler(file_path, "delete")
            except RegistryError as e:
                return ErrorResult(
                    message=str(e),
                    code=e.code,
                    details=e.details,
                )

            database = self._open_database_from_config(auto_analyze=False)
            try:
                project = get_project(database, project_id)
                if not project:
                    return ErrorResult(
                        message=f"Project {project_id} not found",
                        code="PROJECT_NOT_FOUND",
                        details={"project_id": project_id},
                    )

                project_root = Path(str(project.root_path)).resolve()

                marker = MarkFileDeletedCommand(
                    database=database,
                    project_id=project_id,
                    file_path=file_path,
                    trash_dir=None,
                )
                relative_norm = marker._normalize_relative_file_path(project_root)
                if relative_norm is None:
                    return ErrorResult(
                        message=(
                            "file_path must be a non-empty project-relative file path "
                            "without absolute paths or traversal."
                        ),
                        code="INVALID_FILE_PATH",
                        details={"file_path": file_path, "handler_id": handler_id},
                    )

                absolute_path = (project_root / relative_norm).resolve()
                env_block = _reject_legacy_delete_blocked_paths(
                    absolute_path, project_root
                )
                if env_block is not None:
                    details = dict(env_block.details or {})
                    details.setdefault("handler_id", handler_id)
                    return ErrorResult(
                        message=env_block.message,
                        code=env_block.code or "VALIDATION_ERROR",
                        details=details,
                    )

                trash_dir: Optional[str] = None
                try:
                    from ..core.storage_paths import (
                        load_raw_config,
                        resolve_storage_paths,
                    )

                    config_path = self._resolve_config_path()
                    config_data = load_raw_config(config_path)
                    storage = resolve_storage_paths(
                        config_data=config_data, config_path=config_path
                    )
                    trash_dir = str(storage.trash_dir)
                except Exception:
                    pass

                if not trash_dir:
                    return ErrorResult(
                        code="DELETE_FILE_CONFIG_ERROR",
                        message=(
                            "trash_dir not configured. Set code_analysis.storage.trash_dir "
                            "in config.json to use delete_file."
                        ),
                        details={"handler_id": handler_id},
                    )

                command = MarkFileDeletedCommand(
                    database=database,
                    project_id=project_id,
                    file_path=file_path,
                    trash_dir=trash_dir,
                )
                result = await command.execute()

                err_detail_base: Dict[str, Any] = {
                    "handler_id": handler_id,
                    "file_path": file_path,
                    "project_id": project_id,
                }

                if result.get("error") == "FILE_NOT_FOUND":
                    return ErrorResult(
                        code="FILE_NOT_FOUND",
                        message=result.get(
                            "message", f"File not found in project: {file_path}"
                        ),
                        details={**err_detail_base, "mark_error": result.get("error")},
                    )
                if result.get("error"):
                    return ErrorResult(
                        code="DELETE_FILE_ERROR",
                        message=result.get("message", str(result.get("error"))),
                        details={
                            **err_detail_base,
                            "error": result.get("error"),
                        },
                    )

                data = dict(result)
                data["handler_id"] = handler_id
                data["legacy_full_file_delete"] = True
                if handler_id != HANDLER_TEXT:
                    data["registry_note"] = _REGISTRY_NOTE_NON_TEXT

                try:
                    orig_git = (project_root / relative_norm).resolve()
                    git_ok, git_err = commit_after_write(
                        project_root,
                        [orig_git],
                        "delete_file",
                        config_data=self._get_raw_config(),
                    )
                    if not git_ok and git_err:
                        logger.warning("Git commit after delete_file: %s", git_err)
                except Exception as exc:
                    logger.warning("Git integration after delete_file: %s", exc)

                return SuccessResult(data=data)
            finally:
                database.disconnect()

        except Exception as e:
            return self._handle_error(e, "DELETE_FILE_ERROR", "delete_file")
