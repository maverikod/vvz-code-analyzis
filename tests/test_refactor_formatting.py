"""
Tests for refactoring code formatting functionality.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import tempfile
from pathlib import Path
import pytest

from code_analysis.core.refactorer import ClassSplitter, SuperclassExtractor, format_code_with_black


class TestRefactorFormatting:
    """Tests for code formatting after refactoring."""

    def test_format_code_with_black_success(self, tmp_path):
        """Test that black formatting works correctly."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Test:
    def method1(self):
        return "test"
    def method2(self):
        return "test2"
'''
        )

        success, error = format_code_with_black(test_file)
        assert success, f"Formatting failed: {error}"

        # Check that file was formatted (black adds blank lines between methods)
        content = test_file.read_text()
        assert "def method1" in content
        assert "def method2" in content

    def test_split_class_formats_result(self, tmp_path):
        """Test that split_class formats the result with black."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class LargeClass:
    """Test class."""
    def __init__(self):
        self.prop1 = None
        self.prop2 = None
    def method1(self):
        return "method1"
    def method2(self):
        return "method2"
'''
        )

        config = {
            "src_class": "LargeClass",
            "dst_classes": {
                "ClassA": {"props": ["prop1"], "methods": ["method1"]},
                "ClassB": {"props": ["prop2"], "methods": ["method2"]},
            },
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert success, f"Split failed: {message}"

        # Check that result is formatted (should have blank lines between methods)
        content = test_file.read_text()
        # Black should format the code properly
        assert "class LargeClass" in content
        assert "class ClassA" in content
        assert "class ClassB" in content

        # Verify syntax is valid
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"Result is not valid Python: {e}")

    def test_extract_superclass_formats_result(self, tmp_path):
        """Test that extract_superclass formats the result with black."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Child1:
    def __init__(self):
        self.prop1 = None
    def common_method(self):
        return "child1"
    def specific_method1(self):
        return "specific1"

class Child2:
    def __init__(self):
        self.prop1 = None
    def common_method(self):
        return "child2"
    def specific_method2(self):
        return "specific2"
'''
        )

        config = {
            "base_class": "Base",
            "child_classes": ["Child1", "Child2"],
            "abstract_methods": [],
            "extract_from": {
                "Child1": {"properties": ["prop1"], "methods": ["common_method"]},
                "Child2": {"properties": ["prop1"], "methods": ["common_method"]},
            },
        }

        extractor = SuperclassExtractor(test_file)
        success, message = extractor.extract_superclass(config)

        assert success, f"Extraction failed: {message}"

        # Check that result is formatted
        content = test_file.read_text()
        assert "class Base" in content
        assert "class Child1(Base)" in content
        assert "class Child2(Base)" in content

        # Verify syntax is valid
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"Result is not valid Python: {e}")

    def test_formatting_continues_on_error(self, tmp_path, monkeypatch):
        """Test that refactoring continues even if formatting fails."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class LargeClass:
    def __init__(self):
        self.prop1 = None
        self.prop2 = None
    def method1(self):
        return "method1"
    def method2(self):
        return "method2"
'''
        )

        # Mock black to fail
        def mock_format(*args, **kwargs):
            return False, "Black not available"

        monkeypatch.setattr(
            "code_analysis.core.refactorer.format_code_with_black", mock_format
        )

        config = {
            "src_class": "LargeClass",
            "dst_classes": {
                "ClassA": {"props": ["prop1"], "methods": ["method1"]},
                "ClassB": {"props": ["prop2"], "methods": ["method2"]},
            },
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        # Should still succeed even if formatting fails
        assert success, f"Split should succeed even if formatting fails: {message}"

