"""
Tests for docstring and comment preservation during refactoring.

This module contains comprehensive tests to ensure that docstrings and comments
are properly preserved when splitting classes, extracting superclasses, and merging classes.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import pytest
from pathlib import Path

from code_analysis.core.refactorer import ClassSplitter, SuperclassExtractor, ClassMerger


class TestDocstringPreservationSplit:
    """Tests for docstring preservation during class splitting."""

    def test_split_preserves_class_docstring(self, tmp_path):
        """Test that class docstring is preserved in destination classes."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class SourceClass:
    """This is a class docstring.
    
    It has multiple lines.
    And more details.
    """
    
    def __init__(self):
        self.prop1 = 1
    
    def method1(self):
        return 1
'''
        )

        config = {
            "src_class": "SourceClass",
            "dst_classes": {
                "DstClass1": {
                    "props": ["prop1"],
                    "methods": ["method1"]
                }
            }
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert success, f"Split failed: {message}"

        content = test_file.read_text()
        
        # Check that docstring is in destination class
        assert '"""This is a class docstring.' in content
        assert 'It has multiple lines.' in content
        assert 'And more details.' in content
        assert 'class DstClass1:' in content

    def test_split_preserves_method_docstrings(self, tmp_path):
        """Test that method docstrings are preserved when methods are moved."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class SourceClass:
    def method1(self):
        """Method 1 docstring.
        
        This method does something important.
        Returns:
            int: Some value
        """
        return 1
    
    def method2(self):
        """Method 2 docstring."""
        return 2
'''
        )

        config = {
            "src_class": "SourceClass",
            "dst_classes": {
                "DstClass1": {
                    "props": [],
                    "methods": ["method1", "method2"]
                }
            }
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert success, f"Split failed: {message}"

        content = test_file.read_text()
        
        # Check that method docstrings are preserved
        assert '"""Method 1 docstring.' in content
        assert 'This method does something important.' in content
        assert 'Returns:' in content
        assert '"""Method 2 docstring."""' in content

    def test_split_preserves_method_comments(self, tmp_path):
        """Test that inline and block comments in methods are preserved."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class SourceClass:
    def method1(self):
        # This is a comment before code
        result = 1
        # This is a comment after code
        return result
    
    def method2(self):
        """
        Method with comments.
        """
        # Comment at start
        x = 1
        # Comment in middle
        y = 2
        # Comment at end
        return x + y
'''
        )

        config = {
            "src_class": "SourceClass",
            "dst_classes": {
                "DstClass1": {
                    "props": [],
                    "methods": ["method1", "method2"]
                }
            }
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert success, f"Split failed: {message}"

        content = test_file.read_text()
        
        # Check that comments are preserved
        assert '# This is a comment before code' in content
        assert '# This is a comment after code' in content
        assert '# Comment at start' in content
        assert '# Comment in middle' in content
        assert '# Comment at end' in content

    def test_split_preserves_class_comments(self, tmp_path):
        """Test that class-level comments are preserved."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''# This is a comment before class
class SourceClass:
    """Class docstring."""
    
    # This is a comment in class body
    def __init__(self):
        self.prop1 = 1
    
    # Another comment before method
    def method1(self):
        return 1
'''
        )

        config = {
            "src_class": "SourceClass",
            "dst_classes": {
                "DstClass1": {
                    "props": ["prop1"],
                    "methods": ["method1"]
                }
            }
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert success, f"Split failed: {message}"

        content = test_file.read_text()
        
        # Check that class comments are preserved
        assert '# This is a comment in class body' in content or '# Another comment before method' in content

    def test_split_preserves_multiline_docstrings(self, tmp_path):
        """Test that multiline docstrings with complex formatting are preserved."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class SourceClass:
    """Complex docstring.
    
    Args:
        param1: First parameter
        param2: Second parameter
    
    Returns:
        Result object
    
    Raises:
        ValueError: If invalid input
    
    Example:
        >>> obj = SourceClass()
        >>> obj.method()
        42
    """
    
    def method1(self):
        """Method with complex docstring.
        
        This method has:
        - Multiple sections
        - Bullet points
        - Code examples
        
        Example:
            result = method1()
            print(result)
        """
        return 42
'''
        )

        config = {
            "src_class": "SourceClass",
            "dst_classes": {
                "DstClass1": {
                    "props": [],
                    "methods": ["method1"]
                }
            }
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert success, f"Split failed: {message}"

        content = test_file.read_text()
        
        # Check that complex docstrings are preserved
        assert 'Args:' in content
        assert 'Returns:' in content
        assert 'Raises:' in content
        assert 'Example:' in content
        assert 'Multiple sections' in content
        assert 'Bullet points' in content

    def test_split_preserves_docstrings_in_all_destination_classes(self, tmp_path):
        """Test that docstrings are preserved when splitting into multiple classes."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class SourceClass:
    """Source class docstring."""
    
    def __init__(self):
        self.prop1 = 1
        self.prop2 = 2
    
    def method1(self):
        """Method 1 docstring."""
        return 1
    
    def method2(self):
        """Method 2 docstring."""
        return 2
'''
        )

        config = {
            "src_class": "SourceClass",
            "dst_classes": {
                "DstClass1": {
                    "props": ["prop1"],
                    "methods": ["method1"]
                },
                "DstClass2": {
                    "props": ["prop2"],
                    "methods": ["method2"]
                }
            }
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert success, f"Split failed: {message}"

        content = test_file.read_text()
        
        # Check that docstrings are in destination classes
        assert '"""Source class docstring."""' in content
        assert '"""Method 1 docstring."""' in content
        assert '"""Method 2 docstring."""' in content
        assert 'class DstClass1:' in content
        assert 'class DstClass2:' in content


class TestDocstringPreservationExtract:
    """Tests for docstring preservation during superclass extraction."""

    def test_extract_preserves_child_class_docstrings(self, tmp_path):
        """Test that child class docstrings are preserved after extraction."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Child1:
    """Child1 docstring."""
    
    def __init__(self):
        self.prop1 = 1
    
    def method(self):
        """Method docstring."""
        return 1

class Child2:
    """Child2 docstring."""
    
    def __init__(self):
        self.prop1 = 1
    
    def method(self):
        """Method docstring."""
        return 2
'''
        )

        config = {
            "base_class": "Base",
            "child_classes": ["Child1", "Child2"],
            "abstract_methods": [],
            "extract_from": {
                "Child1": {
                    "properties": ["prop1"],
                    "methods": ["method"]
                },
                "Child2": {
                    "properties": ["prop1"],
                    "methods": ["method"]
                }
            }
        }

        extractor = SuperclassExtractor(test_file)
        success, message = extractor.extract_superclass(config)

        assert success, f"Extraction failed: {message}"

        content = test_file.read_text()
        
        # Check that child class docstrings are preserved
        assert '"""Child1 docstring."""' in content
        assert '"""Child2 docstring."""' in content

    def test_extract_preserves_base_class_docstring(self, tmp_path):
        """Test that base class gets appropriate docstring."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Child1:
    def __init__(self):
        self.prop1 = 1
    
    def method(self):
        """Method docstring."""
        return 1

class Child2:
    def __init__(self):
        self.prop1 = 1
    
    def method(self):
        """Method docstring."""
        return 2
'''
        )

        config = {
            "base_class": "Base",
            "child_classes": ["Child1", "Child2"],
            "abstract_methods": [],
            "extract_from": {
                "Child1": {
                    "properties": ["prop1"],
                    "methods": ["method"]
                },
                "Child2": {
                    "properties": ["prop1"],
                    "methods": ["method"]
                }
            }
        }

        extractor = SuperclassExtractor(test_file)
        success, message = extractor.extract_superclass(config)

        assert success, f"Extraction failed: {message}"

        content = test_file.read_text()
        
        # Check that base class exists
        assert 'class Base' in content

    def test_extract_preserves_method_docstrings_in_base(self, tmp_path):
        """Test that method docstrings are preserved in base class."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Child1:
    def method(self):
        """Method docstring."""
        return 1

class Child2:
    def method(self):
        """Method docstring."""
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
        success, message = extractor.extract_superclass(config)

        assert success, f"Extraction failed: {message}"

        content = test_file.read_text()
        
        # Check that method docstring is in base class
        assert '"""Method docstring."""' in content
        assert 'class Base' in content


class TestDocstringPreservationMerge:
    """Tests for docstring preservation during class merging."""

    def test_merge_preserves_source_class_docstrings(self, tmp_path):
        """Test that source class docstrings are preserved in merged class."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Source1:
    """Source1 docstring."""
    
    def method1(self):
        """Method1 docstring."""
        return 1

