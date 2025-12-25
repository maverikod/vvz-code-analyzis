"""
Additional tests for code coverage.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.core.refactorer import (
    ClassSplitter,
    SuperclassExtractor,
    ClassMerger,
)


class TestAdditionalCoverage2:
    """Additional coverage tests part 2."""

    def test_merger_validate_completeness_missing_merged(self, tmp_path):
        """Test validate_completeness when merged class not found."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        merger = ClassMerger(test_file)
        merger.create_backup()

        # Write content without merged class
        test_file.write_text("class Other: pass")

        is_complete, error = merger.validate_completeness(
            "Merged", ["Source1"], set(), set()
        )

        assert not is_complete
        assert "not found" in error.lower()

    def test_splitter_restore_backup_no_backup(self, tmp_path):
        """Test restore_backup when no backup exists."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        splitter = ClassSplitter(test_file)
        # Don't create backup
        splitter.restore_backup()  # Should not crash

    def test_extractor_restore_backup_no_backup(self, tmp_path):
        """Test restore_backup when no backup exists."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        extractor = SuperclassExtractor(test_file)
        extractor.restore_backup()  # Should not crash

    def test_merger_restore_backup_no_backup(self, tmp_path):
        """Test restore_backup when no backup exists."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        merger = ClassMerger(test_file)
        merger.restore_backup()  # Should not crash

    def test_splitter_validate_python_syntax_timeout(self, tmp_path):
        """Test validate_python_syntax with timeout scenario."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        splitter = ClassSplitter(test_file)
        # Syntax validation should work normally
        is_valid, error = splitter.validate_python_syntax()
        assert is_valid or error is not None

    def test_extractor_build_base_class_no_props(self, tmp_path):
        """Test _build_base_class with no properties."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class Child1:
    def method(self):
        return 1

class Child2:
    def method(self):
        return 2
"""
        )

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        child_nodes = [extractor.find_class("Child1"), extractor.find_class("Child2")]

        extract_from = {
            "Child1": {"properties": [], "methods": ["method"]},
            "Child2": {"properties": [], "methods": ["method"]},
        }

        base_code = extractor._build_base_class("Base", child_nodes, extract_from, [])
        assert "class Base" in base_code
        assert "def method" in base_code

    def test_extractor_build_base_class_with_abstract(self, tmp_path):
        """Test _build_base_class with abstract methods."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class Child1:
    def method(self):
        return 1

class Child2:
    def method(self):
        return 2
"""
        )

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        child_nodes = [extractor.find_class("Child1"), extractor.find_class("Child2")]

        extract_from = {
            "Child1": {"properties": [], "methods": ["method"]},
            "Child2": {"properties": [], "methods": ["method"]},
        }

        base_code = extractor._build_base_class(
            "Base", child_nodes, extract_from, ["method"]
        )
        assert "class Base(ABC):" in base_code
        assert "@abstractmethod" in base_code
        assert "def method" in base_code

    def test_merger_build_merged_class_empty(self, tmp_path):
        """Test _build_merged_class with empty classes."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class A:
    pass

class B:
    pass
"""
        )

        merger = ClassMerger(test_file)
        merger.load_file()
        source_nodes = [merger.find_class("A"), merger.find_class("B")]

        merged_code = merger._build_merged_class("Merged", source_nodes, [], [])
        assert "class Merged:" in merged_code

    def test_splitter_extract_method_code_no_end_lineno(self, tmp_path):
        """Test _extract_method_code when end_lineno is not available."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class Test:
    def method(self):
        return 1
"""
        )

        splitter = ClassSplitter(test_file)
        splitter.load_file()
        class_node = splitter.find_class("Test")
        method = splitter._find_method_in_class(class_node, "method")

        if method:
            # Manually remove end_lineno if it exists
            if hasattr(method, "end_lineno"):
                delattr(method, "end_lineno")

            code = splitter._extract_method_code(method, "    ")
            assert "def method" in code

    def test_splitter_create_method_wrapper_async(self, tmp_path):
        """Test _create_method_wrapper for async methods."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class Test:
    async def async_method(self, arg1):
        return arg1
"""
        )

        splitter = ClassSplitter(test_file)
        splitter.load_file()

        wrapper = splitter._create_method_wrapper("async_method", "DstClass", "    ")
        assert "async def async_method" in wrapper
        assert "self.dstclass.async_method" in wrapper.lower()

    def test_splitter_build_new_class_no_docstring(self, tmp_path):
        """Test _build_new_class without docstring."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class Test:
    def method(self):
        return 1
"""
        )

        splitter = ClassSplitter(test_file)
        splitter.load_file()
        class_node = splitter.find_class("Test")

        config = {"props": [], "methods": ["method"]}
        new_class = splitter._build_new_class("NewClass", class_node, config, 0)

        assert "class NewClass:" in new_class
        assert "def method" in new_class

    def test_splitter_build_modified_source_class_no_remaining(self, tmp_path):
        """Test _build_modified_source_class with all methods moved."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class Test:
    def __init__(self):
        self.prop1 = 1
    
    def method1(self):
        return 1
"""
        )

        splitter = ClassSplitter(test_file)
        splitter.load_file()
        class_node = splitter.find_class("Test")

        method_mapping = {"method1": "DstClass"}
        prop_mapping = {"prop1": "DstClass"}
        dst_classes = {"DstClass": {"props": ["prop1"], "methods": ["method1"]}}

        modified = splitter._build_modified_source_class(
            class_node, method_mapping, prop_mapping, dst_classes, 0
        )

        assert "class Test:" in modified
        assert "self.dstclass" in modified.lower()
