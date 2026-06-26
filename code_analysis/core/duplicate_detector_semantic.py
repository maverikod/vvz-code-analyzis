"""
Semantic duplicate detection: embeddings and hybrid AST+semantic logic.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import logging
from typing import Any, Dict, List, Optional, Set, Tuple, cast

import numpy as np

logger = logging.getLogger(__name__)


async def get_function_embedding(
    detector: Any,
    func_node: ast.AST,
    source_code: Optional[str] = None,
) -> Optional[np.ndarray]:
    """
    Get embedding for a function using semantic service.

    Args:
        detector: DuplicateDetector instance (use_semantic, _svo_client_manager).
        func_node: AST function node.
        source_code: Optional source code for extracting function text.

    Returns:
        Embedding vector or None if unavailable.
    """
    if not getattr(detector, "use_semantic", True) or not getattr(
        detector, "_svo_client_manager", None
    ):
        return None

    try:
        if source_code and hasattr(func_node, "lineno"):
            start_line = func_node.lineno
            end_line = getattr(func_node, "end_lineno", start_line) or start_line
            lines = source_code.split("\n")
            func_code = "\n".join(lines[start_line - 1 : end_line])
        else:
            func_code = ast.dump(func_node)

        class FunctionChunk:
            """Represent FunctionChunk."""

            def __init__(self: "FunctionChunk", text: str) -> None:
                """Initialize the instance."""
                self.body = text
                self.text = text

        chunk = FunctionChunk(func_code)
        svo = detector._svo_client_manager
        chunks_with_emb = await svo.get_embeddings([chunk])

        if chunks_with_emb and hasattr(chunks_with_emb[0], "embedding"):
            embedding = getattr(chunks_with_emb[0], "embedding")
            embedding_array = np.array(embedding, dtype="float32")
            norm = float(np.linalg.norm(embedding_array))
            if norm > 0:
                embedding_array = embedding_array / norm
            return embedding_array
    except Exception as e:
        logger.debug("Failed to get embedding for function: %s", e)
    return None


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Cosine similarity between two normalized vectors."""
    return float(np.dot(vec1, vec2))


async def find_semantic_duplicates_impl(
    detector: Any,
    functions: List[Tuple[ast.AST, str, Optional[str], str]],
    source_code: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Find semantically similar functions using embeddings.

    Args:
        detector: DuplicateDetector instance.
        functions: List of (func_node, func_name, class_name, func_type).
        source_code: Optional source code.

    Returns:
        List of duplicate groups with semantic similarity.
    """
    if not getattr(detector, "use_semantic", True) or not getattr(
        detector, "_svo_client_manager", None
    ):
        return []

    function_embeddings: Dict[int, Tuple[np.ndarray, Tuple]] = {}
    for idx, (func_node, func_name, class_name, func_type) in enumerate(functions):
        embedding = await get_function_embedding(detector, func_node, source_code)
        if embedding is not None:
            function_embeddings[idx] = (
                embedding,
                (func_node, func_name, class_name, func_type),
            )

    duplicate_groups: Dict[str, Dict[str, Any]] = {}
    indices = list(function_embeddings.keys())
    semantic_threshold = getattr(detector, "semantic_threshold", 0.85)

    for i in range(len(indices)):
        for j in range(i + 1, len(indices)):
            idx1, idx2 = indices[i], indices[j]
            emb1, func1_data = function_embeddings[idx1]
            emb2, func2_data = function_embeddings[idx2]

            sim = cosine_similarity(emb1, emb2)
            if sim < semantic_threshold:
                continue

            group_key = f"semantic_{idx1}_{idx2}"
            if group_key not in duplicate_groups:
                duplicate_groups[group_key] = {
                    "hash": group_key,
                    "similarity": sim,
                    "occurrences": [],
                }

            func_node1, func_name1, class_name1, func_type1 = func1_data
            func_node2, func_name2, class_name2, func_type2 = func2_data

            existing_names = {
                (occ["function_name"], occ.get("class_name"))
                for occ in duplicate_groups[group_key]["occurrences"]
            }

            def add_occurrence(
                func_node: ast.AST,
                func_name: str,
                class_name: Optional[str],
                func_type: str,
            ) -> None:
                """Return add occurrence."""
                if (func_name, class_name) in existing_names:
                    return
                start_line = getattr(func_node, "lineno", 0) or 0
                end_line = getattr(func_node, "end_lineno", start_line) or start_line
                code_snippet = ""
                if source_code:
                    try:
                        lines = source_code.split("\n")
                        code_snippet = "\n".join(lines[start_line - 1 : end_line])
                    except Exception:
                        pass
                duplicate_groups[group_key]["occurrences"].append(
                    {
                        "function_name": func_name,
                        "class_name": class_name,
                        "type": func_type,
                        "start_line": start_line,
                        "end_line": end_line,
                        "code_snippet": code_snippet,
                    }
                )
                existing_names.add((func_name, class_name))

            add_occurrence(func_node1, func_name1, class_name1, func_type1)
            add_occurrence(func_node2, func_name2, class_name2, func_type2)

    return list(duplicate_groups.values())


async def find_duplicates_in_ast_hybrid_impl(
    detector: Any,
    tree: ast.AST,
    source_code: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Find duplicates using both AST normalization and semantic similarity.

    Args:
        detector: DuplicateDetector instance.
        tree: AST tree to analyze.
        source_code: Optional source code.

    Returns:
        List of duplicate groups.
    """
    ast_duplicates = detector.find_duplicates_in_ast(tree, source_code)

    functions: List[Tuple[ast.AST, str, Optional[str], str]] = []
    classes: Dict[str, ast.ClassDef] = {}
    min_lines = getattr(detector, "min_lines", 5)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes[node.name] = node
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if detector.count_lines(item) >= min_lines:
                        functions.append((item, item.name, node.name, "method"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_method = any(node in c.body for c in classes.values())
            if not is_method and detector.count_lines(node) >= min_lines:
                functions.append((node, node.name, None, "function"))

    semantic_duplicates = await find_semantic_duplicates_impl(
        detector, functions, source_code
    )

    all_groups = ast_duplicates.copy()
    seen_occurrences: Set[Tuple[str, Optional[str], int]] = set()

    for group in ast_duplicates:
        for occ in group["occurrences"]:
            key = (
                occ["function_name"],
                occ.get("class_name"),
                occ["start_line"],
            )
            seen_occurrences.add(key)

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

    return cast(List[Dict[str, Any]], all_groups)
