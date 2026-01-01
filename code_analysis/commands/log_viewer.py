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
        self.tail = tail
        self.limit = limit

        # Select event patterns based on worker type
        if worker_type == "file_watcher":
            self.event_patterns = FILE_WATCHER_EVENT_PATTERNS
        elif worker_type == "vectorization":
            self.event_patterns = VECTORIZATION_EVENT_PATTERNS
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

        Expected format: "YYYY-MM-DD HH:MM:SS | LEVEL | message"

        Args:
            line: Log line to parse

        Returns:
            Dictionary with parsed information or None if line doesn't match format
        """
        if not line.strip():
            return None

        # Try to parse structured format: "YYYY-MM-DD HH:MM:SS | LEVEL | message"
        parts = line.split(" | ", 2)
        if len(parts) == 3:
            timestamp_str, level, message = parts
            try:
                timestamp = datetime.strptime(
                    timestamp_str.strip(), "%Y-%m-%d %H:%M:%S"
                )
                return {
                    "timestamp": timestamp,
                    "level": level.strip(),
                    "message": message.strip(),
                    "raw": line,
                }
            except ValueError:
                pass

        # Try alternative format: "YYYY-MM-DD HH:MM:SS - LEVEL - message"
        parts = line.split(" - ", 2)
        if len(parts) == 3:
            timestamp_str, level, message = parts
            try:
                timestamp = datetime.strptime(
                    timestamp_str.strip(), "%Y-%m-%d %H:%M:%S"
                )
                return {
                    "timestamp": timestamp,
                    "level": level.strip(),
                    "message": message.strip(),
                    "raw": line,
                }
            except ValueError:
                pass

        # If no structured format, try to extract timestamp from beginning
        # Format: "YYYY-MM-DD HH:MM:SS ..."
        match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
        if match:
            try:
                timestamp = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                # Try to extract level
                level_match = re.search(
                    r"\b(DEBUG|INFO|WARNING|ERROR|CRITICAL)\b", line
                )
                level = level_match.group(1) if level_match else "UNKNOWN"
                return {
                    "timestamp": timestamp,
                    "level": level,
                    "message": line,
                    "raw": line,
                }
            except ValueError:
                pass

        # Return as unparsed line
        return {
            "timestamp": None,
            "level": "UNKNOWN",
            "message": line,
            "raw": line,
        }

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

        # Search pattern filter
        if self.search_pattern:
            message = parsed_line.get("message", "")
            if not self.search_pattern.search(message):
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

            # Parse and filter lines
            for line in lines:
                parsed = self._parse_log_line(line.rstrip("\n"))
                if not parsed:
                    continue

                if self._matches_filters(parsed):
                    result["entries"].append(parsed)
                    result["filtered_lines"] += 1

                    # Apply limit
                    if len(result["entries"]) >= self.limit:
                        break

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
        }

        # Default log directories if not specified
        if not self.log_dirs:
            self.log_dirs = [Path("logs")]

        # Known log file patterns
        log_patterns = {
            "file_watcher": ["file_watcher.log*", "file_watcher*.log*"],
            "vectorization": ["vectorization_worker.log*", "vectorization*.log*"],
            "analysis": ["comprehensive_analysis.log*", "comprehensive_analysis*.log*"],
            "server": [
                "mcp_proxy_adapter.log*",
                "mcp_proxy_adapter*.log*",
                "*.log*",  # Fallback: all .log files
            ],
        }

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
                                if self.worker_type == "server" and detected_type not in [
                                    "file_watcher",
                                    "vectorization",
                                    "analysis",
                                ]:
                                    pass  # Include server logs
                                else:
                                    continue

                            result["log_files"].append(
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
            unique_files = []
            for log_file in sorted(
                result["log_files"], key=lambda x: x["modified"], reverse=True
            ):
                if log_file["path"] not in seen_paths:
                    unique_files.append(log_file)
                    seen_paths.add(log_file["path"])

            result["log_files"] = unique_files
            result["total_files"] = len(result["log_files"])
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
            Type of log: "file_watcher", "vectorization", "analysis", "server", or "unknown"
        """
        filename_lower = filename.lower()
        if "file_watcher" in filename_lower:
            return "file_watcher"
        elif "vectorization" in filename_lower:
            return "vectorization"
        elif "comprehensive_analysis" in filename_lower:
            return "analysis"
        elif "mcp_proxy_adapter" in filename_lower:
            return "server"
        elif filename_lower.endswith(".log") or filename_lower.endswith(".log."):
            # Default to server for other .log files
            return "server"
        return "unknown"
