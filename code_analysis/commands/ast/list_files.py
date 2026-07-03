"""
MCP command wrapper: list_project_files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

from typing import Any, Dict, List, Optional
from mcp_proxy_adapter.commands.result import (
    CommandResult,
    ErrorResult,
    SuccessResult,
)

from ..base_mcp_command import BaseMCPCommand
from ..file_management.relative_path_list_pattern import (
    canonical_relative_path,
    effective_listing_pattern,
    relative_path_matches_listing_pattern,
)
from ..project_fs_enumerate import enumerate_project_paths
from ...core.venv_path_policy import project_root_listing_error
from ...core.list_pagination import (
    build_list_page_payload,
    list_pagination_schema_properties,
    paginate_sequence,
    resolve_list_pagination,
)


def _build_file_id_lookup(rows: List[Dict[str, Any]]) -> Dict[str, str]:
    """Map path keys (relative_path and path as stored) -> files.id string."""
    m: Dict[str, str] = {}
    for row in rows:
        raw_id = row.get("id")
        if raw_id is None:
            continue
        fid = str(raw_id).strip()
        if not fid:
            continue
        rel = str(row.get("relative_path") or "").strip().replace("\\", "/")
        path_col = str(row.get("path") or "").strip().replace("\\", "/")
        if rel:
            m[rel] = fid
            if rel.startswith("./"):
                m[rel[2:]] = fid
        if path_col:
            m[path_col] = fid
    return m


def _resolve_file_id_for_row(
    *,
    rel: str,
    abs_path_str: str,
    id_by_key: Dict[str, str],
) -> Optional[str]:
    """Match a disk row to ``files.id`` using relative and absolute path keys."""
    fid = id_by_key.get(rel)
    if fid:
        return fid
    norm_abs = abs_path_str.replace("\\", "/")
    fid = id_by_key.get(norm_abs)
    if fid:
        return fid
    try:
        fid = id_by_key.get(Path(abs_path_str).resolve().as_posix())
    except (OSError, ValueError):
        fid = None
    return fid


def _fs_file_dict_with_optional_id(
    project_id: str,
    project_root: Path,
    absolute_path: Path,
    id_by_key: Dict[str, str],
) -> Dict[str, Any]:
    """One listed file: disk fields plus ``file_id`` when a ``files`` row matches."""
    abs_r = absolute_path.resolve()
    rel = canonical_relative_path(project_root, abs_r)
    abs_str = str(abs_r)
    return {
        "project_id": project_id,
        "path": abs_str,
        "relative_path": rel,
        "deleted": False,
        "file_id": _resolve_file_id_for_row(
            rel=rel, abs_path_str=abs_str, id_by_key=id_by_key
        ),
    }


class ListProjectFilesMCPCommand(BaseMCPCommand):
    """List project files from disk; enrich with ``files.id`` when the index has a match."""

    name = "list_project_files"

    version = "1.3.0"

    descr = (
        "List project files from disk (``ls`` semantics). Each row includes ``file_id`` "
        "(UUID from table ``files``) when the path matches an indexed non-deleted row for "
        "this ``project_id``, otherwise ``null``. Optional filters: ``file_pattern`` or "
        "``glob`` — fnmatch on the full project-relative POSIX path (``*`` crosses ``/``); "
        "literals without ``*?[]`` act as a directory prefix. Skips dot-prefixed dirs "
        "(``ls`` without ``-a``), cache dirs, and ``.venv``/``venv`` unless ``show_hidden``, "
        "``show_venv``, or ``include_venv_ignore_exceptions``. Set ``python_only`` for legacy "
        "``.py``-only enumeration. Returns paginated ``items`` (default ``page_size`` "
        "20); use ``block_position`` for the next page (same contract as ``search``)."
    )

    category = "ast"

    author = "Vasiliy Zdanovskiy"

    email = "vasilyvz@gmail.com"

    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the command input schema."""
        pagination = list_pagination_schema_properties()
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
                        "Optional fnmatch pattern against the **entire** path relative to project "
                        "root (not the basename alone): e.g. ``*.py`` matches ``pkg/mod.py`` too "
                        "because ``*`` spans ``/`` on POSIX. After trimming, ``\\\\`` → ``/``. "
                        "With no ``*?[]`` metacharacters, matches that exact relative path or any "
                        "path under it as a directory prefix. ``**`` is adjacent ``*``, not "
                        "pathlib ``rglob`` semantics."
                    ),
                },
                "glob": {
                    "type": "string",
                    "description": (
                        "Same as ``file_pattern`` (full relative path, fnmatch / directory-prefix "
                        "rules). Use whichever parameter name your client emits; if both are set, "
                        "non-empty ``file_pattern`` wins."
                    ),
                },
                **pagination,
                "show_venv": {
                    "type": "boolean",
                    "description": (
                        "When true, add config-allowlisted virtualenv site-packages "
                        "``.py`` files (RECORD-based) on top of project sources. "
                        "When false, project-local ``.venv``/``venv`` trees are omitted "
                        "from listing (same as watcher default)."
                    ),
                    "default": False,
                },
                "include_venv_ignore_exceptions": {
                    "type": "boolean",
                    "description": (
                        "Diagnostic: when true, include ``code_analysis.ignore_exceptions`` "
                        "matches that live under ``.venv``/``venv``. Default false so "
                        "broad venv globs do not flood ``list_project_files``."
                    ),
                    "default": False,
                },
                "show_hidden": {
                    "type": "boolean",
                    "description": (
                        "When true, ``ls -a``-style listing: descend into directory names starting "
                        "with ``.`` except project ``.venv``/``venv``, and into cache basenames "
                        "(``__pycache__``, ``.mypy_cache``, ``.pytest_cache``, ``.ruff_cache``, "
                        "``.cache``). Vendor/build dirs (e.g. ``node_modules``, ``dist``) stay "
                        "excluded. Bytecode/binary suffixes remain excluded. Default false."
                    ),
                    "default": False,
                },
                "python_only": {
                    "type": "boolean",
                    "description": (
                        "When true, enumerate only ``.py`` files (legacy behavior aligned with "
                        "indexing). When false (default), all ordinary project files are listed."
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
        glob: Optional[str] = None,
        page_size: Optional[int] = None,
        block_position: Optional[int] = None,
        limit: Optional[int] = None,
        offset: int = 0,
        show_venv: bool = False,
        python_only: bool = False,
        include_venv_ignore_exceptions: bool = False,
        show_hidden: bool = False,
        **kwargs: Any,
    ) -> CommandResult:
        """List project files from disk and attach ``file_id`` from the index when known.

        Args:
            project_id: Project UUID string.
            file_pattern: Optional shell-style glob or directory prefix to filter files.
            glob: Same as ``file_pattern`` when the client uses the name ``glob``.
            limit: Legacy alias for page_size.
            offset: Legacy row offset when block_position is omitted.
            page_size: Rows per page (default 20).
            block_position: 1-based page index (default 1).
            show_venv: If True, include allowlisted venv site-packages files.
            python_only: If True, return only ``.py`` files.
            include_venv_ignore_exceptions: If True, include venv paths from ignore_exceptions.
            show_hidden: If True, include paths under dot-directories and cache dirs (see schema).
            **kwargs: Accepted for API parity with base class.

        Returns:
            SuccessResult with files list, count, total, and offset;
            or ErrorResult on failure.
        """
        try:
            project_root = self._resolve_project_root(project_id).resolve()

            # A directory can be traversable (execute bit) yet not listable
            # (read bit); enumeration then silently returns empty. Surface a
            # typed error instead of a misleading empty listing.
            listing_error = project_root_listing_error(project_root)
            if listing_error is not None:
                return ErrorResult(
                    message=(
                        f"Project root exists but cannot be listed: {project_root}. "
                        "The server process lacks read permission on this "
                        "directory, so file enumeration returns empty. Restore "
                        "the owner read bit on the project root."
                    ),
                    code="PROJECT_ROOT_NOT_READABLE",
                    details={
                        "project_id": project_id,
                        "root_path": str(project_root),
                        "error": str(listing_error),
                    },
                )

            fs_paths = enumerate_project_paths(
                project_root,
                show_venv=show_venv,
                python_only=python_only,
                include_venv_ignore_exceptions=include_venv_ignore_exceptions,
                show_hidden=show_hidden,
            )

            effective_pattern = effective_listing_pattern(file_pattern, glob)
            if effective_pattern:
                fs_paths = [
                    p
                    for p in fs_paths
                    if relative_path_matches_listing_pattern(
                        canonical_relative_path(project_root, p), effective_pattern
                    )
                ]

            total = len(fs_paths)
            page_size, offset, block_position = resolve_list_pagination(
                {
                    "page_size": page_size,
                    "block_position": block_position,
                    "limit": limit,
                    "offset": offset,
                }
            )
            page_paths = paginate_sequence(fs_paths, offset=offset, page_size=page_size)

            id_by_key: Dict[str, str] = {}
            try:
                db = self._open_database_from_config(auto_analyze=False)
                rows = db.get_project_file_rows(project_id, include_deleted=False)
                id_by_key = _build_file_id_lookup(list(rows or []))
            except Exception:
                id_by_key = {}

            files_data: List[Dict[str, Any]] = [
                _fs_file_dict_with_optional_id(
                    project_id, project_root, abs_path, id_by_key
                )
                for abs_path in page_paths
            ]

            return SuccessResult(
                data=build_list_page_payload(
                    items=files_data,
                    total=total,
                    page_size=page_size,
                    block_position=block_position,
                    offset=offset,
                    legacy_items_key="files",
                )
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
                "Filesystem ``ls`` for a registered project: walks the tree on disk, then loads "
                "non-deleted ``files`` rows for this ``project_id`` once and attaches ``file_id`` "
                "(primary key UUID) when ``relative_path`` or ``path`` matches the disk row. "
                "If the DB is unavailable or the path is not indexed, ``file_id`` is ``null``. "
                "Use ``fulltext_search``, ``semantic_search``, and AST commands for indexed or "
                "semantic search. "
                "Bytecode, native libraries, and similar binary suffixes are skipped. "
                "Dot-prefixed directories (``ls -a``) and tool cache directory basenames are not "
                "descended into unless ``show_hidden`` is true (project ``.venv``/``venv`` roots "
                "stay excluded from free walk; use ``show_venv`` or "
                "``include_venv_ignore_exceptions`` for venv). Vendor/build dirs such as "
                "``node_modules`` / ``dist`` remain skipped even with ``show_hidden``. Set "
                "``python_only`` to true for legacy ``.py``-only enumeration (aligned with "
                "indexing).\n\n"
                "Operation flow:\n"
                "1. Resolves project root from ``project_id`` (projects registry only)\n"
                "2. Enumerates files on disk (project tree + ignore_exceptions matches + "
                "optional allowlisted venv RECORD ``.py`` paths; dot dirs and cache dirs only if "
                "``show_hidden``)\n"
                "3. If ``file_pattern`` or ``glob`` is set, keeps paths whose relative POSIX path "
                "matches (normalized patterns, optional directory-prefix semantics; see below)\n"
                "4. Loads ``files`` rows for ``project_id`` (non-deleted) and builds a path→id map\n"
                "5. Sorts by ``relative_path``, applies ``offset`` / ``limit``\n"
                "6. For each path, emits: ``project_id``, ``path``, ``relative_path``, "
                "``deleted``: false, ``file_id``: UUID or null\n\n"
                "Pattern / name templates (``file_pattern`` or ``glob``):\n"
                "- Matching is against the **full** ``relative_path`` from project root (POSIX "
                "string), not only the leaf filename; ``*.py`` therefore matches ``a/b/c.py``.\n"
                "- Patterns are trimmed; backslashes are normalized to ``/`` before matching\n"
                "- If the pattern has no ``*``, ``?``, or ``[`` metacharacters, it matches that "
                "exact relative path or any path under it (directory prefix), e.g. "
                "``docs/plans/foo`` matches ``docs/plans/foo/README.md``\n"
                "- Otherwise case-sensitive :func:`fnmatch.fnmatch` on that full relative path\n"
                "- ``*`` matches slashes, so ``docs/plans/foo/*`` also lists that subtree\n"
                "- ``code_analysis/commands/*`` includes nested modules\n"
                "- ``**`` is not pathlib ``rglob`` syntax; it behaves as repeated ``*`` "
                "wildcards (e.g. ``**/*.md`` usually matches Markdown at any depth)\n\n"
                "Important notes:\n"
                "- Only on-disk files appear; there is no DB-only ghost listing\n"
                "- ``file_id`` is null when the file is not in the index or DB read failed\n"
                "- ``total`` is the count after ``file_pattern`` / ``glob`` but before pagination; "
                "``count`` is the number of entries returned in ``files``\n"
                "- Pagination: ``offset`` and optional ``limit`` slice the sorted list"
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
                        "Optional fnmatch pattern or directory prefix on the **full** path "
                        "relative to project root (POSIX: ``*`` matches ``/``, so ``*.py`` hits "
                        "``src/pkg/mod.py``). Backslashes are normalized to ``/``. "
                        "Examples: ``*.py``, ``docs/plans/myplan`` (prefix, no wildcards), "
                        "``docs/plans/myplan/*``, ``code_analysis/commands/*``, ``**/*.md``. "
                        "If omitted and ``glob`` is omitted, no pattern filter is applied."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": [
                        "*.py",
                        "docs/plans/myplan",
                        "docs/plans/myplan/*",
                        "code_analysis/commands/*",
                        "**/*.md",
                    ],
                },
                "glob": {
                    "description": (
                        "Same semantics as ``file_pattern`` (full relative path; fnmatch or "
                        "directory-prefix when no ``*?[]``). Prefer one parameter; if both are "
                        "set, non-empty ``file_pattern`` takes precedence."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": ["*.md", "tests/**", "src/models"],
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
                        "(dist-info RECORD). Does not by itself surface arbitrary paths under "
                        "``.venv``/``venv``; use ``include_venv_ignore_exceptions`` for "
                        "``ignore_exceptions`` matches there."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "python_only": {
                    "description": (
                        "When true, enumerate only ``.py`` files (legacy indexing-aligned "
                        "listing). When false (default), list ordinary project files of any "
                        "included extension."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "include_venv_ignore_exceptions": {
                    "description": (
                        "When true, include ``code_analysis.ignore_exceptions`` matches that "
                        "live under ``.venv``/``venv``. Default false so broad venv globs do "
                        "not flood listings."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
                "show_hidden": {
                    "description": (
                        "When true, ``ls -a``-style: descend into dot-prefixed dirs (except "
                        "``.venv``/``venv``) and cache basenames (``__pycache__``, ``.mypy_cache``, "
                        "…); ``node_modules``/``dist``/… stay pruned; bytecode/binary suffixes "
                        "excluded."
                    ),
                    "type": "boolean",
                    "required": False,
                    "default": False,
                },
            },
            "usage_examples": [
                {
                    "description": "List all ordinary project files on disk",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                    },
                    "explanation": (
                        "Returns project files from disk with ``file_id`` when the path is indexed."
                    ),
                },
                {
                    "description": "List only Python files (same as legacy default)",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "python_only": True,
                    },
                    "explanation": (
                        "Restricts the walk to ``.py`` sources plus venv RECORD/ignore rules "
                        "for Python only."
                    ),
                },
                {
                    "description": "Filter to Python by pattern",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_pattern": "*.py",
                    },
                    "explanation": (
                        "Matches any ``.py`` under the project: ``*`` spans ``/`` on the full "
                        "relative path."
                    ),
                },
                {
                    "description": "Same filter using the glob parameter name",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "glob": "*.md",
                    },
                    "explanation": (
                        "``glob`` is an alias of ``file_pattern``; use it when the client schema "
                        "uses ``glob``."
                    ),
                },
                {
                    "description": "Directory prefix without wildcards",
                    "command": {
                        "project_id": "550e8400-e29b-41d4-a716-446655440000",
                        "file_pattern": "docs/plans/my_feature",
                    },
                    "explanation": (
                        "Literal path with no ``*?[]`` matches that folder or file and every "
                        "path under it (prefix semantics)."
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
                            "List of dicts: ``project_id``, ``path`` (absolute), ``relative_path`` "
                            "(posix under project root), ``deleted``: false, ``file_id``: "
                            "``files`` table UUID string or null if not indexed / no DB match."
                        ),
                        "count": "Number of files in current page (after pagination)",
                        "total": "Total number of files matching criteria (before pagination)",
                        "offset": "Offset used for pagination",
                    },
                    "example": {
                        "success": True,
                        "files": [
                            {
                                "project_id": "223e4567-e89b-12d3-a456-426614174000",
                                "path": "/home/proj/src/main.py",
                                "relative_path": "src/main.py",
                                "deleted": False,
                                "file_id": "aaaaaaaa-bbbb-4ccc-dddd-eeeeeeeeeeee",
                            },
                            {
                                "path": "/home/proj/src/new.py",
                                "relative_path": "src/new.py",
                                "project_id": "223e4567-e89b-12d3-a456-426614174000",
                                "deleted": False,
                                "file_id": None,
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
                "Remember patterns apply to the full relative path from project root, not only "
                "the leaf file name; narrow with a path prefix (e.g. tests/) when needed",
                "Use file_pattern or glob to narrow by directory prefix, extension, or fnmatch",
                "Use python_only when you intentionally want the legacy .py-only catalog",
                "Use limit and offset for pagination with large projects",
                "Check total vs count to page through filtered results",
                "Use show_venv only when config allowlists specific distributions",
                "Use show_hidden sparingly (dotdirs + caches; noisy trees like node_modules stay out)",
                "Use ``file_id`` for transfer-by-id commands; run update_indexes if paths lack ids",
            ],
        }
