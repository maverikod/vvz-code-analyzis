"""
Directory scanner for file watcher worker.

Scans configured directories for code files and detects changes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import fnmatch
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# File extensions to process
CODE_FILE_EXTENSIONS = {".py", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}

# Default patterns to ignore (always applied)
DEFAULT_IGNORE_PATTERNS = {
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    ".venv",
    "venv",
    "data/versions",  # Version directory for deleted files
    "data/versions/**",  # All subdirectories in versions
    "*.pyc",
}


def should_ignore_path(path: Path, ignore_patterns: Optional[List[str]] = None) -> bool:
    """
    Check if path should be ignored.

    Args:
        path: Path to check
        ignore_patterns: Additional ignore patterns from config (optional)

    Returns:
        True if path should be ignored, False otherwise
    """
    # Combine default and config patterns
    all_patterns = set(DEFAULT_IGNORE_PATTERNS)
    if ignore_patterns:
        all_patterns.update(ignore_patterns)

    # Convert path to string for pattern matching
    path_str = str(path)
    rel_path_str = None
    if path.is_absolute():
        # Try to get relative path for better matching
        try:
            rel_path_str = str(path.relative_to(path.anchor))
        except (ValueError, AttributeError):
            pass

    # Check each part of the path
    for part in path.parts:
        # Direct name match
        if part in all_patterns:
            return True

        # Special handling for "data" and "versions" directories
        if part == "data":
            # Check if next part is "versions" or if path contains "data/versions"
            try:
                part_idx = path.parts.index(part)
                if part_idx + 1 < len(path.parts) and path.parts[part_idx + 1] == "versions":
                    return True
            except (ValueError, IndexError):
                pass

    # Pattern matching for full path and subpaths
    for pattern in all_patterns:
        # Check if pattern matches full path
        if fnmatch.fnmatch(path_str, pattern):
            return True
        if rel_path_str and fnmatch.fnmatch(rel_path_str, pattern):
            return True
        
        # Check if pattern matches any part of the path
        if "**" in pattern or "/" in pattern:
            # Glob pattern with ** or path separator
            for i in range(len(path.parts)):
                subpath = "/".join(path.parts[i:])
                if fnmatch.fnmatch(subpath, pattern):
                    return True
                # Also check with leading slash
                if fnmatch.fnmatch("/" + subpath, pattern):
                    return True
        
        # Simple pattern matching for each part
        for part in path.parts:
            if fnmatch.fnmatch(part, pattern):
                return True

    # Check for hidden directories (except current/parent)
    for part in path.parts:
        if part.startswith(".") and part != "." and part != "..":
            if path.is_dir():
                return True

    # Check file extension
    if path.is_file():
        return path.suffix not in CODE_FILE_EXTENSIONS

    return False


def scan_directory(
    root_dir: Path,
    project_root: Optional[Path] = None,
    ignore_patterns: Optional[List[str]] = None,
) -> Dict[str, Dict]:
    """
    Scan directory recursively for code files.

    Implements Step 5 of refactor plan: all file paths are absolute.
    Returns dictionary with absolute paths as keys.

    Args:
        root_dir: Root directory to scan
        project_root: Project root directory (unused, kept for compatibility)
        ignore_patterns: Glob patterns to ignore

    Returns:
        Dictionary mapping absolute file paths to file info:
        {
            "/absolute/path/to/file.py": {
                "path": Path("/absolute/path/to/file.py"),
                "mtime": 1234567890.0,
                "size": 1024,
            }
        }
    """
    from ..project_resolution import normalize_abs_path

    files: Dict[str, Dict] = {}

    try:
        for item in root_dir.rglob("*"):
            if should_ignore_path(item, ignore_patterns):
                continue

            if item.is_file():
                try:
                    stat = item.stat()
                    # Always use absolute resolved path (Step 5: absolute paths everywhere)
                    abs_path = normalize_abs_path(item)
                    path_key = abs_path

                    files[path_key] = {
                        "path": Path(abs_path),
                        "mtime": stat.st_mtime,
                        "size": stat.st_size,
                    }
                except OSError as e:
                    logger.debug(f"Error accessing file {item}: {e}")
                    continue

    except OSError as e:
        logger.error(f"Error scanning directory {root_dir}: {e}")

    return files


def find_missing_files(
    scanned_files: Dict[str, Dict], db_files: List[Dict]
) -> Set[str]:
    """
    Find files that exist in database but not on disk.

    Args:
        scanned_files: Files found on disk (from scan_directory)
        db_files: Files in database

    Returns:
        Set of file paths that are missing on disk
    """
    missing = set()
    for db_file in db_files:
        file_path = db_file.get("path")
        if file_path and file_path not in scanned_files:
            missing.add(file_path)
    return missing
