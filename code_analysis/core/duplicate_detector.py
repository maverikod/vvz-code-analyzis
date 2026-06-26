"""
Duplicate code detector using AST normalization and semantic vectors.

This module provides functionality to find duplicate code blocks
by combining AST normalization with semantic similarity using embeddings.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .duplicate_detector_ast_normalizer import ASTNormalizer
from .duplicate_detector_semantic import (
    find_duplicates_in_ast_hybrid_impl,
    find_semantic_duplicates_impl,
)

logger = logging.getLogger(__name__)

__all__ = ["ASTNormalizer", "DuplicateDetector"]


class DuplicateDetector:
    """
    Detector for duplicate code blocks using AST normalization and semantic vectors.

    Finds duplicate code by combining:
    1. AST normalization (variable names, literals) - for exact structural duplicates
    2. Semantic embeddings - for logically similar code with different structure
    3. Hash-based detection for fast exact matches
    4. Vector similarity for semantic similarity

    This hybrid approach finds both:
    - Exact duplicates (same structure, different variable names)
    - Semantic duplicates (similar logic, different implementation)
    """

    def __init__(
        self,
        min_lines: int = 5,
        min_similarity: float = 0.8,
        ignore_whitespace: bool = True,
        use_semantic: bool = True,
        semantic_threshold: float = 0.85,
    ) -> None:
        """
        Initialize duplicate detector.

        Args:
            min_lines: Minimum lines for duplicate block (default: 5).
            min_similarity: Minimum similarity threshold for AST (default: 0.8).
            ignore_whitespace: Ignore whitespace differences (default: True).
            use_semantic: Use semantic vectors for similarity (default: True).
            semantic_threshold: Minimum semantic similarity threshold (default: 0.85).
        """
        self.min_lines = min_lines
        self.min_similarity = min_similarity
        self.ignore_whitespace = ignore_whitespace
        self.use_semantic = use_semantic
        self.semantic_threshold = semantic_threshold
        self._svo_client_manager: Optional[Any] = None

    def normalize_ast(self, node: ast.AST) -> ast.AST:
        """
        Normalize AST node by replacing variable names and literals.

        Args:
            node: AST node to normalize.

        Returns:
            Normalized AST node.
        """
        normalizer = ASTNormalizer()
        normalized = normalizer.visit(ast.fix_missing_locations(node))
        return normalized

    def ast_to_hash(self, node: ast.AST) -> str:
        """
        Convert normalized AST to hash string.

        Args:
            node: Normalized AST node.

        Returns:
            SHA256 hash of AST structure.
        """
        # Convert AST to string representation
        ast_str = ast.dump(node, annotate_fields=False, include_attributes=False)
        # Compute hash
        return hashlib.sha256(ast_str.encode()).hexdigest()

    def count_lines(self, node: ast.AST) -> int:
        """
        Count approximate lines in AST node.

        Args:
            node: AST node.

        Returns:
            Approximate line count.
        """
        if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
            if node.end_lineno and node.lineno:
                return node.end_lineno - node.lineno + 1
        # Fallback: count nodes
        return len(list(ast.walk(node)))

    def find_duplicates_in_ast(
        self, tree: ast.AST, source_code: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Find duplicate code blocks in AST tree.

        Args:
            tree: AST tree to analyze.
            source_code: Optional source code for extracting snippets.

        Returns:
            List of duplicate groups with occurrences.
        """
        # Extract all function and method definitions
        functions: List[Tuple[ast.FunctionDef, Optional[str], Optional[str]]] = []
        classes: Dict[str, ast.ClassDef] = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes[node.name] = node
                # Extract methods
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        functions.append((item, node.name, "method"))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check if it's not a method
                is_method = False
                for class_node in classes.values():
                    if node in class_node.body:
                        is_method = True
                        break
                if not is_method:
                    functions.append((node, None, "function"))

        # Normalize and hash each function
        normalized_hashes: Dict[str, List[Tuple[ast.AST, str, Optional[str], str]]] = {}
        for func_node, class_name, func_type in functions:
            # Skip if too short
            line_count = self.count_lines(func_node)
            if line_count < self.min_lines:
                continue

            try:
                normalized = self.normalize_ast(func_node)
                hash_str = self.ast_to_hash(normalized)
                key = f"{func_type}:{hash_str}"

                if key not in normalized_hashes:
                    normalized_hashes[key] = []

                func_name = func_node.name
                normalized_hashes[key].append(
                    (func_node, func_name, class_name, func_type)
                )
            except Exception:
                # Skip functions that can't be normalized
                continue

        # Group duplicates (hash groups with size > 1)
        duplicate_groups: List[Dict[str, Any]] = []

        for hash_key, occurrences in normalized_hashes.items():
            if len(occurrences) > 1:
                # Extract code snippets
                group_occurrences: List[Dict[str, Any]] = []

                for func_node, func_name, class_name, func_type in occurrences:
                    start_line = func_node.lineno
                    end_line = (
                        getattr(func_node, "end_lineno", start_line) or start_line
                    )

                    code_snippet = ""
                    if source_code:
                        try:
                            lines = source_code.split("\n")
                            snippet_lines = lines[start_line - 1 : end_line]
                            code_snippet = "\n".join(snippet_lines)
                        except Exception:
                            pass

                    occurrence = {
                        "function_name": func_name,
                        "class_name": class_name,
                        "type": func_type,
                        "start_line": start_line,
                        "end_line": end_line,
                        "code_snippet": code_snippet,
                    }
                    group_occurrences.append(occurrence)

                duplicate_group = {
                    "hash": hash_key,
                    "similarity": 1.0,  # Exact match
                    "occurrences": group_occurrences,
                }
                duplicate_groups.append(duplicate_group)

        return duplicate_groups

    def find_duplicates_in_file(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Find duplicate code blocks in a file.

        Args:
            file_path: Path to Python file.

        Returns:
            List of duplicate groups with occurrences.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            source_code = f.read()

        try:
            tree = ast.parse(source_code, filename=file_path)
        except SyntaxError:
            return []

        return self.find_duplicates_in_ast(tree, source_code)

    def find_duplicates_in_code(
        self, source_code: str, file_path: str = "<string>"
    ) -> List[Dict[str, Any]]:
        """
        Find duplicate code blocks in source code string.

        Args:
            source_code: Python source code.
            file_path: Optional file path for context.

        Returns:
            List of duplicate groups with occurrences.
        """
        try:
            tree = ast.parse(source_code, filename=file_path)
        except SyntaxError:
            return []

        return self.find_duplicates_in_ast(tree, source_code)

    def calculate_similarity(self, node1: ast.AST, node2: ast.AST) -> float:
        """
        Calculate similarity between two AST nodes.

        Args:
            node1: First AST node.
            node2: Second AST node.

        Returns:
            Similarity score between 0.0 and 1.0.
        """
        # Normalize both nodes
        norm1 = self.normalize_ast(node1)
        norm2 = self.normalize_ast(node2)

        # Compare normalized structures
        hash1 = self.ast_to_hash(norm1)
        hash2 = self.ast_to_hash(norm2)

        if hash1 == hash2:
            return 1.0

        # Simple similarity: compare structure
        dump1 = ast.dump(norm1, annotate_fields=False, include_attributes=False)
        dump2 = ast.dump(norm2, annotate_fields=False, include_attributes=False)

        # Use edit distance for similarity
        return self._edit_distance_similarity(dump1, dump2)

    def _edit_distance_similarity(self, s1: str, s2: str) -> float:
        """
        Calculate similarity using edit distance.

        Args:
            s1: First string.
            s2: Second string.

        Returns:
            Similarity score between 0.0 and 1.0.
        """

        # Simple implementation using longest common subsequence
        def lcs_length(s1: str, s2: str) -> int:
            """Return lcs length."""
            m, n = len(s1), len(s2)
            dp = [[0] * (n + 1) for _ in range(m + 1)]

            for i in range(1, m + 1):
                for j in range(1, n + 1):
                    if s1[i - 1] == s2[j - 1]:
                        dp[i][j] = dp[i - 1][j - 1] + 1
                    else:
                        dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

            return dp[m][n]

        lcs = lcs_length(s1, s2)
        max_len = max(len(s1), len(s2))
        if max_len == 0:
            return 1.0
        return lcs / max_len

    def set_svo_client_manager(self, svo_client_manager: Any) -> None:
        """
        Set SVO client manager for semantic embeddings.

        Args:
            svo_client_manager: SVOClientManager instance for getting embeddings.
        """
        self._svo_client_manager = svo_client_manager

    async def find_semantic_duplicates(
        self,
        functions: List[Tuple[ast.AST, str, Optional[str], str]],
        source_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find semantically similar functions using embeddings.

        Args:
            functions: List of (func_node, func_name, class_name, func_type) tuples.
            source_code: Optional source code for extracting function text.

        Returns:
            List of duplicate groups with semantic similarity.
        """
        return await find_semantic_duplicates_impl(self, functions, source_code)

    async def find_duplicates_in_ast_hybrid(
        self, tree: ast.AST, source_code: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Find duplicates using both AST normalization and semantic similarity.

        Args:
            tree: AST tree to analyze.
            source_code: Optional source code for extracting snippets.

        Returns:
            List of duplicate groups with occurrences.
        """
        return await find_duplicates_in_ast_hybrid_impl(self, tree, source_code)
