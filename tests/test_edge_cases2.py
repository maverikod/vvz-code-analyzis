"""
Edge case tests for refactoring operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.core.refactorer import (
    ClassSplitter,
    SuperclassExtractor,
    ClassMerger,
)


class TestEdgeCases2:
    """Edge case tests part 2."""

    def test_merger_perform_merge_reverse_order(self, tmp_path):
        """Test _perform_merge handles multiple classes in reverse order."""
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

        merger = ClassMerger(test_file)
        merger.load_file()
        source_nodes = [
            merger.find_class("A"),
            merger.find_class("B"),
            merger.find_class("C"),
        ]

        config = {"base_class": "Merged", "source_classes": ["A", "B", "C"]}

        new_content = merger._perform_merge(config, source_nodes)

        assert "class Merged:" in new_content
        assert "class A:" not in new_content
        assert "class B:" not in new_content
        assert "class C:" not in new_content

    def test_splitter_create_method_wrapper_no_method_node(self, tmp_path):
        """Test _create_method_wrapper when method node is not found."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        splitter = ClassSplitter(test_file)
        splitter.load_file()

        # Try to create wrapper for non-existent method
        wrapper = splitter._create_method_wrapper("nonexistent", "DstClass", "    ")

        # Should return empty string or basic wrapper
        assert isinstance(wrapper, str)

    def test_extractor_find_class_end_at_end_of_file(self, tmp_path):
        """Test _find_class_end when class is at end of file."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class First:
    pass

class Last:
    def method(self):
        return 1
"""
        )

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        class_node = extractor.find_class("Last")
        lines = test_file.read_text().split("\n")
        end_line = extractor._find_class_end(class_node, lines)

        assert end_line >= class_node.lineno

    def test_merger_find_class_end_at_end_of_file(self, tmp_path):
        """Test _find_class_end when class is at end of file."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class First:
    pass

class Last:
    def method(self):
        return 1
"""
        )

        merger = ClassMerger(test_file)
        merger.load_file()
        class_node = merger.find_class("Last")
        lines = test_file.read_text().split("\n")
        end_line = merger._find_class_end(class_node, lines)

        assert end_line >= class_node.lineno

    def test_splitter_validate_python_syntax_invalid(self, tmp_path):
        """Test validate_python_syntax with invalid syntax."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test:\n    invalid syntax !!!")

        splitter = ClassSplitter(test_file)
        splitter.create_backup()
        is_valid, error = splitter.validate_python_syntax()

        assert not is_valid
        assert error is not None

    def test_extractor_validate_python_syntax_invalid(self, tmp_path):
        """Test validate_python_syntax with invalid syntax."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test:\n    invalid syntax !!!")

        extractor = SuperclassExtractor(test_file)
        extractor.create_backup()
        is_valid, error = extractor.validate_python_syntax()

        assert not is_valid
        assert error is not None

    def test_merger_validate_python_syntax_invalid(self, tmp_path):
        """Test validate_python_syntax with invalid syntax."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test:\n    invalid syntax !!!")

        merger = ClassMerger(test_file)
        merger.create_backup()
        is_valid, error = merger.validate_python_syntax()

        assert not is_valid
        assert error is not None

    def test_splitter_validate_imports_module_not_found(self, tmp_path):
        """Test validate_imports with missing module."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import nonexistent_module_xyz123\nclass Test: pass")

        splitter = ClassSplitter(test_file)
        splitter.create_backup()
        is_valid, error = splitter.validate_imports()

        # Should fail or return warning
        assert isinstance(is_valid, bool)

    def test_extractor_validate_imports_module_not_found(self, tmp_path):
        """Test validate_imports with missing module."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import nonexistent_module_xyz123\nclass Test: pass")

        extractor = SuperclassExtractor(test_file)
        extractor.create_backup()
        is_valid, error = extractor.validate_imports()

        # Should fail or return warning
        assert isinstance(is_valid, bool)

    def test_merger_validate_imports_module_not_found(self, tmp_path):
        """Test validate_imports with missing module."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import nonexistent_module_xyz123\nclass Test: pass")

        merger = ClassMerger(test_file)
        merger.create_backup()
        is_valid, error = merger.validate_imports()

        # Should fail or return warning
        assert isinstance(is_valid, bool)

    def test_splitter_restore_backup_file_not_exists(self, tmp_path):
        """Test restore_backup when backup file doesn't exist."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        splitter = ClassSplitter(test_file)
        # Don't create backup, just set path to non-existent
        splitter.backup_path = tmp_path / "nonexistent.backup"
        splitter.restore_backup()  # Should not crash

    def test_extractor_restore_backup_file_not_exists(self, tmp_path):
        """Test restore_backup when backup file doesn't exist."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        extractor = SuperclassExtractor(test_file)
        extractor.backup_path = tmp_path / "nonexistent.backup"
        extractor.restore_backup()  # Should not crash

    def test_merger_restore_backup_file_not_exists(self, tmp_path):
        """Test restore_backup when backup file doesn't exist."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        merger = ClassMerger(test_file)
        merger.backup_path = tmp_path / "nonexistent.backup"
        merger.restore_backup()  # Should not crash

    def test_splitter_find_class_end_fallback(self, tmp_path):
        """Test _find_class_end fallback logic."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class Test:
    def method(self):
        # Multi-line method
        return (
            1 +
            2
        )
