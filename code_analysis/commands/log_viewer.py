"""
Internal commands for viewing worker logs with filtering.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from code_analysis.logging import importance_from_level

logger = logging.getLogger(__name__)

# Event type patterns for File Watcher Worker
FILE_WATCHER_EVENT_PATTERNS = {
    "new_file": r"\[NEW FILE\]",
    "changed_file": r"\[CHANGED FILE\]",
    "deleted_file": r"\[DELETED FILE\]",
    "cycle": r"\[CYCLE #\d+\]",
    "scan_start": r"\[SCAN START\]",
    "scan_end": r"\[SCAN END\]",
    "queue": r"\[QUEUE\]",
    "error": r"ERROR|✗",
    "info": r"INFO",
    "warning": r"WARNING",
}

# Event type patterns for Vectorization Worker
VECTORIZATION_EVENT_PATTERNS = {
    "cycle": r"\[CYCLE #\d+\]",
    "processed": r"processed|vectorized",
    "error": r"ERROR|✗|failed",
    "info": r"INFO",
    "warning": r"WARNING",
    "circuit_breaker": r"circuit.*breaker|circuit.*open|circuit.*closed",
}

# Event type patterns for Indexing Worker
INDEXING_EVENT_PATTERNS = {
    "cycle": r"\[CYCLE #\d+\]|Starting indexing cycle",
    "indexed": r"Indexed|index_file",
    "error": r"ERROR|✗|failed",
    "info": r"INFO",
    "warning": r"WARNING",
    "database": r"Database is now available|Database is unavailable",
}

# Event type patterns for Database Driver
DATABASE_DRIVER_EVENT_PATTERNS = {
    "rpc": r"rpc_server|_process_request|handle_",
    "execute": r"execute|sql_preview",
    "error": r"ERROR|✗|failed",
    "info": r"INFO",
    "warning": r"WARNING",
}


class LogViewerCommand:
    """
    Command to view worker logs with filtering.

    Supports:
    - Filtering by time range (from_time, to_time)
    - Filtering by event type (new_file, changed_file, deleted_file, etc.)
    - Filtering by log level (INFO, ERROR, WARNING, DEBUG)
    - Tail mode (last N lines)
    - Search by text pattern
    """

    def __init__(
        self,
        log_path: str,
        worker_type: str = "file_watcher",  # "file_watcher" or "vectorization"
        from_time: Optional[str] = None,  # ISO format or "YYYY-MM-DD HH:MM:SS"
        to_time: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        log_levels: Optional[List[str]] = None,
        search_pattern: Optional[str] = None,
        importance_min: Optional[int] = None,  # 0-10
        importance_max: Optional[int] = None,  # 0-10
        tail: Optional[int] = None,  # Last N lines
        limit: int = 1000,  # Maximum lines to return
    ):
        """
        Initialize log viewer command.

        Args:
            log_path: Path to log file
            worker_type: Type of worker ("file_watcher" or "vectorization")
            from_time: Start time filter (ISO format or "YYYY-MM-DD HH:MM:SS")
            to_time: End time filter (ISO format or "YYYY-MM-DD HH:MM:SS")
            event_types: List of event types to filter (e.g., ["new_file", "changed_file"])
            log_levels: List of log levels to filter (e.g., ["INFO", "ERROR"])
            search_pattern: Text pattern to search for (regex supported)
            importance_min: Minimum importance 0-10 (inclusive)
            importance_max: Maximum importance 0-10 (inclusive)
            tail: Return last N lines (if specified, ignores time filters)
            limit: Maximum number of lines to return
        """
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

        # Select event patterns based on worker type
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
        """
        Parse time string to datetime.

        Supports:
        - ISO format: "2025-01-26T10:30:00"
        - Simple format: "2025-01-26 10:30:00"
        - Date only: "2025-01-26" (assumes 00:00:00)

        Args:
            time_str: Time string to parse

        Returns:
            datetime object or None if parsing fails
        """
        if not time_str:
            return None

        # Try ISO format first
        try:
            return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        except ValueError:
            pass

        # Try simple format
        try:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

        # Try date only
        try:
            return datetime.strptime(time_str, "%Y-%m-%d")
        except ValueError:
            pass

        logger.warning(f"Could not parse time string: {time_str}")
        return None

    def _parse_log_line(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Parse a log line and extract information.

        Supports:
        - Unified: "YYYY-MM-DD HH:MM:SS | LEVEL | IMPORTANCE | message"
        - Legacy:  "YYYY-MM-DD HH:MM:SS | LEVEL | message" (importance from level)
        - Alt:     "YYYY-MM-DD HH:MM:SS - LEVEL - message"
        - Loose:   "YYYY-MM-DD HH:MM:SS ..." (level from regex, importance from level)

        Args:
            line: Log line to parse

        Returns:
            Dictionary with timestamp, level, importance (0-10), message, raw; or None if empty.
        """
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

        # Unified format: "YYYY-MM-DD HH:MM:SS | LEVEL | IMPORTANCE | message"
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

        # Legacy 3-part: "YYYY-MM-DD HH:MM:SS | LEVEL | message"
        if len(parts) == 3:
            timestamp_str, level, message = parts
            try:
                timestamp = datetime.strptime(
                    timestamp_str.strip(), "%Y-%m-%d %H:%M:%S"
                )
                return make_entry(timestamp, level.strip(), message.strip())
            except ValueError:
                pass

        # Alternative format: "YYYY-MM-DD HH:MM:SS - LEVEL - message"
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

        # Loose: "YYYY-MM-DD HH:MM:SS ..."
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
        """
        Check if log line matches any of the specified event types.

        Args:
            parsed_line: Parsed log line

        Returns:
            True if matches event type filter, False otherwise
        """
        if not self.event_types:
            return True

        message = parsed_line.get("message", "")
        for event_type in self.event_types:
            pattern = self.event_patterns.get(event_type)
            if pattern and re.search(pattern, message, re.IGNORECASE):
                return True

        return False

    def _matches_filters(self, parsed_line: Dict[str, Any]) -> bool:
        """
        Check if log line matches all filters.

        Args:
            parsed_line: Parsed log line

        Returns:
            True if matches all filters, False otherwise
        """
        # Time filter
        timestamp = parsed_line.get("timestamp")
        if timestamp:
            if self.from_time and timestamp < self.from_time:
                return False
            if self.to_time and timestamp > self.to_time:
                return False
        elif self.from_time or self.to_time:
            # If time filter is set but line has no timestamp, exclude it
            return False

        # Log level filter
        if self.log_levels:
            level = parsed_line.get("level", "").upper()
            if level not in self.log_levels:
                return False

        # Event type filter
        if not self._matches_event_type(parsed_line):
            return False

        # Search pattern filter (regex on message)
        if self.search_pattern:
            message = parsed_line.get("message", "")
            if not self.search_pattern.search(message):
                return False

        # Importance filter (0-10)
        importance = parsed_line.get("importance", 4)
        if self.importance_min is not None and importance < self.importance_min:
            return False
        if self.importance_max is not None and importance > self.importance_max:
            return False

        return True

    async def execute(self) -> Dict[str, Any]:
        """
        Execute log viewer command.

        Returns:
            Dictionary with log entries and statistics
        """
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

        if not self.log_path.exists():
            result["error"] = f"Log file not found: {self.log_path}"
            return result

        try:
            # Read log file
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            result["total_lines"] = len(lines)

            # If tail mode, take last N lines
            if self.tail:
                lines = lines[-self.tail :]

            entries_list: List[Dict[str, Any]] = []
            filtered_count = 0

            # Parse and filter lines
            for line in lines:
                parsed = self._parse_log_line(line.rstrip("\n"))
                if not parsed:
                    continue

                if self._matches_filters(parsed):
                    # Serialize for JSON: timestamp as ISO, include importance
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

                    # Apply limit
                    if len(entries_list) >= self.limit:
                        break

            result["entries"] = entries_list
            result["filtered_lines"] = filtered_count

            result["message"] = (
                f"Found {result['filtered_lines']} matching entries "
                f"(from {result['total_lines']} total lines)"
            )

        except Exception as e:
            logger.error(f"Error reading log file {self.log_path}: {e}", exc_info=True)
            result["error"] = str(e)

        return result


