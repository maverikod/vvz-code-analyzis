"""
MCP command: fs_grep

Line-oriented search over project files on disk (``grep``), no full-text index.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import re
from time import perf_counter
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
    version = "1.1.0"
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
                "max_file_bytes": {
                    "type": "integer",
                    "description": (
                        "Skip individual files larger than this many bytes before opening them. "
                        "Use 0 to disable the guard. Default: 5242880 (5 MiB)."
                    ),
                    "default": 5242880,
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
        max_file_bytes: int = 5 * 1024 * 1024,
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
        if max_file_bytes < 0:
            return ErrorResult(
                message="max_file_bytes must be >= 0",
                code="INVALID_LIMIT",
                details={"max_file_bytes": max_file_bytes},
            )
        try:
            started_at = perf_counter()
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

            logger.info(
                "fs_grep start project_id=%s root=%s pattern=%r literal=%s "
                "case_sensitive=%s file_pattern=%r max_matches=%s max_file_bytes=%s "
                "candidate_files=%s",
                project_id,
                project_root,
                pattern,
                literal,
                case_sensitive,
                effective_pattern,
                max_matches,
                max_file_bytes,
                len(fs_paths),
            )
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
            files_skipped_large = 0
            files_skipped_io = 0
            skipped_large_samples: List[Dict[str, Any]] = []
            for abs_path in fs_paths:
                if len(matches) >= max_matches:
                    break
                rel = canonical_relative_path(project_root, abs_path)
                try:
                    size = abs_path.stat().st_size
                except OSError as e:
                    files_skipped_io += 1
                    logger.debug("fs_grep skip stat %s: %s", abs_path, e)
                    continue
                if max_file_bytes and size > max_file_bytes:
                    files_skipped_large += 1
                    if len(skipped_large_samples) < 20:
                        skipped_large_samples.append(
                            {"relative_path": rel, "size_bytes": size}
                        )
                    continue
                files_scanned += 1
                try:
                    with abs_path.open("r", encoding="utf-8", errors="replace") as fh:
                        for i, line in enumerate(fh, start=1):
                            if len(matches) >= max_matches:
                                break
                            if "\0" in line:
                                break
                            line = line.rstrip("\r\n")
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
                except OSError as e:
                    files_skipped_io += 1
                    logger.debug("fs_grep skip read %s: %s", abs_path, e)
                    continue

            elapsed = perf_counter() - started_at
            logger.info(
                "fs_grep done project_id=%s elapsed=%.3fs matches=%s "
                "files_scanned=%s files_skipped_large=%s files_skipped_io=%s truncated=%s",
                project_id,
                elapsed,
                len(matches),
                files_scanned,
                files_skipped_large,
                files_skipped_io,
                len(matches) >= max_matches,
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
                    "files_skipped_large": files_skipped_large,
                    "files_skipped_io": files_skipped_io,
                    "skipped_large_samples": skipped_large_samples,
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
                "Walks the project tree like ``list_project_files``, streams each file as UTF-8 "
                "(with replacement), skips files larger than ``max_file_bytes`` before opening "
                "them, skips binary-looking content (NUL byte), and collects matching lines. "
                "For corpus-wide indexed search use ``fulltext_search``."
            ),
            "parameters": {
                "project_id": {
                    "description": "Project UUID from create_project or list_projects.",
                    "type": "string",
                    "required": True,
                },
                "pattern": {
                    "description": "Literal substring or Python regular expression to search.",
                    "type": "string",
                    "required": True,
                },
                "literal": {
                    "description": "When true, match pattern as a plain substring.",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "case_sensitive": {
                    "description": "When false, perform case-insensitive matching.",
                    "type": "boolean",
                    "required": False,
                    "default": True,
                },
                "file_pattern": {
                    "description": "Optional project-relative listing pattern.",
                    "type": "string",
                    "required": False,
                },
                "glob": {
                    "description": "Alias for file_pattern; file_pattern wins when both are set.",
                    "type": "string",
                    "required": False,
                },
                "max_matches": {
                    "description": "Stop after this many matching lines.",
                    "type": "integer",
                    "required": False,
                    "default": 500,
                },
                "max_file_bytes": {
                    "description": (
                        "Skip files larger than this limit before opening them. Use 0 to disable."
                    ),
                    "type": "integer",
                    "required": False,
                    "default": 5242880,
                },
            },
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
            "error_cases": {
                "INVALID_PATTERN": {
                    "description": "The pattern is empty or whitespace only.",
                    "message": "pattern must be non-empty",
                    "solution": "Pass a non-empty search string.",
                },
                "INVALID_LIMIT": {
                    "description": "max_matches or max_file_bytes is outside the supported range.",
                    "message": "max_matches must be >= 1 or max_file_bytes must be >= 0",
                    "solution": "Use max_matches >= 1 and max_file_bytes >= 0.",
                },
                "INVALID_REGEX": {
                    "description": "literal=false and pattern is not valid Python regex syntax.",
                    "message": "Invalid regex: {details}",
                    "solution": "Fix the regular expression or set literal=true.",
                },
            },
            "best_practices": [
                "Narrow with file_pattern when possible — scanning huge trees is expensive.",
                "Keep max_file_bytes enabled for broad searches; skipped files are returned in the result.",
                "Prefer fulltext_search when the project is indexed and you need docstring/body FTS.",
            ],
        }
