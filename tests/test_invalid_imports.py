import sys
import textwrap
from pathlib import Path

import ast
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from code_analysis.analyzer import CodeAnalyzer
from code_analysis.issue_detector import IssueDetector


class AnalysisEnv:
    def __init__(self, root_dir):
        self.root_dir = root_dir

    def create_file(self, relative_path, content=""):
        file_path = self.root_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def run_analysis(self, relative_path, content):
        output_dir = self.root_dir / "test_output"
        analyzer = CodeAnalyzer(
            root_dir=str(self.root_dir),
            output_dir=str(output_dir),
            max_lines=400,
        )
        issue_detector = IssueDetector(analyzer.issues, analyzer.root_dir)
        analyzer.issue_detector = issue_detector

        file_path = self.create_file(relative_path, textwrap.dedent(content))
        analyzer.analyze_file(file_path)
        return analyzer.issues["invalid_imports"]


@pytest.fixture
def analysis_env(tmp_path):
    return AnalysisEnv(tmp_path)


def _has_issue(issues, *, module, issue_type):
    return any(
        issue.get("module") == module and issue.get("type") == issue_type
        for issue in issues
    )


def _no_invalid_imports(issues):
    return len(issues) == 0


def _create_issue_detector():
    return IssueDetector({
        "any_type_usage": [],
        "generic_exception_usage": [],
        "imports_in_middle": [],
        "invalid_imports": [],
    })


def _run_method_detector(source):
    tree = ast.parse(textwrap.dedent(source))
    func_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
    detector = _create_issue_detector()
    detector.check_method_issues(func_node, file_path="sample.py", class_name="Sample")
    return detector.issues


def test_import_nonexistent_module(analysis_env):
    issues = analysis_env.run_analysis(
        "module.py",
        """
        import totally_missing_module
        """,
    )

    assert _has_issue(
        issues,
        module="totally_missing_module",
        issue_type="import",
    )


def test_from_nonexistent_module_import(analysis_env):
    issues = analysis_env.run_analysis(
        "module.py",
        """
        from ghost_package import phantom
        """,
    )

    assert _has_issue(
        issues,
        module="ghost_package",
        issue_type="import_from",
    )


def test_relative_import_missing_module_in_package(analysis_env):
    analysis_env.create_file("pkg/__init__.py", "")

    issues = analysis_env.run_analysis(
        "pkg/module.py",
        """
        from . import missing_submodule
        """,
    )

    assert _has_issue(
        issues,
        module=".missing_submodule",
        issue_type="import_from_relative",
    )


def test_relative_import_missing_nested_module(analysis_env):
    analysis_env.create_file("pkg/__init__.py", "")
    analysis_env.create_file("pkg/sub/__init__.py", "")

    issues = analysis_env.run_analysis(
        "pkg/sub/module.py",
        """
        from ..unknown_package import value
        """,
    )

    assert _has_issue(
        issues,
        module="..unknown_package",
        issue_type="import_from_relative",
    )


def test_relative_import_exceeding_package_root(analysis_env):
    analysis_env.create_file("pkg/__init__.py", "")

    issues = analysis_env.run_analysis(
        "pkg/module.py",
        """
        from ...ghost import entity
        """,
    )

    assert _has_issue(
        issues,
        module="...ghost",
        issue_type="import_from_relative",
    )


def test_reports_all_invalid_imports_in_single_file(analysis_env):
    issues = analysis_env.run_analysis(
        "module.py",
        """
        import missing_one
        from nowhere import nothing
        """,
    )

    assert _has_issue(issues, module="missing_one", issue_type="import")
    assert _has_issue(issues, module="nowhere", issue_type="import_from")


def test_standard_library_import_not_flagged(analysis_env):
    issues = analysis_env.run_analysis(
        "module.py",
        """
        import sys
        from pathlib import Path
        """,
    )

    assert _no_invalid_imports(issues)


def test_local_module_import_not_flagged(analysis_env):
    analysis_env.create_file("pkg/__init__.py", "")
    analysis_env.create_file(
        "pkg/utils.py",
        """
        def helper():
            return 42
        """,
    )

    issues = analysis_env.run_analysis(
        "pkg/main.py",
        """
        import pkg.utils
        from pkg import utils
        """,
    )

    assert _no_invalid_imports(issues)


def test_relative_import_within_package_not_flagged(analysis_env):
    analysis_env.create_file("pkg/__init__.py", "")
    analysis_env.create_file("pkg/sub/__init__.py", "")
    analysis_env.create_file(
        "pkg/sub/util.py",
        """
        CONSTANT = 1
        """,
    )

    issues = analysis_env.run_analysis(
        "pkg/sub/module.py",
        """
        from . import util
        from ..sub import util as util_alias
        """,
    )

    assert _no_invalid_imports(issues)


def test_any_type_usage_detected():
    issues = _run_method_detector(
        """
        from typing import Any

        def example(value: Any) -> Any:
            return value
        """
    )

    any_issues = issues["any_type_usage"]
    assert len(any_issues) == 2
    issue_types = {issue["type"] for issue in any_issues}
    assert issue_types == {"parameter", "return_type"}


def test_generic_exception_patterns_detected():
    issues = _run_method_detector(
        """
        import builtins

        def handler():
            try:
                raise Exception("bad call")
            except builtins.Exception:
                pass
            except Exception:
                pass
            except:
                pass
            raise Exception
        """
    )

    descriptions = [issue["type"] for issue in issues["generic_exception_usage"]]
    assert "except_clause" in descriptions
    assert "bare_except" in descriptions
    assert descriptions.count("raise_exception") >= 2


def test_specific_exception_not_flagged():
    issues = _run_method_detector(
        """
        def safe_handler():
            try:
                raise ValueError("bad")
            except ValueError:
                raise RuntimeError("wrap")
        """
    )

    assert issues["generic_exception_usage"] == []


def test_check_imports_in_middle_records_issue():
    detector = _create_issue_detector()
    detector.check_imports_in_middle("sample.py", 42)

    assert detector.issues["imports_in_middle"] == [
        {"file": "sample.py", "line": 42}
    ]

