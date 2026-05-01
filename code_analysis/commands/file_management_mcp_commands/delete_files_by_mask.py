"""
MCP: soft-delete all files under a project matching a path mask (tree or glob).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ..base_mcp_command import BaseMCPCommand
from ..file_management import MarkFilesDeletedByMaskCommand


class DeleteFilesByMaskMCPCommand(BaseMCPCommand):
    """Move every indexed file matching ``path_mask`` to trash (same semantics as delete_file)."""

    name = "delete_files_by_mask"
    version = "1.0.0"
    descr = (
        "Bulk soft-delete: DB-tracked files matching a path mask (prefix, rm-like globs, "
        "or ``**/``) are moved to trash_dir. A leading ``/`` is the project root, not host ``/``."
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
                "Bulk soft-delete to file trash: every **indexed** file in ``files`` for "
                "``project_id`` whose project-relative path matches ``path_mask`` is moved "
                "under ``code_analysis.storage.trash_dir`` and marked deleted — same lifecycle "
                "as ``delete_file``.\n\n"
                "**Leading ``/``:** denotes the **project root** (like ``rm`` from the "
                "project directory), not the machine filesystem root; ``/build`` and "
                "``build`` are equivalent. Relative paths never use the server process "
                "``cwd`` — the logical working directory is always the project root.\n\n"
                "**Prefix mode** (no ``* ? [``): ``path_mask`` is a prefix for a **directory "
                "tree or a single file path** — ``build/`` matches all indexed files under "
                "``build/``; ``README.md`` matches that file (and paths prefixed with it).\n\n"
                "**Rm-style glob (wildcards, no ``/`` in mask):** ``*`` and ``?`` do not "
                "cross ``/``; the pattern applies only to the **first** path component "
                "(e.g. ``tes*`` matches ``testing/foo.py`` and ``tes.py``).\n\n"
                "**Path glob (contains ``/``):** split on ``/``; ``**`` matches any depth; "
                "other segments use per-segment globs (e.g. ``tests/**/*.py``). "
                "Only ``files`` rows are matched."
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": (
                        "Project UUID (from ``create_project`` or ``list_projects``). "
                        "Must exist in the database."
                    ),
                },
                "path_mask": {
                    "type": "string",
                    "description": (
                        "Mask relative to project root (see ``path_mask_match`` semantics — **not** "
                        "the same as ``list_project_files`` ``file_pattern``: rm-style globs without "
                        "``/`` match only the first path segment; ``**`` is segment-aware). Optional "
                        "leading ``/`` = project root. Examples: ``/build`` (prefix tree); ``/tes*``; "
                        "``tests/**/*.py``; ``**/*.tmp``. Backslashes → ``/``; trimmed."
                    ),
                },
            },
            "required": ["project_id", "path_mask"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: type["DeleteFilesByMaskMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        Includes parameter semantics, usage examples, errors, and return shape
        (aligned with other file_management MCP commands).
        """
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "**Trash / recycle bin:** Like ``delete_file``, this command does **not** "
                "shred data in place. Each matching file is soft-deleted: the row is updated "
                "and the file bytes are moved under ``code_analysis.storage.trash_dir`` "
                "(per-project layout under ``trash_dir/{project_id}/...``).\n\n"
                "**Selection:** The command loads active file rows for ``project_id``, "
                "computes each path relative to ``projects.root_path``, and keeps rows "
                "that match ``path_mask`` after normalizing a leading ``/`` to project root "
                "(prefix, rm-like one-segment globs, or ``/``-separated path globs with "
                "``**``; see ``get_schema``).\n\n"
                "**Order:** Longer paths are processed first to reduce edge cases when "
                "moving nested files.\n\n"
                "**Recovery:** Use ``unmark_deleted_file`` per path when a trashed copy "
                "still exists, same as for single ``delete_file``.\n\n"
                "**Permanent removal:** this command only **moves** matches to trash. To purge "
                "soft-deleted file rows and bytes later, use ``cleanup_deleted_files`` with "
                "``hard_delete=True``.\n\n"
                "**Requirements:** ``trash_dir`` must be set in config; otherwise "
                "``DELETE_FILES_BY_MASK_CONFIG_ERROR``. If some paths fail after others "
                "succeeded, the command returns ``DELETE_FILES_BY_MASK_PARTIAL`` with "
                "details listing failures.\n\n"
                "**Scope:** Only paths present in the ``files`` table (indexed files) are "
                "considered; there is no separate DB row for an empty directory.\n\n"
                "**Examples (see usage_examples):** "
                "**Directory** = delete “the whole tree”: use a **prefix** with no wildcards "
                "(``/path/to/dir`` or ``path/to/dir/``) — every indexed file under that path "
                "is trashed, same effect as removing a folder with ``rm -r`` on tracked files. "
                "**Files** = either a **fixed relative path** (prefix with no ``*?[]``, e.g. "
                "``/README.md`` only matches that file and cannot match deeper paths unless "
                "the path is a prefix) or a **glob** (``tests/**/*.py``, ``**/*.tmp``, "
                "``/tes*`` for top-level name patterns)."
            ),
            "parameters": {
                "project_id": {
                    "description": (
                        "Project UUID the files belong to. The project must exist and have "
                        "``root_path`` in the database for relative-path resolution."
                    ),
                    "type": "string",
                    "required": True,
                },
                "path_mask": {
                    "description": (
                        "Project-relative mask; leading ``/`` is stripped and means “from "
                        "project root”. **Prefix:** no wildcards — subtree ``mask/``. "
                        "**Rm-style:** wildcards but no ``/`` in mask — first path segment only "
                        "(``*`` does not cross ``/``). **Path glob:** contains ``/`` — "
                        "``**`` spans segments; other segments use fnmatch (e.g. "
                        "``tests/**/*.py``)."
                    ),
                    "type": "string",
                    "required": True,
                },
            },
            "best_practices": [
                "Prefer a narrow prefix or glob; bulk delete is irreversible for workflow "
                "until you restore from trash.",
                "Remember: ``/foo`` is project-root, not host ``/``.",
                "For “any depth” file patterns use ``**`` (e.g. ``**/*.pyc``); a bare ``*.py`` "
                "only matches top-level names, like ``rm *.py``.",
                "Run ``list_projects`` / inspect DB if unsure of ``project_id``.",
                "After a partial failure, inspect ``error.data.errors`` for per-path messages.",
                "Use ``delete_file`` for a single known path instead of a broad mask.",
            ],
            "usage_examples": [
                {
                    "description": (
                        "Directory (subtree): remove all indexed files under a folder path "
                        "(same idea as rm -r on that directory for tracked files)"
                    ),
                    "command": {
                        "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "path_mask": "/src/legacy_module",
                    },
                    "explanation": (
                        "Prefix mode, no wildcards: matches ``src/legacy_module`` and every "
                        "``src/legacy_module/...`` file in the DB (nested packages, assets, etc.). "
                        "Leading ``/`` is project root only."
                    ),
                },
                {
                    "description": (
                        "Directory (subtree): alternate spelling with trailing slash on project root"
                    ),
                    "command": {
                        "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "path_mask": "/docs/generated/",
                    },
                    "explanation": (
                        "Same as ``docs/generated``: all indexed files under ``docs/generated/``."
                    ),
                },
                {
                    "description": (
                        "Single file: exact project-relative path (prefix, no wildcards)"
                    ),
                    "command": {
                        "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "path_mask": "/README.md",
                    },
                    "explanation": (
                        "Only rows whose path equals ``README.md`` at project root (or starts "
                        "with ``README.md/``, uncommon) match — typical use: one known file."
                    ),
                },
                {
                    "description": (
                        "Files by pattern: all ``.py`` tests under ``tests/`` at any depth"
                    ),
                    "command": {
                        "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "path_mask": "tests/**/*.py",
                    },
                    "explanation": (
                        "Path glob: ``**`` crosses directories; only ``*.py`` under ``tests/`` "
                        "(not ``tests/README.md``)."
                    ),
                },
                {
                    "description": (
                        "Files by pattern: given extension anywhere in the project tree"
                    ),
                    "command": {
                        "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "path_mask": "**/*.tmp",
                    },
                    "explanation": (
                        "Every indexed path ending with ``.tmp`` at any depth."
                    ),
                },
                {
                    "description": (
                        "Directory (build output): trash whole ``build/`` tree from project root"
                    ),
                    "command": {
                        "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "path_mask": "/build",
                    },
                    "explanation": (
                        "Equivalent to ``build``: all files under ``build/`` (objects, wheels, "
                        "nested dirs) as long as they are indexed."
                    ),
                },
                {
                    "description": (
                        "Files / top-level dirs by rm-style pattern: names under project root "
                        "matching ``tes*``, plus every file inside those first-level paths"
                    ),
                    "command": {
                        "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "path_mask": "/tes*",
                    },
                    "explanation": (
                        "Wildcards with no ``/`` in the pattern: first path segment must match "
                        "``tes*``. Matches ``testing/deep/file.py`` and ``tes.py``; not "
                        "``src/tes.py`` (first segment ``src``)."
                    ),
                },
            ],
            "error_cases": {
                "DELETE_FILES_BY_MASK_CONFIG_ERROR": {
                    "description": "`code_analysis.storage.trash_dir` is missing or not resolved",
                    "example": "config.json has no trash_dir; command cannot move files",
                    "solution": (
                        "Set ``code_analysis.storage.trash_dir`` in config.json (same as for "
                        "``delete_file``), then retry."
                    ),
                },
                "VALIDATION_ERROR": {
                    "description": "`path_mask` is empty or whitespace-only after strip",
                    "example": "path_mask='   '",
                    "solution": "Pass a non-empty mask (see usage_examples).",
                },
                "DELETE_FILES_BY_MASK_PARTIAL": {
                    "description": (
                        "One or more matched files failed ``mark_file_deleted`` "
                        "(others may have succeeded)"
                    ),
                    "example": "Permission denied moving a file; disk full on later file",
                    "solution": (
                        "Read ``error.data`` (matched, moved_to_trash, failed, errors, paths). "
                        "Fix filesystem issues and re-run for remaining paths if needed."
                    ),
                },
                "DELETE_FILES_BY_MASK_ERROR": {
                    "description": "Unhandled exception (DB, project root, RPC, etc.)",
                    "example": "Project root path missing; connection failure",
                    "solution": "Check logs; verify project_id and server config.",
                },
            },
            "return_value": {
                "success": {
                    "description": "All matched files were moved to trash (or none matched)",
                    "data": {
                        "success": "True when failed count is 0 (including matched=0)",
                        "project_id": "Echo of request project_id",
                        "path_mask": "Echo of request path_mask",
                        "matched": "Number of indexed file rows matching the mask",
                        "moved_to_trash": "Number of successful mark_file_deleted calls",
                        "failed": "Number of failures",
                        "paths": "List of project-relative paths successfully trashed",
                        "errors": (
                            "List of {path, code, message} for failures (empty on full success)"
                        ),
                    },
                    "example": {
                        "success": True,
                        "project_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "path_mask": "build",
                        "matched": 3,
                        "moved_to_trash": 3,
                        "failed": 0,
                        "paths": ["build/a.o", "build/sub/b.o", "build/sub/c.o"],
                        "errors": [],
                    },
                },
                "error": {
                    "description": "Configuration, validation, partial failure, or fatal error",
                    "code": (
                        "DELETE_FILES_BY_MASK_CONFIG_ERROR | VALIDATION_ERROR | "
                        "DELETE_FILES_BY_MASK_PARTIAL | DELETE_FILES_BY_MASK_ERROR"
                    ),
                    "message": "Human-readable summary",
                    "data": (
                        "On PARTIAL, same shape as success payload (matched, paths, errors, ...)"
                    ),
                },
            },
        }

    async def execute(
        self,
        project_id: str,
        path_mask: str,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """
        Execute bulk delete-by-mask (soft delete + trash).

        Args:
            project_id: Project UUID.
            path_mask: Project-relative prefix or glob.

        Returns:
            SuccessResult with statistics, or ErrorResult on failure.
        """
        try:
            self._resolve_project_root(project_id)
            database = self._open_database_from_config(auto_analyze=False)

            trash_dir: Optional[str] = None
            try:
                from ...core.storage_paths import load_raw_config, resolve_storage_paths

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
                    message=(
                        "trash_dir not configured. Set code_analysis.storage.trash_dir "
                        "in config.json to use delete_files_by_mask."
                    ),
                    code="DELETE_FILES_BY_MASK_CONFIG_ERROR",
                )

            mask = (path_mask or "").strip()
            if not mask:
                return ErrorResult(
                    message="path_mask must be a non-empty string",
                    code="VALIDATION_ERROR",
                )

            try:
                command = MarkFilesDeletedByMaskCommand(
                    database=database,
                    project_id=project_id,
                    path_mask=mask,
                    trash_dir=trash_dir,
                )
                result = await command.execute()
                if not result.get("success"):
                    return ErrorResult(
                        message=(
                            f"Matched {result.get('matched', 0)}; "
                            f"moved {result.get('moved_to_trash', 0)}; "
                            f"failed {result.get('failed', 0)}"
                        ),
                        code="DELETE_FILES_BY_MASK_PARTIAL",
                        details=result,
                    )
                return SuccessResult(data=result)
            finally:
                database.disconnect()

        except Exception as e:
            return self._handle_error(e, "DELETE_FILES_BY_MASK_ERROR", "delete_files_by_mask")
