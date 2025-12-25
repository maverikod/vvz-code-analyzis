"""
Tests for SuperclassExtractor refactoring functionality.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.core.refactorer import SuperclassExtractor


class TestSuperclassExtractorNegative:
    """Negative test cases for SuperclassExtractor."""

    def test_extract_superclass_missing_base_class(self, tmp_path):
        """Test error when base_class is not specified."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        config = {
            "child_classes": ["Test"],
            "extract_from": {"Test": {"properties": [], "methods": []}},
        }

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        is_valid, errors = extractor.validate_config(config)

        assert not is_valid
        assert any("base_class" in error.lower() for error in errors)

    def test_extract_superclass_empty_child_classes(self, tmp_path):
        """Test error when child_classes is empty."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        config = {"base_class": "Base", "child_classes": [], "extract_from": {}}

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        is_valid, errors = extractor.validate_config(config)

        assert not is_valid
        assert any("empty" in error.lower() for error in errors)

    def test_extract_superclass_child_not_in_extract_from(self, tmp_path):
        """Test error when child class is not in extract_from."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        config = {
            "base_class": "Base",
            "child_classes": ["Test", "Other"],
            "extract_from": {"Test": {"properties": [], "methods": []}},
        }

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        is_valid, errors = extractor.validate_config(config)

        assert not is_valid
        assert any("other" in error.lower() for error in errors)

    def test_extract_superclass_base_already_exists(self, tmp_path):
        """Test error when base class already exists."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class Base:
    pass

class Child:
    pass
"""
        )

        config = {
            "base_class": "Base",
            "child_classes": ["Child"],
            "extract_from": {"Child": {"properties": [], "methods": []}},
        }

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()
        is_valid, errors = extractor.validate_config(config)

        assert not is_valid
        assert any("already exists" in error.lower() for error in errors)

    def test_extract_superclass_child_not_found(self, tmp_path):
        """Test error when child class doesn't exist."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Test: pass")

        config = {
            "base_class": "Base",
            "child_classes": ["NonExistent"],
            "extract_from": {"NonExistent": {"properties": [], "methods": []}},
        }

        extractor = SuperclassExtractor(test_file)
        success, message = extractor.extract_superclass(config)

        assert not success
        assert "not found" in message.lower()

    def test_extract_superclass_multiple_inheritance_conflict(self, tmp_path):
        """Test error when child already has a base class."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class ExistingBase:
    pass

class Child(ExistingBase):
    def method(self):
        return 1
"""
        )

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()

        is_safe, error = extractor.check_multiple_inheritance_conflicts(
            ["Child"], "NewBase"
        )

        assert not is_safe
        assert "already inherits" in error.lower()

    def test_extract_superclass_incompatible_method_signatures(self, tmp_path):
        """Test error when methods have incompatible signatures."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class Child1:
    def method(self, arg1):
        return arg1

class Child2:
    def method(self, arg1, arg2):
        return arg1 + arg2
"""
        )

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()

        is_compatible, error = extractor.check_method_compatibility(
            ["Child1", "Child2"], "method"
        )

        assert not is_compatible
        assert "incompatible" in error.lower()

    def test_extract_superclass_method_not_in_all_classes(self, tmp_path):
        """Test error when method doesn't exist in all classes."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class Child1:
    def method(self):
        return 1

class Child2:
    def other_method(self):
        return 2
"""
        )

        extractor = SuperclassExtractor(test_file)
        extractor.load_file()

        is_compatible, error = extractor.check_method_compatibility(
            ["Child1", "Child2"], "method"
        )

        assert not is_compatible
        assert "not found" in error.lower()
