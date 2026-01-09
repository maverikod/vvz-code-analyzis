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

from ..settings_manager import get_settings

logger = logging.getLogger(__name__)

# Get settings from SettingsManager
settings = get_settings()

# File extensions to process (from settings)
CODE_FILE_EXTENSIONS = set(settings.get("code_file_extensions"))

# Default patterns to ignore (from settings)
DEFAULT_IGNORE_PATTERNS = set(settings.get("default_ignore_patterns"))


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
    watch_dirs: List[Path],
    ignore_patterns: Optional[List[str]] = None,
) -> Dict[str, Dict]:
    """
    Scan directory recursively for code files and discover projects.
    
    Implements project discovery: for each file, finds the nearest project root
    by walking up the directory tree and looking for projectid files.
    
    Args:
        root_dir: Root directory to scan
        watch_dirs: List of watched directories for project discovery (REQUIRED)
        ignore_patterns: Glob patterns to ignore
    
    Returns:
        Dictionary mapping absolute file paths to file info:
        {
            "/absolute/path/to/file.py": {
                "path": Path("/absolute/path/to/file.py"),
                "mtime": 1234567890.0,
                "size": 1024,
                "project_root": Path("/project/root"),
                "project_id": "uuid-here",
            }
        }
        
        Files without a project (no projectid found) are skipped with a warning.
    """
    from ..path_normalization import normalize_file_path
    from ..exceptions import NestedProjectError, ProjectNotFoundError
    from typing import Any
    
    files: Dict[str, Dict] = {}
    
    # Resolve watch_dirs to absolute paths
    watch_dirs_resolved = [Path(wd).resolve() for wd in watch_dirs]
    
    try:
        for item in root_dir.rglob("*"):
            if should_ignore_path(item, ignore_patterns):
                continue

            if item.is_file():
                try:
                    stat = item.stat()
                    # Use unified path normalization method
                    try:
                        normalized = normalize_file_path(item, watch_dirs=watch_dirs_resolved)
                        path_key = normalized.absolute_path
                        
                        file_info: Dict[str, Any] = {
                            "path": Path(normalized.absolute_path),
                            "mtime": stat.st_mtime,
                            "size": stat.st_size,
                            "project_root": normalized.project_root,
                            "project_id": normalized.project_id,
                        }
                        files[path_key] = file_info
                    except (ProjectNotFoundError, NestedProjectError) as e:
                        logger.warning(
                            f"No project found for file {item}: {e}, skipping"
                        )
                        continue
                    except Exception as e:
                        logger.debug(f"Error normalizing path for {item}: {e}")
                        continue
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
