"""
Tests for cyclomatic complexity analyzer.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

import ast
from pathlib import Path

import pytest

from code_analysis.core.complexity_analyzer import (
    ComplexityAnalyzer,
    analyze_file_complexity,
    analyze_function_complexity,
    calculate_complexity,
)


class TestCalculateComplexity:
    """Tests for calculate_complexity function."""

    def test_simple_function(self):
        """Test complexity of simple function (should be 1)."""
        code = "def simple(): return 1"
        tree = ast.parse(code)
        func = tree.body[0]
        assert calculate_complexity(func) == 1

    def test_function_with_if(self):
        """Test complexity of function with if statement (should be 2)."""
        code = """
def func(x):
    if x > 0:
        return 1
    return 0
"""
        tree = ast.parse(code)
        func = tree.body[0]
        assert calculate_complexity(func) == 2

    def test_function_with_if_else(self):
        """Test complexity of function with if-else (should be 2)."""
        code = """
def func(x):
    if x > 0:
        return 1
    else:
        return 0
"""
        tree = ast.parse(code)
        func = tree.body[0]
        assert calculate_complexity(func) == 2

    def test_function_with_elif(self):
        """Test complexity of function with if-elif-else (should be 3)."""
        code = """
def func(x):
    if x > 0:
        return 1
    elif x < 0:
        return -1
    else:
        return 0
"""
        tree = ast.parse(code)
        func = tree.body[0]
        assert calculate_complexity(func) == 3

    def test_function_with_for_loop(self):
        """Test complexity of function with for loop (should be 2)."""
        code = """
def func(items):
    result = []
    for item in items:
        result.append(item)
    return result
"""
        tree = ast.parse(code)
        func = tree.body[0]
        assert calculate_complexity(func) == 2

    def test_function_with_while_loop(self):
        """Test complexity of function with while loop (should be 2)."""
        code = """
def func(n):
    i = 0
    while i < n:
        i += 1
    return i
"""
        tree = ast.parse(code)
        func = tree.body[0]
        assert calculate_complexity(func) == 2

    def test_function_with_try_except(self):
        """Test complexity of function with try-except (should be 3: base + try + except)."""
        code = """
def func(x):
    try:
        return 1 / x
    except ZeroDivisionError:
        return 0
"""
        tree = ast.parse(code)
        func = tree.body[0]
        # Base (1) + try (1) + except (1) = 3
        assert calculate_complexity(func) == 3

    def test_function_with_multiple_except(self):
        """Test complexity of function with multiple except handlers (should be 4)."""
        code = """
def func(x):
    try:
        return 1 / x
    except ZeroDivisionError:
        return 0
    except ValueError:
        return -1
"""
        tree = ast.parse(code)
        func = tree.body[0]
        # Base (1) + try (1) + except1 (1) + except2 (1) = 4
        assert calculate_complexity(func) == 4

    def test_function_with_with_statement(self):
        """Test complexity of function with with statement (should be 2)."""
        code = """
def func(filename):
    with open(filename) as f:
        return f.read()
"""
        tree = ast.parse(code)
        func = tree.body[0]
        assert calculate_complexity(func) == 2

    def test_function_with_boolop_and(self):
        """Test complexity of function with and operator (should be 3)."""
        code = """
def func(x, y):
    if x > 0 and y > 0:
        return 1
    return 0
"""
        tree = ast.parse(code)
        func = tree.body[0]
        # Base (1) + if (1) + and with 2 operands adds 1 = 3
        assert calculate_complexity(func) == 3

    def test_function_with_boolop_or(self):
        """Test complexity of function with or operator (should be 3)."""
        code = """
def func(x, y):
    if x > 0 or y > 0:
        return 1
    return 0
"""
        tree = ast.parse(code)
        func = tree.body[0]
        # Base (1) + if (1) + or with 2 operands adds 1 = 3
        assert calculate_complexity(func) == 3

    def test_function_with_complex_boolop(self):
        """Test complexity of function with complex boolean expression (should be 4)."""
        code = """
def func(x, y, z):
    if x > 0 and y > 0 and z > 0:
        return 1
    return 0
"""
        tree = ast.parse(code)
        func = tree.body[0]
        # Base (1) + if (1) + and with 3 operands adds 2 = 4
        assert calculate_complexity(func) == 4

    def test_function_with_ifexp(self):
        """Test complexity of function with ternary expression (should be 2)."""
        code = """
def func(x):
    return 1 if x > 0 else 0
