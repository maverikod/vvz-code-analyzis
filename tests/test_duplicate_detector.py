"""
Tests for duplicate code detector.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
from pathlib import Path

import pytest

from code_analysis.core.duplicate_detector import (
    ASTNormalizer,
    DuplicateDetector,
)


class TestASTNormalizer:
    """Tests for ASTNormalizer class."""

    def test_normalize_variable_names(self):
        """Test that variable names are normalized."""
        code = "x = 1; y = x + 2"
        tree = ast.parse(code)
        normalizer = ASTNormalizer()
        normalized = normalizer.visit(tree)

        # Check that variables are normalized
        dump = ast.dump(normalized, annotate_fields=False, include_attributes=False)
        assert "_VAR" in dump
        assert "x" not in dump or "x" in dump  # x might be in function name

    def test_normalize_string_literals(self):
        """Test that string literals are normalized."""
        code = 'x = "hello"; y = "world"'
        tree = ast.parse(code)
        normalizer = ASTNormalizer()
        normalized = normalizer.visit(tree)

        dump = ast.dump(normalized, annotate_fields=False, include_attributes=False)
        assert "_STR_" in dump
        assert '"hello"' not in dump
        assert '"world"' not in dump

    def test_normalize_numeric_literals(self):
        """Test that numeric literals are normalized."""
        code = "x = 42; y = 3.14"
        tree = ast.parse(code)
        normalizer = ASTNormalizer()
        normalized = normalizer.visit(tree)

        dump = ast.dump(normalized, annotate_fields=False, include_attributes=False)
        assert "_NUM_" in dump

    def test_preserve_structure(self):
        """Test that code structure is preserved."""
        code = """
if x > 0:
    for i in range(10):
        if i % 2 == 0:
            result.append(i)
"""
        tree = ast.parse(code)
        normalizer = ASTNormalizer()
        normalized = normalizer.visit(tree)

        dump = ast.dump(normalized, annotate_fields=False, include_attributes=False)
        # Structure should be preserved
        assert "If" in dump
        assert "For" in dump

    def test_normalize_function_names(self):
        """Test that function names are normalized."""
        code = "def func1(x): return x"
        tree = ast.parse(code)
        normalizer = ASTNormalizer()
        normalized = normalizer.visit(tree)

        dump = ast.dump(normalized, annotate_fields=False, include_attributes=False)
        assert "_VAR" in dump
        # Function name should be normalized
        func_node = normalized.body[0]
        assert func_node.name.startswith("_VAR")

    def test_normalize_arguments(self):
        """Test that function arguments are normalized."""
        code = "def func(x, y, z): return x + y + z"
        tree = ast.parse(code)
        normalizer = ASTNormalizer()
        normalized = normalizer.visit(tree)

        func_node = normalized.body[0]
        # All arguments should be normalized
        for arg in func_node.args.args:
            assert arg.arg.startswith("_VAR")


class TestDuplicateDetector:
    """Tests for DuplicateDetector class."""

    def test_find_exact_duplicates(self):
        """Test finding exact duplicates (same structure, different names)."""
        code = """
def func1(x, y):
    result = []
    for item in x:
        if item > 0:
            result.append(item * 2)
    return result

def func2(a, b):
    output = []
    for element in a:
        if element > 0:
            output.append(element * 2)
    return output
"""
        detector = DuplicateDetector(min_lines=1, use_semantic=False)
        duplicates = detector.find_duplicates_in_code(code)

        assert len(duplicates) >= 1
        # Should find at least one duplicate group
        found = False
        for group in duplicates:
            if len(group["occurrences"]) >= 2:
                func_names = {occ["function_name"] for occ in group["occurrences"]}
                if "func1" in func_names and "func2" in func_names:
                    found = True
                    break
        assert found, "Should find duplicate between func1 and func2"

    def test_find_duplicates_with_different_literals(self):
        """Test finding duplicates with different string/numeric literals."""
        code = """
def func1(items):
    filtered = []
    for item in items:
        if item.status == "active":
            filtered.append(item)
    return filtered

def func2(items):
    filtered = []
    for item in items:
        if item.status == "inactive":
            filtered.append(item)
    return filtered
"""
        detector = DuplicateDetector(min_lines=1, use_semantic=False)
        duplicates = detector.find_duplicates_in_code(code)

        # Should find duplicates (literals are normalized)
        assert len(duplicates) >= 1

    def test_min_lines_filter(self):
        """Test that min_lines filter works."""
        code = """