class ListLogFilesCommand:
    """
    Command to list available log files for workers and server.

    Scans configured log directories and returns available log files.
    Supports worker logs (file_watcher, vectorization) and server logs (mcp_proxy_adapter, etc.).
    """

    def __init__(
        self,
        log_dirs: Optional[List[str]] = None,
        worker_type: Optional[
            str
        ] = None,  # "file_watcher", "vectorization", "server", or None for all
    ):
        """
        Initialize list log files command.

        Args:
            log_dirs: List of directories to scan for log files (optional)
            worker_type: Filter by worker type (optional)
        """
        self.log_dirs = [Path(d) for d in log_dirs] if log_dirs else []
        self.worker_type = worker_type

    async def execute(self) -> Dict[str, Any]:
        """
        Execute list log files command.

        Returns:
            Dictionary with available log files
        """
        result = {
            "log_files": [],
            "total_files": 0,
            "scanned_dirs": [str(d) for d in self.log_dirs],
        }

        # Default log directories if not specified
        if not self.log_dirs:
            self.log_dirs = [Path("logs")]
            result["scanned_dirs"] = ["logs"]

        # Known log file patterns (one log file per worker type)
        log_patterns = {
            "file_watcher": ["file_watcher.log*", "file_watcher*.log*"],
            "vectorization": ["vectorization_worker.log*", "vectorization*.log*"],
            "indexing": ["indexing_worker.log*", "indexing*.log*"],
            "database_driver": ["database_driver.log*", "database_driver*.log*"],
            "analysis": ["comprehensive_analysis.log*", "comprehensive_analysis*.log*"],
            "server": [
                "mcp_proxy_adapter.log*",
                "mcp_proxy_adapter*.log*",
                "mcp_server.log*",
                "*.log*",  # Fallback: all .log files
            ],
        }

        log_files_list: List[Dict[str, Any]] = []
        try:
            for log_dir in self.log_dirs:
                if not log_dir.exists():
                    continue

                # Get patterns to search
                if self.worker_type:
                    patterns = log_patterns.get(self.worker_type, [])
                else:
                    # If no worker_type specified, search all patterns
                    patterns = []
                    for patterns_list in log_patterns.values():
                        patterns.extend(patterns_list)
                    # Remove duplicates while preserving order
                    seen_patterns = set()
                    unique_patterns = []
                    for pattern in patterns:
                        if pattern not in seen_patterns:
                            unique_patterns.append(pattern)
                            seen_patterns.add(pattern)

                    patterns = unique_patterns

                # Search for log files
                found_files = set()  # Track found files to avoid duplicates
                for pattern in patterns:
                    for log_file in log_dir.glob(pattern):
                        if log_file.is_file() and str(log_file) not in found_files:
                            found_files.add(str(log_file))
                            stat = log_file.stat()
                            detected_type = self._detect_worker_type(log_file.name)

                            # Apply worker_type filter if specified
                            if self.worker_type and detected_type != self.worker_type:
                                # Special handling: if worker_type is "server", include all non-worker logs
                                if (
                                    self.worker_type == "server"
                                    and detected_type
                                    not in [
                                        "file_watcher",
                                        "vectorization",
                                        "indexing",
                                        "database_driver",
                                        "analysis",
                                    ]
                                ):
                                    pass  # Include server logs
                                else:
                                    continue

                            log_files_list.append(
                                {
                                    "path": str(log_file),
                                    "size": stat.st_size,
                                    "modified": datetime.fromtimestamp(
                                        stat.st_mtime
                                    ).isoformat(),
                                    "worker_type": detected_type,
                                }
                            )

            # Remove duplicates and sort by modified time (newest first)
            seen_paths = set()
            unique_files: List[Dict[str, Any]] = []
            for item in sorted(
                log_files_list, key=lambda x: x["modified"], reverse=True
            ):
                if item["path"] not in seen_paths:
                    unique_files.append(item)
                    seen_paths.add(item["path"])

            result["log_files"] = unique_files
            result["total_files"] = len(unique_files)
            result["message"] = f"Found {result['total_files']} log files"

        except Exception as e:
            logger.error(f"Error listing log files: {e}", exc_info=True)
            result["error"] = str(e)

        return result

    def _detect_worker_type(self, filename: str) -> str:
        """
        Detect worker type from filename.

        Args:
            filename: Name of the log file

        Returns:
            Type of log: "file_watcher", "vectorization", "indexing",
            "database_driver", "analysis", "server", or "unknown"
        """
        filename_lower = filename.lower()
        if "file_watcher" in filename_lower:
            return "file_watcher"
        elif "vectorization" in filename_lower:
            return "vectorization"
        elif "indexing_worker" in filename_lower or "indexing" in filename_lower:
            return "indexing"
        elif "database_driver" in filename_lower:
            return "database_driver"
        elif "comprehensive_analysis" in filename_lower:
            return "analysis"
        elif "mcp_proxy_adapter" in filename_lower or "mcp_server" in filename_lower:
            return "server"
        elif filename_lower.endswith(".log") or filename_lower.endswith(".log."):
            return "server"
        return "unknown"


