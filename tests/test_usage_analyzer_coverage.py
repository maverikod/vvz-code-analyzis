"""
Additional tests for usage analyzer to achieve 90%+ coverage.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
from unittest.mock import Mock

from code_analysis.core.usage_analyzer import UsageAnalyzer, UsageVisitor


class TestUsageAnalyzerCoverage:
    """Additional tests for coverage."""

    def test_collect_definitions_with_async_methods(self, tmp_path):
        """Test collecting async method definitions."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class MyClass:
    async def async_method(self):
        pass
    
    def sync_method(self):
        pass
"""
        )

        analyzer = UsageAnalyzer()
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content)
        analyzer._collect_definitions(tree)

        assert "MyClass" in analyzer._class_methods
        assert "async_method" in analyzer._class_methods["MyClass"]
        assert "sync_method" in analyzer._class_methods["MyClass"]

    def test_visit_call_with_arguments(self):
        """Test visiting method call with arguments."""
        db = Mock()
        db.add_usage = Mock()
        visitor = UsageVisitor(db, 1, {"MyClass": {"method"}}, {})
        visitor.current_class = "MyClass"

        # Create AST for: self.method(arg1, arg2)
        call_node = ast.Call(
            func=ast.Attribute(
                value=ast.Name(id="self", ctx=ast.Load()),
                attr="method",
                ctx=ast.Load(),
            ),
            args=[
                ast.Name(id="arg1", ctx=ast.Load()),
                ast.Name(id="arg2", ctx=ast.Load()),
            ],
            keywords=[],
            lineno=5,
        )

        visitor.visit_Call(call_node)
        assert db.add_usage.called

    def test_visit_attribute_not_self(self):
        """Test visiting attribute access not on self."""
        db = Mock()
        visitor = UsageVisitor(db, 1, {}, {})
        visitor.current_class = "MyClass"

        # Create AST for: obj.attr (not self)
        attr_node = ast.Attribute(
            value=ast.Name(id="obj", ctx=ast.Load()),
            attr="attr",
            ctx=ast.Load(),
            lineno=5,
        )

        visitor.visit_Attribute(attr_node)
        # Should not call add_usage for non-self attributes
        db.add_usage.assert_not_called()

    def test_visit_call_function_not_method(self):
        """Test visiting function call (not method)."""
        db = Mock()
        visitor = UsageVisitor(db, 1, {}, {})

        # Create AST for: func()
        call_node = ast.Call(
            func=ast.Name(id="func", ctx=ast.Load()),
            args=[],
            keywords=[],
            lineno=5,
        )

        visitor.visit_Call(call_node)
        # Should not call add_usage for function calls
        db.add_usage.assert_not_called()

    def test_analyze_file_with_complex_code(self, tmp_path):
        """Test analyzing file with complex code."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class MyClass:
    def __init__(self):
        self.prop1 = 1
        self.prop2: int = 2
    
    def method1(self):
        self.method2()
        value = self.prop1
        return value
    
    def method2(self):
        pass
"""
        )

        db = Mock()
        db.add_usage = Mock()

        analyzer = UsageAnalyzer(database=db)
        analyzer.analyze_file(test_file, file_id=1)

        # Should detect both method calls and property access
        assert db.add_usage.call_count >= 2

    def test_visit_attribute_in_assignment(self):
        """Test visiting attribute in assignment context."""
        db = Mock()
        class_properties = {"MyClass": {"prop1"}}
        visitor = UsageVisitor(db, 1, {}, class_properties)
        visitor.current_class = "MyClass"

        # Create AST for: value = self.prop1
        assign_node = ast.Assign(
            targets=[ast.Name(id="value", ctx=ast.Store())],
            value=ast.Attribute(
                value=ast.Name(id="self", ctx=ast.Load()),
                attr="prop1",
                ctx=ast.Load(),
                lineno=5,
            ),
            lineno=5,
        )

        # Visit the attribute in the assignment
        visitor.visit(assign_node)
        assert db.add_usage.called

    def test_visit_call_in_expression(self):
        """Test visiting method call in expression."""
        db = Mock()
        class_methods = {"MyClass": {"method"}}
        visitor = UsageVisitor(db, 1, class_methods, {})
        visitor.current_class = "MyClass"

        # Create AST for: result = self.method() + 1
        binop_node = ast.BinOp(
            left=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="self", ctx=ast.Load()),
                    attr="method",
                    ctx=ast.Load(),
                ),
                args=[],
                keywords=[],
                lineno=5,
            ),
            op=ast.Add(),
            right=ast.Constant(value=1),
            lineno=5,
        )

        visitor.visit(binop_node)
        assert db.add_usage.called

    def test_collect_definitions_multiple_classes(self, tmp_path):
        """Test collecting definitions from multiple classes."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """class ClassA:
    def method_a(self):
        pass

