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
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class ASTNormalizer(ast.NodeTransformer):
    """
    AST node transformer that normalizes code structure.

    Normalizes:
    - Variable names -> _VAR_, _VAR2_, etc.
    - String literals -> _STR_
    - Numeric literals -> _NUM_
    - Preserves structure (if/for/while/call)
    """

    def __init__(self) -> None:
        """Initialize normalizer."""
        self._var_counter = 0
        self._var_map: Dict[str, str] = {}
        self._str_counter = 0
        self._num_counter = 0

    def _get_var_name(self, name: str) -> str:
        """Get normalized variable name."""
        if name not in self._var_map:
            self._var_counter += 1
            self._var_map[name] = f"_VAR{self._var_counter}_"
        return self._var_map[name]

    def visit_Name(self, node: ast.Name) -> ast.Name:
        """Normalize variable names."""
        # Don't normalize builtins, constants, etc.
        if node.id in ("True", "False", "None", "self", "cls"):
            return node
        normalized_id = self._get_var_name(node.id)
        return ast.Name(id=normalized_id, ctx=node.ctx)

    def visit_Attribute(self, node: ast.Attribute) -> ast.Attribute:
        """Normalize attribute access (keep structure, normalize value if needed)."""
        value = self.visit(node.value)
        # Keep attribute names as-is for structure (method names, etc.)
        return ast.Attribute(value=value, attr=node.attr, ctx=node.ctx)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """Normalize function definition (normalize name and arguments)."""
        # Normalize function name
        normalized_name = self._get_var_name(node.name)
        # Normalize arguments
        args = self.visit(node.args)
        # Normalize body and decorators
        body = [self.visit(stmt) for stmt in node.body]
        decorator_list = [self.visit(dec) for dec in node.decorator_list]
        return ast.FunctionDef(
            name=normalized_name,
            args=args,
            body=body,
            decorator_list=decorator_list,
            returns=self.visit(node.returns) if node.returns else None,
        )

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> ast.AsyncFunctionDef:
        """Normalize async function definition."""
        normalized_name = self._get_var_name(node.name)
        args = self.visit(node.args)
        body = [self.visit(stmt) for stmt in node.body]
        decorator_list = [self.visit(dec) for dec in node.decorator_list]
        return ast.AsyncFunctionDef(
            name=normalized_name,
            args=args,
            body=body,
            decorator_list=decorator_list,
            returns=self.visit(node.returns) if node.returns else None,
        )

    def visit_arguments(self, node: ast.arguments) -> ast.arguments:
        """Normalize function arguments."""
        # Normalize all argument names
        posonlyargs = [self._normalize_arg(arg) for arg in node.posonlyargs]
        args = [self._normalize_arg(arg) for arg in node.args]
        kwonlyargs = [self._normalize_arg(arg) for arg in node.kwonlyargs]
        # Normalize defaults
        defaults = [self.visit(default) for default in node.defaults]
        kw_defaults = [
            self.visit(default) if default else None for default in node.kw_defaults
        ]
        return ast.arguments(
            posonlyargs=posonlyargs,
            args=args,
            vararg=self._normalize_arg(node.vararg) if node.vararg else None,
            kwonlyargs=kwonlyargs,
            kwarg=self._normalize_arg(node.kwarg) if node.kwarg else None,
            defaults=defaults,
            kw_defaults=kw_defaults,
        )

    def _normalize_arg(self, arg: ast.arg) -> ast.arg:
        """Normalize function argument."""
        normalized_id = self._get_var_name(arg.arg)
        return ast.arg(
            arg=normalized_id,
            annotation=self.visit(arg.annotation) if arg.annotation else None,
        )

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        """Normalize constants (strings and numbers)."""
        if isinstance(node.value, str):
            self._str_counter += 1
            return ast.Constant(value="_STR_", kind=node.kind)
        elif isinstance(node.value, (int, float, complex)):
            self._num_counter += 1
            return ast.Constant(value="_NUM_", kind=node.kind)
        elif isinstance(node.value, bool):
            # Keep boolean values
            return node
        elif node.value is None:
            # Keep None
            return node
        else:
            # Other constants (bytes, etc.)
            self._str_counter += 1
            return ast.Constant(value="_STR_", kind=node.kind)

    def visit_Str(self, node: ast.Str) -> ast.Constant:
        """Normalize string literals (Python < 3.8 compatibility)."""
        self._str_counter += 1
        return ast.Constant(value="_STR_")

    def visit_Num(self, node: ast.Num) -> ast.Constant:
        """Normalize numeric literals (Python < 3.8 compatibility)."""
        self._num_counter += 1
        return ast.Constant(value="_NUM_")

    def visit_List(self, node: ast.List) -> ast.List:
        """Normalize list literals."""
        elts = [self.visit(elt) for elt in node.elts]
        return ast.List(elts=elts, ctx=node.ctx)

    def visit_Dict(self, node: ast.Dict) -> ast.Dict:
        """Normalize dict literals."""
        keys = [self.visit(key) if key else None for key in node.keys]
        values = [self.visit(value) for value in node.values]
        return ast.Dict(keys=keys, values=values)

    def visit_Tuple(self, node: ast.Tuple) -> ast.Tuple:
        """Normalize tuple literals."""
        elts = [self.visit(elt) for elt in node.elts]
        return ast.Tuple(elts=elts, ctx=node.ctx)


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

    async def _get_function_embedding(
        self, func_node: ast.AST, source_code: Optional[str] = None
    ) -> Optional[np.ndarray]:
        """
        Get embedding for a function using semantic service.

        Args:
            func_node: AST function node.
            source_code: Optional source code for extracting function text.

        Returns:
            Embedding vector or None if unavailable.
        """
        if not self.use_semantic or not self._svo_client_manager:
            return None

        try:
            # Extract function code
            if source_code and hasattr(func_node, "lineno"):
                start_line = func_node.lineno
                end_line = getattr(func_node, "end_lineno", start_line) or start_line
                lines = source_code.split("\n")
                func_code = "\n".join(lines[start_line - 1 : end_line])
            else:
                # Fallback: use AST dump
                func_code = ast.dump(func_node)

            # Create chunk object for embedding
            class FunctionChunk:
                def __init__(self, text: str):
                    self.body = text
                    self.text = text

            chunk = FunctionChunk(func_code)
            chunks_with_emb = await self._svo_client_manager.get_embeddings([chunk])

            if chunks_with_emb and hasattr(chunks_with_emb[0], "embedding"):
                embedding = getattr(chunks_with_emb[0], "embedding")
                embedding_array = np.array(embedding, dtype="float32")
                # Normalize vector
                norm = float(np.linalg.norm(embedding_array))
                if norm > 0:
                    embedding_array = embedding_array / norm
                return embedding_array
        except Exception as e:
            logger.debug(f"Failed to get embedding for function: {e}")
            return None

        return None

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two vectors.

        Args:
            vec1: First normalized vector.
            vec2: Second normalized vector.

        Returns:
            Cosine similarity between 0.0 and 1.0.
        """
        return float(np.dot(vec1, vec2))

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
        if not self.use_semantic or not self._svo_client_manager:
            return []

        # Get embeddings for all functions
        function_embeddings: Dict[int, Tuple[np.ndarray, Tuple]] = {}
        for idx, (func_node, func_name, class_name, func_type) in enumerate(functions):
            embedding = await self._get_function_embedding(func_node, source_code)
            if embedding is not None:
                function_embeddings[idx] = (
                    embedding,
                    (func_node, func_name, class_name, func_type),
                )

        # Find similar pairs
        duplicate_groups: Dict[str, Dict[str, Any]] = {}
        indices = list(function_embeddings.keys())

        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                idx1, idx2 = indices[i], indices[j]
                emb1, func1_data = function_embeddings[idx1]
                emb2, func2_data = function_embeddings[idx2]

                similarity = self._cosine_similarity(emb1, emb2)

                if similarity >= self.semantic_threshold:
                    # Create or update duplicate group
                    group_key = f"semantic_{idx1}_{idx2}"
                    if group_key not in duplicate_groups:
                        duplicate_groups[group_key] = {
                            "hash": group_key,
                            "similarity": similarity,
                            "occurrences": [],
                        }

                    # Add both functions to group
                    func_node1, func_name1, class_name1, func_type1 = func1_data
                    func_node2, func_name2, class_name2, func_type2 = func2_data

                    # Check if already added
                    existing_names = {
                        (occ["function_name"], occ.get("class_name"))
                        for occ in duplicate_groups[group_key]["occurrences"]
                    }

                    if (func_name1, class_name1) not in existing_names:
                        start_line1 = func_node1.lineno
                        end_line1 = (
                            getattr(func_node1, "end_lineno", start_line1)
                            or start_line1
                        )
                        code_snippet1 = ""
                        if source_code:
                            try:
                                lines = source_code.split("\n")
                                code_snippet1 = "\n".join(
                                    lines[start_line1 - 1 : end_line1]
                                )
                            except Exception:
                                pass

                        duplicate_groups[group_key]["occurrences"].append(
                            {
                                "function_name": func_name1,
                                "class_name": class_name1,
                                "type": func_type1,
                                "start_line": start_line1,
                                "end_line": end_line1,
                                "code_snippet": code_snippet1,
                            }
                        )

                    if (func_name2, class_name2) not in existing_names:
                        start_line2 = func_node2.lineno
                        end_line2 = (
                            getattr(func_node2, "end_lineno", start_line2)
                            or start_line2
                        )
                        code_snippet2 = ""
                        if source_code:
                            try:
                                lines = source_code.split("\n")
                                code_snippet2 = "\n".join(
                                    lines[start_line2 - 1 : end_line2]
                                )
                            except Exception:
                                pass

                        duplicate_groups[group_key]["occurrences"].append(
                            {
                                "function_name": func_name2,
                                "class_name": class_name2,
                                "type": func_type2,
                                "start_line": start_line2,
                                "end_line": end_line2,
                                "code_snippet": code_snippet2,
                            }
                        )

        return list(duplicate_groups.values())

    async def find_duplicates_in_ast_hybrid(
        self, tree: ast.AST, source_code: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Find duplicates using both AST normalization and semantic similarity.

        Combines:
        1. AST-based exact duplicates (same structure, different names)
        2. Semantic duplicates (similar logic, different implementation)

        Args:
            tree: AST tree to analyze.
            source_code: Optional source code for extracting snippets.

        Returns:
            List of duplicate groups with occurrences.
        """
        # First, find AST-based duplicates
        ast_duplicates = self.find_duplicates_in_ast(tree, source_code)

        # Extract all functions for semantic analysis
        functions: List[Tuple[ast.FunctionDef, Optional[str], Optional[str]]] = []
        classes: Dict[str, ast.ClassDef] = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes[node.name] = node
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        line_count = self.count_lines(item)
                        if line_count >= self.min_lines:
                            functions.append((item, node.name, "method"))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                is_method = False
                for class_node in classes.values():
                    if node in class_node.body:
                        is_method = True
                        break
                if not is_method:
                    line_count = self.count_lines(node)
                    if line_count >= self.min_lines:
                        functions.append((node, None, "function"))

        # Find semantic duplicates
        semantic_duplicates = await self.find_semantic_duplicates(
            functions, source_code
        )

        # Merge results (avoid duplicates)
        all_groups = ast_duplicates.copy()
        seen_occurrences: Set[Tuple[str, Optional[str], int]] = set()

        # Track AST duplicates
        for group in ast_duplicates:
            for occ in group["occurrences"]:
                key = (
                    occ["function_name"],
                    occ.get("class_name"),
                    occ["start_line"],
                )
                seen_occurrences.add(key)

        # Add semantic duplicates that aren't already found
        for group in semantic_duplicates:
            new_occurrences = []
            for occ in group["occurrences"]:
                key = (
                    occ["function_name"],
                    occ.get("class_name"),
                    occ["start_line"],
                )
                if key not in seen_occurrences:
                    new_occurrences.append(occ)
                    seen_occurrences.add(key)

            if len(new_occurrences) >= 2:
                all_groups.append(
                    {
                        "hash": group["hash"],
                        "similarity": group["similarity"],
                        "occurrences": new_occurrences,
                    }
                )

        return all_groups
