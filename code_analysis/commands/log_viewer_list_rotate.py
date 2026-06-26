"""
List and rotate log commands: get_logs_by_id, ListLogsByIdCommand, ListLogFilesCommand, RotateLogsCommand.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from code_analysis.core.log_rotation_all import collect_log_paths

from .log_viewer_utils import LOG_ID_DESCRIPTIONS

logger = logging.getLogger(__name__)


def get_logs_by_id(
    config_data: Dict[str, Any],
    config_dir: Path,
    include_paths: bool = False,
) -> List[Dict[str, Any]]:
    """Return list of logs by identifier (log_id). Uses server config to resolve paths."""
    paths_and_labels = collect_log_paths(config_data, config_dir, log_filter=None)
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for path, label in paths_and_labels:
        if label in seen:
            continue
        seen.add(label)
        entry: Dict[str, Any] = {
            "log_id": label,
            "description": LOG_ID_DESCRIPTIONS.get(label, label),
        }
        if include_paths:
            entry["path"] = str(path)
        out.append(entry)
    return out


class ListLogsByIdCommand:
    """List available logs by identifier (log_id)."""

    def __init__(
        self,
        config_data: Dict[str, Any],
        config_dir: Path,
        include_paths: bool = False,
    ):
        """Store configuration used to resolve logs by stable identifier."""
        self.config_data = config_data
        self.config_dir = Path(config_dir)
        self.include_paths = include_paths

    async def execute(self) -> Dict[str, Any]:
        """Return configured logs and optional resolved filesystem paths."""
        logs = get_logs_by_id(
            self.config_data, self.config_dir, include_paths=self.include_paths
        )
        return {
            "logs": logs,
            "total": len(logs),
            "message": f"Found {len(logs)} log(s) by identifier",
        }


class ListLogFilesCommand:
    """Command to list available log files for workers and server."""

    def __init__(
        self,
        log_dirs: Optional[List[str]] = None,
        worker_type: Optional[str] = None,
    ):
        """Store log directories and optional worker-type filter."""
        self.log_dirs = [Path(d) for d in log_dirs] if log_dirs else []
        self.worker_type = worker_type

    def _detect_worker_type(self, filename: str) -> str:
        """Infer the worker category from a log filename."""
        filename_lower = filename.lower()
        if "file_watcher" in filename_lower:
            return "file_watcher"
        if "vectorization" in filename_lower:
            return "vectorization"
        if "indexing_worker" in filename_lower or "indexing" in filename_lower:
            return "indexing"
        if "database_driver" in filename_lower:
            return "database_driver"
        if "comprehensive_analysis" in filename_lower:
            return "analysis"
        if "mcp_proxy_adapter" in filename_lower or "mcp_server" in filename_lower:
            return "server"
        if filename_lower.endswith(".log") or filename_lower.endswith(".log."):
            return "server"
        return "unknown"

    async def execute(self) -> Dict[str, Any]:
        """Scan configured directories and return deduplicated log files."""
        result = {
            "log_files": [],
            "total_files": 0,
            "scanned_dirs": [str(d) for d in self.log_dirs],
        }
        if not self.log_dirs:
            self.log_dirs = [Path("logs")]
            result["scanned_dirs"] = ["logs"]
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
                "*.log*",
            ],
        }
        log_files_list: List[Dict[str, Any]] = []
        try:
            for log_dir in self.log_dirs:
                if not log_dir.exists():
                    continue
                if self.worker_type:
                    patterns = log_patterns.get(self.worker_type, [])
                else:
                    seen_p = set()
                    patterns = []
                    for pl in log_patterns.values():
                        for p in pl:
                            if p not in seen_p:
                                seen_p.add(p)
                                patterns.append(p)
                found_files = set()
                for pattern in patterns:
                    for log_file in log_dir.glob(pattern):
                        if not log_file.is_file() or str(log_file) in found_files:
                            continue
                        found_files.add(str(log_file))
                        stat = log_file.stat()
                        detected_type = self._detect_worker_type(log_file.name)
                        if self.worker_type and detected_type != self.worker_type:
                            if self.worker_type == "server" and detected_type not in (
                                "file_watcher",
                                "vectorization",
                                "indexing",
                                "database_driver",
                                "analysis",
                            ):
                                pass
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
            seen_paths = set()
            unique_files = []
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
            logger.error("Error listing log files: %s", e, exc_info=True)
            result["error"] = str(e)
        return result


class RotateLogsCommand:
    """Manually rotate a log file: rename current to .1, .1 to .2, etc., create new empty log."""

    def __init__(self, log_path: str, backup_count: int = 5):
        """Store the target log path and number of rotated backups."""
        self.log_path = Path(log_path)
        self.backup_count = backup_count

    def _rotation_path(self, n: int) -> Path:
        """Return the numbered backup path for one rotation generation."""
        return Path(str(self.log_path) + "." + str(n))

    async def execute(self) -> Dict[str, Any]:
        """Rotate the log file and create a fresh empty current log."""
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
            for i in range(self.backup_count - 1, 0, -1):
                src = self._rotation_path(i)
                if src.exists():
                    dst = self._rotation_path(i + 1)
                    if dst.exists():
                        dst.unlink()
                    src.rename(dst)
                    result["rotated_paths"].append(str(dst))
            dst1 = self._rotation_path(1)
            if dst1.exists():
                dst1.unlink()
            self.log_path.rename(dst1)
            result["rotated_paths"].insert(0, str(dst1))
            self.log_path.touch()
            result["message"] = (
                f"Rotated {self.log_path} to {dst1}; created new empty log. "
                f"Backups: {result['rotated_paths']}"
            )
        except OSError as e:
            logger.error("Log rotation failed for %s: %s", self.log_path, e)
            result["error"] = str(e)
        return result
