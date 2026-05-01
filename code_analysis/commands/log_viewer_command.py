"""
LogViewerCommand: view worker logs with filtering.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from code_analysis.logging import importance_from_level

from .log_viewer_utils import (
    DATABASE_DRIVER_EVENT_PATTERNS,
    FILE_WATCHER_EVENT_PATTERNS,
    INDEXING_EVENT_PATTERNS,
    VECTORIZATION_EVENT_PATTERNS,
    get_log_files_for_reading,
    read_log_lines,
)

logger = logging.getLogger(__name__)


class LogViewerCommand:
    """
    Command to view worker logs with filtering.

    Supports time range, event type, log level, tail mode, search pattern, importance.
    """

    def __init__(
        self,
        log_path: str,
        worker_type: str = "file_watcher",
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        log_levels: Optional[List[str]] = None,
        search_pattern: Optional[str] = None,
        importance_min: Optional[int] = None,
        importance_max: Optional[int] = None,
        tail: Optional[int] = None,
        limit: int = 1000,
    ):
        self.log_path = Path(log_path)
        self.worker_type = worker_type
        self.from_time = self._parse_time(from_time) if from_time else None
        self.to_time = self._parse_time(to_time) if to_time else None
        self.event_types = set(event_types) if event_types else None
        self.log_levels = set(log_levels) if log_levels else None
        self.search_pattern = (
            re.compile(search_pattern, re.IGNORECASE) if search_pattern else None
        )
        self.importance_min = importance_min
        self.importance_max = importance_max
        self.tail = tail
        self.limit = limit
        if worker_type == "file_watcher":
            self.event_patterns = FILE_WATCHER_EVENT_PATTERNS
        elif worker_type == "vectorization":
            self.event_patterns = VECTORIZATION_EVENT_PATTERNS
        elif worker_type == "indexing":
            self.event_patterns = INDEXING_EVENT_PATTERNS
        elif worker_type == "database_driver":
            self.event_patterns = DATABASE_DRIVER_EVENT_PATTERNS
        else:
            self.event_patterns = {}

    def _parse_time(self, time_str: str) -> Optional[datetime]:
        if not time_str:
            return None
        try:
            return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        except ValueError:
            pass
        try:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
        try:
            return datetime.strptime(time_str, "%Y-%m-%d")
        except ValueError:
            pass
        logger.warning("Could not parse time string: %s", time_str)
        return None

    def _parse_log_line(self, line: str) -> Optional[Dict[str, Any]]:
        if not line.strip():
            return None

        def make_entry(
            ts: Optional[datetime],
            lvl: str,
            msg: str,
            imp: Optional[int] = None,
        ) -> Dict[str, Any]:
            importance = imp if imp is not None else importance_from_level(lvl)
            return {
                "timestamp": ts,
                "level": lvl,
                "importance": max(0, min(10, importance)),
                "message": msg,
                "raw": line,
            }

        parts = line.split(" | ", 3)
        if len(parts) >= 4:
            timestamp_str, level, importance_str, message = (
                parts[0],
                parts[1],
                parts[2],
                parts[3],
            )
            try:
                timestamp = datetime.strptime(
                    timestamp_str.strip(), "%Y-%m-%d %H:%M:%S"
                )
                imp = None
                try:
                    imp = int(importance_str.strip())
                except (ValueError, AttributeError):
                    pass
                return make_entry(timestamp, level.strip(), message.strip(), imp)
            except ValueError:
                pass
        if len(parts) == 3:
            timestamp_str, level, message = parts
            try:
                timestamp = datetime.strptime(
                    timestamp_str.strip(), "%Y-%m-%d %H:%M:%S"
                )
                return make_entry(timestamp, level.strip(), message.strip())
            except ValueError:
                pass
        parts_alt = line.split(" - ", 2)
        if len(parts_alt) == 3:
            timestamp_str, level, message = parts_alt
            try:
                timestamp = datetime.strptime(
                    timestamp_str.strip(), "%Y-%m-%d %H:%M:%S"
                )
                return make_entry(timestamp, level.strip(), message.strip())
            except ValueError:
                pass
        match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
        if match:
            try:
                timestamp = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                level_match = re.search(
                    r"\b(DEBUG|INFO|WARNING|ERROR|CRITICAL)\b", line
                )
                level = level_match.group(1) if level_match else "UNKNOWN"
                return make_entry(timestamp, level, line)
            except ValueError:
                pass
        return make_entry(None, "UNKNOWN", line)

    def _matches_event_type(self, parsed_line: Dict[str, Any]) -> bool:
        if not self.event_types:
            return True
        message = parsed_line.get("message", "")
        for event_type in self.event_types:
            pattern = self.event_patterns.get(event_type)
            if pattern and re.search(pattern, message, re.IGNORECASE):
                return True
        return False

    def _matches_filters(self, parsed_line: Dict[str, Any]) -> bool:
        timestamp = parsed_line.get("timestamp")
        if timestamp:
            if self.from_time and timestamp < self.from_time:
                return False
            if self.to_time and timestamp > self.to_time:
                return False
        elif self.from_time or self.to_time:
            return False
        if self.log_levels:
            level = parsed_line.get("level", "").upper()
            if level not in self.log_levels:
                return False
        if not self._matches_event_type(parsed_line):
            return False
        if self.search_pattern:
            if not self.search_pattern.search(parsed_line.get("message", "")):
                return False
        importance = parsed_line.get("importance", 4)
        if self.importance_min is not None and importance < self.importance_min:
            return False
        if self.importance_max is not None and importance > self.importance_max:
            return False
        return True

    async def execute(self) -> Dict[str, Any]:
        """Execute log viewer command; return dict with entries and stats."""
        import gzip

        result = {
            "log_path": str(self.log_path),
            "worker_type": self.worker_type,
            "entries": [],
            "total_lines": 0,
            "filtered_lines": 0,
            "filters": {
                "from_time": self.from_time.isoformat() if self.from_time else None,
                "to_time": self.to_time.isoformat() if self.to_time else None,
                "event_types": list(self.event_types) if self.event_types else None,
                "log_levels": list(self.log_levels) if self.log_levels else None,
                "search_pattern": (
                    self.search_pattern.pattern if self.search_pattern else None
                ),
                "importance_min": self.importance_min,
                "importance_max": self.importance_max,
                "tail": self.tail,
            },
        }
        files_to_read = get_log_files_for_reading(self.log_path)
        if not files_to_read:
            result["error"] = f"Log file not found: {self.log_path}"
            return result
        try:

            def _read_all_log_files_sync() -> List[str]:
                out_lines: List[str] = []
                for p in files_to_read:
                    try:
                        out_lines.extend(read_log_lines(p))
                    except (OSError, gzip.BadGzipFile) as e:
                        logger.warning("Skip reading %s: %s", p, e)
                return out_lines

            lines = await asyncio.to_thread(_read_all_log_files_sync)
            result["total_lines"] = len(lines)
            result["files_read"] = len(files_to_read)
            if self.tail:
                lines = lines[-self.tail :]
            entries_list: List[Dict[str, Any]] = []
            filtered_count = 0
            for line in lines:
                parsed = self._parse_log_line(line.rstrip("\n"))
                if not parsed:
                    continue
                if self._matches_filters(parsed):
                    entry = {
                        "timestamp": (
                            parsed["timestamp"].isoformat()
                            if parsed.get("timestamp")
                            else None
                        ),
                        "level": parsed.get("level", "UNKNOWN"),
                        "importance": parsed.get("importance", 4),
                        "message": parsed.get("message", ""),
                        "raw": parsed.get("raw", ""),
                    }
                    entries_list.append(entry)
                    filtered_count += 1
                    if len(entries_list) >= self.limit:
                        break
            result["entries"] = entries_list
            result["filtered_lines"] = filtered_count
            result["message"] = (
                f"Found {result['filtered_lines']} matching entries "
                f"(from {result['total_lines']} total lines)"
            )
        except Exception as e:
            logger.error(
                "Error reading log file %s: %s", self.log_path, e, exc_info=True
            )
            result["error"] = str(e)
        return result
