"""
MCP command wrapper: list_project_files.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path

from typing import Any, Dict, List, Optional, cast
from mcp_proxy_adapter.commands.result import CommandResult, SuccessResult


from ...core.project_ignore_policy import (
    filter_paths_for_default_project_listing,
    path_is_under_project_local_venv,
)

from ...core.venv_path_policy import (
    build_allowlisted_site_packages_py_files,
    expand_ignore_exception_all_files,
    expand_ignore_exception_py_files,
    iter_project_files_excluding_venv,
    iter_project_python_files_excluding_venv,
    load_ignore_exceptions_from_config,
    load_venv_site_packages_index_allowlist_from_config,
)

from ..base_mcp_command import BaseMCPCommand
from ..file_management.relative_path_list_pattern import (
    canonical_relative_path,
    effective_listing_pattern,
    relative_path_matches_listing_pattern,
)


def _relative_key_for_db_file(project_root: Path, file_obj: Any) -> str:
    """Normalize DB file row path to the same key as :func:`canonical_relative_path`.

    Args:
        project_root: Project root directory used to resolve relative paths.
        file_obj: File record object with ``relative_path`` or ``path`` attribute.

    Returns:
        Canonical posix relative path string for joining with FS-derived keys.
    """
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
    """Map canonical relative path to file object (first wins).

    Args:
        project_root: Project root directory for path normalization.
        files: List of DB file record objects.

    Returns:
        Dict mapping canonical posix relative path to the first matching file object.
    """
    out: Dict[str, Any] = {}
    for f in files:
        key = _relative_key_for_db_file(project_root, f)
        if key not in out:
            out[key] = f
    return out


def _enumerate_project_paths(
    project_root: Path,
    show_venv: bool,
    *,
    python_only: bool,
    include_venv_ignore_exceptions: bool = False,
    show_hidden: bool = False,
) -> List[Path]:
    """Filesystem paths for ``list_project_files``.

    When ``python_only`` is false (default), walks all non-skipped ordinary files under
    the project, merges ``ignore_exceptions`` for any matched file type, and optionally
    appends RECORD-derived ``.py`` from allowlisted venv distributions when ``show_venv``.

    When ``python_only`` is true, uses the legacy Python-only walk plus ``.py``-only
    ignore_exceptions (parity with indexing).

    Args:
        project_root: Project root directory to enumerate.
        show_venv: If True, include allowlisted venv site-packages ``.py`` files.
        python_only: If True, enumerate only ``.py`` files (legacy mode).
        include_venv_ignore_exceptions: If True, include venv paths from ignore_exceptions.
        show_hidden: If True, list like ls -a: descend into dot-prefixed directories except
            project .venv/venv roots, and into cache basenames (__pycache__, .mypy_cache, …).

    Returns:
        Sorted list of absolute paths found under the project root.
    """
    root = project_root.resolve()
    found: List[Path]
    if python_only:
        found = list(
            iter_project_python_files_excluding_venv(root, show_hidden=show_hidden)
        )
        exc_expand = expand_ignore_exception_py_files
    else:
        found = list(iter_project_files_excluding_venv(root, show_hidden=show_hidden))
        exc_expand = expand_ignore_exception_all_files
    if show_venv:
        allowlist = load_venv_site_packages_index_allowlist_from_config()
        found.extend(build_allowlisted_site_packages_py_files(root, allowlist))
    exc_patterns = load_ignore_exceptions_from_config()
    if exc_patterns:
        extra = list(exc_expand(root, exc_patterns))
        if not include_venv_ignore_exceptions:
            extra = [
                p
                for p in extra
                if not path_is_under_project_local_venv(p.resolve(), root)
            ]
        found.extend(extra)
    uniq = {p.resolve() for p in found}
    ordered = sorted(uniq, key=lambda p: canonical_relative_path(root, p))
    return filter_paths_for_default_project_listing(
        ordered,
        root,
        include_venv=show_venv,
        include_venv_ignore_exceptions=include_venv_ignore_exceptions,
        show_hidden=show_hidden,
    )


def _file_obj_to_dict(f: Any) -> Dict[str, Any]:
    """Convert a DB file record object to a plain dict.

    Args:
        f: File record object with optional ``to_db_row`` method.

    Returns:
        Plain dict representation of the file record.
    """
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
    """Minimal row compatible with DB-backed entries when the file is not indexed yet.

    Args:
        project_id: Project UUID string.
        project_root: Project root directory for relative path computation.
        absolute_path: Absolute filesystem path to the file.

    Returns:
        Dict with project_id, path, relative_path, and deleted fields.
    """
    abs_r = absolute_path.resolve()
    rel = canonical_relative_path(project_root, abs_r)
    return {
        "project_id": project_id,
        "path": str(abs_r),
        "relative_path": rel,
        "deleted": False,
    }


class ListProjectFilesMCPCommand(BaseMCPCommand):
    """Filesystem-first list of project files with optional DB metadata."""

    name = "list_project_files"

    version = "1.0.0"

    descr = (
        "List project files from disk first (text, configs, Python, etc.); merge DB metadata "
        "when indexed. Optional path/name filters: ``file_pattern`` or ``glob`` — fnmatch on "
        "the full project-relative POSIX path (``*`` crosses ``/``); literals without "
        "``*?[]`` act as a directory prefix. Skips dot-prefixed dirs (``ls`` without ``-a``), "
        "cache dirs (``__pycache__``, ``.mypy_cache``, …), and ``.venv``/``venv`` unless "
        "``show_hidden`` (hidden+caches), or ``show_venv`` / ``include_venv_ignore_exceptions`` "
        "for venv. ``ignore_exceptions`` under venv only when ``include_venv_ignore_exceptions``. "
        "Set ``python_only`` for legacy .py-only enumeration."
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
        limit: Optional[int] = None,
        offset: int = 0,
        show_venv: bool = False,
        python_only: bool = False,
        include_venv_ignore_exceptions: bool = False,
        show_hidden: bool = False,
        **kwargs: Any,
    ) -> CommandResult:
        """List project files from filesystem merged with DB metadata.

        Args:
            project_id: Project UUID string.
            file_pattern: Optional shell-style glob or directory prefix to filter files.
            glob: Same as ``file_pattern`` when the client uses the name ``glob``.
            limit: Maximum number of files to return.
            offset: Number of files to skip from the beginning.
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
            db = self._open_database_from_config(auto_analyze=False)

            db_files = db.get_project_files(project_id, include_deleted=False)
            db_by_rel = _build_db_map_by_rel_key(project_root, db_files)

            fs_paths = _enumerate_project_paths(
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
            if offset > 0 or limit is not None:
                fs_paths = fs_paths[offset : offset + (limit or len(fs_paths))]

            files_data: List[Dict[str, Any]] = []
            for abs_path in fs_paths:
                key = canonical_relative_path(project_root, abs_path)
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
                "The list_project_files command walks the project tree on disk (by default all "
                "ordinary text and config files, not only ``.py``), then attaches database "
                "metadata when a non-deleted indexed row matches the same normalized relative "
                "path. Bytecode, native libraries, and similar binary suffixes are skipped. "
                "Dot-prefixed directories (``ls -a``) and tool cache directory basenames are not "
                "descended into unless ``show_hidden`` is true (project ``.venv``/``venv`` roots "
                "stay excluded from free walk; use ``show_venv`` or "
                "``include_venv_ignore_exceptions`` for venv). Vendor/build dirs such as "
                "``node_modules`` / ``dist`` remain skipped even with ``show_hidden``. Set "
                "``python_only`` to true for legacy ``.py``-only enumeration (aligned with "
                "indexing).\n\n"
                "Operation flow:\n"
                "1. Resolves project root from ``project_id``\n"
                "2. Opens database connection\n"
                "3. Loads non-deleted file rows for the project (for metadata join)\n"
                "4. Enumerates files on disk (project tree + ignore_exceptions matches + "
                "optional allowlisted venv RECORD ``.py`` paths; dot dirs and cache dirs only if "
                "``show_hidden``)\n"
                "5. If ``file_pattern`` or ``glob`` is set, keeps paths whose relative POSIX path "
                "matches (normalized patterns, optional directory-prefix semantics; see below)\n"
                "6. Sorts by ``relative_path``, applies ``offset`` / ``limit``\n"
                "7. For each path, emits the DB row when present, else a minimal FS-only row "
                "(``project_id``, ``path``, ``relative_path``, ``deleted``: false)\n\n"
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
                "- Filesystem-first: DB-only rows with no on-disk file are omitted\n"
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
                        "Returns non-binary project files with DB metadata when indexed."
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
                            "List of file dicts. Indexed rows mirror :meth:`File.to_db_row` "
                            "keys present on the model (``project_id``, ``path``, ``deleted``, "
                            "optional ``id``, ``watch_dir_id``, ``relative_path``, ``lines``, "
                            "``has_docstring``, timestamps, …) with ``deleted`` as bool. "
                            "Filesystem-only entries add ``project_id``, ``path``, "
                            "``relative_path``, ``deleted``: false."
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
                                "project_id": "223e4567-e89b-12d3-a456-426614174000",
                                "watch_dir_id": "550e8400-e29b-41d4-a716-446655440001",
                                "path": "/home/proj/src/main.py",
                                "relative_path": "src/main.py",
                                "lines": 10,
                                "has_docstring": 1,
                                "deleted": False,
                            },
                            {
                                "path": "/home/proj/src/new.py",
                                "relative_path": "src/new.py",
                                "project_id": "223e4567-e89b-12d3-a456-426614174000",
                                "deleted": False,
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
                "Compare listed paths to DB-backed rows to find unindexed files",
            ],
        }
