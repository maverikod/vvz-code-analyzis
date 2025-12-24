"""
Tests for refactoring preview functionality.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import tempfile
from pathlib import Path
import pytest

from code_analysis.core.refactorer import ClassSplitter, SuperclassExtractor


class TestRefactorPreview:
    """Tests for preview functionality."""

    def test_preview_split_class(self, tmp_path):
        """Test that preview_split returns preview without making changes."""
        test_file = tmp_path / "test.py"
        original_content = '''class LargeClass:
    def __init__(self):
        self.prop1 = None
        self.prop2 = None
    def method1(self):
        return "method1"
    def method2(self):
        return "method2"
'''
        test_file.write_text(original_content)

        config = {
            "src_class": "LargeClass",
            "dst_classes": {
                "ClassA": {"props": ["prop1"], "methods": ["method1"]},
                "ClassB": {"props": ["prop2"], "methods": ["method2"]},
            },
        }

        splitter = ClassSplitter(test_file)
        success, error_msg, preview = splitter.preview_split(config)

        assert success, f"Preview failed: {error_msg}"
        assert preview is not None
        assert "class LargeClass" in preview
        assert "class ClassA" in preview
        assert "class ClassB" in preview

        # Verify original file was not changed
        assert test_file.read_text() == original_content

        # Verify preview is valid Python
        try:
            ast.parse(preview)
        except SyntaxError as e:
            pytest.fail(f"Preview is not valid Python: {e}")

    def test_preview_extract_superclass(self, tmp_path):
        """Test that preview_extraction returns preview without making changes."""
        test_file = tmp_path / "test.py"
        original_content = '''class Child1:
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
        test_file.write_text(original_content)

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
        success, error_msg, preview = extractor.preview_extraction(config)

        assert success, f"Preview failed: {error_msg}"
        assert preview is not None
        assert "class Base" in preview
        assert "class Child1(Base)" in preview
        assert "class Child2(Base)" in preview

        # Verify original file was not changed
        assert test_file.read_text() == original_content

        # Verify preview is valid Python
        try:
            ast.parse(preview)
        except SyntaxError as e:
            pytest.fail(f"Preview is not valid Python: {e}")

    def test_preview_split_invalid_config(self, tmp_path):
        """Test that preview_split returns error for invalid config."""
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

        # Incomplete config
        config = {
            "src_class": "LargeClass",
            "dst_classes": {
                "ClassA": {"props": ["prop1"], "methods": ["method1"]},
            },
        }

        splitter = ClassSplitter(test_file)
        success, error_msg, preview = splitter.preview_split(config)

        assert not success
        assert error_msg is not None
        assert preview is None
        assert "ошибка конфигурации" in error_msg.lower() or "Ошибка конфигурации" in error_msg