class Source2:
    """Source2 docstring."""
    
    def method2(self):
        """Method2 docstring."""
        return 2
'''
        )

        config = {
            "base_class": "Merged",
            "source_classes": ["Source1", "Source2"]
        }

        merger = ClassMerger(test_file)
        success, message = merger.merge_classes(config)

        assert success, f"Merge failed: {message}"

        content = test_file.read_text()
        
        # Check that merged class exists
        assert 'class Merged' in content
        # Method docstrings should be preserved
        assert '"""Method1 docstring."""' in content
        assert '"""Method2 docstring."""' in content

    def test_merge_preserves_all_method_docstrings(self, tmp_path):
        """Test that all method docstrings from source classes are preserved."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Source1:
    def method1(self):
        """Method 1 detailed docstring.
        
        This method does something.
        """
        return 1
    
    def method2(self):
        """Method 2 docstring."""
        return 2

class Source2:
    def method3(self):
        """Method 3 docstring."""
        return 3
'''
        )

        config = {
            "base_class": "Merged",
            "source_classes": ["Source1", "Source2"]
        }

        merger = ClassMerger(test_file)
        success, message = merger.merge_classes(config)

        assert success, f"Merge failed: {message}"

        content = test_file.read_text()
        
        # Check that all method docstrings are preserved
        assert '"""Method 1 detailed docstring.' in content
        assert 'This method does something.' in content
        assert '"""Method 2 docstring."""' in content
        assert '"""Method 3 docstring."""' in content