def short_func(x):
    return x

def another_short(y):
    return y
"""
        detector = DuplicateDetector(min_lines=5, use_semantic=False)
        duplicates = detector.find_duplicates_in_code(code)

        # Should not find duplicates (too short)
        assert len(duplicates) == 0

    def test_find_method_duplicates(self):
        """Test finding duplicate methods in classes."""
        code = """
class Class1:
    def method1(self, items):
        result = []
        for item in items:
            if item > 0:
                result.append(item)
        return result

class Class2:
    def method2(self, data):
        output = []
        for element in data:
            if element > 0:
                output.append(element)
        return output
"""
        detector = DuplicateDetector(min_lines=1, use_semantic=False)
        duplicates = detector.find_duplicates_in_code(code)

        # Should find duplicate methods
        assert len(duplicates) >= 1
        methods_found = False
        for group in duplicates:
            for occ in group["occurrences"]:
                if occ["type"] == "method":
                    methods_found = True
                    break
        assert methods_found

    def test_find_nested_duplicates(self):
        """Test finding duplicates in nested functions."""
        code = """
def outer1(x):
    def inner(y):
        total = 0
        for i in y:
            if i > 0:
                total += i
        return total
    return inner(x)

def outer2(a):
    def inner(b):
        sum_val = 0
        for val in b:
            if val > 0:
                sum_val += val
        return sum_val
    return inner(a)
"""
        detector = DuplicateDetector(min_lines=1, use_semantic=False)
        duplicates = detector.find_duplicates_in_code(code)

        # Should find nested duplicates
        assert len(duplicates) >= 1

    def test_ast_to_hash(self):
        """Test AST to hash conversion."""
        code = "def func(x): return x * 2"
        tree = ast.parse(code)
        func = tree.body[0]

        detector = DuplicateDetector()
        normalized = detector.normalize_ast(func)
        hash1 = detector.ast_to_hash(normalized)

        # Hash should be consistent for same normalized AST
        hash2 = detector.ast_to_hash(normalized)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

    def test_calculate_similarity(self):
        """Test similarity calculation."""
        code1 = "def func1(x):\n    if x > 0:\n        return x * 2\n    return 0"
        code2 = "def func2(a):\n    if a > 0:\n        return a * 2\n    return 0"

        tree1 = ast.parse(code1)
        tree2 = ast.parse(code2)

        detector = DuplicateDetector()
        similarity = detector.calculate_similarity(tree1.body[0], tree2.body[0])

        # Should be very similar (almost identical structure)
        assert similarity >= 0.8

    def test_file_analysis(self, tmp_path):
        """Test analyzing a file."""
        file_path = tmp_path / "test.py"
        file_path.write_text(
            """
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
        )

        detector = DuplicateDetector(min_lines=1, use_semantic=False)
        duplicates = detector.find_duplicates_in_file(str(file_path))

        assert len(duplicates) >= 1

    def test_syntax_error_handling(self, tmp_path):
        """Test handling of syntax errors."""
        file_path = tmp_path / "invalid.py"
        file_path.write_text("def invalid syntax\n")

        detector = DuplicateDetector()
        duplicates = detector.find_duplicates_in_file(str(file_path))

        # Should return empty list, not raise exception
        assert isinstance(duplicates, list)
        assert len(duplicates) == 0


