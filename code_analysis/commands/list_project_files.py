"""
Command for listing all files in a project.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.database import CodeDatabase  # noqa: F401

logger = logging.getLogger(__name__)


class ListProjectFilesCommand:
    """Command for listing all files in a project."""

    def __init__(
        self,
        database: "CodeDatabase",
        project_id: str,
        file_pattern: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ):
        """
        Initialize list project files command.

        Args:
            database: Database instance
            project_id: Project UUID
            file_pattern: Optional pattern to filter files (e.g., "*.py", "core/*")
            limit: Optional limit on number of results
            offset: Offset for pagination
        """
        self.database = database
        self.project_id = project_id
        self.file_pattern = file_pattern
        self.limit = limit
        self.offset = offset

    async def execute(self) -> Dict[str, Any]:
        """
        Execute file listing.

        Returns:
            Dictionary with list of files and metadata
        """
        try:
            assert self.database.conn is not None
            cursor = self.database.conn.cursor()
            
            # Build query
            query = """
                SELECT 
                    f.id,
                    f.path,
                    f.lines,
                    f.last_modified,
                    f.has_docstring,
                    f.created_at,
                    f.updated_at,
                    COUNT(DISTINCT c.id) as class_count,
                    COUNT(DISTINCT func.id) as function_count,
                    COUNT(DISTINCT m.id) as method_count,
                    COUNT(DISTINCT ch.id) as chunk_count,
                    CASE WHEN a.id IS NOT NULL THEN 1 ELSE 0 END as has_ast
                FROM files f
                LEFT JOIN classes c ON f.id = c.file_id
                LEFT JOIN functions func ON f.id = func.file_id
                LEFT JOIN methods m ON c.id = m.class_id
                LEFT JOIN code_chunks ch ON f.id = ch.file_id
                LEFT JOIN ast_trees a ON f.id = a.file_id
                WHERE f.project_id = ?
            """
            params = [self.project_id]
            
            # Add pattern filter if provided
            if self.file_pattern:
                if "*" in self.file_pattern:
                    # Convert glob pattern to SQL LIKE
                    like_pattern = self.file_pattern.replace("*", "%")
                    query += " AND f.path LIKE ?"
                    params.append(like_pattern)
                else:
                    # Exact match or substring
                    query += " AND f.path LIKE ?"
                    params.append(f"%{self.file_pattern}%")
            
            query += " GROUP BY f.id, f.path, f.lines, f.last_modified, f.has_docstring, f.created_at, f.updated_at, a.id"
            query += " ORDER BY f.path"
            
            # Add pagination
            if self.limit:
                query += " LIMIT ?"
                params.append(self.limit)
                if self.offset:
                    query += " OFFSET ?"
                    params.append(self.offset)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            files = []
            for row in rows:
                files.append({
                    "id": row["id"],
                    "path": row["path"],
                    "lines": row["lines"],
                    "last_modified": row["last_modified"],
                    "has_docstring": bool(row["has_docstring"]),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "class_count": row["class_count"],
                    "function_count": row["function_count"],
                    "method_count": row["method_count"],
                    "chunk_count": row["chunk_count"],
                    "has_ast": bool(row["has_ast"]),
                })
            
            # Get total count for pagination
            count_query = "SELECT COUNT(DISTINCT f.id) as total FROM files f WHERE f.project_id = ?"
            count_params = [self.project_id]
            if self.file_pattern:
                if "*" in self.file_pattern:
                    like_pattern = self.file_pattern.replace("*", "%")
                    count_query += " AND f.path LIKE ?"
                    count_params.append(like_pattern)
                else:
                    count_query += " AND f.path LIKE ?"
                    count_params.append(f"%{self.file_pattern}%")
            
            cursor.execute(count_query, count_params)
            total_count = cursor.fetchone()["total"]
            
            return {
                "success": True,
                "message": f"Found {len(files)} files",
                "total": total_count,
                "limit": self.limit,
                "offset": self.offset,
                "files": files,
            }
            
        except Exception as e:
            logger.error(f"Error listing project files: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Error listing project files: {e}",
                "error": str(e),
            }

