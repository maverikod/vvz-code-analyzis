"""
Search command implementation.

Provides search functionality for code analysis.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SearchCommand:
    """
    Command for searching code content, classes, and methods.

    Wraps CodeDatabase search methods for easier use.
    """

    def __init__(self, database: Any, project_id: str):
        """
        Initialize search command.

        Args:
            database: CodeDatabase instance
            project_id: Project ID to filter by
        """
        self.database = database
        self.project_id = project_id

    def full_text_search(
        self, query: str, entity_type: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Perform full-text search in code content and docstrings.

        Args:
            query: Search query text
            entity_type: Optional filter by entity type
            limit: Maximum number of results

        Returns:
            List of matching records with file paths
        """
        return self.database.full_text_search(
            query, self.project_id, entity_type=entity_type, limit=limit
        )

    def search_classes(self, pattern: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search classes by name pattern.

        Args:
            pattern: Optional name pattern to search

        Returns:
            List of matching classes
        """
        return self.database.search_classes(name_pattern=pattern, project_id=self.project_id)

    def search_methods(
        self, class_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search methods, optionally filtered by class name.

        Args:
            class_name: Optional class name to filter by

        Returns:
            List of matching methods
        """
        return self.database.search_methods(
            name_pattern=None, class_name=class_name, project_id=self.project_id
        )

