"""
Tests for usage analyzer.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
from unittest.mock import Mock

from code_analysis.core.usage_analyzer import UsageAnalyzer, UsageVisitor


class TestUsageAnalyzer:
    """Tests for UsageAnalyzer class."""

    def test_init(self):
        """Test UsageAnalyzer initialization."""
        analyzer = UsageAnalyzer()
        assert analyzer.database is None
        assert analyzer._class_methods == {}
        assert analyzer._class_properties == {}

    def test_init_with_database(self):
        """Test UsageAnalyzer initialization with database."""
        db = Mock()
        analyzer = UsageAnalyzer(database=db)
        assert analyzer.database == db

    def test_collect_definitions_methods(self, tmp_path):
        """Test collecting method definitions."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class MyClass:
    def method1(self):
        pass
    
    def method2(self):
        pass
"""
        )

        analyzer = UsageAnalyzer()
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content)
        analyzer._collect_definitions(tree)

        assert "MyClass" in analyzer._class_methods
        assert "method1" in analyzer._class_methods["MyClass"]
        assert "method2" in analyzer._class_methods["MyClass"]

    def test_collect_definitions_properties(self, tmp_path):
        """Test collecting property definitions."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class MyClass:
    def __init__(self):
        self.prop1 = 1
        self.prop2 = 2
"""
        )

        analyzer = UsageAnalyzer()
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content)
        analyzer._collect_definitions(tree)

        assert "MyClass" in analyzer._class_properties
        assert "prop1" in analyzer._class_properties["MyClass"]
        assert "prop2" in analyzer._class_properties["MyClass"]

    def test_collect_definitions_annotated_properties(self, tmp_path):
        """Test collecting annotated property definitions."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class MyClass:
    def __init__(self):
        self.prop1: int = 1
        self.prop2: str = "test"
"""
        )

        analyzer = UsageAnalyzer()
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content)
        analyzer._collect_definitions(tree)

        assert "MyClass" in analyzer._class_properties
        assert "prop1" in analyzer._class_properties["MyClass"]
        assert "prop2" in analyzer._class_properties["MyClass"]

    def test_collect_definitions_empty_class(self, tmp_path):
        """Test collecting definitions from empty class."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class EmptyClass:
    pass
"""
        )

        analyzer = UsageAnalyzer()
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content)
        analyzer._collect_definitions(tree)

        # Empty class should not be in dictionaries
        assert "EmptyClass" not in analyzer._class_methods
        assert "EmptyClass" not in analyzer._class_properties

    def test_analyze_file_method_calls(self, tmp_path):
        """Test analyzing file for method calls."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class MyClass:
    def method1(self):
        self.method2()
        return self.method3()
"""
        )

        db = Mock()
        db.add_usage = Mock()

        analyzer = UsageAnalyzer(database=db)
        analyzer.analyze_file(test_file, file_id=1)

        # Should detect method calls
        assert db.add_usage.called

    def test_analyze_file_attribute_access(self, tmp_path):
        """Test analyzing file for attribute access."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class MyClass:
    def __init__(self):
        self.prop1 = 1
    
    def method(self):
        value = self.prop1
        return value
"""
        )

        db = Mock()
        db.add_usage = Mock()

        analyzer = UsageAnalyzer(database=db)
        analyzer.analyze_file(test_file, file_id=1)

        # Should detect property access
        assert db.add_usage.called

    def test_analyze_file_no_file_id(self, tmp_path):
        """Test analyzing file without file_id."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class MyClass:
    def method(self):
        pass
