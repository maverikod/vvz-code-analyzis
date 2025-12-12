"""
Issues command implementation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Dict, List, Any, Optional

from ..core import CodeDatabase

logger = logging.getLogger(__name__)


class IssuesCommand:
    """Command for retrieving code quality issues."""

    def __init__(self, database: CodeDatabase, project_id: str):
        """
        Initialize issues command.

        Args:
            database: Database instance
            project_id: Project UUID
        """
        self.database = database
        self.project_id = project_id

    async def get_issues(
        self, issue_type: Optional[str] = None
    ) -> Dict[str, Any] | List[Dict[str, Any]]:
        """
        Get code quality issues from analysis.

        Args:
            issue_type: Filter by issue type (optional)

        Returns:
            Dictionary of issues grouped by type, or list if issue_type is specified
        """
        logger.info(
            f"Retrieving issues from project {self.project_id}"
            + (f" (type: {issue_type})" if issue_type else "")
        )

        if issue_type:
            issues = self.database.get_issues_by_type(issue_type, self.project_id)
            logger.info(f"Found {len(issues)} issues")
            return issues

        # Return all issues grouped by type
        all_issues = {}
        for issue_type_name in [
            "methods_with_pass",
            "not_implemented_in_non_abstract",
            "methods_without_docstrings",
            "files_without_docstrings",
            "classes_without_docstrings",
            "files_too_large",
        ]:
            issues = self.database.get_issues_by_type(issue_type_name, self.project_id)
            if issues:
                all_issues[issue_type_name] = issues

        total = sum(len(v) if isinstance(v, list) else 1 for v in all_issues.values())
        logger.info(f"Found {total} issues across {len(all_issues)} types")

        return all_issues
