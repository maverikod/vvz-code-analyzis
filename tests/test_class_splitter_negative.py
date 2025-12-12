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

from code_analysis.core.refactorer import ClassSplitter


class TestClassSplitterNegative:
    """Negative test cases for ClassSplitter."""

    def test_split_class_missing_src_class(self, tmp_path):
        """Test error when source class is not specified."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        config = {}

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert not success
        assert "not specified" in message.lower()

    def test_split_class_class_not_found(self, tmp_path):
        """Test error when source class doesn't exist."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        config = {"src_class": "NonExistentClass", "dst_classes": {}}

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert not success
        assert "not found" in message.lower()

    def test_split_class_missing_properties(self, tmp_path):
        """Test error when properties are missing from config."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Test:
    def __init__(self):
        self.prop1 = 1
        self.prop2 = 2
'''
        )

        config = {
            "src_class": "Test",
            "dst_classes": {
                "TestA": {
                    "props": ["prop1"],  # prop2 missing
                    "methods": []
                }
            }
        }

        splitter = ClassSplitter(test_file)
        splitter.load_file()
        src_class = splitter.find_class("Test")
        is_valid, errors = splitter.validate_split_config(src_class, config)

        assert not is_valid
        assert any("missing" in error.lower() and "prop" in error.lower() for error in errors)

    def test_split_class_missing_methods(self, tmp_path):
        """Test error when methods are missing from config."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Test:
    def method1(self):
        pass
    
    def method2(self):
        pass
'''
        )

        config = {
            "src_class": "Test",
            "dst_classes": {
                "TestA": {
                    "props": [],
                    "methods": ["method1"]  # method2 missing
                }
            }
        }

        splitter = ClassSplitter(test_file)
        splitter.load_file()
        src_class = splitter.find_class("Test")
        is_valid, errors = splitter.validate_split_config(src_class, config)

        assert not is_valid
        assert any("missing" in error.lower() and "method" in error.lower() for error in errors)

    def test_split_class_extra_properties(self, tmp_path):
        """Test error when config has properties not in class."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Test:
    def __init__(self):
        self.prop1 = 1
'''
        )

        config = {
            "src_class": "Test",
            "dst_classes": {
                "TestA": {
                    "props": ["prop1", "nonexistent_prop"],
                    "methods": []
                }
            }
        }

        splitter = ClassSplitter(test_file)
        splitter.load_file()
        src_class = splitter.find_class("Test")
        is_valid, errors = splitter.validate_split_config(src_class, config)

        assert not is_valid
        assert any("extra" in error.lower() and "prop" in error.lower() for error in errors)

    def test_split_class_extra_methods(self, tmp_path):
        """Test error when config has methods not in class."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class Test:
    def method1(self):
        pass
'''
        )

        config = {
            "src_class": "Test",
            "dst_classes": {
                "TestA": {
                    "props": [],
                    "methods": ["method1", "nonexistent_method"]
                }
            }
        }

        splitter = ClassSplitter(test_file)
        splitter.load_file()
        src_class = splitter.find_class("Test")
        is_valid, errors = splitter.validate_split_config(src_class, config)

        assert not is_valid
        assert any("extra" in error.lower() and "method" in error.lower() for error in errors)

    def test_split_class_invalid_syntax_rollback(self, tmp_path):
        """Test that invalid syntax causes rollback."""
        test_file = tmp_path / "test.py"
        original_content = '''class Test:
    def __init__(self):
        self.x = 1
    
    def method1(self):
        return 1
'''
        test_file.write_text(original_content)

        # Create a config that might cause issues
        # We'll manually corrupt the file after split to test rollback
        config = {
            "src_class": "Test",
            "dst_classes": {
                "TestA": {
                    "props": [],
                    "methods": ["method1"]
                }
            }
        }

        splitter = ClassSplitter(test_file)
        splitter.create_backup()
        splitter.load_file()
        src_class = splitter.find_class("Test")
        
        # Perform split
        new_content = splitter._perform_split(src_class, config)
        
        # Corrupt the content to cause syntax error
        corrupted_content = new_content + "\n    invalid syntax here !!!"
        test_file.write_text(corrupted_content)

        # Try to validate - should fail and rollback
        is_valid, error_msg = splitter.validate_python_syntax()
        assert not is_valid

        # Manually restore to test restore_backup
        splitter.restore_backup()
        restored_content = test_file.read_text()
        assert restored_content == original_content

    def test_split_class_file_not_found(self):
        """Test error when file doesn't exist."""
        non_existent = Path("/nonexistent/path/test.py")
        
        with pytest.raises(FileNotFoundError):
            ClassSplitter(non_existent)
