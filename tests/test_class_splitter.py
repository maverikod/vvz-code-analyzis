"""
Tests for ClassSplitter refactoring functionality.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import json
import tempfile
from pathlib import Path
import pytest

from code_analysis.refactorer import ClassSplitter


class TestClassSplitterPositive:
    """Positive test cases for ClassSplitter."""

    def test_split_class_basic(self, tmp_path):
        """Test basic class splitting with methods and properties."""
        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class TestClass:
    """Test class for splitting."""
    
    def __init__(self):
        self.prop1 = None
        self.prop2 = None
        self.prop3 = None
    
    def method1(self):
        """First method."""
        return "method1"
    
    def method2(self):
        """Second method."""
        return "method2"
    
    def method3(self):
        """Third method."""
        return "method3"
'''
        )

        # Configuration - validation requires ALL properties and methods to be in config
        # Properties/methods not in dst_classes will remain in source class
        config = {
            "src_class": "TestClass",
            "dst_classes": {
                "TestClassA": {
                    "props": ["prop1"],
                    "methods": ["method1"]
                },
                "TestClassB": {
                    "props": ["prop2"],
                    "methods": ["method2"]
                },
                "TestClassC": {
                    "props": ["prop3"],
                    "methods": ["method3"]
                }
            }
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert success, f"Split failed: {message}"
        assert "successfully" in message.lower()

        # Verify file was modified
        content = test_file.read_text()
        assert "class TestClass:" in content
        assert "class TestClassA:" in content
        assert "class TestClassB:" in content

        # Verify methods are in new classes
        tree = ast.parse(content)
        classes = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        
        assert "TestClass" in classes
        assert "TestClassA" in classes
        assert "TestClassB" in classes
        assert "TestClassC" in classes
        
        # Check TestClassA has method1
        test_class_a_methods = [
            item.name for item in classes["TestClassA"].body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert "method1" in test_class_a_methods
        
        # Check TestClassB has method2
        test_class_b_methods = [
            item.name for item in classes["TestClassB"].body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert "method2" in test_class_b_methods
        
        # Check TestClassC has method3
        test_class_c_methods = [
            item.name for item in classes["TestClassC"].body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert "method3" in test_class_c_methods

    def test_split_class_with_async_methods(self, tmp_path):
        """Test splitting class with async methods."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class AsyncClass:
    """Class with async methods."""
    
    def __init__(self):
        self.data = None
    
    async def async_method1(self):
        """Async method 1."""
        return "async1"
    
    async def async_method2(self):
        """Async method 2."""
        return "async2"
    
    def sync_method(self):
        """Sync method."""
        return "sync"
'''
        )

        config = {
            "src_class": "AsyncClass",
            "dst_classes": {
                "AsyncClassA": {
                    "props": ["data"],
                    "methods": ["async_method1"]
                },
                "AsyncClassB": {
                    "props": [],
                    "methods": ["async_method2", "sync_method"]
                }
            }
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert success, f"Split failed: {message}"

        # Verify async method is preserved
        content = test_file.read_text()
        tree = ast.parse(content)
        classes = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        
        assert "AsyncClassA" in classes
        async_class_a = classes["AsyncClassA"]
        methods = [
            item for item in async_class_a.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        
        async_methods = [m.name for m in methods if isinstance(m, ast.AsyncFunctionDef)]
        assert "async_method1" in async_methods

    def test_split_class_completeness_check(self, tmp_path):
        """Test that all original methods and properties are preserved."""
        test_file = tmp_path / "test.py"
        original_content = '''class CompleteClass:
    """Class for completeness testing."""
    
    def __init__(self):
        self.prop1 = "value1"
        self.prop2 = "value2"
        self.prop3 = "value3"
    
    def method1(self):
        return 1
    
    def method2(self):
        return 2
    
    def method3(self):
        return 3
    
    def method4(self):
        return 4
