"""
Search commands implementation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from typing import Dict, List, Any, Optional

from ..core import CodeDatabase

logger = logging.getLogger(__name__)


class SearchCommand:
    """Commands for searching code."""

    def __init__(self, database: CodeDatabase, project_id: str):
        """
        Initialize search command.

        Args:
            database: Database instance
            project_id: Project UUID
        """
        self.database = database
        self.project_id = project_id

    def find_usages(
        self,
        name: str,
        target_type: Optional[str] = None,
        target_class: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find all usages of a method or property.

        Args:
            name: Name of method/property to find
            target_type: Filter by type (method, property, function)
            target_class: Filter by class name

        Returns:
            List of usage records
        """
        logger.info(f"Searching for usages of '{name}' in project {self.project_id}")
        usages = self.database.find_usages(
            name, self.project_id, target_type, target_class
        )
        logger.info(f"Found {len(usages)} usages")
        return usages

    def full_text_search(
        self, query: str, entity_type: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Perform full-text search in code content and docstrings.

        Args:
            query: Search query text
            entity_type: Filter by entity type (class, method, function)
            limit: Maximum number of results

        Returns:
            List of matching records
        """
        logger.info(
            f"Performing full-text search for '{query}' in project {self.project_id}"
        )
        results = self.database.full_text_search(
            query, self.project_id, entity_type, limit
        )
        logger.info(f"Found {len(results)} results")
        return results

    def search_classes(self, pattern: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search classes by name pattern.

        Args:
            pattern: Name pattern to search (optional)

        Returns:
            List of class records
        """
        logger.info(
            f"Searching classes in project {self.project_id}"
            + (f" with pattern '{pattern}'" if pattern else "")
        )
        classes = self.database.search_classes(pattern, self.project_id)
        logger.info(f"Found {len(classes)} classes")
        return classes

    def search_methods(self, pattern: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search methods by name pattern.

        Args:
            pattern: Name pattern to search (optional)

        Returns:
            List of method records
        """
        logger.info(
            f"Searching methods in project {self.project_id}"
            + (f" with pattern '{pattern}'" if pattern else "")
        )
        methods = self.database.search_methods(pattern, self.project_id)
        logger.info(f"Found {len(methods)} methods")
        return methods
