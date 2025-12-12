"""
Tests for SuperclassExtractor refactoring functionality.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import pytest
from pathlib import Path

from code_analysis.core.refactorer import SuperclassExtractor


class TestSuperclassExtractorPositive:
    """Positive test cases for SuperclassExtractor."""

    def test_extract_superclass_basic(self, tmp_path):
        """Test basic superclass extraction."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Child1:
    """First child class."""
    
    def __init__(self):
        self.prop1 = None
        self.prop2 = None
    
    def common_method(self):
        return "child1"
    
    def specific_method1(self):
        return "specific1"

class Child2:
    """Second child class."""
    
    def __init__(self):
        self.prop1 = None
        self.prop3 = None
    
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
                "Child1": {
                    "properties": ["prop1"],
                    "methods": ["common_method"]
                },
                "Child2": {
                    "properties": ["prop1"],
                    "methods": ["common_method"]
                }
            }
        }

        extractor = SuperclassExtractor(test_file)
        success, message = extractor.extract_superclass(config)

        assert success, f"Extraction failed: {message}"

        content = test_file.read_text()
        assert "class Base" in content
        assert "class Child1" in content
        assert "class Child2" in content

        # Verify inheritance
        tree = ast.parse(content)
        classes = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        
        assert "Base" in classes
        assert "Child1" in classes
        assert "Child2" in classes
        
        # Check Child1 inherits from Base
        child1_bases = [base.id for base in classes["Child1"].bases if isinstance(base, ast.Name)]
        assert "Base" in child1_bases
        
        # Check Child2 inherits from Base
        child2_bases = [base.id for base in classes["Child2"].bases if isinstance(base, ast.Name)]
        assert "Base" in child2_bases

    def test_extract_superclass_with_abstract_methods(self, tmp_path):
        """Test extraction with abstract methods."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Dog:
    def __init__(self):
        self.name = None
    
    def make_sound(self):
        return "Woof"
    
    def move(self):
        return "running"

class Cat:
    def __init__(self):
        self.name = None
    
    def make_sound(self):
        return "Meow"
    
    def move(self):
        return "walking"
'''
        )

        config = {
            "base_class": "Animal",
            "child_classes": ["Dog", "Cat"],
            "abstract_methods": ["make_sound"],
            "extract_from": {
                "Dog": {
                    "properties": ["name"],
                    "methods": ["make_sound", "move"]
                },
                "Cat": {
                    "properties": ["name"],
                    "methods": ["make_sound", "move"]
                }
            }
        }

        extractor = SuperclassExtractor(test_file)
        success, message = extractor.extract_superclass(config)

        assert success, f"Extraction failed: {message}"

        content = test_file.read_text()
        tree = ast.parse(content)
        classes = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        
        assert "Animal" in classes
        animal_class = classes["Animal"]
        
        # Check Animal inherits from ABC
        bases = [base.id for base in animal_class.bases if isinstance(base, ast.Name)]
        assert "ABC" in bases
        
        # Check abstractmethod decorator
        has_abstractmethod = False
        for item in animal_class.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if item.name == "make_sound":
                    # Check for @abstractmethod decorator
                    for decorator in item.decorator_list:
                        if isinstance(decorator, ast.Name) and decorator.id == "abstractmethod":
                            has_abstractmethod = True
                            break
        
        assert has_abstractmethod, "Abstract method should have @abstractmethod decorator"

    def test_extract_superclass_completeness(self, tmp_path):
        """Test that all extracted members are in base class."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class A:
    def __init__(self):
        self.prop1 = 1
        self.prop2 = 2
    
    def method1(self):
        return 1
    
    def method2(self):
        return 2

class B:
    def __init__(self):
        self.prop1 = 1
        self.prop3 = 3
    
    def method1(self):
        return 1
    
    def method2(self):
        return 2  # method2 must be in both for extraction
'''
        )

        config = {
            "base_class": "Base",
            "child_classes": ["A", "B"],
            "abstract_methods": [],
            "extract_from": {
                "A": {
                    "properties": ["prop1", "prop2"],
                    "methods": ["method1", "method2"]
                },
                "B": {
                    "properties": ["prop1", "prop3"],
                    "methods": ["method1", "method2"]  # method2 must be in both
                }
            }
        }

        extractor = SuperclassExtractor(test_file)
        success, message = extractor.extract_superclass(config)

        assert success, f"Extraction failed: {message}"

        content = test_file.read_text()
        tree = ast.parse(content)
        classes = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
        
        assert "Base" in classes
        base_class = classes["Base"]
        
        # Collect properties and methods from base
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
        assert expected_props.issubset(base_props), \
            f"Missing properties in base: {expected_props - base_props}"
        
        # All extracted methods should be in base (only methods in both classes)
        expected_methods = {"method1", "method2"}
        assert expected_methods.issubset(base_methods), \
            f"Missing methods in base: {expected_methods - base_methods}"

    def test_extract_superclass_method_compatibility(self, tmp_path):
        """Test that method compatibility is checked."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Compatible1:
    def __init__(self):
        pass
    
    def method(self, arg1, arg2):
        return arg1 + arg2

class Compatible2:
    def __init__(self):
        pass
    
    def method(self, arg1, arg2):
        return arg1 * arg2
'''
        )

        config = {
            "base_class": "Base",
            "child_classes": ["Compatible1", "Compatible2"],
            "abstract_methods": [],
            "extract_from": {
                "Compatible1": {
                    "properties": [],
                    "methods": ["method"]
                },
                "Compatible2": {
                    "properties": [],
                    "methods": ["method"]
                }
            }
        }

        extractor = SuperclassExtractor(test_file)
        success, message = extractor.extract_superclass(config)

        assert success, f"Extraction failed: {message}"

    def test_extract_superclass_no_multiple_inheritance_conflict(self, tmp_path):
        """Test that classes without bases can be used."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Child1:
    def method(self):
        return 1

class Child2:
    def method(self):
        return 2
'''
        )

        config = {
            "base_class": "Base",
            "child_classes": ["Child1", "Child2"],
            "abstract_methods": [],
            "extract_from": {
                "Child1": {
                    "properties": [],
                    "methods": ["method"]
                },
                "Child2": {
                    "properties": [],
                    "methods": ["method"]
                }
            }
        }

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        
        is_safe, error = extractor.check_multiple_inheritance_conflicts(
            ["Child1", "Child2"], "Base"
        )
        
        assert is_safe, f"Should not have conflicts: {error}"