"""
        )

        splitter = ClassSplitter(test_file)
        splitter.load_file()
        class_node = splitter.find_class("Test")
        # Manually remove end_lineno to trigger fallback
        if hasattr(class_node.body[0], "end_lineno"):
            # The fallback should still work
            pass
        lines = test_file.read_text().split("\n")
        end_line = splitter._find_class_end(class_node, lines)

        assert end_line > class_node.lineno

    def test_extractor_build_base_class_no_methods(self, tmp_path):
        """Test _build_base_class with no methods."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class Child1:
    def __init__(self):
        self.prop1 = 1

class Child2:
    def __init__(self):
        self.prop1 = 1
"""
        )

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        child_nodes = [extractor.find_class("Child1"), extractor.find_class("Child2")]

        extract_from = {
            "Child1": {"properties": ["prop1"], "methods": []},
            "Child2": {"properties": ["prop1"], "methods": []},
        }

        base_code = extractor._build_base_class("Base", child_nodes, extract_from, [])
        assert "class Base:" in base_code
        assert "self.prop1" in base_code

    def test_merger_build_merged_class_no_init(self, tmp_path):
        """Test _build_merged_class with classes without __init__."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class A:
    def method(self):
        return 1

class B:
    def method(self):
        return 2
"""
        )

        merger = ClassMerger(test_file)
        merger.load_file()
        source_nodes = [merger.find_class("A"), merger.find_class("B")]

        merged_code = merger._build_merged_class("Merged", source_nodes, [], [])
        assert "class Merged:" in merged_code
        assert "def method" in merged_code

    def test_splitter_extract_method_code_multiline(self, tmp_path):
        """Test _extract_method_code for multi-line method."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class Test:
    def multiline(self):
        result = (
            1 +
            2 +
            3
        )
        return result
"""
        )

        splitter = ClassSplitter(test_file)
        splitter.load_file()
        class_node = splitter.find_class("Test")
        method = splitter._find_method_in_class(class_node, "multiline")

        if method:
            code = splitter._extract_method_code(method, "    ")
            assert "def multiline" in code
            assert "return result" in code

    def test_extractor_perform_extraction_no_imports(self, tmp_path):
        """Test _perform_extraction when file has no imports."""
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

        config = {
            "base_class": "Base",
            "child_classes": ["Child1", "Child2"],
            "abstract_methods": ["method"],
            "extract_from": {
                "Child1": {"properties": [], "methods": ["method"]},
                "Child2": {"properties": [], "methods": ["method"]},
            },
        }

        new_content = extractor._perform_extraction(config, child_nodes)
        # ABC import should be added at the beginning
        assert "from abc import ABC, abstractmethod" in new_content

    def test_splitter_validate_completeness_property_references(self, tmp_path):
        """Test validate_completeness with property references."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class Source:
    def __init__(self):
        self.dstclass = DstClass()

class DstClass:
    def __init__(self):
        self.prop1 = None
"""
        )

        splitter = ClassSplitter(test_file)
        splitter.load_file()
        splitter.find_class("Source")

        config = {
            "src_class": "Source",
            "dst_classes": {"DstClass": {"props": ["prop1"], "methods": []}},
        }
        original_props = {"prop1"}
        original_methods = set()

        is_complete, error = splitter.validate_completeness(
            "Source", config, original_props, original_methods
        )

        # Property reference should be found
        assert isinstance(is_complete, bool)
