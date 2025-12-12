#!/usr/bin/env python3
"""
Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com

Code mapper for BHLFF project.

This script analyzes the codebase and generates a comprehensive
code map with method signatures, class hierarchies, and dependencies.
"""

import os
import argparse
from pathlib import Path
import logging

# Import from separate modules
from .core.analyzer import CodeAnalyzer
from .core.issue_detector import IssueDetector
from .core.reporter import CodeReporter
from .core.database import CodeDatabase

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CodeMapper:
    """Main code mapper class."""

    def __init__(
        self,
        root_dir: str = ".",
        output_dir: str = "code_analysis",
        max_lines: int = 400,
        use_sqlite: bool = True,
    ):
        """Initialize code mapper."""
        self.output_dir = Path(output_dir)
        self.use_sqlite = use_sqlite

        # Initialize database if using SQLite
        self.database = None
        self.project_id = None
        if use_sqlite:
            db_path = self.output_dir / "code_analysis.db"
            self.database = CodeDatabase(db_path)
            # Get or create project
            root_path = Path(root_dir).resolve()
            self.project_id = self.database.get_or_create_project(
                str(root_path), name=root_path.name
            )

        self.analyzer = CodeAnalyzer(
            root_dir, output_dir, max_lines, database=self.database
        )
        self.issue_detector = IssueDetector(
            self.analyzer.issues, self.analyzer.root_dir, database=self.database
        )
        self.analyzer.issue_detector = self.issue_detector
        self.reporter = CodeReporter(self.analyzer.output_dir, use_sqlite=use_sqlite)

    def analyze_directory(self, directory: str = ".") -> None:
        """Analyze entire directory."""
        print(f"INFO:__main__:Сканирование директории: {directory}")

        for root, dirs, files in os.walk(directory):
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
                    print(f"INFO:__main__:Анализ файла: {file_path}")
                    self.analyzer.analyze_file(file_path)

    def generate_reports(self) -> None:
        """Generate all reports."""
        self.reporter.generate_code_map(self.analyzer.code_map)
        self.reporter.generate_issues_report(self.analyzer.issues)
        self.reporter.generate_method_index(self.analyzer.code_map)
        self.reporter.print_summary(self.analyzer.issues, self.analyzer.max_lines)
        # Close database connection
        if self.database:
            self.database.close()


def main() -> None:
    """Main function."""
    parser = argparse.ArgumentParser(description="Analyze Python codebase")
    parser.add_argument("--root-dir", default=".", help="Root directory to analyze")
    parser.add_argument(
        "--output-dir", default="code_analysis", help="Output directory for reports"
    )
    parser.add_argument(
        "--max-lines", type=int, default=400, help="Maximum lines per file"
    )

    args = parser.parse_args()

    mapper = CodeMapper(args.root_dir, args.output_dir, args.max_lines)
    mapper.analyze_directory(args.root_dir)
    mapper.generate_reports()


if __name__ == "__main__":
    main()
