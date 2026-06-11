"""
Analyze timing bottlenecks from worker log [TIMING] lines MCP command.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from ...core.exceptions import ValidationError
from ..base_mcp_command import BaseMCPCommand
from ..log_viewer import parse_log_timestamp, parse_timing_line

from ._shared import WORKER_LOG_FILENAMES
from .parse_time import parse_time_optional


class AnalyzeTimingBottlenecksMCPCommand(BaseMCPCommand):
    """
    Collect [TIMING] lines from a worker log and compute bottlenecks by operation.

    Requires log_all_operations_timing enabled for the worker that produced the log.
    """

    name = "analyze_timing_bottlenecks"
    version = "1.0.0"
    descr = (
        "Collect [TIMING] lines from this server's worker logs and report bottlenecks "
        "by internal operation (server-side only; not about user projects the server serves)."
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
                "log_path": {
                    "type": "string",
                    "description": "Path to log file (optional if worker_type is set and config available)",
                },
                "worker_type": {
                    "type": "string",
                    "enum": [
                        "file_watcher",
                        "vectorization",
                        "indexing",
                        "database_driver",
                        "analysis",
                    ],
                    "description": "Worker type to resolve default log path; default vectorization",
                    "default": "vectorization",
                },
                "from_time": {
                    "type": "string",
                    "description": "Start time filter (ISO or YYYY-MM-DD HH:MM:SS); only lines on or after this time",
                },
                "to_time": {
                    "type": "string",
                    "description": "End time filter (ISO or YYYY-MM-DD HH:MM:SS); only lines before this time",
                },
                "tail": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Analyze only last N lines of the log (ignores time filters when set)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of log lines to scan (default 50000)",
                    "default": 50000,
                    "minimum": 1,
                    "maximum": 1000000,
                },
                "top_n": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Number of top bottlenecks to return by total and by average time (default 10)",
                    "default": 10,
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Reject ``top_n`` and ``limit`` outside schema min/max after schema validation."""
        params = super().validate_params(params)
        schema = self.get_schema()
        props = schema.get("properties") or {}
        for key in ("top_n", "limit", "tail"):
            if key not in params or params[key] is None:
                continue
            value = params[key]
            prop = props.get(key) or {}
            minimum = prop.get("minimum")
            maximum = prop.get("maximum")
            if minimum is not None and value < minimum:
                raise ValidationError(
                    f"{self.name}: parameter {key!r} must be >= {minimum}, got {value!r}",
                    field=key,
                    details={"minimum": minimum, "maximum": maximum},
                )
            if maximum is not None and value > maximum:
                raise ValidationError(
                    f"{self.name}: parameter {key!r} must be <= {maximum}, got {value!r}",
                    field=key,
                    details={"minimum": minimum, "maximum": maximum},
                )
        return params

    def _resolve_worker_log_path(self, worker_type: str) -> Optional[str]:
        """Resolve default log path for worker_type from server config."""
        try:
            storage = BaseMCPCommand._get_shared_storage()
            log_name = WORKER_LOG_FILENAMES.get(worker_type)
            if not log_name:
                return None
            path = storage.log_dir / log_name
            return str(path)
        except Exception as e:
            import logging

            logging.getLogger(__name__).debug(
                "Could not resolve worker log path from config: %s", e
            )
            return None

    def _is_timing_enabled(self) -> bool:
        """Return True if log_all_operations_timing is enabled in code_analysis.worker config."""
        try:
            from ...core.storage_paths import load_raw_config

            config_path = BaseMCPCommand._resolve_config_path()
            config_data = load_raw_config(config_path)
            worker_config = config_data.get("code_analysis", {}).get("worker", {})
            return bool(worker_config.get("log_all_operations_timing", False))
        except Exception:
            return False

    async def execute(
        self,
        log_path: Optional[str] = None,
        worker_type: str = "vectorization",
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        tail: Optional[int] = None,
        limit: int = 50000,
        top_n: int = 10,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute analyze timing bottlenecks: read log, parse [TIMING] lines, aggregate by op_name."""
        params: Dict[str, Any] = {
            "log_path": log_path,
            "worker_type": worker_type,
            "from_time": from_time,
            "to_time": to_time,
            "tail": tail,
            "limit": limit,
            "top_n": top_n,
        }
        params.update(kwargs)
        try:
            params = self.validate_params(params)
        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details=getattr(e, "details", None)
                or {"field": getattr(e, "field", None)},
            )
        log_path = params.get("log_path")
        worker_type = str(params.get("worker_type") or "vectorization")
        from_time = params.get("from_time")
        to_time = params.get("to_time")
        tail = params.get("tail")
        limit = int(params.get("limit", 50000))
        top_n = int(params.get("top_n", 10))
        if not self._is_timing_enabled():
            return ErrorResult(
                code="TIMING_DISABLED",
                message=(
                    "Timing is disabled. Enable log_all_operations_timing in code_analysis.worker config "
                    "to log [TIMING] lines and use this command."
                ),
            )
        resolved_path = log_path
        if not resolved_path:
            resolved_path = self._resolve_worker_log_path(worker_type)
        if not resolved_path:
            return ErrorResult(
                code="MISSING_LOG_PATH",
                message="Provide log_path or worker_type with server config to resolve default log path",
            )
        path = Path(resolved_path)
        if not path.exists() or not path.is_file():
            return ErrorResult(
                code="LOG_FILE_NOT_FOUND",
                message=f"Log file not found or not a file: {resolved_path}",
            )
        dt_from = parse_time_optional(from_time)
        dt_to = parse_time_optional(to_time)

        agg: Dict[str, List[float]] = {}
        lines_scanned = 0
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                if tail is not None and tail > 0:
                    buf = deque(f, maxlen=min(tail, limit))
                    lines_scanned = len(buf)
                    for line in buf:
                        parsed = parse_timing_line(line)
                        if parsed is None:
                            continue
                        op_name, duration = parsed
                        agg.setdefault(op_name, []).append(duration)
                else:
                    for line in f:
                        if lines_scanned >= limit:
                            break
                        lines_scanned += 1
                        if dt_from is not None or dt_to is not None:
                            ts = parse_log_timestamp(line)
                            if ts is not None:
                                if dt_from is not None and ts < dt_from:
                                    continue
                                if dt_to is not None and ts > dt_to:
                                    continue
                        parsed = parse_timing_line(line)
                        if parsed is None:
                            continue
                        op_name, duration = parsed
                        agg.setdefault(op_name, []).append(duration)
        except OSError as e:
            return self._handle_error(e, "LOG_READ_ERROR", "analyze_timing_bottlenecks")

        operations: List[Dict[str, Any]] = []
        for op_name, durations in agg.items():
            total_sec = sum(durations)
            count = len(durations)
            operations.append(
                {
                    "op_name": op_name,
                    "count": count,
                    "total_sec": round(total_sec, 3),
                    "avg_sec": round(total_sec / count, 3),
                    "min_sec": round(min(durations), 3),
                    "max_sec": round(max(durations), 3),
                }
            )
        operations.sort(key=lambda x: x["total_sec"], reverse=True)
        total_events = sum(len(d) for d in agg.values())
        total_duration_sec = sum(sum(d) for d in agg.values())

        bottlenecks_by_total = operations[:top_n]
        bottlenecks_by_avg = sorted(
            operations, key=lambda x: x["avg_sec"], reverse=True
        )[:top_n]

        data: Dict[str, Any] = {
            "log_path": resolved_path,
            "from_time": from_time,
            "to_time": to_time,
            "tail": tail,
            "lines_scanned": lines_scanned,
            "timing_events": total_events,
            "total_duration_sec": round(total_duration_sec, 3),
            "operations": operations,
            "bottlenecks_by_total": bottlenecks_by_total,
            "bottlenecks_by_avg": bottlenecks_by_avg,
            "message": (
                f"Parsed {total_events} timing events from {lines_scanned} lines; "
                f"total time {total_duration_sec:.1f}s across {len(operations)} operations."
            ),
        }
        return SuccessResult(data=data)

    @classmethod
    def metadata(cls: type["AnalyzeTimingBottlenecksMCPCommand"]) -> Dict[str, Any]:
        """Get detailed command metadata for AI models."""
        from .analyze_timing_bottlenecks_metadata import (
            get_analyze_timing_bottlenecks_metadata,
        )

        return get_analyze_timing_bottlenecks_metadata(cls)