'''
        test_file.write_text(original_content)

        # Parse original to get all members
        original_tree = ast.parse(original_content)
        original_class = None
        for node in ast.walk(original_tree):
            if isinstance(node, ast.ClassDef) and node.name == "CompleteClass":
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
            "src_class": "CompleteClass",
            "dst_classes": {
                "CompleteClassA": {
                    "props": ["prop1", "prop2"],
                    "methods": ["method1", "method2"]
                },
                "CompleteClassB": {
                    "props": ["prop3"],
                    "methods": ["method3", "method4"]
                }
            }
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert success, f"Split failed: {message}"

        # Verify completeness
        new_content = test_file.read_text()
        new_tree = ast.parse(new_content)
        
        all_new_props = set()
        all_new_methods = set()
        
        for node in ast.walk(new_tree):
            if isinstance(node, ast.ClassDef):
                # Get properties
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

        # All original properties should be present
        assert original_props.issubset(all_new_props), \
            f"Missing properties: {original_props - all_new_props}"
        
        # All original methods should be present (excluding __init__)
        special_methods = {"__init__"}
        regular_original = original_methods - special_methods
        regular_new = all_new_methods - special_methods
        assert regular_original.issubset(regular_new), \
            f"Missing methods: {regular_original - regular_new}"

    def test_split_class_backup_created(self, tmp_path):
        """Test that backup is created before splitting."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class BackupTest:
    def __init__(self):
        self.x = 1
'''
        )

        config = {
            "src_class": "BackupTest",
            "dst_classes": {}
        }

        splitter = ClassSplitter(test_file)
        splitter.create_backup()

        backup_dir = test_file.parent / ".code_mapper_backups"
        assert backup_dir.exists()
        
        backups = list(backup_dir.glob("*.backup"))
        assert len(backups) > 0

    def test_split_class_remaining_methods_in_source(self, tmp_path):
        """Test that methods not moved to dst classes remain in source class."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class RemainingTest:
    def __init__(self):
        self.x = 1
    
    def method1(self):
        return 1
    
    def method2(self):
        return 2
    
    def method3(self):
        return 3
'''
        )

        # All methods and properties must be accounted for
        config = {
            "src_class": "RemainingTest",
            "dst_classes": {
                "RemainingTestA": {
                    "props": ["x"],
                    "methods": ["method1"]
                },
                "RemainingTestB": {
                    "props": [],
                    "methods": ["method2", "method3"]
                }
            }
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert success, f"Split failed: {message}"

        content = test_file.read_text()
        tree = ast.parse(content)
        classes = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        
        source_class = classes["RemainingTest"]
        source_methods = [
            item.name for item in source_class.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        
        # method2 and method3 are in RemainingTestB, but wrappers should be in source
        # Actually, all methods should have wrappers in source
        assert "method1" in source_methods  # wrapper
        assert "method2" in source_methods  # wrapper
        assert "method3" in source_methods  # wrapper

    def test_split_class_wrapper_methods(self, tmp_path):
        """Test that wrapper methods are created in source class."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class WrapperTest:
    def __init__(self):
        self.x = 1
    
    def method1(self, arg1, arg2):
        return arg1 + arg2
'''
        )

        config = {
            "src_class": "WrapperTest",
            "dst_classes": {
                "WrapperTestA": {
                    "props": ["x"],
                    "methods": ["method1"]
                }
            }
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert success, f"Split failed: {message}"

        content = test_file.read_text()
        tree = ast.parse(content)
        classes = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        
        source_class = classes["WrapperTest"]
        source_methods = [
            item.name for item in source_class.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        
        # method1 should be in source as wrapper
        assert "method1" in source_methods
        
        # Check wrapper delegates to new class
        # The wrapper should call self.wrappertesta.method1
        content_lower = content.lower()
        assert "def method1" in content, "method1 wrapper should exist"
        assert "self.wrappertesta.method1" in content_lower, \
            "Wrapper should delegate to wrappertesta.method1"