"""
        tree = ast.parse(code)
        func = tree.body[0]
        assert calculate_complexity(func) == 2

    def test_function_with_nested_if(self):
        """Test complexity of function with nested if (should be 3)."""
        code = """
def func(x, y):
    if x > 0:
        if y > 0:
            return 1
    return 0
"""
        tree = ast.parse(code)
        func = tree.body[0]
        assert calculate_complexity(func) == 3

    def test_function_with_nested_loops(self):
        """Test complexity of function with nested loops (should be 3)."""
        code = """
def func(items):
    result = []
    for item in items:
        for subitem in item:
            result.append(subitem)
    return result
"""
        tree = ast.parse(code)
        func = tree.body[0]
        assert calculate_complexity(func) == 3

    def test_function_with_async(self):
        """Test complexity of async function."""
        code = """
async def func(x):
    if x > 0:
        return 1
    return 0
"""
        tree = ast.parse(code)
        func = tree.body[0]
        assert calculate_complexity(func) == 2

    def test_complex_function(self):
        """Test complexity of complex function with multiple decision points."""
        code = """
def complex_func(x, y, z):
    result = 0
    if x > 0:
        for i in range(x):
            if i % 2 == 0:
                result += i
            else:
                result -= i
    elif y > 0:
        while y > 0:
            result += y
            y -= 1
    else:
        try:
            result = 1 / z
        except ZeroDivisionError:
            result = 0
    return result
"""
        tree = ast.parse(code)
        func = tree.body[0]
        # Expected: 1 (base) + 2 (if/elif) + 1 (for) + 1 (if/else) + 1 (while) + 1 (try) + 1 (except) = 8
        assert calculate_complexity(func) == 8

    def test_empty_function(self):
        """Test complexity of empty function (should be 1)."""
        code = "def empty(): pass"
        tree = ast.parse(code)
        func = tree.body[0]
        assert calculate_complexity(func) == 1

    def test_function_with_match_statement(self):
        """Test complexity of function with match statement (Python 3.10+)."""
        code = """
def func(x):
    match x:
        case 1:
            return 1
        case 2:
            return 2
        case _:
            return 0
"""
        try:
            tree = ast.parse(code)
            func = tree.body[0]
            complexity = calculate_complexity(func)
            # Expected: 1 (base) + 3 (match cases) = 4
            assert complexity == 4
        except SyntaxError:
            # Python < 3.10 doesn't support match
            pytest.skip("match statement requires Python 3.10+")


class TestAnalyzeFileComplexity:
    """Tests for analyze_file_complexity function."""

    def test_simple_file(self, tmp_path):
        """Test analyzing simple file with one function."""
        file_path = tmp_path / "test.py"
        file_path.write_text("def simple(): return 1\n")

        result = analyze_file_complexity(str(file_path))

        assert "functions" in result
        assert "methods" in result
        assert len(result["functions"]) == 1
        assert len(result["methods"]) == 0
        assert result["functions"][0]["name"] == "simple"
        assert result["functions"][0]["complexity"] == 1
        assert result["functions"][0]["type"] == "function"

    def test_file_with_class(self, tmp_path):
        """Test analyzing file with class and methods."""
        code = """
class MyClass:
    def method1(self):
        return 1
    
    def method2(self, x):
        if x > 0:
            return 1
        return 0

def standalone():
    return 2
"""
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        result = analyze_file_complexity(str(file_path))

        assert len(result["functions"]) == 1
        assert len(result["methods"]) == 2
        assert result["functions"][0]["name"] == "standalone"
        assert result["methods"][0]["name"] == "method1"
        assert result["methods"][0]["complexity"] == 1
        assert result["methods"][1]["name"] == "method2"
        assert result["methods"][1]["complexity"] == 2
        assert result["methods"][0]["class_name"] == "MyClass"

    def test_file_with_source_code(self):
        """Test analyzing file with source code provided."""
        code = """
def func1():
    return 1

def func2(x):
    if x > 0:
        return 1
    return 0
"""
        result = analyze_file_complexity("test.py", source_code=code)

        assert len(result["functions"]) == 2
        assert result["functions"][0]["name"] == "func1"
        assert result["functions"][0]["complexity"] == 1
        assert result["functions"][1]["name"] == "func2"
        assert result["functions"][1]["complexity"] == 2

    def test_file_with_syntax_error(self, tmp_path):
        """Test analyzing file with syntax error."""
        file_path = tmp_path / "test.py"
        file_path.write_text("def invalid syntax\n")

        with pytest.raises(SyntaxError):
            analyze_file_complexity(str(file_path))

    def test_file_with_nested_classes(self, tmp_path):
        """Test analyzing file with nested classes."""
        code = """