"""
        )

        db = Mock()
        analyzer = UsageAnalyzer(database=db)
        analyzer.analyze_file(test_file, file_id=None)

        # Should not call database without file_id
        db.add_usage.assert_not_called()

    def test_analyze_file_syntax_error(self, tmp_path):
        """Test handling syntax errors."""
        test_file = tmp_path / "test.py"
        test_file.write_text("invalid syntax here !!!")

        db = Mock()
        analyzer = UsageAnalyzer(database=db)
        # Should not raise, just log warning
        analyzer.analyze_file(test_file, file_id=1)

    def test_analyze_file_missing_file(self, tmp_path):
        """Test handling missing file."""
        missing_file = tmp_path / "missing.py"

        db = Mock()
        analyzer = UsageAnalyzer(database=db)
        # Should not raise, just log warning
        analyzer.analyze_file(missing_file, file_id=1)


class TestUsageVisitor:
    """Tests for UsageVisitor class."""

    def test_visit_class_def(self):
        """Test visiting class definition."""
        db = Mock()
        visitor = UsageVisitor(db, 1, {}, {})
        node = ast.ClassDef(name="TestClass", body=[], lineno=1, col_offset=0)

        visitor.visit_ClassDef(node)
        # After visiting, current_class should be restored to None (was None before)
        assert visitor.current_class is None

    def test_visit_class_def_nested(self):
        """Test visiting nested class definitions."""
        db = Mock()
        visitor = UsageVisitor(db, 1, {}, {})

        # Create nested structure
        inner = ast.ClassDef(name="Inner", body=[], lineno=2, col_offset=0)
        outer = ast.ClassDef(name="Outer", body=[inner], lineno=1, col_offset=0)

        visitor.visit_ClassDef(outer)
        # After visiting, current_class should be restored
        assert visitor.current_class is None

    def test_visit_call_method_on_self(self):
        """Test visiting method call on self."""
        db = Mock()
        class_methods = {"MyClass": {"method1"}}
        visitor = UsageVisitor(db, 1, class_methods, {})
        visitor.current_class = "MyClass"

        # Create AST for: self.method1()
        call_node = ast.Call(
            func=ast.Attribute(
                value=ast.Name(id="self", ctx=ast.Load()),
                attr="method1",
                ctx=ast.Load(),
            ),
            args=[],
            keywords=[],
            lineno=5,
        )

        visitor.visit_Call(call_node)
        assert db.add_usage.called
        call_args = db.add_usage.call_args
        assert call_args[1]["target_name"] == "method1"
        assert call_args[1]["target_class"] == "MyClass"
        assert call_args[1]["usage_type"] == "method_call"

    def test_visit_call_method_on_variable(self):
        """Test visiting method call on variable."""
        db = Mock()
        visitor = UsageVisitor(db, 1, {}, {})

        # Create AST for: obj.method()
        call_node = ast.Call(
            func=ast.Attribute(
                value=ast.Name(id="obj", ctx=ast.Load()),
                attr="method",
                ctx=ast.Load(),
            ),
            args=[],
            keywords=[],
            lineno=5,
        )

        visitor.visit_Call(call_node)
        assert db.add_usage.called
        call_args = db.add_usage.call_args
        assert call_args[1]["target_name"] == "method"

    def test_visit_attribute_self_property(self):
        """Test visiting attribute access on self."""
        db = Mock()
        class_properties = {"MyClass": {"prop1"}}
        visitor = UsageVisitor(db, 1, {}, class_properties)
        visitor.current_class = "MyClass"

        # Create AST for: self.prop1
        attr_node = ast.Attribute(
            value=ast.Name(id="self", ctx=ast.Load()),
            attr="prop1",
            ctx=ast.Load(),
            lineno=5,
        )

        visitor.visit_Attribute(attr_node)
        assert db.add_usage.called
        call_args = db.add_usage.call_args
        assert call_args[1]["target_name"] == "prop1"
        assert call_args[1]["target_class"] == "MyClass"
        assert call_args[1]["usage_type"] == "attribute_access"

    def test_visit_attribute_not_property(self):
        """Test visiting attribute that is not a known property."""
        db = Mock()
        visitor = UsageVisitor(db, 1, {}, {})
        visitor.current_class = "MyClass"

        # Create AST for: self.unknown
        attr_node = ast.Attribute(
            value=ast.Name(id="self", ctx=ast.Load()),
            attr="unknown",
            ctx=ast.Load(),
            lineno=5,
        )

        visitor.visit_Attribute(attr_node)
        # Should not call add_usage for unknown properties
        db.add_usage.assert_not_called()

    def test_visit_call_chained(self):
        """Test visiting chained method call."""
        db = Mock()
        visitor = UsageVisitor(db, 1, {}, {})
        visitor.current_class = "MyClass"

        # Create AST for: self.obj.method()
        call_node = ast.Call(
            func=ast.Attribute(
                value=ast.Attribute(
                    value=ast.Name(id="self", ctx=ast.Load()),
                    attr="obj",
                    ctx=ast.Load(),
                ),
                attr="method",
                ctx=ast.Load(),
            ),
            args=[],
            keywords=[],
            lineno=5,
        )

        visitor.visit_Call(call_node)
        assert db.add_usage.called

    def test_get_context(self):
        """Test getting context for usage."""
        db = Mock()
        visitor = UsageVisitor(db, 1, {}, {})

        node = ast.Call(
            func=ast.Name(id="func", ctx=ast.Load()),
            args=[],
            keywords=[],
            lineno=5,
        )

        # Context might be None if parent not set
        context = visitor._get_context(node)
        # Should not raise
        assert context is None or isinstance(context, str)

    def test_database_error_handling(self, tmp_path):
        """Test handling database errors gracefully."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class MyClass:
    def method(self):
        self.method()
"""
        )

        db = Mock()
        db.add_usage = Mock(side_effect=Exception("DB error"))

        analyzer = UsageAnalyzer(database=db)
        # Should not raise, just log
        analyzer.analyze_file(test_file, file_id=1)
