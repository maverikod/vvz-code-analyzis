"""
Tests for ClassMerger refactoring functionality.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import pytest
from pathlib import Path

from code_analysis.core.refactorer import ClassMerger


class TestClassMergerNegative:
    """Negative test cases for ClassMerger."""

    def test_merge_classes_missing_base_class(self, tmp_path):
        """Test error when base_class is not specified."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        config = {"source_classes": ["Test"]}

        merger = ClassMerger(test_file)
        merger.load_file()
        is_valid, errors = merger.validate_config(config)

        assert not is_valid
        assert any("base_class" in error.lower() for error in errors)

    def test_merge_classes_empty_source_classes(self, tmp_path):
        """Test error when source_classes is empty."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        config = {"base_class": "Merged", "source_classes": []}

        merger = ClassMerger(test_file)
        merger.load_file()
        is_valid, errors = merger.validate_config(config)

        assert not is_valid
        assert any("empty" in error.lower() for error in errors)

    def test_merge_classes_base_already_exists(self, tmp_path):
        """Test error when base class already exists."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class Merged:
    pass

class Source:
    pass
"""
        )

        config = {"base_class": "Merged", "source_classes": ["Source"]}

        merger = ClassMerger(test_file)
        merger.load_file()
        is_valid, errors = merger.validate_config(config)

        assert not is_valid
        assert any("already exists" in error.lower() for error in errors)

    def test_merge_classes_source_not_found(self, tmp_path):
        """Test error when source class doesn't exist."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        config = {"base_class": "Merged", "source_classes": ["NonExistent"]}

        merger = ClassMerger(test_file)
        success, message = merger.merge_classes(config)

        assert not success
        assert "not found" in message.lower()

    def test_merge_classes_file_not_found(self):
        """Test error when file doesn't exist."""
        non_existent = Path("/nonexistent/path/test.py")

        with pytest.raises(FileNotFoundError):
            ClassMerger(non_existent)

    def test_merge_classes_invalid_syntax_rollback(self, tmp_path):
        """Test that invalid syntax causes rollback."""
        test_file = tmp_path / "test.py"
        original_content = """class A:
    def method(self):
        return 1

class B:
    def method(self):
        return 2
"""
        test_file.write_text(original_content)

        config = {"base_class": "Merged", "source_classes": ["A", "B"]}

        merger = ClassMerger(test_file)
        merger.create_backup()

        # Manually corrupt after merge to test rollback
        merger.load_file()
        source_nodes = [merger.find_class("A"), merger.find_class("B")]
        new_content = merger._perform_merge(config, source_nodes)

        # Corrupt content
        corrupted_content = new_content + "\n    invalid syntax !!!"
        test_file.write_text(corrupted_content)

        # Validate should fail
        is_valid, error_msg = merger.validate_python_syntax()
        assert not is_valid

        # Restore backup
        merger.restore_backup()
        restored_content = test_file.read_text()
        assert restored_content == original_content