class TestCommentPreservation:
    """Tests for comment preservation during all refactoring operations."""

    def test_split_preserves_inline_comments(self, tmp_path):
        """Test that inline comments are preserved during splitting."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class SourceClass:
    def method1(self):
        x = 1  # Inline comment
        y = 2  # Another inline comment
        return x + y  # Return statement comment
'''
        )

        config = {
            "src_class": "SourceClass",
            "dst_classes": {
                "DstClass1": {
                    "props": [],
                    "methods": ["method1"]
                }
            }
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert success, f"Split failed: {message}"

        content = test_file.read_text()
        
        # Check that inline comments are preserved
        assert '# Inline comment' in content
        assert '# Another inline comment' in content
        assert '# Return statement comment' in content

    def test_split_preserves_block_comments(self, tmp_path):
        """Test that block comments are preserved during splitting."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class SourceClass:
    # Block comment before method
    def method1(self):
        # Comment inside method
        result = 1
        # Another comment
        return result
    # Comment after method
'''
        )

        config = {
            "src_class": "SourceClass",
            "dst_classes": {
                "DstClass1": {
                    "props": [],
                    "methods": ["method1"]
                }
            }
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert success, f"Split failed: {message}"

        content = test_file.read_text()
        
        # Check that block comments are preserved
        assert '# Block comment before method' in content
        assert '# Comment inside method' in content
        assert '# Another comment' in content

    def test_extract_preserves_comments(self, tmp_path):
        """Test that comments are preserved during superclass extraction."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Child1:
    # Comment in child class
    def method(self):
        # Comment in method
        return 1

class Child2:
    def method(self):
        # Comment in method
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
        success, message = extractor.extract_superclass(config)

        assert success, f"Extraction failed: {message}"

        content = test_file.read_text()
        
        # Check that comments are preserved
        assert '# Comment in child class' in content or '# Comment in method' in content

    def test_merge_preserves_comments(self, tmp_path):
        """Test that comments are preserved during class merging."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Source1:
    # Comment in source1
    def method1(self):
        # Comment in method1
        return 1

class Source2:
    def method2(self):
        # Comment in method2
        return 2
'''
        )

        config = {
            "base_class": "Merged",
            "source_classes": ["Source1", "Source2"]
        }

        merger = ClassMerger(test_file)
        success, message = merger.merge_classes(config)

        assert success, f"Merge failed: {message}"

        content = test_file.read_text()
        
        # Check that comments are preserved
        assert '# Comment in method1' in content or '# Comment in method2' in content

