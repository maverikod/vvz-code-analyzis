"""
Code Duplicate and Statistics operations API methods for database client.

Provides object-oriented API methods for CodeDuplicate operations and statistics.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .objects.analysis import CodeDuplicate
from .objects.mappers import (
    db_row_to_object,
    db_rows_to_objects,
    get_table_name_for_object,
    object_to_db_row,
)


class _ClientAPIDuplicatesStatsMixin:
    """Mixin class with CodeDuplicate and Statistics operation methods."""

    # ============================================================================
    # Code Duplicate Operations
    # ============================================================================

    def create_code_duplicate(self, duplicate: CodeDuplicate) -> CodeDuplicate:
        """Create new code duplicate in database.

        Args:
            duplicate: CodeDuplicate object to create

        Returns:
            Created CodeDuplicate object with ID and updated timestamps

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
            ValueError: If duplicate data is invalid
        """
        table_name = get_table_name_for_object(duplicate)
        if table_name is None:
            raise ValueError("Unknown table for CodeDuplicate object")

        data = object_to_db_row(duplicate)
        row_id = self.insert(table_name, data)

        # Fetch created duplicate
        rows = self.select(table_name, where={"id": row_id})
        if not rows:
            raise ValueError("Failed to create code duplicate")

        return db_row_to_object(rows[0], CodeDuplicate)

    def get_code_duplicate(self, duplicate_id: int) -> Optional[CodeDuplicate]:
        """Get code duplicate by ID.

        Args:
            duplicate_id: Duplicate identifier

        Returns:
            CodeDuplicate object or None if not found

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        rows = self.select("code_duplicates", where={"id": duplicate_id})
        if not rows:
            return None

        return db_row_to_object(rows[0], CodeDuplicate)

    def get_project_duplicates(
        self, project_id: str, min_similarity: float = 0.0
    ) -> List[CodeDuplicate]:
        """Get all code duplicates for a project.

        Args:
            project_id: Project identifier
            min_similarity: Minimum similarity score (default: 0.0)

        Returns:
            List of CodeDuplicate objects

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        # Use execute for similarity comparison
        sql = """
            SELECT * FROM code_duplicates
            WHERE project_id = ? AND similarity >= ?
            ORDER BY similarity DESC
        """
        result = self.execute(sql, (project_id, min_similarity))
        rows = result.get("data", [])

        return db_rows_to_objects(rows, CodeDuplicate)

    # ============================================================================
    # Statistics Methods
    # ============================================================================

    def get_project_statistics(self, project_id: str) -> Dict[str, int]:
        """Get statistics for a project.

        Args:
            project_id: Project identifier

        Returns:
            Dictionary with statistics:
                - files: Number of files
                - classes: Number of classes
                - functions: Number of functions
                - methods: Number of methods
                - imports: Number of imports
                - issues: Number of issues
                - usages: Number of usages
                - duplicates: Number of code duplicates

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        stats = {}

        # Count files
        files = self.get_project_files(project_id)
        stats["files"] = len(files)

        # Count classes, functions, methods, imports
        sql = """
            SELECT 
                (SELECT COUNT(*) FROM classes c JOIN files f ON c.file_id = f.id WHERE f.project_id = ?) as classes,
                (SELECT COUNT(*) FROM functions fu JOIN files f ON fu.file_id = f.id WHERE f.project_id = ?) as functions,
                (SELECT COUNT(*) FROM methods m JOIN classes c ON m.class_id = c.id JOIN files f ON c.file_id = f.id WHERE f.project_id = ?) as methods,
                (SELECT COUNT(*) FROM imports i JOIN files f ON i.file_id = f.id WHERE f.project_id = ?) as imports,
                (SELECT COUNT(*) FROM issues WHERE project_id = ?) as issues,
                (SELECT COUNT(*) FROM usages u JOIN files f ON u.file_id = f.id WHERE f.project_id = ?) as usages,
                (SELECT COUNT(*) FROM code_duplicates WHERE project_id = ?) as duplicates
        """
        result = self.execute(sql, (project_id,) * 7)
        rows = result.get("data", [])
        if rows:
            row = rows[0]
            stats["classes"] = row.get("classes", 0)
            stats["functions"] = row.get("functions", 0)
            stats["methods"] = row.get("methods", 0)
            stats["imports"] = row.get("imports", 0)
            stats["issues"] = row.get("issues", 0)
            stats["usages"] = row.get("usages", 0)
            stats["duplicates"] = row.get("duplicates", 0)
        else:
            stats.update(
                {
                    "classes": 0,
                    "functions": 0,
                    "methods": 0,
                    "imports": 0,
                    "issues": 0,
                    "usages": 0,
                    "duplicates": 0,
                }
            )

        return stats

    def get_file_statistics(self, file_id: int) -> Dict[str, int]:
        """Get statistics for a file.

        Args:
            file_id: File identifier

        Returns:
            Dictionary with statistics:
                - classes: Number of classes
                - functions: Number of functions
                - methods: Number of methods
                - imports: Number of imports
                - issues: Number of issues
                - usages: Number of usages

        Raises:
            RPCClientError: If RPC call fails
            RPCResponseError: If response contains error
        """
        stats = {}

        # Count classes, functions, imports
        classes = self.get_file_classes(file_id)
        functions = self.get_file_functions(file_id)
        imports = self.get_file_imports(file_id)

        stats["classes"] = len(classes)
        stats["functions"] = len(functions)
        stats["imports"] = len(imports)

        # Count methods (sum from all classes)
        total_methods = 0
        for class_obj in classes:
            methods = self.get_class_methods(class_obj.id)
            total_methods += len(methods)
        stats["methods"] = total_methods

        # Count issues and usages
        issues = self.get_file_issues(file_id)
        usages = self.get_file_usages(file_id)

        stats["issues"] = len(issues)
        stats["usages"] = len(usages)

        return stats
