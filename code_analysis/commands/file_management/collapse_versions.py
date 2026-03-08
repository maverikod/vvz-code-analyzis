"""
Command to collapse file versions, keeping only latest by last_modified.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.database_client.client import DatabaseClient
else:
    DatabaseClient = Any

logger = logging.getLogger(__name__)


class CollapseVersionsCommand:
    """
    Command to collapse file versions, keeping only latest by last_modified.

    Finds all records with same path but different last_modified.
    Keeps the one with latest last_modified, deletes others (hard delete).

    Options:
    - project_id: Project ID
    - keep_latest: If True, keep latest version (default: True)
    - dry_run: Show what would be collapsed without actually collapsing
    """

    def __init__(
        self,
        database: "DatabaseClient",
        project_id: str,
        keep_latest: bool = True,
        dry_run: bool = False,
    ):
        """
        Initialize collapse command.

        Args:
            database: DatabaseClient instance
            project_id: Project ID
            keep_latest: If True, keep latest version (default: True)
            dry_run: If True, only show what would be collapsed
        """
        self.database = database
        self.project_id = project_id
        self.keep_latest = keep_latest
        self.dry_run = dry_run

    async def execute(self) -> Dict[str, Any]:
        """
        Execute collapse command.

        Returns:
            Dictionary with collapse statistics
        """
        result = {
            "kept_count": 0,
            "deleted_count": 0,
            "collapsed_files": [],
            "dry_run": self.dry_run,
        }

        try:
            if self.dry_run:
                # Just analyze, don't delete
                query_result = self.database.execute(
                    """
                    SELECT path, COUNT(*) as version_count
                    FROM files
                    WHERE project_id = ?
                    GROUP BY path
                    HAVING COUNT(*) > 1
                    """,
                    (self.project_id,),
                )
                files_with_versions = query_result.get("data", [])

                for path_row in files_with_versions:
                    file_path = path_row["path"]
                    version_count = path_row["version_count"]

                    # Get all versions
                    versions = self.database.get_file_versions(
                        file_path, self.project_id
                    )

                    if self.keep_latest:
                        keep_version = versions[0]  # Latest
                        delete_versions = versions[1:]
                    else:
                        keep_version = versions[-1]  # Oldest
                        delete_versions = versions[:-1]

                    result["collapsed_files"].append(
                        {
                            "path": file_path,
                            "version_count": version_count,
                            "keep": {
                                "id": keep_version["id"],
                                "last_modified": keep_version.get("last_modified"),
                            },
                            "delete": [
                                {"id": v["id"], "last_modified": v.get("last_modified")}
                                for v in delete_versions
                            ],
                        }
                    )
                    result["kept_count"] += 1
                    result["deleted_count"] += len(delete_versions)

                result["message"] = (
                    f"Would collapse {len(result['collapsed_files'])} files: "
                    f"keep {result['kept_count']}, delete {result['deleted_count']}"
                )
            else:
                # Actually collapse
                collapse_result = self.database.collapse_file_versions(
                    self.project_id, self.keep_latest
                )
                result.update(collapse_result)
                result["message"] = (
                    f"Collapsed {len(result['collapsed_files'])} files: "
                    f"kept {result['kept_count']}, deleted {result['deleted_count']}"
                )

        except Exception as e:
            logger.error(f"Error in collapse command: {e}", exc_info=True)
            result["error"] = str(e)

        return result
