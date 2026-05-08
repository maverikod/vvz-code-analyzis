"""
MCP command: fs_grep

Line-oriented search over project files on disk (``grep``), no full-text index.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .file_management.relative_path_list_pattern import (
    canonical_relative_path,
    effective_listing_pattern,
    relative_path_matches_listing_pattern,
)
from .project_fs_enumerate import enumerate_project_paths

logger = logging.getLogger(__name__)


class FsGrepCommand(BaseMCPCommand):
    """Scan files on disk for a pattern (regex or literal)."""

    name = "fs_grep"
    version = "1.0.0"
    descr = (
        "Search file contents on disk (grep-style). Does not use the database full-text index; "
        "use ``fulltext_search`` for indexed search. Respects the same walk rules as "
        "``list_project_files``."
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
                "pattern": {
                    "type": "string",
                    "description": (
                        "Search pattern. When literal=true, matched as substring per line. "
                        "When literal=false, Python ``re`` regex (multiline off; line by line)."
                    ),
                },
                "literal": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true, treat pattern as plain substring (not regex).",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "default": True,
                    "description": "If false, use case-insensitive matching.",
                },
                "file_pattern": {
                    "type": "string",
                    "description": (
                        "Optional filter on project-relative path (same rules as list_project_files "
                        "``file_pattern``)."
                    ),
                },
                "glob": {
                    "type": "string",
                    "description": "Alias of file_pattern; file_pattern wins when both set.",
                },
                "max_matches": {
                    "type": "integer",
                    "description": "Stop after this many matching lines (default 500).",
                    "default": 500,
                },
                "show_venv": {"type": "boolean", "default": False},
                "python_only": {"type": "boolean", "default": False},
                "include_venv_ignore_exceptions": {"type": "boolean", "default": False},
                "show_hidden": {"type": "boolean", "default": False},
            },
            "required": ["project_id", "pattern"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        project_id: str,
        pattern: str,
        literal: bool = True,
        case_sensitive: bool = True,
        file_pattern: Optional[str] = None,
        glob: Optional[str] = None,
        max_matches: int = 500,
        show_venv: bool = False,
        python_only: bool = False,
        include_venv_ignore_exceptions: bool = False,
        show_hidden: bool = False,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        if not (pattern or "").strip():
            return ErrorResult(
                message="pattern must be non-empty",
                code="INVALID_PATTERN",
                details={},
            )
        if max_matches < 1:
            return ErrorResult(
                message="max_matches must be >= 1",
                code="INVALID_LIMIT",
                details={"max_matches": max_matches},
            )
        try:
            project_root = self._resolve_project_root(project_id).resolve()
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

            flags = 0 if case_sensitive else re.IGNORECASE
            needle = pattern
            regex: Optional[re.Pattern[str]] = None
            if not literal:
                try:
                    regex = re.compile(needle, flags)
                except re.error as e:
                    return ErrorResult(
                        message=f"Invalid regex: {e}",
                        code="INVALID_REGEX",
                        details={"pattern": needle},
                    )

            matches: List[Dict[str, Any]] = []
            files_scanned = 0
            for abs_path in fs_paths:
                if len(matches) >= max_matches:
                    break
                files_scanned += 1
                rel = canonical_relative_path(project_root, abs_path)
                try:
                    data = abs_path.read_text(encoding="utf-8", errors="replace")
                except OSError as e:
                    logger.debug("fs_grep skip read %s: %s", abs_path, e)
                    continue
                if "\0" in data:
                    continue
                for i, line in enumerate(data.splitlines(), start=1):
                    if len(matches) >= max_matches:
                        break
                    ok = False
                    if literal:
                        hay = line if case_sensitive else line.lower()
                        nd = needle if case_sensitive else needle.lower()
                        ok = nd in hay
                    else:
                        assert regex is not None
                        ok = regex.search(line) is not None
                    if ok:
                        matches.append(
                            {
                                "relative_path": rel,
                                "line": i,
                                "text": line,
                            }
                        )

            return SuccessResult(
                data={
                    "success": True,
                    "pattern": needle,
                    "literal": literal,
                    "case_sensitive": case_sensitive,
                    "matches": matches,
                    "match_count": len(matches),
                    "files_scanned": files_scanned,
                    "truncated": len(matches) >= max_matches,
                }
            )
        except Exception as e:
            return self._handle_error(e, "FS_GREP_ERROR", "fs_grep")

    @classmethod
    def metadata(cls: type["FsGrepCommand"]) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "detailed_description": (
                "Walks the project tree like ``list_project_files``, reads each file as UTF-8 "
                "(with replacement), skips binary-looking content (NUL byte), and collects "
                "matching lines. For corpus-wide indexed search use ``fulltext_search``."
            ),
            "parameters": {},
            "return_value": {
                "success": {
                    "description": "Matches and scan stats.",
                    "data": {},
                    "example": {},
                },
                "error": {
                    "description": "Validation or IO failure.",
                    "code": "FS_GREP_ERROR",
                    "message": "Human-readable message",
                },
            },
            "usage_examples": [],
            "error_cases": {},
            "best_practices": [
                "Narrow with file_pattern when possible — scanning huge trees is expensive.",
                "Prefer fulltext_search when the project is indexed and you need docstring/body FTS.",
            ],
        }
