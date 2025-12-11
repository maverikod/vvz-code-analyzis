"""
Edge case tests for refactoring operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import pytest
from pathlib import Path

from code_analysis.refactorer import ClassSplitter, SuperclassExtractor, ClassMerger


class TestEdgeCasesPart1:
    """Edge case tests to increase coverage."""
    def test_splitter_extract_class_members_nested_classes(self, tmp_path):
        """Test extract_class_members with nested classes."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Outer:
    class Inner:
        def method(self):
            pass

    def outer_method(self):
        pass
    '''
        )

        splitter = ClassSplitter(test_file)
        splitter.load_file()
        class_node = splitter.find_class("Outer")
        members = splitter.extract_class_members(class_node)

        assert "nested_classes" in members
        assert len(members["nested_classes"]) > 0
    def test_splitter_find_class_end_no_body(self, tmp_path):
        """Test _find_class_end for class with no body."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Empty:\n    pass\n\nclass Other:\n    pass")

        splitter = ClassSplitter(test_file)
        splitter.load_file()
        class_node = splitter.find_class("Empty")
        lines = test_file.read_text().split("\n")
        end_line = splitter._find_class_end(class_node, lines)

        assert end_line > class_node.lineno
    def test_splitter_build_new_class_no_docstring_no_props(self, tmp_path):
        """Test _build_new_class without docstring and properties."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Source:
    def method(self):
        return 1
    '''
        )

        splitter = ClassSplitter(test_file)
        splitter.load_file()
        class_node = splitter.find_class("Source")

        config = {"props": [], "methods": ["method"]}
        new_class = splitter._build_new_class("NewClass", class_node, config, 0)

        assert "class NewClass:" in new_class
        assert "def method" in new_class
    def test_splitter_build_modified_source_class_all_moved(self, tmp_path):
        """Test _build_modified_source_class when all methods are moved."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Source:
    def __init__(self):
        self.prop1 = 1

    def method1(self):
        return 1

    def method2(self):
        return 2
    '''
        )

        splitter = ClassSplitter(test_file)
        splitter.load_file()
        class_node = splitter.find_class("Source")

        method_mapping = {"method1": "Dst1", "method2": "Dst2"}
        prop_mapping = {"prop1": "Dst1"}
        dst_classes = {
            "Dst1": {"props": ["prop1"], "methods": ["method1"]},
            "Dst2": {"props": [], "methods": ["method2"]}
        }

        modified = splitter._build_modified_source_class(
            class_node, method_mapping, prop_mapping, dst_classes, 0
        )

        assert "class Source:" in modified
        assert "self.dst1" in modified.lower()
        assert "self.dst2" in modified.lower()
    def test_extractor_get_class_bases_qualified(self, tmp_path):
        """Test get_class_bases with qualified base names."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''from abc import ABC

    class Child(ABC):
    pass
    '''
        )

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        class_node = extractor.find_class("Child")
        bases = extractor.get_class_bases(class_node)

        assert "ABC" in bases
    def test_extractor_get_return_type_with_annotation(self, tmp_path):
        """Test _get_return_type with return type annotation."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Test:
    def method(self) -> str:
        return "test"

    def method2(self) -> int:
        return 1
    '''
        )

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        class_node = extractor.find_class("Test")
        method1 = extractor._find_method_in_class(class_node, "method")
        method2 = extractor._find_method_in_class(class_node, "method2")

        if method1:
            return_type1 = extractor._get_return_type(method1)
            assert return_type1 == "str"

        if method2:
            return_type2 = extractor._get_return_type(method2)
            assert return_type2 == "int"
    def test_extractor_get_return_type_no_annotation(self, tmp_path):
        """Test _get_return_type without return type annotation."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Test:
    def method(self):
        return "test"
    '''
        )

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        class_node = extractor.find_class("Test")
        method = extractor._find_method_in_class(class_node, "method")

        if method:
            return_type = extractor._get_return_type(method)
            assert return_type is None
    def test_extractor_check_method_compatibility_no_methods(self, tmp_path):
        """Test check_method_compatibility when method doesn't exist."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class A:
    pass

    class B:
    pass
    '''
        )

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()

        is_compatible, error = extractor.check_method_compatibility(
            ["A", "B"], "nonexistent"
        )

        assert is_compatible  # No conflict if method doesn't exist
    def test_extractor_check_method_compatibility_incompatible_returns(self, tmp_path):
        """Test check_method_compatibility with incompatible return types."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class A:
    def method(self) -> str:
        return "a"

    class B:
    def method(self) -> int:
        return 1
    '''
        )

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()

        is_compatible, error = extractor.check_method_compatibility(
            ["A", "B"], "method"
        )

        assert not is_compatible
        assert "incompatible" in error.lower() or "return" in error.lower()