class RotateLogsCommand:
    """
    Manually rotate a log file: rename current to .1, .1 to .2, etc., then create new empty log.

    Same naming as logging.handlers.RotatingFileHandler (log -> log.1 -> log.2 ...).
    The running worker may continue writing to the previous file (now .1) until it restarts
    or reopens the log.
    """

    def __init__(
        self,
        log_path: str,
        backup_count: int = 5,
    ):
        """
        Initialize rotate logs command.

        Args:
            log_path: Path to the log file to rotate.
            backup_count: Number of backup files to keep (default 5); keeps log.1 .. log.N.
        """
        self.log_path = Path(log_path)
        self.backup_count = max(1, min(backup_count, 99))

    def _rotation_path(self, n: int) -> Path:
        """Path for rotated file: log -> log.1, log.1 -> log.2, etc."""
        return Path(str(self.log_path) + "." + str(n))

    async def execute(self) -> Dict[str, Any]:
        """
        Perform rotation: shift .1->.2, .2->.3, ... then log->.1, create new empty log.

        Returns:
            Dict with rotated_paths (list of paths created/renamed), main_path, error (if any).
        """
        result: Dict[str, Any] = {
            "log_path": str(self.log_path),
            "backup_count": self.backup_count,
            "rotated_paths": [],
            "message": None,
        }
        if not self.log_path.exists():
            result["message"] = (
                f"Log file does not exist: {self.log_path}; nothing to rotate"
            )
            return result

        try:
            # Rotate existing backups: .(N-1) -> .N, .(N-2) -> .(N-1), ... .1 -> .2
            for i in range(self.backup_count - 1, 0, -1):
                src = self._rotation_path(i)
                if src.exists():
                    dst = self._rotation_path(i + 1)
                    if dst.exists():
                        dst.unlink()
                    src.rename(dst)
                    result["rotated_paths"].append(str(dst))

            # Current log -> .1
            dst1 = self._rotation_path(1)
            if dst1.exists():
                dst1.unlink()
            self.log_path.rename(dst1)
            result["rotated_paths"].insert(0, str(dst1))

            # Create new empty log file (same path)
            self.log_path.touch()
            result["message"] = (
                f"Rotated {self.log_path} to {dst1}; created new empty log. "
                f"Backups: {result['rotated_paths']}"
            )
        except OSError as e:
            logger.error("Log rotation failed for %s: %s", self.log_path, e)
            result["error"] = str(e)
        return result


