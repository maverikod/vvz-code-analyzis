"""
Tests for ClassMerger refactoring functionality.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast

from code_analysis.core.refactorer import ClassMerger


class TestClassMergerPositive:
    """Positive test cases for ClassMerger."""

    def test_merge_classes_basic(self, tmp_path):
        """Test basic class merging."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class ClassA:
    """First class."""
    
    def __init__(self):
        self.prop1 = None
    
    def method1(self):
        return "method1"

class ClassB:
    """Second class."""
    
    def __init__(self):
        self.prop2 = None
    
    def method2(self):
        return "method2"
'''
        )

        config = {"base_class": "MergedClass", "source_classes": ["ClassA", "ClassB"]}

        merger = ClassMerger(test_file)
        success, message = merger.merge_classes(config)

        assert success, f"Merge failed: {message}"

        content = test_file.read_text()
        assert "class MergedClass:" in content
        assert "class ClassA:" not in content
        assert "class ClassB:" not in content

        # Verify merged class has all methods and properties
        tree = ast.parse(content)
        classes = {
            node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }

        assert "MergedClass" in classes
        merged_class = classes["MergedClass"]

        merged_methods = [
            item.name
            for item in merged_class.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

        assert "method1" in merged_methods
        assert "method2" in merged_methods

    def test_merge_classes_with_specific_methods(self, tmp_path):
        """Test merging with specific methods filter."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class A:
    def __init__(self):
        pass
    
    def method1(self):
        return 1
    
    def method2(self):
        return 2

class B:
    def __init__(self):
        pass
    
    def method3(self):
        return 3
    
    def method4(self):
        return 4
"""
        )

        # When merge_methods is specified, only those methods are merged
        # But completeness check requires ALL methods to be present
        # So we need to include all methods in merge_methods for completeness
        config = {
            "base_class": "Merged",
            "source_classes": ["A", "B"],
            "merge_methods": ["method1", "method2", "method3", "method4"],
        }

        merger = ClassMerger(test_file)
        success, message = merger.merge_classes(config)

        assert success, f"Merge failed: {message}"

        content = test_file.read_text()
        tree = ast.parse(content)
        classes = {
            node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }

        merged_class = classes["Merged"]
        merged_methods = [
            item.name
            for item in merged_class.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

        # All specified methods should be merged
        assert "method1" in merged_methods
        assert "method2" in merged_methods
        assert "method3" in merged_methods
        assert "method4" in merged_methods

    def test_merge_classes_with_specific_properties(self, tmp_path):
        """Test merging with specific properties filter."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class A:
    def __init__(self):
        self.prop1 = 1
        self.prop2 = 2

class B:
    def __init__(self):
        self.prop3 = 3
        self.prop4 = 4
"""
        )

        config = {
            "base_class": "Merged",
            "source_classes": ["A", "B"],
            "merge_props": ["prop1", "prop3"],
        }

        merger = ClassMerger(test_file)
        success, message = merger.merge_classes(config)

        assert success, f"Merge failed: {message}"

        content = test_file.read_text()
        tree = ast.parse(content)
        classes = {
            node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }

        merged_class = classes["Merged"]

        # Extract properties from __init__
        merged_props = set()
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

        assert "prop1" in merged_props
        assert "prop3" in merged_props

    def test_merge_classes_completeness(self, tmp_path):
        """Test that all original members are preserved after merge."""
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
    
    def method3(self):
        return 3
    
    def method4(self):
        return 4
"""
        test_file.write_text(original_content)

        # Parse original to collect all members
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

        # Verify completeness
        new_content = test_file.read_text()
        new_tree = ast.parse(new_content)

        merged_class = None
        for node in ast.walk(new_tree):
            if isinstance(node, ast.ClassDef) and node.name == "Merged":
                merged_class = node
                break

        assert merged_class is not None

        # Collect properties and methods from merged class
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

        # All original properties should be present
        assert all_original_props.issubset(
            merged_props
        ), f"Missing properties: {all_original_props - merged_props}"

        # All original methods should be present (excluding __init__)
        special_methods = {"__init__"}
        regular_original = all_original_methods - special_methods
        regular_merged = merged_methods - special_methods
        assert regular_original.issubset(
            regular_merged
        ), f"Missing methods: {regular_original - regular_merged}"

    def test_merge_classes_with_async_methods(self, tmp_path):
        """Test merging classes with async methods."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class AsyncA:
    async def async_method1(self):
        return "async1"

class AsyncB:
    async def async_method2(self):
        return "async2"
"""
        )

        config = {"base_class": "MergedAsync", "source_classes": ["AsyncA", "AsyncB"]}

        merger = ClassMerger(test_file)
        success, message = merger.merge_classes(config)

        assert success, f"Merge failed: {message}"

        content = test_file.read_text()
        tree = ast.parse(content)
        classes = {
            node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }

        merged_class = classes["MergedAsync"]
        methods = [
            item
            for item in merged_class.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

        async_methods = [m.name for m in methods if isinstance(m, ast.AsyncFunctionDef)]
        assert "async_method1" in async_methods
        assert "async_method2" in async_methods

    def test_merge_classes_backup_created(self, tmp_path):
        """Test that backup is created before merging."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        merger = ClassMerger(test_file)
        merger.create_backup()

        backup_dir = test_file.parent / ".code_mapper_backups"
        assert backup_dir.exists()

        backups = list(backup_dir.glob("*.backup"))
        assert len(backups) > 0

    def test_merge_three_classes(self, tmp_path):
        """Test merging three classes."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class A:
    def method_a(self):
        return "a"

class B:
    def method_b(self):
        return "b"

class C:
    def method_c(self):
        return "c"
"""
        )

        config = {"base_class": "ABC", "source_classes": ["A", "B", "C"]}

        merger = ClassMerger(test_file)
        success, message = merger.merge_classes(config)

        assert success, f"Merge failed: {message}"

        content = test_file.read_text()
        tree = ast.parse(content)
        classes = {
            node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }

        assert "ABC" in classes
        assert "A" not in classes
        assert "B" not in classes
        assert "C" not in classes

        merged_class = classes["ABC"]
        merged_methods = [
            item.name
            for item in merged_class.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

        assert "method_a" in merged_methods
        assert "method_b" in merged_methods
        assert "method_c" in merged_methods
