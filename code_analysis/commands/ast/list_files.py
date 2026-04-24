"""
MCP command wrapper: list_project_files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from mcp_proxy_adapter.commands.result import SuccessResult

from ...core.venv_path_policy import (
    build_allowlisted_site_packages_py_files,
    expand_ignore_exception_py_files,
    iter_project_python_files_excluding_venv,
    load_ignore_exceptions_from_config,
    load_venv_site_packages_index_allowlist_from_config,
)
from ..base_mcp_command import BaseMCPCommand


def _canonical_relative_path(project_root: Path, absolute_path: Path) -> str:
    """Stable posix relative path from project root for FS/DB joins."""
    return absolute_path.resolve().relative_to(project_root.resolve()).as_posix()


def _relative_key_for_db_file(project_root: Path, file_obj: Any) -> str:
    """Normalize DB file row path to the same key as :func:`_canonical_relative_path`."""
    rel = getattr(file_obj, "relative_path", None)
    if rel:
        return Path(str(rel)).as_posix()
    raw = getattr(file_obj, "path", None) or ""
    p = Path(str(raw))
    root = project_root.resolve()
    try:
        if p.is_absolute():
            return p.resolve().relative_to(root).as_posix()
    except ValueError:
        pass
    try:
        return (root / p).resolve().relative_to(root).as_posix()
    except ValueError:
        return Path(str(raw)).as_posix()


def _build_db_map_by_rel_key(project_root: Path, files: List[Any]) -> Dict[str, Any]:
    """Map canonical relative path -> file object (first wins)."""
    out: Dict[str, Any] = {}
    for f in files:
        key = _relative_key_for_db_file(project_root, f)
        if key not in out:
            out[key] = f
    return out


def _enumerate_project_py_paths(project_root: Path, show_venv: bool) -> List[Path]:
    """
    File system list aligned with indexing / watcher discovery.

    Includes project sources (excluding venv trees), ``.py`` paths from
    ``code_analysis.ignore_exceptions`` (glob, project-relative), and — when
    ``show_venv`` — allowlisted site-packages files from RECORD (same as
    :func:`code_analysis.core.venv_path_policy.collect_python_files_for_indexing`).
    """
    root = project_root.resolve()
    found: List[Path] = list(iter_project_python_files_excluding_venv(root))
    if show_venv:
        allowlist = load_venv_site_packages_index_allowlist_from_config()
        found.extend(build_allowlisted_site_packages_py_files(root, allowlist))
    exc_patterns = load_ignore_exceptions_from_config()
    if exc_patterns:
        found.extend(expand_ignore_exception_py_files(root, exc_patterns))
    uniq = {p.resolve() for p in found}
    return sorted(uniq, key=lambda p: _canonical_relative_path(root, p))


def _file_obj_to_dict(f: Any) -> Dict[str, Any]:
    if hasattr(f, "to_db_row"):
        d = cast(Dict[str, Any], f.to_db_row())
        d["deleted"] = bool(f.deleted)
        return d
    if isinstance(f, dict):
        return dict(f)
    return {}


def _fs_only_file_dict(
    project_id: str, project_root: Path, absolute_path: Path
) -> Dict[str, Any]:
    """Minimal row compatible with DB-backed entries when the file is not indexed yet."""
    abs_r = absolute_path.resolve()
    rel = _canonical_relative_path(project_root, abs_r)
    return {
        "project_id": project_id,
        "path": str(abs_r),
        "relative_path": rel,
        "deleted": False,
    }


class ListProjectFilesMCPCommand(BaseMCPCommand):
    """Filesystem-first list of project ``.py`` files with optional DB metadata."""

    name = "list_project_files"
    version = "1.0.0"
    descr = (
        "List project .py files from disk first; merge DB metadata when indexed. "
        "Skips project-local .venv/venv except paths matched by "
        "code_analysis.ignore_exceptions and (when show_venv) RECORD-allowlisted "
        "site-packages distributions."
    )
    category = "ast"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects).",
                },
                "file_pattern": {
                    "type": "string",
                    "description": (
                        "Optional fnmatch pattern on relative paths (e.g. '*.py', 'src/*', "
                        "'tests/test_*.py'). Not pathlib-style ``**`` recursion."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Optional limit on number of results",
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset for pagination",
                    "default": 0,
                },
                "show_venv": {
                    "type": "boolean",
                    "description": (
                        "When true, add config-allowlisted virtualenv site-packages "
                        "``.py`` files (RECORD-based) on top of project sources and "
                        "``code_analysis.ignore_exceptions`` matches. When false, "
                        "``.venv``/``venv`` are still skipped except for paths matched by "
                        "``ignore_exceptions`` (same as indexing)."
                    ),
                    "default": False,
                },
            },
            "required": ["project_id"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        file_pattern: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        show_venv: bool = False,
        **kwargs,
    ) -> SuccessResult:
        try:
            project_root = self._resolve_project_root(project_id).resolve()
            db = self._open_database_from_config(auto_analyze=False)

            db_files = db.get_project_files(project_id, include_deleted=False)
            db_by_rel = _build_db_map_by_rel_key(project_root, db_files)

            fs_paths = _enumerate_project_py_paths(project_root, show_venv=show_venv)

            def _rel_for_match(abs_p: Path) -> str:
                return _canonical_relative_path(project_root, abs_p)

            if file_pattern:
                fs_paths = [
                    p
                    for p in fs_paths
                    if fnmatch.fnmatch(_rel_for_match(p), file_pattern)
                ]

            total = len(fs_paths)
            if offset > 0 or limit is not None:
                fs_paths = fs_paths[offset : offset + (limit or len(fs_paths))]

            files_data: List[Dict[str, Any]] = []
            for abs_path in fs_paths:
                key = _canonical_relative_path(project_root, abs_path)
                row = db_by_rel.get(key)
                if row is not None:
                    files_data.append(_file_obj_to_dict(row))
                else:
                    files_data.append(
                        _fs_only_file_dict(project_id, project_root, abs_path)
                    )

            db.disconnect()

            return SuccessResult(
                data={
                    "success": True,
                    "files": files_data,
                    "count": len(files_data),
                    "total": total,
                    "offset": offset,
                }
            )
        except Exception as e:
            return self._handle_error(e, "LIST_FILES_ERROR", "list_project_files")

    @classmethod
    def metadata(cls: type["ListProjectFilesMCPCommand"]) -> Dict[str, Any]:
        """
        Get detailed command metadata for AI models.

        This method provides comprehensive information about the command,
        including detailed descriptions, usage examples, and edge cases.
        The metadata should be as detailed and clear as a man page.

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
                "The list_project_files command lists Python source files under the project "
                "root by walking the filesystem first, then attaching database metadata when "
                "a matching indexed row exists. Project-local ``.venv`` and ``venv`` "
                "trees are skipped except for ``.py`` paths matched by "
                "``code_analysis.ignore_exceptions`` (same as the file watcher and indexing). "
                "Set ``show_venv`` to true to additionally include RECORD-derived ``.py`` "
                "files for pip distributions in "
                "``venv_site_packages_index_allowlisted_distributions``.\n\n"
                "Operation flow:\n"
                "1. Resolves project root from ``project_id``\n"
                "2. Opens database connection\n"
                "3. Loads non-deleted file rows for the project (for metadata join)\n"
                "4. Enumerates ``.py`` files on disk (project sources + ignore_exceptions + "
                "optional allowlisted venv RECORD paths)\n"
                "5. If ``file_pattern`` is provided, filters by fnmatch on relative paths\n"
                "6. Sorts paths stably, then applies pagination (offset/limit)\n"
                "7. For each filesystem file, merges DB row when relative path matches; "
                "otherwise returns a minimal row (path / relative_path / project_id)\n\n"
                "File Metadata:\n"
                "Each file entry includes:\n"
                "- path: Absolute file path (when indexed, as stored in DB)\n"
                "- relative_path: Relative path from project root (posix)\n"
                "- id and statistics: present when the file is indexed in the database\n"
                "- Files on disk without a DB row include path metadata only\n\n"
                "Pattern Matching:\n"
                "- Uses fnmatch on relative paths (shell-style wildcards; not ``rglob``-style ``**``)\n"
                "- Examples: '*.py', 'src/*', 'tests/test_*.py', 'code_analysis/*/*.py'\n"
                "- Case-sensitive matching\n\n"
                "Use cases:\n"
                "- Catalog of Python sources as they exist on disk\n"
                "- Filter files by pattern (e.g., all Python files under src/)\n"
                "- See which files are indexed vs present only on disk\n"
                "- Optionally surface allowlisted third-party sources under venv\n\n"
                "Important notes:\n"
                "- Filesystem-first: DB-only rows not backed by an on-disk file are omitted\n"
                "- Supports pagination with limit and offset\n"
                "- Pattern matching uses fnmatch (shell wildcards)\n"
                "- Returns total count before pagination"
            ),
            "parameters": {
                "project_id": {
                    "description": (
                        "Project UUID (from create_project or list_projects). "
                        "Required; project root is resolved from the database."
                    ),
                    "type": "string",
                    "required": True,
                },
                "file_pattern": {
                    "description": (
                        "Optional pattern to filter files. Uses fnmatch on relative paths "
                        "(shell-style wildcards; not pathlib ``**`` recursion). Examples: "
                        "'*.py', 'src/*', 'tests/test_*.py', 'code_analysis/*/*.py'. "
                        "If not provided, returns all enumerated files."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "*.py",
                        "src/*",
                        "tests/test_*.py",
                        "code_analysis/*/*.py",
                    ],
                },
                "limit": {
                    "description": (
                        "Optional limit on number of results. Use for pagination or "
                        "to limit large result sets."
                    ),
                    "type": "integer",
                    "required": False,
                },
                "offset": {
                    "description": (
                        "Offset for pagination. Default is 0. Use with limit for paginated results."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 0,
                },
                "show_venv": {
                    "description": (
                        "When true, add ``.py`` files under site-packages for pip distributions "
                        "allowlisted in ``venv_site_packages_index_allowlisted_distributions`` "
                        "(dist-info RECORD). ``ignore_exceptions`` paths are always included "
                        "when false or true; this flag only adds the extra allowlisted venv "
                        "RECORD set."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
            },
            "usage_examples": [
                {
                    "description": "List all Python source files on disk",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    },
                    "explanation": (
                        "Returns project ``.py`` files with DB metadata when indexed."
                    ),
                },
                {
                    "description": "List only Python files",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_pattern": "*.py",
                    },
                    "explanation": (
                        "Returns only entries whose relative path matches *.py."
                    ),
                },
                {
                    "description": "Include allowlisted venv site-packages files",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "show_venv": True,
                    },
                    "explanation": (
                        "Adds RECORD-derived .py paths for allowlisted distributions only."
                    ),
                },
                {
                    "description": "List files with pagination",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_pattern": "*.py",
                        "limit": 100,
                        "offset": 0,
                    },
                    "explanation": (
                        "Returns first 100 matching paths. Use offset for next page."
                    ),
                },
            ],
            "error_cases": {
                "PROJECT_NOT_FOUND": {
                    "description": "Project not found in database",
                    "example": "Unknown project_id",
                    "solution": "Ensure project is registered. Use list_projects.",
                },
                "LIST_FILES_ERROR": {
                    "description": "General error during file listing",
                    "example": "Database error, invalid parameters, or corrupted data",
                    "solution": (
                        "Check database integrity, verify parameters, ensure project root exists."
                    ),
                },
            },
            "return_value": {
                "success": {
                    "description": "Command executed successfully",
                    "data": {
                        "success": "Always true on success",
                        "files": (
                            "List of file dictionaries. Indexed files include full DB fields; "
                            "unindexed on-disk files include path, relative_path, and project_id."
                        ),
                        "count": "Number of files in current page (after pagination)",
                        "total": "Total number of files matching criteria (before pagination)",
                        "offset": "Offset used for pagination",
                    },
                    "example": {
                        "success": True,
                        "files": [
                            {
                                "id": 1,
                                "path": "/home/proj/src/main.py",
                                "relative_path": "src/main.py",
                                "classes_count": 2,
                                "functions_count": 5,
                                "chunks_count": 10,
                                "has_ast": True,
                            },
                            {
                                "path": "/home/proj/src/new.py",
                                "relative_path": "src/new.py",
                                "project_id": "uuid",
                            },
                        ],
                        "count": 2,
                        "total": 42,
                        "offset": 0,
                    },
                },
                "error": {
                    "description": "Command failed",
                    "code": "Error code (e.g., PROJECT_NOT_FOUND, LIST_FILES_ERROR)",
                    "message": "Human-readable error message",
                },
            },
            "best_practices": [
                "Use file_pattern to filter files by type or location",
                "Use limit and offset for pagination with large projects",
                "Check total field to see total count before pagination",
                "Use show_venv only when config allowlists specific distributions",
                "Compare listed paths to DB-backed rows to find unindexed files",
            ],
        }