# Regex for parsing [TIMING] lines: "[TIMING] op_name duration=X.XXXs key=value ..."
TIMING_LINE_RE = re.compile(
    r"\[TIMING\]\s+(\S+)\s+duration=([\d.]+)s",
    re.IGNORECASE,
)


def parse_timing_line(line: str) -> Optional[tuple[str, float]]:
    """
    Parse a log line containing [TIMING] and return (op_name, duration_sec).

    Expected message format: "[TIMING] op_name duration=X.XXXs [key=value ...]"

    Args:
        line: Full log line (unified format: "date | level | importance | message").

    Returns:
        (op_name, duration_sec) if line is a valid TIMING line, else None.
    """
    if "[TIMING]" not in line:
        return None
    # Message is after last " | " in unified format, or full line
    parts = line.split(" | ", 3)
    message = parts[-1].strip() if len(parts) >= 4 else line.strip()
    match = TIMING_LINE_RE.search(message)
    if not match:
        return None
    op_name = match.group(1)
    try:
        duration = float(match.group(2))
    except ValueError:
        return None
    return (op_name, duration)


def parse_log_timestamp(line: str) -> Optional[datetime]:
    """Parse timestamp from start of log line (YYYY-MM-DD HH:MM:SS). Returns None if not matched."""
    match = re.match(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", line.strip())
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