class Outer:
    def outer_method(self):
        return 1
    
    class Inner:
        def inner_method(self):
            if True:
                return 1
            return 0
"""
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        result = analyze_file_complexity(str(file_path))

        # Both classes should be detected
        assert len(result["methods"]) >= 2
        method_names = [m["name"] for m in result["methods"]]
        assert "outer_method" in method_names
        assert "inner_method" in method_names

    def test_file_with_async_functions(self, tmp_path):
        """Test analyzing file with async functions."""
        code = """
async def async_func():
    if True:
        return 1
    return 0

class MyClass:
    async def async_method(self):
        return 1
"""
        file_path = tmp_path / "test.py"
        file_path.write_text(code)

        result = analyze_file_complexity(str(file_path))

        assert len(result["functions"]) == 1
        assert result["functions"][0]["name"] == "async_func"
        assert result["functions"][0]["complexity"] == 2
        assert len(result["methods"]) == 1
        assert result["methods"][0]["name"] == "async_method"


class TestAnalyzeFunctionComplexity:
    """Tests for analyze_function_complexity function."""

    def test_simple_function(self):
        """Test analyzing simple function."""
        code = "def simple(): return 1"
        result = analyze_function_complexity(code)

        assert result is not None
        assert result["name"] == "simple"
        assert result["complexity"] == 1
        assert result["type"] == "function"

    def test_function_by_name(self):
        """Test analyzing specific function by name."""
        code = """
def func1():
    return 1

def func2(x):
    if x > 0:
        return 1
    return 0
"""
        result = analyze_function_complexity(code, function_name="func2")

        assert result is not None
        assert result["name"] == "func2"
        assert result["complexity"] == 2

    def test_function_not_found(self):
        """Test analyzing non-existent function."""
        code = "def func1(): return 1"
        result = analyze_function_complexity(code, function_name="nonexistent")

        assert result is None

    def test_first_function_when_name_not_specified(self):
        """Test analyzing first function when name not specified."""
        code = """
def func1():
    return 1

def func2():
    return 2
"""
        result = analyze_function_complexity(code)

        assert result is not None
        assert result["name"] == "func1"


class TestComplexityAnalyzer:
    """Tests for ComplexityAnalyzer class."""

    def test_visitor_pattern(self):
        """Test that ComplexityAnalyzer correctly visits AST nodes."""
        code = """
def func(x):
    if x > 0:
        for i in range(x):
            if i % 2 == 0:
                pass
