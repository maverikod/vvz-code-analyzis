"""
Tests for improved error messages in refactoring operations.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import tempfile
from pathlib import Path
import pytest

from code_analysis.core.refactorer import ClassSplitter, format_error_message


class TestRefactorErrorMessages:
    """Tests for improved error messages."""

    def test_format_error_message_python_syntax(self):
        """Test formatting of Python syntax errors."""
        error = format_error_message(
            "python_syntax",
            "IndentationError: expected an indented block after function definition on line 19 (test.py, line 22)",
            Path("test.py")
        )
        
        assert "Рефакторинг не выполнен" in error
        assert "test.py" in error
        assert "Файл восстановлен" in error
        assert "отсутствует отступ" in error

    def test_format_error_message_config_validation(self):
        """Test formatting of configuration validation errors."""
        error = format_error_message(
            "config_validation",
            "Missing properties in split config: {'prop3'}; Missing methods in split config: {'method3'}",
            Path("test.py")
        )
        
        assert "Ошибка конфигурации" in error
        assert "test.py" in error
        assert "проверьте" in error.lower() or "проверьте" in error

    def test_format_error_message_completeness(self):
        """Test formatting of completeness validation errors."""
        error = format_error_message(
            "completeness",
            "Missing property 'prop1' in class 'ClassA'",
            Path("test.py")
        )
        
        assert "Рефакторинг не выполнен" in error
        assert "потеря данных" in error
        assert "Файл восстановлен" in error

    def test_split_class_error_message_config_validation(self, tmp_path):
        """Test that split_class returns improved error message for config validation."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            '''class LargeClass:
    def __init__(self):
        self.prop1 = None
        self.prop2 = None
        self.prop3 = None
    def method1(self):
        return "method1"
    def method2(self):
        return "method2"
    def method3(self):
        return "method3"
'''
        )

        # Incomplete config - missing prop3 and method3
        config = {
            "src_class": "LargeClass",
            "dst_classes": {
                "ClassA": {"props": ["prop1"], "methods": ["method1"]},
                "ClassB": {"props": ["prop2"], "methods": ["method2"]},
            },
        }

        splitter = ClassSplitter(test_file)
        success, message = splitter.split_class(config)

        assert not success
        assert "Ошибка конфигурации" in message or "ошибка конфигурации" in message.lower()
        assert "проверьте" in message.lower() or "проверьте" in message

