"""
Analyze command implementation.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import logging
from pathlib import Path
from typing import Dict, Any

from ..core import CodeAnalyzer, CodeDatabase, IssueDetector

logger = logging.getLogger(__name__)


class AnalyzeCommand:
    """Command for analyzing Python projects."""

    def __init__(
        self,
        database: CodeDatabase,
        project_id: str,
        root_path: str,
        max_lines: int = 400,
        force: bool = False,
    ):
        """
        Initialize analyze command.

        Args:
            database: Database instance
            project_id: Project UUID
            root_path: Root directory path
            max_lines: Maximum lines per file
        """
        self.database = database
        self.project_id = project_id
        self.root_path = Path(root_path).resolve()
        self.max_lines = max_lines
        self.force = force

        # Initialize analyzer
        output_dir = self.root_path / "code_analysis"
        self.analyzer = CodeAnalyzer(
            str(self.root_path),
            str(output_dir),
            max_lines,
            database=self.database,
        )
        self.issue_detector = IssueDetector(
            self.analyzer.issues, self.root_path, database=self.database
        )
        self.analyzer.issue_detector = self.issue_detector

    async def execute(self) -> Dict[str, Any]:
        """
        Execute project analysis.

        Returns:
            Dictionary with analysis results
        """
        import os

        logger.info(f"Analyzing project: {self.root_path}")

        # Clear all existing data for this project before analysis
        logger.info(f"Clearing existing data for project: {self.project_id}")
        await self.database.clear_project_data(self.project_id)

        for root, dirs, files in os.walk(self.root_path):
            # Skip certain directories
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".")
                and d not in ["__pycache__", "node_modules", ".venv", "venv"]
            ]

            for file in files:
                if file.endswith(".py"):
                    file_path = Path(root) / file
                    await self.analyzer.analyze_file(file_path, force=self.force)

        # Get statistics from database for this project
        assert self.database.conn is not None
        cursor = self.database.conn.cursor()
        
        cursor.execute(
            "SELECT COUNT(*) FROM files WHERE project_id = ?", (self.project_id,)
        )
        files_count = cursor.fetchone()[0]
        
        cursor.execute(
            """
            SELECT COUNT(*) FROM classes c
            INNER JOIN files f ON c.file_id = f.id
            WHERE f.project_id = ?
            """,
            (self.project_id,),
        )
        classes_count = cursor.fetchone()[0]
        
        cursor.execute(
            """
            SELECT COUNT(*) FROM functions func
            INNER JOIN files f ON func.file_id = f.id
            WHERE f.project_id = ?
            """,
            (self.project_id,),
        )
        functions_count = cursor.fetchone()[0]
        
        cursor.execute(
            "SELECT COUNT(*) FROM issues WHERE project_id = ?", (self.project_id,)
        )
        issues_count = cursor.fetchone()[0]

        result = {
            "files_analyzed": files_count,
            "classes": classes_count,
            "functions": functions_count,
            "issues": issues_count,
            "project_id": self.project_id,
        }

        logger.info(
            f"Analysis complete: {result['files_analyzed']} files, "
            f"{result['classes']} classes, {result['functions']} functions"
        )

        return result
