"""
API layer for code analysis library.

This module provides high-level API for using code analysis as a library.
Designed for integration with MCP servers and other applications.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path
from typing import Dict, List, Any, Optional, TYPE_CHECKING

from ..core import CodeDatabase
from ..commands import AnalyzeCommand, SearchCommand, IssuesCommand, RefactorCommand
from ..commands.semantic_search import SemanticSearchCommand

if TYPE_CHECKING:
    from ..core.svo_client_manager import SVOClientManager
    from ..core.faiss_manager import FaissIndexManager


class CodeAnalysisAPI:
    """
    High-level API for code analysis operations.

    This class provides a clean interface for using code analysis
    functionality programmatically.
    """

    def __init__(
        self,
        root_path: str,
        db_path: Optional[Path] = None,
        max_lines: int = 400,
        comment: Optional[str] = None,
        svo_client_manager: Optional["SVOClientManager"] = None,
        faiss_manager: Optional["FaissIndexManager"] = None,
    ):
        """
        Initialize code analysis API.

        Args:
            root_path: Root directory of the project to analyze
            db_path: Path to SQLite database (optional)
            max_lines: Maximum lines per file
            comment: Optional human-readable comment/identifier for project
            svo_client_manager: SVO client manager for chunking and embedding
            faiss_manager: FAISS index manager for vector storage
        """
        self.root_path = Path(root_path).resolve()
        self.max_lines = max_lines

        # Initialize database
        if db_path:
            self.db_path = Path(db_path)
        else:
            # Default: use data directory in project root
            data_dir = self.root_path / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = data_dir / "code_analysis.db"

        self.database = CodeDatabase(self.db_path)
        self.project_id = self.database.get_or_create_project(
            str(self.root_path), name=self.root_path.name, comment=comment
        )
        self.svo_client_manager = svo_client_manager
        self.faiss_manager = faiss_manager

        # Initialize command instances (will be created with force parameter when needed)
        self.max_lines = max_lines
        self.search_cmd = SearchCommand(self.database, self.project_id)
        self.issues_cmd = IssuesCommand(self.database, self.project_id)
        self.refactor_cmd = RefactorCommand(self.project_id)
        self.semantic_search_cmd = SemanticSearchCommand(
            self.database, self.project_id, faiss_manager, svo_client_manager
        )

    async def analyze_project(self, force: bool = False) -> Dict[str, Any]:
        """
        Analyze entire project.

        Args:
            force: If True, process all files regardless of modification time

        Returns:
            Dictionary with analysis results
        """
        analyze_cmd = AnalyzeCommand(
            self.database,
            self.project_id,
            str(self.root_path),
            self.max_lines,
            force,
            svo_client_manager=self.svo_client_manager,
            faiss_manager=self.faiss_manager,
        )
        return await analyze_cmd.execute()

    async def find_usages(
        self,
        name: str,
        target_type: Optional[str] = None,
        target_class: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find all usages of a method or property.

        Args:
            name: Name of method/property
            target_type: Filter by type (method, property)
            target_class: Filter by class name

        Returns:
            List of usage records
        """
        return self.search_cmd.find_usages(name, target_type, target_class)

    async def full_text_search(
        self, query: str, entity_type: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Perform full-text search in code.

        Args:
            query: Search query
            entity_type: Filter by entity type
            limit: Maximum results

        Returns:
            List of matching records
        """
        return self.search_cmd.full_text_search(query, entity_type, limit)

    async def search_classes(
        self, pattern: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search classes by name pattern.

        Args:
            pattern: Name pattern (optional)

        Returns:
            List of class records
        """
        return self.search_cmd.search_classes(pattern)

    async def search_methods(
        self, pattern: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search methods by name pattern.

        Args:
            pattern: Name pattern (optional)

        Returns:
            List of method records
        """
        return self.search_cmd.search_methods(pattern)

    async def get_issues(
        self, issue_type: Optional[str] = None
    ) -> Dict[str, Any] | List[Dict[str, Any]]:
        """
        Get issues from database.

        Args:
            issue_type: Filter by issue type (optional)

        Returns:
            Dictionary of issues grouped by type, or a list if issue_type is specified
        """
        return await self.issues_cmd.get_issues(issue_type)

    async def split_class(
        self, file_path: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Split a class into multiple smaller classes.

        Args:
            file_path: Path to Python file
            config: Split configuration

        Returns:
            Dictionary with success status and message
        """
        return await self.refactor_cmd.split_class(
            str(self.root_path), file_path, config
        )

    async def extract_superclass(
        self, file_path: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract common functionality into base class.

        Args:
            file_path: Path to Python file
            config: Extraction configuration

        Returns:
            Dictionary with success status and message
        """
        return await self.refactor_cmd.extract_superclass(
            str(self.root_path), file_path, config
        )

    async def merge_classes(
        self, file_path: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge multiple classes into a single base class.

        Args:
            file_path: Path to Python file
            config: Merge configuration

        Returns:
            Dictionary with success status and message
        """
        return await self.refactor_cmd.merge_classes(
            str(self.root_path), file_path, config
        )

    async def semantic_search(
        self,
        query: str,
        k: int = 10,
        max_distance: Optional[float] = None,
        include_ast_node: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search using vector embeddings.

        Args:
            query: Text query to search for
            k: Number of results to return (default: 10)
            max_distance: Maximum distance threshold (optional)
            include_ast_node: If True, include full AST node JSON (default: False)

        Returns:
            List of search results with AST node information and context
        """
        return await self.semantic_search_cmd.search(
            query, k=k, max_distance=max_distance, include_ast_node=include_ast_node
        )

    def close(self) -> None:
        """Close database connection."""
        if self.database:
            self.database.close()


__all__ = ["CodeAnalysisAPI"]
