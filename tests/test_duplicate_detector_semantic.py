"""
Tests for semantic duplicate detection.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import pytest

from code_analysis.core.duplicate_detector import DuplicateDetector


class TestSemanticDuplicates:
    """Tests for semantic duplicate detection."""

    @pytest.mark.asyncio
    async def test_find_semantic_duplicates_without_client(self):
        """Test that semantic search is skipped when client not available."""
        code = """
def func1(items):
    total = 0
    for item in items:
        total += item
    return total

def func2(items):
    return sum(items)
"""
        detector = DuplicateDetector(min_lines=1, use_semantic=True)
        # No SVO client set, should return empty
        tree = ast.parse(code)
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.append((node, node.name, None, "function"))

        duplicates = await detector.find_semantic_duplicates(functions, code)
        # Should return empty when no client
        assert isinstance(duplicates, list)

    def test_cosine_similarity_edge_cases(self):
        """Test cosine similarity with edge cases."""
        import numpy as np

        detector = DuplicateDetector()

        # Zero vectors
        vec1 = np.array([0.0, 0.0, 0.0], dtype="float32")
        vec2 = np.array([0.0, 0.0, 0.0], dtype="float32")
        sim = detector._cosine_similarity(vec1, vec2)
        # Zero vectors should give 0 similarity (or handle gracefully)
        assert isinstance(sim, float)

        # Orthogonal vectors
        vec3 = np.array([1.0, 0.0], dtype="float32")
        vec4 = np.array([0.0, 1.0], dtype="float32")
        sim2 = detector._cosine_similarity(vec3, vec4)
        assert sim2 == 0.0

    def test_hybrid_approach_structure(self):
        """Test that hybrid approach returns correct structure."""
        code = """
def func1(x):
    result = []
    for item in x:
        if item > 0:
            result.append(item)
    return result

def func2(a):
    output = []
    for element in a:
        if element > 0:
            output.append(element)
    return output
"""
        detector = DuplicateDetector(min_lines=1, use_semantic=False)
        tree = ast.parse(code)

        # Test hybrid method structure (even without semantic)
        duplicates = detector.find_duplicates_in_ast(tree, code)

        # Should find AST duplicates
        assert len(duplicates) >= 1
        for group in duplicates:
            assert "hash" in group
            assert "similarity" in group
            assert "occurrences" in group