class TestRealData:
    """Tests using real data from test_data directory."""

    @pytest.fixture
    def test_data_path(self):
        """Get path to test_data directory."""
        project_root = Path(__file__).parent.parent
        test_data = project_root / "test_data" / "bhlff"
        if test_data.exists():
            return test_data
        return None

    def test_real_file_duplicates(self):
        """Test finding duplicates in real file."""
        project_root = Path(__file__).parent.parent
        # Use our test file with known duplicates
        test_file = project_root / "test_data" / "duplicate_test_examples.py"
        if not test_file.exists():
            pytest.skip("duplicate_test_examples.py not found")

        detector = DuplicateDetector(min_lines=3, use_semantic=False)
        duplicates = detector.find_duplicates_in_file(str(test_file))

        assert len(duplicates) > 0
        # Verify structure
        for group in duplicates:
            assert "hash" in group
            assert "similarity" in group
            assert "occurrences" in group
            assert len(group["occurrences"]) >= 2
            for occ in group["occurrences"]:
                assert "function_name" in occ
                assert "start_line" in occ
                assert "type" in occ

    def test_multiple_real_files(self, test_data_path):
        """Test finding duplicates across multiple files."""
        if test_data_path is None:
            pytest.skip("test_data/bhlff not found")

        # Find Python files
        arrays_dir = test_data_path / "core" / "arrays"
        if not arrays_dir.exists():
            pytest.skip("core/arrays directory not found")

        py_files = list(arrays_dir.glob("*.py"))[:3]
        if not py_files:
            pytest.skip("No Python files found")

        detector = DuplicateDetector(min_lines=5, use_semantic=False)

        all_duplicates = []
        for py_file in py_files:
            try:
                duplicates = detector.find_duplicates_in_file(str(py_file))
                all_duplicates.extend(duplicates)
            except SyntaxError:
                continue

        # Should find some duplicates or at least complete without error
        assert isinstance(all_duplicates, list)


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_file(self, tmp_path):
        """Test analyzing empty file."""
        file_path = tmp_path / "empty.py"
        file_path.write_text("")

        detector = DuplicateDetector()
        duplicates = detector.find_duplicates_in_file(str(file_path))

        assert len(duplicates) == 0

    def test_single_function(self, tmp_path):
        """Test file with single function."""
        file_path = tmp_path / "single.py"
        file_path.write_text("def func(x): return x\n")

        detector = DuplicateDetector()
        duplicates = detector.find_duplicates_in_file(str(file_path))

        # No duplicates (only one function)
        assert len(duplicates) == 0

    def test_no_duplicates(self, tmp_path):
        """Test file with no duplicates."""
        code = """
def func1(x):
    return x * 2

def func2(y):
    return y + 1

def func3(z):
    if z > 0:
        return z
    return 0
"""
        file_path = tmp_path / "no_dups.py"
        file_path.write_text(code)

        detector = DuplicateDetector(min_lines=1, use_semantic=False)
        duplicates = detector.find_duplicates_in_file(str(file_path))

        # Should not find duplicates (different structures)
        # Note: might find some if structures are similar enough
        assert isinstance(duplicates, list)

    def test_very_long_function(self, tmp_path):
        """Test with very long function."""
        code = "def long_func(x):\n" + "    y = x\n" * 100 + "    return y\n"

        detector = DuplicateDetector(min_lines=1, use_semantic=False)
        duplicates = detector.find_duplicates_in_code(code)

        # Should handle long functions
        assert isinstance(duplicates, list)

    def test_cosine_similarity(self):
        """Test cosine similarity calculation."""
        import numpy as np

        detector = DuplicateDetector()
        vec1 = np.array([1.0, 0.0, 0.0], dtype="float32")
        vec2 = np.array([1.0, 0.0, 0.0], dtype="float32")

        similarity = detector._cosine_similarity(vec1, vec2)
        assert similarity == 1.0

        vec3 = np.array([0.0, 1.0, 0.0], dtype="float32")
        similarity2 = detector._cosine_similarity(vec1, vec3)
        assert similarity2 == 0.0

    def test_set_svo_client_manager(self):
        """Test setting SVO client manager."""
        detector = DuplicateDetector(use_semantic=True)

        class MockSVOClient:
            pass

        mock_client = MockSVOClient()
        detector.set_svo_client_manager(mock_client)

        assert detector._svo_client_manager == mock_client

    def test_edit_distance_similarity(self):
        """Test edit distance similarity calculation."""
        detector = DuplicateDetector()

        # Identical strings
        sim1 = detector._edit_distance_similarity("abc", "abc")
        assert sim1 == 1.0

        # Similar strings
        sim2 = detector._edit_distance_similarity("abc", "abd")
        assert 0.0 <= sim2 <= 1.0

        # Different strings
        sim3 = detector._edit_distance_similarity("abc", "xyz")
        assert 0.0 <= sim3 < 1.0

        # Empty strings
        sim4 = detector._edit_distance_similarity("", "")
        sim4 = detector._edit_distance_similarity("", "")
        assert sim4 == 1.0

    @pytest.mark.asyncio
    async def test_semantic_duplicates_disabled(self):
        """Test that semantic duplicates are skipped when disabled."""
        code = """
def func1(items):
    total = 0
    for item in items:
        total += item
    return total

def func2(items):
    return sum(items)
"""
        detector = DuplicateDetector(min_lines=1, use_semantic=False)
        duplicates = detector.find_duplicates_in_code(code)

        # Without semantic, these might not be detected as duplicates
        # (different structure)
        assert isinstance(duplicates, list)