class ClassB:
    def method_b(self):
        pass
"""
        )

        analyzer = UsageAnalyzer()
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content)
        analyzer._collect_definitions(tree)

        assert "ClassA" in analyzer._class_methods
        assert "ClassB" in analyzer._class_methods
        assert "method_a" in analyzer._class_methods["ClassA"]
        assert "method_b" in analyzer._class_methods["ClassB"]

    def test_visit_call_method_not_in_class(self):
        """Test visiting method call when method not in known class methods."""
        db = Mock()
        visitor = UsageVisitor(db, 1, {}, {})
        visitor.current_class = "MyClass"

        # Create AST for: self.unknown_method()
        call_node = ast.Call(
            func=ast.Attribute(
                value=ast.Name(id="self", ctx=ast.Load()),
                attr="unknown_method",
                ctx=ast.Load(),
            ),
            args=[],
            keywords=[],
            lineno=5,
        )

        visitor.visit_Call(call_node)
        # Should still call add_usage even if method not in known methods
        assert db.add_usage.called

    def test_visit_attribute_property_not_known(self):
        """Test visiting property access when property not in known properties."""
        db = Mock()
        visitor = UsageVisitor(db, 1, {}, {})
        visitor.current_class = "MyClass"

        # Create AST for: self.unknown_prop
        attr_node = ast.Attribute(
            value=ast.Name(id="self", ctx=ast.Load()),
            attr="unknown_prop",
            ctx=ast.Load(),
            lineno=5,
        )

        visitor.visit_Attribute(attr_node)
        # Should not call add_usage for unknown properties
        db.add_usage.assert_not_called()

    def test_get_context_with_parent_function(self):
        """Test getting context when parent is function."""
        db = Mock()
        visitor = UsageVisitor(db, 1, {}, {})

        # Create a function node with parent attribute
        func_node = ast.FunctionDef(
            name="test_func", args=ast.arguments(), body=[], lineno=1
        )
        call_node = ast.Call(
            func=ast.Name(id="func", ctx=ast.Load()),
            args=[],
            keywords=[],
            lineno=2,
        )
        # Manually set parent (in real AST this would be set by parent visitor)
        call_node.parent = func_node

        context = visitor._get_context(call_node)
        # Should return function name
        assert context == "test_func()"

    def test_get_context_with_parent_class(self):
        """Test getting context when parent is class."""
        db = Mock()
        visitor = UsageVisitor(db, 1, {}, {})

        class_node = ast.ClassDef(name="TestClass", body=[], lineno=1, col_offset=0)
        call_node = ast.Call(
            func=ast.Name(id="func", ctx=ast.Load()),
            args=[],
            keywords=[],
            lineno=2,
        )
        call_node.parent = class_node

        context = visitor._get_context(call_node)
        assert context == "TestClass"

    def test_get_context_no_parent(self):
        """Test getting context when no parent."""
        db = Mock()
        visitor = UsageVisitor(db, 1, {}, {})

        call_node = ast.Call(
            func=ast.Name(id="func", ctx=ast.Load()),
            args=[],
            keywords=[],
            lineno=2,
        )

        context = visitor._get_context(call_node)
        assert context is None

    def test_get_context_exception(self):
        """Test getting context when exception occurs."""
        db = Mock()
        visitor = UsageVisitor(db, 1, {}, {})

        # Create node that will cause exception
        class BadNode(ast.AST):
            pass

        bad_node = BadNode()
        context = visitor._get_context(bad_node)
        # Should return None on exception
        assert context is None