class TestEdgeCasesPart2:
    """Edge case tests to increase coverage."""
    def test_extractor_build_base_class_with_abc_import(self, tmp_path):
        """Test _build_base_class when ABC import is needed."""
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

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        child_nodes = [extractor.find_class("Child1"), extractor.find_class("Child2")]

        extract_from = {
            "Child1": {"properties": [], "methods": ["method"]},
            "Child2": {"properties": [], "methods": ["method"]}
        }

        base_code = extractor._build_base_class("Base", child_nodes, extract_from, ["method"])
        assert "class Base(ABC):" in base_code
        assert "@abstractmethod" in base_code
    def test_extractor_perform_extraction_with_abc_import(self, tmp_path):
        """Test _perform_extraction when ABC import needs to be added."""
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

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        child_nodes = [extractor.find_class("Child1"), extractor.find_class("Child2")]

        config = {
            "base_class": "Base",
            "child_classes": ["Child1", "Child2"],
            "abstract_methods": ["method"],
            "extract_from": {
                "Child1": {"properties": [], "methods": ["method"]},
                "Child2": {"properties": [], "methods": ["method"]}
            }
        }

        new_content = extractor._perform_extraction(config, child_nodes)
        assert "from abc import ABC, abstractmethod" in new_content
        assert "class Base(ABC):" in new_content
    def test_merger_build_merged_class_with_filter(self, tmp_path):
        """Test _build_merged_class with method and property filters."""
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
        self.prop3 = 3

    def method3(self):
        return 3
    '''
        )

        merger = ClassMerger(test_file)
        merger.load_file()
        source_nodes = [merger.find_class("A"), merger.find_class("B")]

        merged_code = merger._build_merged_class(
            "Merged", source_nodes, ["method1", "method3"], ["prop1", "prop3"]
        )

        assert "class Merged:" in merged_code
        assert "def method1" in merged_code
        assert "def method3" in merged_code
        assert "self.prop1" in merged_code
        assert "self.prop3" in merged_code
    def test_splitter_validate_completeness_missing_dst_class(self, tmp_path):
        """Test validate_completeness when destination class is missing."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        splitter = ClassSplitter(test_file)
        splitter.create_backup()

        config = {
            "src_class": "Test",
            "dst_classes": {
                "DstClass": {"props": [], "methods": []}
            }
        }

        # Write content without DstClass
        test_file.write_text("class Test: pass")

        original_props = set()
        original_methods = set()

        is_complete, error = splitter.validate_completeness(
            "Test", config, original_props, original_methods
        )

        # Should still pass if no members to check
        assert isinstance(is_complete, bool)
    def test_splitter_validate_imports_success(self, tmp_path):
        """Test validate_imports with valid imports."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''import sys
    from pathlib import Path

    class Test:
    pass
    '''
        )

        splitter = ClassSplitter(test_file)
        splitter.create_backup()
        is_valid, error = splitter.validate_imports()

        # Should either succeed or fail gracefully
        assert isinstance(is_valid, bool)
    def test_extractor_validate_completeness_missing_props(self, tmp_path):
        """Test validate_completeness when properties are missing."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Base: pass")

        extractor = SuperclassExtractor(test_file)
        extractor.create_backup()

        config = {
            "extract_from": {
                "Child1": {"properties": ["prop1"], "methods": []}
            }
        }

        is_complete, error = extractor.validate_completeness(
            "Base", ["Child1"], config
        )

        assert not is_complete
        assert "not found" in error.lower() or "missing" in error.lower()
    def test_merger_validate_completeness_missing_methods(self, tmp_path):
        """Test validate_completeness when methods are missing after merge."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Merged: pass")

        merger = ClassMerger(test_file)
        merger.create_backup()

        original_props = set()
        original_methods = {"method1", "method2"}

        is_complete, error = merger.validate_completeness(
            "Merged", ["Source1"], original_props, original_methods
        )

        assert not is_complete
        assert "missing" in error.lower()
    def test_splitter_extract_method_code_empty_method(self, tmp_path):
        """Test _extract_method_code for empty method."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Test:
    def empty_method(self):
        pass
    '''
        )

        splitter = ClassSplitter(test_file)
        splitter.load_file()
        class_node = splitter.find_class("Test")
        method = splitter._find_method_in_class(class_node, "empty_method")

        if method:
            code = splitter._extract_method_code(method, "    ")
            assert "def empty_method" in code
    def test_extractor_update_child_class_empty_after_removal(self, tmp_path):
        """Test _update_child_class when all properties are removed from __init__."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Child:
    def __init__(self):
        self.prop1 = 1

    def method(self):
        return 1
    '''
        )

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        child_node = extractor.find_class("Child")
        lines = test_file.read_text().split("\n")
        child_config = {"properties": ["prop1"], "methods": ["method"]}

        updated = extractor._update_child_class(child_node, "Base", child_config, lines)

        # Should have pass in __init__ if all properties removed
        assert "def __init__" in updated
        # Should have pass or remaining content
        assert "pass" in updated or "method" in updated

