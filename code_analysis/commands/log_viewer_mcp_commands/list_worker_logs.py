"""
List worker log files MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ...core.list_pagination import (
    apply_list_pagination_defaults,
    apply_pagination_fields,
    list_pagination_schema_properties,
)
from ..base_mcp_command import BaseMCPCommand
from ..file_management.relative_path_list_pattern import (
    effective_listing_pattern,
    relative_path_matches_listing_pattern,
)
from ..log_viewer import ListLogFilesCommand


def _dedupe_log_files_by_resolved_path(
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Drop duplicate rows that point at the same inode (different path spellings).

    Default ``log_dirs`` may list both ``<config_dir>/logs`` and ``logs``; when they
    resolve to the same directory, :class:`ListLogFilesCommand` can emit the same file
    twice with different ``path`` strings. Keep the first occurrence in scan order.
    """
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        raw = str(row.get("path") or "")
        if not raw:
            continue
        try:
            key = str(Path(raw).resolve())
        except OSError:
            key = Path(raw).as_posix()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


class ListWorkerLogsMCPCommand(BaseMCPCommand):
    """List available worker log files."""

    name = "list_worker_logs"
    version = "1.1.0"
    descr = (
        "List worker log files under scanned dirs; optional ``file_pattern`` / ``glob`` "
        "as fnmatch on each file's absolute path (normalized ``\\\\`` → ``/``). "
        "When multiple scan roots resolve to the same directory, each physical file "
        "appears once in the response. Returns paginated ``items`` / ``log_files`` "
        "(default ``page_size`` 20); use ``block_position`` for the next page."
    )
    category = "logging"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for command parameters."""
        return {
            "type": "object",
            "properties": {
                "log_dirs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Directories to scan (absolute or relative to server CWD). "
                        'If omitted, defaults to ``[<config_dir>/logs>, "logs"]`` from '
                        "server storage (two entries so both config-adjacent and CWD "
                        '``logs/`` are covered); falls back to ``["logs"]`` if storage '
                        "is unavailable."
                    ),
                },
                "worker_type": {
                    "type": "string",
                    "enum": [
                        "file_watcher",
                        "vectorization",
                        "indexing",
                        "database_driver",
                        "analysis",
                        "server",
                    ],
                    "description": (
                        "Optional filter: only include files whose detected type matches. "
                        "Values: file_watcher, vectorization, indexing, database_driver, "
                        "analysis (comprehensive_analysis logs), server (MCP/proxy and other "
                        "generic ``*.log`` when no other rule matches)."
                    ),
                },
                "file_pattern": {
                    "type": "string",
                    "description": (
                        "Optional fnmatch on each log file's **absolute** path after "
                        "normalizing slashes (``*`` crosses ``/``). ``glob`` is an alias."
                    ),
                },
                "glob": {
                    "type": "string",
                    "description": (
                        "Alias of ``file_pattern``; non-empty ``file_pattern`` wins when both set."
                    ),
                },
                **list_pagination_schema_properties(),
            },
            "required": [],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize pagination params after schema validation."""
        params = super().validate_params(params)
        apply_list_pagination_defaults(params)
        return params

    async def execute(
        self,
        log_dirs: Optional[List[str]] = None,
        worker_type: Optional[str] = None,
        file_pattern: Optional[str] = None,
        glob: Optional[str] = None,
        page_size: Optional[int] = None,
        block_position: Optional[int] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute list worker logs command."""
        try:
            params = self.validate_params(
                {
                    "log_dirs": log_dirs,
                    "worker_type": worker_type,
                    "file_pattern": file_pattern,
                    "glob": glob,
                    "page_size": page_size,
                    "block_position": block_position,
                    "limit": limit,
                    "offset": offset,
                    **kwargs,
                }
            )
            log_dirs = params.get("log_dirs")
            worker_type = params.get("worker_type")
            file_pattern = params.get("file_pattern")
            glob = params.get("glob")
            page_size_val = int(params["page_size"])
            offset_val = int(params["offset"])
            block_position_val = int(params["block_position"])
            resolved_dirs = log_dirs
            if not resolved_dirs:
                try:
                    storage = BaseMCPCommand._get_shared_storage()
                    config_logs = str(storage.log_dir)
                    resolved_dirs = [config_logs, "logs"]
                except Exception:
                    resolved_dirs = ["logs"]
            command = ListLogFilesCommand(
                log_dirs=resolved_dirs, worker_type=worker_type
            )
            result = await command.execute()
            if isinstance(result, dict) and result.get("log_files"):
                result = {
                    **result,
                    "log_files": _dedupe_log_files_by_resolved_path(
                        list(result["log_files"])
                    ),
                }
            eff = effective_listing_pattern(file_pattern, glob)
            if eff and isinstance(result, dict):
                logs = result.get("log_files") or []
                filtered = [
                    row
                    for row in logs
                    if relative_path_matches_listing_pattern(
                        Path(str(row.get("path", ""))).as_posix(), eff
                    )
                ]
                result = {
                    **result,
                    "log_files": filtered,
                }
            if isinstance(result, dict):
                all_files = list(result.get("log_files") or [])
                apply_pagination_fields(
                    result,
                    all_items=all_files,
                    legacy_items_key="log_files",
                    page_size=page_size_val,
                    block_position=block_position_val,
                    offset=offset_val,
                )
                result["total_files"] = result["total"]
                result["message"] = (
                    f"Found {result['total']} log file(s); "
                    f"returning page {block_position_val} ({result['count']} rows)"
                )
            return SuccessResult(data=result)
        except Exception as e:
            return self._handle_error(e, "LOG_LIST_ERROR", "list_worker_logs")

    @classmethod
    def metadata(cls: type["ListWorkerLogsMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
            "parameters_summary": (
                "Optional: ``worker_type``, ``log_dirs``, ``file_pattern`` / ``glob`` (fnmatch on "
                "each log file's absolute path)."
            ),
            "detailed_description": (
                "The list_worker_logs command lists worker and server log files under the "
                "configured scan directories. Detected worker kinds include file_watcher, "
                "vectorization, indexing, database_driver, analysis (comprehensive_analysis "
                "filenames), and server (MCP/proxy logs and other ``*.log`` files).\n\n"
                "Operation flow:\n"
                "1. If ``log_dirs`` is provided, those directories are scanned\n"
                '2. If omitted, uses ``[<config_dir>/logs>, "logs"]`` from server storage, '
                'or ``["logs"]`` alone when storage metadata is unavailable\n'
                "3. Glob patterns per ``worker_type`` (or all patterns when unset) find files\n"
                "4. If ``worker_type`` is set, rows whose detected type does not match are dropped "
                "(with a special case so ``server`` can still include unmatched ``*.log`` files)\n"
                "5. Rows that resolve to the same absolute path (duplicate scan roots) are merged\n"
                "6. If ``file_pattern`` or ``glob`` is set, keeps entries whose absolute ``path`` "
                "matches (fnmatch; ``*`` crosses ``/``; literals without ``*?[]`` match exact path "
                "or directory prefix)\n"
                "7. Returns log_files (path, size, modified, worker_type), total_files, scanned_dirs"
            ),
            "parameters": {
                "log_dirs": {
                    "description": (
                        "Directories to scan. Optional. When omitted, the server uses "
                        "``<config_dir>/logs`` plus ``logs`` (see command schema)."
                    ),
                    "type": "array",
                    "required": False,
                    "items": {"type": "string"},
                },
                "worker_type": {
                    "description": (
                        "Optional filter matching detected log kind (see schema enum)."
                    ),
                    "type": "string",
                    "required": False,
                    "enum": [
                        "file_watcher",
                        "vectorization",
                        "indexing",
                        "database_driver",
                        "analysis",
                        "server",
                    ],
                },
                "file_pattern": {
                    "description": (
                        "Optional fnmatch on each log file's absolute path (posix slashes). "
                        "``glob`` is an alias."
                    ),
                    "type": "string",
                    "required": False,
                    "examples": ["*file_watcher*.log*", "*/logs/*.log"],
                },
                "glob": {
                    "description": "Alias of ``file_pattern``.",
                    "type": "string",
                    "required": False,
                },
            },
            "usage_examples": [
                {
                    "description": "List all log files",
                    "command": {},
                    "explanation": (
                        "Uses default scan dirs (config ``logs`` plus ``logs`` under CWD when "
                        "both exist); merges duplicate paths that resolve to the same file."
                    ),
                },
                {
                    "description": "List file_watcher logs",
                    "command": {"worker_type": "file_watcher"},
                    "explanation": "Only file_watcher logs.",
                },
            ],
            "error_cases": {
                "LOG_LIST_ERROR": {
                    "description": "General error during log listing",
                    "solution": "Verify log directories exist and are accessible.",
                },
            },
            "return_value": {
                "success": {
                    "data": {
                        "log_files": "List of log files with path, size, modified_time.",
                        "total_files": "Count.",
                        "scanned_dirs": "Dirs scanned.",
                    }
                },
                "error": {
                    "code": "LOG_LIST_ERROR",
                    "message": "Human-readable message.",
                },
            },
            "best_practices": [
                "Use this command first to discover available log files",
                "Narrow with file_pattern on absolute path (e.g. *vectorization*)",
                "Use returned paths with view_worker_logs",
            ],
        }
