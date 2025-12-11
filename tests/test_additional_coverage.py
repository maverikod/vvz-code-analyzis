"""
Additional tests for code coverage.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
import pytest
from pathlib import Path

from code_analysis.refactorer import ClassSplitter, SuperclassExtractor, ClassMerger


class TestAdditionalCoverage:
    """Additional tests to increase code coverage."""

    def test_splitter_extract_class_members(self, tmp_path):
        """Test extract_class_members method."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Test:
    def method(self):
        pass
    
    class Nested:
        pass
'''
        )

        splitter = ClassSplitter(test_file)
        splitter.load_file()
        class_node = splitter.find_class("Test")
        members = splitter.extract_class_members(class_node)

        assert "methods" in members
        assert "nested_classes" in members
        assert len(members["methods"]) > 0

    def test_splitter_find_class_end(self, tmp_path):
        """Test _find_class_end method."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Test:
    def method(self):
        pass

class Other:
    pass
'''
        )

        splitter = ClassSplitter(test_file)
        splitter.load_file()
        class_node = splitter.find_class("Test")
        lines = test_file.read_text().split("\n")
        end_line = splitter._find_class_end(class_node, lines)

        assert end_line > class_node.lineno

    def test_splitter_get_indent(self, tmp_path):
        """Test _get_indent method."""
        test_file = tmp_path / "dummy.py"
        test_file.write_text("class Test: pass")
        splitter = ClassSplitter(test_file)
        assert splitter._get_indent("    test") == 4
        assert splitter._get_indent("test") == 0

    def test_splitter_validate_imports_warning(self, tmp_path):
        """Test validate_imports with missing dependencies."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''import nonexistent_module

class Test:
    pass
'''
        )

        splitter = ClassSplitter(test_file)
        splitter.create_backup()
        is_valid, error = splitter.validate_imports()
        # Should fail or warn, but not crash
        assert isinstance(is_valid, bool)

    def test_extractor_get_class_bases(self, tmp_path):
        """Test get_class_bases method."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Child(Base1, Base2):
    pass
'''
        )

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        class_node = extractor.find_class("Child")
        bases = extractor.get_class_bases(class_node)

        assert "Base1" in bases
        assert "Base2" in bases

    def test_extractor_get_return_type(self, tmp_path):
        """Test _get_return_type method."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Test:
    def method(self) -> str:
        return "test"
'''
        )

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        class_node = extractor.find_class("Test")
        method = extractor._find_method_in_class(class_node, "method")
        
        if method:
            return_type = extractor._get_return_type(method)
            assert return_type == "str"

    def test_extractor_find_class_end(self, tmp_path):
        """Test _find_class_end in extractor."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Test:
    def method(self):
        pass
'''
        )

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        class_node = extractor.find_class("Test")
        lines = test_file.read_text().split("\n")
        end_line = extractor._find_class_end(class_node, lines)

        assert end_line > class_node.lineno

    def test_merger_extract_init_properties(self, tmp_path):
        """Test extract_init_properties in merger."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Test:
    def __init__(self):
        self.prop1 = 1
        self.prop2 = 2
'''
        )

        merger = ClassMerger(test_file)
        merger.load_file()
        class_node = merger.find_class("Test")
        props = merger.extract_init_properties(class_node)

        assert "prop1" in props
        assert "prop2" in props

    def test_merger_find_class_end(self, tmp_path):
        """Test _find_class_end in merger."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Test:
    def method(self):
        pass
'''
        )

        merger = ClassMerger(test_file)
        merger.load_file()
        class_node = merger.find_class("Test")
        lines = test_file.read_text().split("\n")
        end_line = merger._find_class_end(class_node, lines)

        assert end_line > class_node.lineno

    def test_splitter_validate_completeness_missing_class(self, tmp_path):
        """Test validate_completeness when class not found."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        splitter = ClassSplitter(test_file)
        splitter.create_backup()
        splitter.load_file()
        
        config = {"src_class": "Test", "dst_classes": {}}
        original_props = set()
        original_methods = set()
        
        # Manually write invalid content
        test_file.write_text("class Other: pass")
        
        is_complete, error = splitter.validate_completeness(
            "Test", config, original_props, original_methods
        )
        
        assert not is_complete
        assert "not found" in error.lower()

    def test_extractor_validate_completeness_missing_base(self, tmp_path):
        """Test validate_completeness when base class not found."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        extractor = SuperclassExtractor(test_file)
        extractor.create_backup()
        
        # Write content without base class
        test_file.write_text("class Other: pass")
        
        is_complete, error = extractor.validate_completeness(
            "Base", ["Child1"], {}
        )
        
        assert not is_complete
        assert "not found" in error.lower()

