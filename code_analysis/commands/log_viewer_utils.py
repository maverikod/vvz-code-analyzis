"""
Log viewer utilities: file reading, patterns, timing/timestamp parsing.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import gzip
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

LOG_ID_DESCRIPTIONS: Dict[str, str] = {
    "mcp_server": "MCP server main log",
    "code_analysis": "Code analysis service log",
    "vectorization": "Vectorization worker log",
    "file_watcher": "File watcher worker log",
    "indexing_worker": "Indexing worker log",
}

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

VECTORIZATION_EVENT_PATTERNS = {
    "cycle": r"\[CYCLE #\d+\]",
    "processed": r"processed|vectorized",
    "error": r"ERROR|✗|failed",
    "info": r"INFO",
    "warning": r"WARNING",
    "circuit_breaker": r"circuit.*breaker|circuit.*open|circuit.*closed",
}

INDEXING_EVENT_PATTERNS = {
    "cycle": r"\[CYCLE #\d+\]|Starting indexing cycle",
    "indexed": r"Indexed|index_file",
    "error": r"ERROR|✗|failed",
    "info": r"INFO",
    "warning": r"WARNING",
    "database": r"Database is now available|Database is unavailable",
}

DATABASE_DRIVER_EVENT_PATTERNS = {
    "rpc": r"rpc_server|_process_request|handle_",
    "execute": r"execute|sql_preview",
    "error": r"ERROR|✗|failed",
    "info": r"INFO",
    "warning": r"WARNING",
}


def get_log_files_for_reading(
    base_path: Path,
    backup_count: int = 20,
) -> List[Path]:
    """Collect log file paths for reading in chronological order (oldest first)."""
    result: List[Path] = []
    base_path = base_path.resolve()
    for n in range(backup_count, 0, -1):
        p_plain = Path(str(base_path) + "." + str(n))
        p_gz = Path(str(p_plain) + ".gz")
        if p_gz.exists():
            result.append(p_gz)
        elif p_plain.exists():
            result.append(p_plain)
    if base_path.exists():
        result.append(base_path)
    return result


def read_log_lines(path: Path) -> List[str]:
    """Read lines from a log file, decompressing if path ends with .gz."""
    if path.suffix == ".gz" and str(path).endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return f.readlines()
    with open(path, "r", encoding="utf-8") as f:
        return f.readlines()


TIMING_LINE_RE = re.compile(
    r"\[TIMING\]\s+(\S+)\s+duration=([\d.]+)s",
    re.IGNORECASE,
)


def parse_timing_line(line: str) -> Optional[tuple[str, float]]:
    """Parse [TIMING] log line; return (op_name, duration_sec) or None."""
    if "[TIMING]" not in line:
        return None
    parts = line.split(" | ", 3)
    message = parts[-1].strip() if len(parts) >= 4 else line.strip()
    match = TIMING_LINE_RE.search(message)
    if not match:
        return None
    try:
        return (match.group(1), float(match.group(2)))
    except ValueError:
        return None


def parse_log_timestamp(line: str) -> Optional[datetime]:
    """Parse timestamp from start of log line (YYYY-MM-DD HH:MM:SS)."""
    match = re.match(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", line.strip())
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
