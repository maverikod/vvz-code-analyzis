"""
Tests for code integrity validation after refactoring.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import pytest

from code_analysis.core.refactorer import (
    ClassSplitter,
    SuperclassExtractor,
    ClassMerger,
)


class TestCodeIntegrityPart1:
    """Tests for ensuring code integrity after refactoring operations."""

    def test_split_integrity_all_methods_preserved(self, tmp_path):
        """Test that all methods are preserved after class splitting."""
        test_file = tmp_path / "test.py"
        original_content = '''class IntegrityTest:
    """Class for integrity testing."""

    def __init__(self):
        self.prop1 = 1
        self.prop2 = 2
        self.prop3 = 3

    def method1(self):
        return 1

    def method2(self):
        return 2

    def method3(self):
        return 3

    def method4(self):
        return 4

    def method5(self):
        return 5
    '''
        test_file.write_text(original_content)

        # Collect original members
        original_tree = ast.parse(original_content)
        original_class = None
        for node in ast.walk(original_tree):
            if isinstance(node, ast.ClassDef) and node.name == "IntegrityTest":
                original_class = node
                break

        original_props = set()
        original_methods = set()
        for item in original_class.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for stmt in item.body:
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Attribute):
                                if (
                                    isinstance(target.value, ast.Name)
                                    and target.value.id == "self"
                                ):
                                    original_props.add(target.attr)
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                original_methods.add(item.name)

        config = {
            "src_class": "IntegrityTest",
            "dst_classes": {
                "IntegrityTestA": {
                    "props": ["prop1", "prop2"],
                    "methods": ["method1", "method2"],
                },
                "IntegrityTestB": {
                    "props": ["prop3"],
                    "methods": ["method3", "method4", "method5"],
                },
            },
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert success, f"Split failed: {message}"

        # Verify integrity
        new_content = test_file.read_text()
        new_tree = ast.parse(new_content)

        all_new_props = set()
        all_new_methods = set()

        for node in ast.walk(new_tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        for stmt in item.body:
                            if isinstance(stmt, ast.Assign):
                                for target in stmt.targets:
                                    if isinstance(target, ast.Attribute):
                                        if (
                                            isinstance(target.value, ast.Name)
                                            and target.value.id == "self"
                                        ):
                                            all_new_props.add(target.attr)
                    elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        all_new_methods.add(item.name)

        # All original properties must be present
        assert original_props.issubset(
            all_new_props
        ), f"Missing properties: {original_props - all_new_props}"

        # All original methods must be present
        special_methods = {"__init__"}
        regular_original = original_methods - special_methods
        regular_new = all_new_methods - special_methods
        assert regular_original.issubset(
            regular_new
        ), f"Missing methods: {regular_original - regular_new}"

    def test_extract_integrity_all_members_in_base(self, tmp_path):
        """Test that all extracted members are in base class."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class Child1:
    def __init__(self):
        self.prop1 = 1
        self.prop2 = 2

    def method1(self):
        return 1

    def method2(self):
        return 2

class Child2:
    def __init__(self):
        self.prop1 = 1
        self.prop3 = 3

    def method1(self):
        return 1

    def method2(self):
        return 2  # method2 must be in both for extraction
"""
        )

        config = {
            "base_class": "Base",
            "child_classes": ["Child1", "Child2"],
            "abstract_methods": [],
            "extract_from": {
                "Child1": {
                    "properties": ["prop1", "prop2"],
                    "methods": ["method1", "method2"],
                },
                "Child2": {
                    "properties": ["prop1", "prop3"],
                    "methods": ["method1", "method2"],  # Only methods in both classes
                },
            },
        }

        extractor = SuperclassExtractor(test_file)
        success, message = extractor.extract_superclass(config)

        assert success, f"Extraction failed: {message}"

        # Verify all extracted members are in base
        content = test_file.read_text()
        tree = ast.parse(content)

        base_class = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "Base":
                base_class = node
                break

        assert base_class is not None

        base_props = set()
        base_methods = set()

        for item in base_class.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for stmt in item.body:
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Attribute):
                                if (
                                    isinstance(target.value, ast.Name)
                                    and target.value.id == "self"
                                ):
                                    base_props.add(target.attr)
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                base_methods.add(item.name)

        # All extracted properties should be in base
        expected_props = {"prop1", "prop2", "prop3"}
        assert expected_props.issubset(
            base_props
        ), f"Missing properties in base: {expected_props - base_props}"

        # All extracted methods should be in base (only methods in both classes)
        expected_methods = {"method1", "method2"}
        assert expected_methods.issubset(
            base_methods
        ), f"Missing methods in base: {expected_methods - base_methods}"

    def test_merge_integrity_all_members_preserved(self, tmp_path):
        """Test that all members are preserved after merging."""
        test_file = tmp_path / "test.py"
        original_content = """class Source1:
    def __init__(self):
        self.prop1 = 1
        self.prop2 = 2

    def method1(self):
        return 1

    def method2(self):
        return 2

class Source2:
    def __init__(self):
        self.prop3 = 3
        self.prop4 = 4

    def method3(self):
        return 3

    def method4(self):
        return 4