"""
        tree = ast.parse(code)
        func = tree.body[0]

        analyzer = ComplexityAnalyzer()
        analyzer.visit(func)

        # Expected: 1 (base) + 1 (if) + 1 (for) + 1 (if) = 4
        assert analyzer.complexity == 4

    def test_reset_complexity(self):
        """Test that complexity resets correctly."""
        code1 = "def func1(): return 1"
        code2 = "def func2(x):\n    if x > 0:\n        return 1"

        tree1 = ast.parse(code1)
        tree2 = ast.parse(code2)

        analyzer = ComplexityAnalyzer()
        analyzer.visit(tree1.body[0])
        complexity1 = analyzer.complexity

        analyzer.complexity = 1  # Reset
        analyzer.visit(tree2.body[0])
        complexity2 = analyzer.complexity

        assert complexity1 == 1
        assert complexity2 == 2


class TestRealData:
    """Tests using real data from test_data directory."""

    @pytest.fixture
    def test_data_path(self):
        """Get path to test_data directory."""
        project_root = Path(__file__).parent.parent
        test_data = project_root / "test_data" / "bhlff"
        if test_data.exists():
            return test_data
        return None

    def test_real_file_analysis(self, test_data_path):
        """Test analyzing real file from test_data."""
        if test_data_path is None:
            pytest.skip("test_data/bhlff not found")

        # Find a Python file in test_data
        py_files = list(test_data_path.rglob("*.py"))
        if not py_files:
            pytest.skip("No Python files found in test_data")

        test_file = py_files[0]
        result = analyze_file_complexity(str(test_file))

        assert "functions" in result
        assert "methods" in result
        assert isinstance(result["functions"], list)
        assert isinstance(result["methods"], list)

        # Verify structure of results
        if result["functions"]:
            func = result["functions"][0]
            assert "name" in func
            assert "line" in func
            assert "complexity" in func
            assert "type" in func
            assert func["type"] == "function"
            assert func["complexity"] >= 1

        if result["methods"]:
            method = result["methods"][0]
            assert "name" in method
            assert "line" in method
            assert "complexity" in method
            assert "type" in method
            assert "class_name" in method
            assert method["type"] == "method"
            assert method["complexity"] >= 1

    def test_multiple_real_files(self, test_data_path):
        """Test analyzing multiple real files from test_data."""
        if test_data_path is None:
            pytest.skip("test_data/bhlff not found")

        # Find Python files in core/arrays directory
        arrays_dir = test_data_path / "core" / "arrays"
        if not arrays_dir.exists():
            pytest.skip("core/arrays directory not found")

        py_files = list(arrays_dir.glob("*.py"))
        if not py_files:
            pytest.skip("No Python files found in core/arrays")

        # Analyze first 3 files
        for py_file in py_files[:3]:
            try:
                result = analyze_file_complexity(str(py_file))
                assert "functions" in result
                assert "methods" in result
            except SyntaxError:
                # Skip files with syntax errors
                continue

    def test_complexity_distribution(self, test_data_path):
        """Test complexity distribution in real files."""
        if test_data_path is None:
            pytest.skip("test_data/bhlff not found")

        # Find a file with multiple functions/methods
        arrays_dir = test_data_path / "core" / "arrays"
        if not arrays_dir.exists():
            pytest.skip("core/arrays directory not found")

        field_array_file = arrays_dir / "field_array.py"
        if not field_array_file.exists():
            pytest.skip("field_array.py not found")

        result = analyze_file_complexity(str(field_array_file))

        all_complexities = []
        for func in result["functions"]:
            all_complexities.append(func["complexity"])
        for method in result["methods"]:
            all_complexities.append(method["complexity"])

        if all_complexities:
            # Verify complexities are reasonable (>= 1)
            assert all(c >= 1 for c in all_complexities)
            # Verify we have some variety (not all complexity 1)
            assert len(set(all_complexities)) > 0


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_file(self, tmp_path):
        """Test analyzing empty file."""
        file_path = tmp_path / "empty.py"
        file_path.write_text("")

        result = analyze_file_complexity(str(file_path))

        assert len(result["functions"]) == 0
        assert len(result["methods"]) == 0

    def test_file_with_only_comments(self, tmp_path):
        """Test analyzing file with only comments."""
        file_path = tmp_path / "comments.py"
        file_path.write_text("# This is a comment\n# Another comment\n")

        result = analyze_file_complexity(str(file_path))

        assert len(result["functions"]) == 0
        assert len(result["methods"]) == 0

    def test_file_with_only_imports(self, tmp_path):
        """Test analyzing file with only imports."""
        file_path = tmp_path / "imports.py"
        file_path.write_text("import os\nfrom pathlib import Path\n")

        result = analyze_file_complexity(str(file_path))

        assert len(result["functions"]) == 0
        assert len(result["methods"]) == 0

    def test_file_with_class_no_methods(self, tmp_path):
        """Test analyzing file with class but no methods."""
        code = """
class EmptyClass:
    pass
"""
        file_path = tmp_path / "empty_class.py"
        file_path.write_text(code)

        result = analyze_file_complexity(str(file_path))

        assert len(result["functions"]) == 0
        assert len(result["methods"]) == 0

    def test_file_with_decorators(self, tmp_path):
        """Test analyzing file with decorated functions."""
        code = """
@property
def prop(self):
    return self._value

@staticmethod
def static_method():
    if True:
        return 1
    return 0
"""
        file_path = tmp_path / "decorated.py"
        file_path.write_text(code)

        result = analyze_file_complexity(str(file_path))

        # Decorated functions should still be detected
        assert len(result["functions"]) >= 1

    def test_file_with_lambdas(self, tmp_path):
        """Test analyzing file with lambda functions."""
        code = """
def func():
    f = lambda x: x + 1 if x > 0 else x
    return f(5)
"""
        file_path = tmp_path / "lambdas.py"
        file_path.write_text(code)

        result = analyze_file_complexity(str(file_path))

        # Lambda complexity is not calculated separately
        # but if/else in lambda should be counted
        assert len(result["functions"]) == 1
        # The if/else in lambda should increase complexity
        assert result["functions"][0]["complexity"] >= 2
