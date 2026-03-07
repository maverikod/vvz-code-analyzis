"""
File versions: get_file_versions, collapse_file_versions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def get_file_versions(self, file_path: str, project_id: str) -> List[Dict[str, Any]]:
    """
    Get all versions of a file (same path, different last_modified).

    Version = last_modified timestamp.
    Multiple records with same path but different last_modified are considered versions.

    Implements Step 5 of refactor plan: all file paths are absolute.
    Path is normalized to absolute before querying.

    Args:
        file_path: File path (will be normalized to absolute)
        project_id: Project ID

    Returns:
        List of file versions sorted by last_modified (newest first)
    """
    from ...path_normalization import normalize_path_simple

    # Normalize path to absolute (Step 5: absolute paths everywhere)
    abs_path = normalize_path_simple(file_path)

    return self._fetchall(
        """
        SELECT * FROM files 
        WHERE project_id = ? AND path = ?
        ORDER BY last_modified DESC
        """,
        (project_id, abs_path),
    )


def collapse_file_versions(
    self, project_id: str, keep_latest: bool = True
) -> Dict[str, Any]:
    """
    Collapse file versions, keeping only latest by last_modified.

    Finds all records with same path but different last_modified.
    Keeps the one with latest last_modified, deletes others (hard delete).

    Args:
        project_id: Project ID
        keep_latest: If True, keep latest version (default: True)

    Returns:
        Dictionary with:
        - kept_count: Number of versions kept
        - deleted_count: Number of versions deleted
        - collapsed_files: List of file paths that had multiple versions
    """
    # Find all files with multiple versions (same path, different last_modified)
    files_with_versions = self._fetchall(
        """
        SELECT path, COUNT(*) as version_count
        FROM files
        WHERE project_id = ?
        GROUP BY path
        HAVING COUNT(*) > 1
        """,
        (project_id,),
    )

    kept_count = 0
    deleted_count = 0
    collapsed_files = []

    for path_row in files_with_versions:
        file_path = path_row["path"]
        collapsed_files.append(file_path)

        # Get all versions for this file
        versions = self.get_file_versions(file_path, project_id)

        if keep_latest:
            # Keep the first one (newest by last_modified DESC)
            delete_versions = versions[1:]
        else:
            # Keep the oldest
            delete_versions = versions[:-1]

        # Hard delete old versions
        for version in delete_versions:
            self.hard_delete_file(version["id"])
            deleted_count += 1

        kept_count += 1

    logger.info(
        f"Collapsed versions for {len(collapsed_files)} files: "
        f"kept {kept_count}, deleted {deleted_count}"
    )

    return {
        "kept_count": kept_count,
        "deleted_count": deleted_count,
        "collapsed_files": collapsed_files,
    }
