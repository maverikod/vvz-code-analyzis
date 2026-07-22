"""
Issue operations API methods for database client.

Provides object-oriented API methods for Issue operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from .client_base import _DatabaseClientBase
from .objects.analysis import Issue
from .objects.mappers import (
    db_row_to_object,
    get_table_name_for_object,
    object_to_db_row,
)


class _ClientAPIIssuesUsagesMixin(_DatabaseClientBase):
    """Mixin class with Issue operation methods."""

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
        if row_id is None:
            raise ValueError("Failed to create issue: insert returned no row id")

        # Fetch created issue
        rows = self.select(table_name, where={"id": row_id})
        if not rows:
            raise ValueError("Failed to create issue")

        return db_row_to_object(rows[0], Issue)
