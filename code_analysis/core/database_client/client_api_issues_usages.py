"""
Issue and Usage operations API methods for database client.

Provides object-oriented API methods for Issue and Usage operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import List, Optional

from .objects.analysis import Issue, Usage
from .objects.mappers import (
    db_row_to_object,
    db_rows_to_objects,
    get_table_name_for_object,
    object_to_db_row,
)


class _ClientAPIIssuesUsagesMixin:
    """Mixin class with Issue and Usage operation methods."""

    # ============================================================================
    # Issue Operations
    # ============================================================================

    def create_issue(self, issue: Issue) -> Issue:
        """Create new issue in database.

        Args:
            issue: Issue object to create

        Returns:
            Created Issue object with ID and updated timestamps

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
            ValueError: If issue data is invalid
        """
        table_name = get_table_name_for_object(issue)
        if table_name is None:
            raise ValueError("Unknown table for Issue object")

        data = object_to_db_row(issue)
        row_id = self.insert(table_name, data)

        # Fetch created issue
        rows = self.select(table_name, where={"id": row_id})
        if not rows:
            raise ValueError("Failed to create issue")

        return db_row_to_object(rows[0], Issue)

    def get_issue(self, issue_id: int) -> Optional[Issue]:
        """Get issue by ID.

        Args:
            issue_id: Issue identifier

        Returns:
            Issue object or None if not found

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select("issues", where={"id": issue_id})
        if not rows:
            return None

        return db_row_to_object(rows[0], Issue)

    def get_file_issues(self, file_id: int) -> List[Issue]:
        """Get all issues for a file.

        Args:
            file_id: File identifier

        Returns:
            List of Issue objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select("issues", where={"file_id": file_id}, order_by=["line"])
        return db_rows_to_objects(rows, Issue)

    def get_project_issues(
        self, project_id: str, issue_type: Optional[str] = None
    ) -> List[Issue]:
        """Get all issues for a project.

        Args:
            project_id: Project identifier
            issue_type: Filter by issue type (optional)

        Returns:
            List of Issue objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        where = {"project_id": project_id}
        if issue_type:
            where["issue_type"] = issue_type

        rows = self.select("issues", where=where, order_by=["line"])
        return db_rows_to_objects(rows, Issue)

    def search_issues(
        self,
        project_id: Optional[str] = None,
        file_id: Optional[int] = None,
        issue_type: Optional[str] = None,
    ) -> List[Issue]:
        """Search issues by criteria.

        Args:
            project_id: Project identifier (optional)
            file_id: File identifier (optional)
            issue_type: Issue type (optional)

        Returns:
            List of Issue objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        where = {}
        if project_id:
            where["project_id"] = project_id
        if file_id:
            where["file_id"] = file_id
        if issue_type:
            where["issue_type"] = issue_type

        rows = self.select("issues", where=where, order_by=["line"])
        return db_rows_to_objects(rows, Issue)

    # ============================================================================
    # Usage Operations
    # ============================================================================

    def create_usage(self, usage: Usage) -> Usage:
        """Create new usage in database.

        Args:
            usage: Usage object to create

        Returns:
            Created Usage object with ID and updated timestamps

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
            ValueError: If usage data is invalid
        """
        table_name = get_table_name_for_object(usage)
        if table_name is None:
            raise ValueError("Unknown table for Usage object")

        data = object_to_db_row(usage)
        row_id = self.insert(table_name, data)

        # Fetch created usage
        rows = self.select(table_name, where={"id": row_id})
        if not rows:
            raise ValueError("Failed to create usage")

        return db_row_to_object(rows[0], Usage)

    def get_usage(self, usage_id: int) -> Optional[Usage]:
        """Get usage by ID.

        Args:
            usage_id: Usage identifier

        Returns:
            Usage object or None if not found

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select("usages", where={"id": usage_id})
        if not rows:
            return None

        return db_row_to_object(rows[0], Usage)

    def get_file_usages(self, file_id: int) -> List[Usage]:
        """Get all usages for a file.

        Args:
            file_id: File identifier

        Returns:
            List of Usage objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select("usages", where={"file_id": file_id}, order_by=["line"])
        return db_rows_to_objects(rows, Usage)

    def search_usages(
        self,
        target_name: Optional[str] = None,
        target_type: Optional[str] = None,
        usage_type: Optional[str] = None,
    ) -> List[Usage]:
        """Search usages by criteria.

        Args:
            target_name: Target name pattern (optional)
            target_type: Target type (optional)
            usage_type: Usage type (optional)

        Returns:
            List of Usage objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        # Use SQL for LIKE pattern matching when target_name is specified
        if target_name:
            sql = "SELECT * FROM usages WHERE 1=1"
            params = []
            sql += " AND target_name LIKE ?"
            params.append(f"%{target_name}%")
            if target_type:
                sql += " AND target_type = ?"
                params.append(target_type)
            if usage_type:
                sql += " AND usage_type = ?"
                params.append(usage_type)
            sql += " ORDER BY line"
            result = self.execute(sql, tuple(params))
            rows = result.get("data", [])
        else:
            where = {}
            if target_type:
                where["target_type"] = target_type
            if usage_type:
                where["usage_type"] = usage_type
            rows = self.select("usages", where=where, order_by=["line"])

        return db_rows_to_objects(rows, Usage)
