"""
Module base.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import ast
from pathlib import Path
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..usage_analyzer import UsageAnalyzer

if TYPE_CHECKING:
    from ..faiss_manager import FaissIndexManager
    from ..svo_client_manager import SVOClientManager

logger = logging.getLogger(__name__)


class CodeAnalyzer:
    """Core code analyzer functionality."""

    def __init__(
        self,
        root_dir: str = ".",
        output_dir: str = "code_analysis",
        max_lines: int = 400,
        issue_detector=None,
        database=None,
        svo_client_manager: Optional["SVOClientManager"] = None,
        faiss_manager: Optional["FaissIndexManager"] = None,
    ):
        """Initialize code analyzer."""
        self.root_dir = Path(root_dir)
        self.output_dir = Path(output_dir)
        self.max_lines = max_lines
        self.issue_detector = issue_detector
        self.database = database
        self.svo_client_manager = svo_client_manager
        self.faiss_manager = faiss_manager
        self.usage_analyzer = UsageAnalyzer(database) if database else None

        # Initialize docstring chunker if SVO client manager provided
        self.docstring_chunker = None
        if database and svo_client_manager:
            from ..docstring_chunker import DocstringChunker

            # Get min_chunk_length from config if available
            min_chunk_length = 30  # default
            if hasattr(svo_client_manager, "config") and svo_client_manager.config:
                min_chunk_length = getattr(
                    svo_client_manager.config, "min_chunk_length", 30
                )
            self.docstring_chunker = DocstringChunker(
                database=database,
                svo_client_manager=svo_client_manager,
                faiss_manager=faiss_manager,
                min_chunk_length=min_chunk_length,
            )

        # Create output directory if it doesn't exist
        self.output_dir.mkdir(exist_ok=True)

        # Keep code_map for backward compatibility (YAML mode)
        self.code_map: Dict[str, Any] = {
            "files": {},
            "classes": {},
            "functions": {},
            "imports": {},
            "dependencies": {},
        }
        # Issues tracking (for backward compatibility)
        self.issues: Dict[str, List[Any]] = {
            "methods_with_pass": [],
            "not_implemented_in_non_abstract": [],
            "methods_without_docstrings": [],
            "files_without_docstrings": [],
            "classes_without_docstrings": [],
            "files_too_large": [],
            "any_type_usage": [],
            "generic_exception_usage": [],
            "imports_in_middle": [],
            "invalid_imports": [],
        }

    def analyze_file(self, file_path: Path, force: bool = False) -> None:
        """
        Analyze a single Python file (synchronous API).

        This method exists for backward compatibility with older code and tests.
        In async contexts, use `await analyze_file_async(...)`.
        """
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.analyze_file_async(file_path, force=force))
            return
        raise RuntimeError(
            "CodeAnalyzer.analyze_file() cannot be used inside a running event loop. "
            "Use `await analyze_file_async(...)`."
        )

    async def analyze_file_async(self, file_path: Path, force: bool = False) -> None:
        """
        Analyze a single Python file.

        Args:
            file_path: Path to Python file
            force: If True, process file regardless of modification time
        """
        logger.info(f"📄 Analyzing file: {file_path}")
        try:
            file_path_str = str(file_path)
            file_stat = file_path.stat()
            last_modified = file_stat.st_mtime

            logger.debug(
                f"   File size: {file_stat.st_size} bytes, mtime: {last_modified}"
            )
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            logger.debug(
                f"   Content length: {len(content)} chars, lines: {len(content.splitlines())}"
            )
            tree = ast.parse(content)
            logger.debug("   AST parsed successfully")

            # Check file size
            lines = content.split("\n")
            line_count = len(lines)
            has_docstring = self._has_file_docstring(tree)

            # Save file to database if using SQLite
            file_id = None
            project_id = None
            if self.database:
                # Get or create project
                project_id = self.database.get_or_create_project(
                    str(self.root_dir), name=self.root_dir.name
                )
                file_id = self.database.add_file(
                    file_path_str, line_count, last_modified, has_docstring, project_id
                )
                # IMPORTANT:
                # Keep DB consistent on re-analysis by clearing stale per-file data first.
                # Otherwise removed/renamed methods/classes remain in DB forever.
                try:
                    if force or self.database.is_ast_outdated(file_id, last_modified):
                        self.database.clear_file_data(file_id)
                except Exception as e:
                    logger.warning(
                        "Failed to clear stale file data for %s (continuing): %s",
                        file_path_str,
                        e,
                    )

            # Check file size
            if line_count > self.max_lines:
                issue_data = {
                    "file": file_path_str,
                    "lines": line_count,
                    "limit": self.max_lines,
                    "exceeds_limit": line_count - self.max_lines,
                }
                self.issues["files_too_large"].append(issue_data)

                if self.database and file_id:
                    self.database.add_issue(
                        "files_too_large",
                        f"File exceeds line limit: {line_count} > {self.max_lines}",
                        line=None,
                        file_id=file_id,
                        metadata=issue_data,
                    )

            # Check for file docstring
            if not has_docstring:
                self.issues["files_without_docstrings"].append(file_path_str)
                if self.database and file_id:
                    self.database.add_issue(
                        "files_without_docstrings",
                        "File missing docstring",
                        line=None,
                        file_id=file_id,
                    )

            # Analyze AST
            logger.debug("   Analyzing AST structure...")
            self._analyze_ast(tree, file_path, file_id)
            logger.debug("   AST analysis completed")

            # Save AST tree to database
            if self.database and file_id:
                logger.debug("   Saving AST tree to database...")
                ast_saved = await self._save_ast_tree(
                    tree, file_id, project_id, last_modified, force=force
                )
                if ast_saved:
                    logger.debug("   ✅ AST tree saved to database")
                else:
                    logger.debug("   ⏭️  AST tree skipped (up to date)")

            # Analyze usages (method calls, attribute accesses)
            if self.usage_analyzer and file_id:
                logger.debug("   Analyzing usages...")
                self.usage_analyzer.analyze_file(file_path, file_id)

            # IMPORTANT:
            # Chunking/vectorization is handled by the background vectorization worker.
            # Analyzer must not call external services.
            logger.debug("   ⏭️  Docstring chunking skipped (handled by worker)")

            logger.info(f"✅ File analysis completed: {file_path}")

        except (OSError, IOError, ValueError, SyntaxError, UnicodeDecodeError) as e:
            logger.error(f"Error analyzing file {file_path}: {e}")

    def _get_file_content(self, file_path: Path) -> str:
        """Get file content for AST source segment extraction."""
        if not hasattr(self, "_file_content_cache"):
            self._file_content_cache = {}

        file_path_str = str(file_path)
        if file_path_str not in self._file_content_cache:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self._file_content_cache[file_path_str] = f.read()
            except Exception:
                self._file_content_cache[file_path_str] = ""

        return self._file_content_cache[file_path_str]