"""
        test_file.write_text(original_content)

        # Collect original members
        original_tree = ast.parse(original_content)
        all_original_props = set()
        all_original_methods = set()

        for node in ast.walk(original_tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        for stmt in item.body:
                            if isinstance(stmt, ast.Assign):
                                for target in stmt.targets:
                                    if isinstance(target, ast.Attribute):
                                        if (
                                            isinstance(target.value, ast.Name)
                                            and target.value.id == "self"
                                        ):
                                            all_original_props.add(target.attr)
                    elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        all_original_methods.add(item.name)

        config = {"base_class": "Merged", "source_classes": ["Source1", "Source2"]}

        merger = ClassMerger(test_file)
        success, message = merger.merge_classes(config)

        assert success, f"Merge failed: {message}"

        # Verify integrity
        new_content = test_file.read_text()
        new_tree = ast.parse(new_content)

        merged_class = None
        for node in ast.walk(new_tree):
            if isinstance(node, ast.ClassDef) and node.name == "Merged":
                merged_class = node
                break

        assert merged_class is not None

        merged_props = set()
        merged_methods = set()

        for item in merged_class.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for stmt in item.body:
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Attribute):
                                if (
                                    isinstance(target.value, ast.Name)
                                    and target.value.id == "self"
                                ):
                                    merged_props.add(target.attr)
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                merged_methods.add(item.name)

        # All original properties must be present
        assert all_original_props.issubset(
            merged_props
        ), f"Missing properties: {all_original_props - merged_props}"

        # All original methods must be present
        special_methods = {"__init__"}
        regular_original = all_original_methods - special_methods
        regular_merged = merged_methods - special_methods
        assert regular_original.issubset(
            regular_merged
        ), f"Missing methods: {regular_original - regular_merged}"


class TestCodeIntegrityPart2:
    """Tests for ensuring code integrity after refactoring operations."""

    def test_integrity_with_complex_class(self, tmp_path):
        """Test integrity with complex class having many members."""
        test_file = tmp_path / "test.py"
        original_content = '''class ComplexClass:
    """Complex class with many members."""

    def __init__(self):
        self.prop1 = 1
        self.prop2 = 2
        self.prop3 = 3
        self.prop4 = 4
        self.prop5 = 5

    def method1(self):
        return 1

    def method2(self):
        return 2

    def method3(self):
        return 3

    def method4(self):
        return 4

    def method5(self):
        return 5

    async def async_method1(self):
        return "async1"

    async def async_method2(self):
        return "async2"
    '''
        test_file.write_text(original_content)

        # Collect original
        original_tree = ast.parse(original_content)
        original_class = None
        for node in ast.walk(original_tree):
            if isinstance(node, ast.ClassDef) and node.name == "ComplexClass":
                original_class = node
                break

        original_props = set()
        original_methods = set()
        for item in original_class.body:
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for stmt in item.body:
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Attribute):
                                if (
                                    isinstance(target.value, ast.Name)
                                    and target.value.id == "self"
                                ):
                                    original_props.add(target.attr)
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                original_methods.add(item.name)

        config = {
            "src_class": "ComplexClass",
            "dst_classes": {
                "ComplexClassA": {
                    "props": ["prop1", "prop2"],
                    "methods": ["method1", "method2", "async_method1"],
                },
                "ComplexClassB": {
                    "props": ["prop3", "prop4"],
                    "methods": ["method3", "method4", "async_method2"],
                },
                "ComplexClassC": {"props": ["prop5"], "methods": ["method5"]},
            },
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert success, f"Split failed: {message}"

        # Verify all members are present
        new_content = test_file.read_text()
        new_tree = ast.parse(new_content)

        all_new_props = set()
        all_new_methods = set()

        for node in ast.walk(new_tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        for stmt in item.body:
                            if isinstance(stmt, ast.Assign):
                                for target in stmt.targets:
                                    if isinstance(target, ast.Attribute):
                                        if (
                                            isinstance(target.value, ast.Name)
                                            and target.value.id == "self"
                                        ):
                                            all_new_props.add(target.attr)
                    elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        all_new_methods.add(item.name)

        # Verify completeness
        assert original_props.issubset(
            all_new_props
        ), f"Missing properties: {original_props - all_new_props}"

        special_methods = {"__init__"}
        regular_original = original_methods - special_methods
        regular_new = all_new_methods - special_methods
        assert regular_original.issubset(
            regular_new
        ), f"Missing methods: {regular_original - regular_new}"

    def test_integrity_syntax_validation(self, tmp_path):
        """Test that syntax validation works after refactoring."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class SyntaxTest:
    def __init__(self):
        self.x = 1

    def method(self):
        return 1
    """
        )

        config = {
            "src_class": "SyntaxTest",
            "dst_classes": {"SyntaxTestA": {"props": ["x"], "methods": ["method"]}},
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert success, f"Split failed: {message}"

        # Syntax should be valid
        is_valid, error = splitter.validate_python_syntax()
        assert is_valid, f"Syntax validation failed: {error}"

        # File should be parseable
        content = test_file.read_text()
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"Generated code has syntax errors: {e}")
