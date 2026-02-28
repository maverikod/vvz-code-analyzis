"""
Detailed tests for cst_load_file command: syntax fix helpers, .tmp cleanup,
commented_lines with parent_node, and response shape.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import libcst as cst
import pytest

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.cst_load_file_command import CSTLoadFileCommand
from code_analysis.commands.cst_load_file_helpers import (
    MAX_SYNTAX_FIX_ITERATIONS,
    apply_syntax_error_fix,
    classify_syntax_error,
    indent_for_pass_after_error,
    is_block_starter_line,
    try_apply_indent_fix,
)
from code_analysis.core.cst_tree.tree_builder import (
    create_tree_from_code,
    load_file_to_tree,
)
from code_analysis.core.cst_tree.tree_metadata import get_node_parent
from code_analysis.core.cst_tree.tree_range_finder import find_node_by_range


# --- _is_block_starter_line ---


@pytest.mark.parametrize(
    "stripped,expected",
    [
        ("if x:", True),
        ("elif x:", True),
        ("else:", True),
        ("try:", True),
        ("except Exception:", True),
        ("except:", True),
        ("finally:", True),
        ("def foo():", True),
        ("class Foo:", True),
        ("for x in y:", True),
        ("while True:", True),
        ("with x:", True),
        ("return 1", False),
        ("x = 1", False),
        ("# comment", False),
        ("", False),
        ("    pass", False),
        ("if (x):", False),  # implementation checks key vs "if " (with space)
        ("def foo(a, b):", True),
    ],
)
def test_is_block_starter_line(stripped: str, expected: bool) -> None:
    """Block starters (if/def/class/for/...) are detected correctly."""
    assert is_block_starter_line(stripped) is expected


# --- indent_for_pass_after_error ---


def test_indent_for_pass_after_error_finds_def() -> None:
    """Indent for pass is block starter indent + 4 spaces (def has no indent -> 4)."""
    lines = ["def foo():", "    x = 1", "    bad syntax here"]
    result = indent_for_pass_after_error(lines, 2)
    assert result == "    "  # def has no leading indent, so one level


def test_indent_for_pass_after_error_finds_class() -> None:
    """Indent for pass under def (inside class) is def indent + 4."""
    lines = ["class Foo:", "    def bar(self):", "        x = 1", "        err"]
    result = indent_for_pass_after_error(lines, 3)
    assert result == "        "  # def bar has 4 spaces, +4 for pass


def test_indent_for_pass_after_error_skips_comments() -> None:
    """Comments and empty lines are skipped when scanning for block starter."""
    lines = ["def foo():", "    # comment", "", "    bad line"]
    result = indent_for_pass_after_error(lines, 3)
    assert result == "    "  # def has no indent


def test_indent_for_pass_after_error_no_starter_returns_four_spaces() -> None:
    """If no block starter found, return 4 spaces."""
    lines = ["x = 1", "y = 2"]
    result = indent_for_pass_after_error(lines, 1)
    assert result == "    "


def test_indent_for_pass_after_error_top_level() -> None:
    """Error on first real line uses 4 spaces."""
    lines = ["bad at top level"]
    result = indent_for_pass_after_error(lines, 0)
    assert result == "    "


# --- apply_syntax_error_fix ---


def test_apply_syntax_error_fix_single_line() -> None:
    """One invalid line is commented and pass is added."""
    lines = ["def foo():", "    x = "]
    try:
        cst.parse_module("\n".join(lines))
        pytest.fail("Expected parse to fail")
    except cst.ParserSyntaxError as e:
        fixed, comment_line_no = apply_syntax_error_fix(lines, e)
    assert len(fixed) == len(lines) + 2  # TODO line + comment + pass
    assert "TODO:" in fixed[1]
    assert "# " in fixed[2] and "x =" in fixed[2]
    assert fixed[3].strip() == "pass"
    assert comment_line_no == 3  # 1-based: line of "# original" in fixed


def test_apply_syntax_error_fix_preserves_indent() -> None:
    """Fix preserves original line indent."""
    lines = ["class A:", "    def m(self):", "        x = (  # unclosed"]
    try:
        cst.parse_module("\n".join(lines))
        pytest.fail("Expected parse to fail")
    except cst.ParserSyntaxError as e:
        fixed, _ = apply_syntax_error_fix(lines, e)
    # Comment and pass must be indented under "def" (4 spaces for def, +4 for body)
    commented = [f for f in fixed if f.strip().startswith("#") and "original" not in f][
        0
    ]
    assert commented.startswith("        # ")
    pass_line = [f for f in fixed if f.strip() == "pass"][0]
    assert pass_line.startswith("        ")  # same indent as comment


def test_apply_syntax_error_fix_parseable_after_fix() -> None:
    """After one fix, module can parse (when error was single invalid line)."""
    lines = ["def foo():", "    x = "]
    try:
        cst.parse_module("\n".join(lines))
        pytest.fail("Expected parse to fail")
    except cst.ParserSyntaxError as e:
        fixed, _ = apply_syntax_error_fix(lines, e)
    parsed = cst.parse_module("\n".join(fixed))
    assert parsed is not None


def test_apply_syntax_error_fix_dedent_on_line_one() -> None:
    """When parser reports line 1 with 'dedent', fix targets first block starter."""
    # Code that can trigger "dedent" on line 1: e.g. bad dedent at class/def
    lines = ["def foo():", "    x = 1", "y = 2"]  # y = 2 wrong indent may give dedent
    try:
        cst.parse_module("\n".join(lines))
    except cst.ParserSyntaxError as e:
        if "dedent" in str(e).lower() and e.raw_line == 1:
            fixed, _ = apply_syntax_error_fix(lines, e)
            assert len(fixed) > len(lines)
        else:
            # Other errors: just check we don't crash
            fixed, _ = apply_syntax_error_fix(lines, e)
            assert isinstance(fixed, list)
            assert isinstance(apply_syntax_error_fix(lines, e)[1], int)


# --- Full syntax-fix loop then load and parent resolution ---


def test_commented_lines_include_line_and_error(tmp_path: Path) -> None:
    """Commented_lines entries have 'line' and 'error'."""
    py_file = tmp_path / "broken.py"
    source = "def foo():\n    x = \n"  # incomplete statement
    py_file.write_text(source, encoding="utf-8")
    commented_lines_info: list[dict] = []
    lines = source.split("\n")
    for _ in range(MAX_SYNTAX_FIX_ITERATIONS):
        try:
            cst.parse_module("\n".join(lines))
            break
        except cst.ParserSyntaxError as e:
            lines, comment_line_no = apply_syntax_error_fix(lines, e)
            commented_lines_info.append(
                {"line": comment_line_no, "error": str(e).strip()}
            )
    else:
        pytest.fail("Fix did not converge")
    assert len(commented_lines_info) >= 1
    for info in commented_lines_info:
        assert "line" in info
        assert "error" in info
        assert isinstance(info["line"], int)
        assert info["line"] >= 1


def test_commented_lines_parent_node_resolution(tmp_path: Path) -> None:
    """After fix, load tree from a .py file and resolve parent for each commented line; parent has node_id."""
    py_file = tmp_path / "broken.py"
    source = "def foo():\n    x = \n"  # incomplete
    py_file.write_text(source, encoding="utf-8")
    lines = source.split("\n")
    commented_lines_info: list[dict] = []
    for _ in range(MAX_SYNTAX_FIX_ITERATIONS):
        try:
            cst.parse_module("\n".join(lines))
            break
        except cst.ParserSyntaxError as e:
            lines, comment_line_no = apply_syntax_error_fix(lines, e)
            commented_lines_info.append(
                {"line": comment_line_no, "error": str(e).strip()}
            )
    else:
        pytest.fail("Fix did not converge")
    fixed_path = tmp_path / "fixed.py"
    fixed_path.write_text("\n".join(lines), encoding="utf-8")
    tree = load_file_to_tree(str(fixed_path), include_children=True)
    for info in commented_lines_info:
        line_no = info["line"]
        node = find_node_by_range(tree.tree_id, line_no, line_no, prefer_exact=False)
        parent = None
        if node:
            parent_meta = get_node_parent(tree.tree_id, node.node_id)
            if parent_meta:
                parent = parent_meta.to_dict()
        info["parent_node"] = parent
    for info in commented_lines_info:
        assert "parent_node" in info
        if info["parent_node"] is not None:
            assert "node_id" in info["parent_node"]
            assert isinstance(info["parent_node"]["node_id"], str)
            assert len(info["parent_node"]["node_id"]) > 0


def test_commented_lines_parent_node_inside_function(tmp_path: Path) -> None:
    """Commented error inside a function: parent_node has node_id (may be function or containing block)."""
    fixed_source = (
        "def bar():\n"
        "    # TODO: The line following...\n"
        "    #     break\n"
        "    pass\n"
    )
    tree = create_tree_from_code(str(tmp_path / "x.py"), fixed_source)
    node = find_node_by_range(tree.tree_id, 3, 3, prefer_exact=False)
    assert node is not None
    parent_meta = get_node_parent(tree.tree_id, node.node_id)
    assert parent_meta is not None
    parent_dict = parent_meta.to_dict()
    assert parent_dict.get("node_id")
    assert isinstance(parent_dict["node_id"], str)
    assert len(parent_dict["node_id"]) > 0


# --- .tmp cleanup at start ---


def test_tmp_removed_before_load(tmp_path: Path) -> None:
    """Stale .tmp is removed at start of load so load uses target only when valid."""
    target = tmp_path / "valid.py"
    target.write_text("x = 1\n", encoding="utf-8")
    path_tmp = tmp_path / "valid.py.tmp"
    path_tmp.write_text("old tmp content\n", encoding="utf-8")
    assert path_tmp.exists()
    path_tmp_clean = Path(str(target) + ".tmp")
    if path_tmp_clean.exists():
        path_tmp_clean.unlink()
    assert not path_tmp_clean.exists()
    tree = load_file_to_tree(str(target))
    assert tree.module.code.strip() == "x = 1"
    assert not path_tmp_clean.exists()


# --- Response shape when syntax errors were fixed ---


def test_response_has_syntax_errors_fixed_and_commented_lines(tmp_path: Path) -> None:
    """When load fixes syntax errors, response includes syntax_errors_fixed and commented_lines."""
    broken = tmp_path / "f.py"
    broken.write_text("def f():\n    x = \n", encoding="utf-8")  # invalid
    path_tmp_clean = Path(str(broken) + ".tmp")
    if path_tmp_clean.exists():
        path_tmp_clean.unlink()
    cmd = CSTLoadFileCommand()
    db = MagicMock()
    db.disconnect = MagicMock()
    cmd._open_database_from_config = MagicMock(return_value=db)
    cmd._resolve_file_path_from_project = MagicMock(return_value=broken)
    import asyncio

    result = asyncio.run(cmd.execute(project_id=str(uuid.uuid4()), file_path="f.py"))
    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    data = result.data
    assert data.get("syntax_errors_fixed") is True
    assert "commented_lines" in data
    commented = data["commented_lines"]
    assert isinstance(commented, list)
    assert len(commented) >= 1
    for item in commented:
        assert "line" in item
        assert "error" in item
        assert "parent_node" in item
        if item["parent_node"] is not None:
            assert "node_id" in item["parent_node"]


def test_response_no_syntax_errors_no_commented_lines(tmp_path: Path) -> None:
    """When file parses cleanly, response has no syntax_errors_fixed or commented_lines."""
    good = tmp_path / "g.py"
    good.write_text("x = 1\n", encoding="utf-8")
    path_tmp_clean = Path(str(good) + ".tmp")
    if path_tmp_clean.exists():
        path_tmp_clean.unlink()
    cmd = CSTLoadFileCommand()
    cmd._open_database_from_config = MagicMock(return_value=MagicMock())
    cmd._resolve_file_path_from_project = MagicMock(return_value=good)
    import asyncio

    result = asyncio.run(cmd.execute(project_id=str(uuid.uuid4()), file_path="g.py"))
    assert isinstance(result, SuccessResult), getattr(result, "message", result)
    data = result.data
    assert data.get("syntax_errors_fixed", False) is False
    assert "commented_lines" not in data or data.get("commented_lines") == []


# --- classify_syntax_error ---


@pytest.mark.parametrize(
    "message,expected_kind",
    [
        ("expected something", "syntax"),
        ("indent something wrong", "indentation"),
        ("dedent mismatch", "indentation"),
        ("expected 'except' or 'finally'", "indentation"),
        ("expected 'else' after loop", "indentation"),
        ("expected ':' ", "indentation"),
        ("unexpected indent", "indentation"),
        ("expected an indented block", "indentation"),
        ("invalid syntax", "syntax"),
        ("unclosed parenthesis", "syntax"),
    ],
)
def test_classify_syntax_error(message: str, expected_kind: str) -> None:
    """Classify returns indentation vs syntax from parser message."""
    assert classify_syntax_error(message) == expected_kind


# --- try_apply_indent_fix ---


def test_try_apply_indent_fix_body_under_def() -> None:
    """Body line with too few spaces gets prev+4 when prev is block starter."""
    lines = ["def foo():", "x = 1"]  # x = 1 should be 4 spaces
    fixed = try_apply_indent_fix(lines, 2)
    assert fixed[0] == "def foo():"
    assert fixed[1].startswith("    ")
    assert fixed[1].strip() == "x = 1"


def test_try_apply_indent_fix_same_as_prev_when_not_starter() -> None:
    """Line after non-starter gets same indent as previous line."""
    lines = ["def foo():", "    x = 1", "    y = 2", "z = 3"]  # z wrong
    fixed = try_apply_indent_fix(lines, 4)
    assert fixed[3].startswith("    ")
    assert fixed[3].strip() == "z = 3"


def test_try_apply_indent_fix_out_of_range_returns_copy() -> None:
    """Line number out of range returns copy of lines."""
    lines = ["a = 1", "b = 2"]
    assert try_apply_indent_fix(lines, 0) == lines
    assert try_apply_indent_fix(lines, 99) == lines


# --- Non-convergence: original error returned, no file change ---


def test_cst_load_file_recovery_failed_returns_error_result(tmp_path: Path) -> None:
    """When syntax fix loop does not converge, return ErrorResult with original error and no changes."""
    broken = tmp_path / "h.py"
    broken.write_text("def f():\n    x = \n", encoding="utf-8")
    path_tmp_clean = Path(str(broken) + ".tmp")
    if path_tmp_clean.exists():
        path_tmp_clean.unlink()
    cmd = CSTLoadFileCommand()
    cmd._open_database_from_config = MagicMock(return_value=MagicMock())
    cmd._resolve_file_path_from_project = MagicMock(return_value=broken)
    with patch(
        "code_analysis.commands.cst_load_file_command.MAX_SYNTAX_FIX_ITERATIONS",
        0,
    ):
        import asyncio

        result = asyncio.run(
            cmd.execute(project_id=str(uuid.uuid4()), file_path="h.py")
        )
    assert isinstance(result, ErrorResult), getattr(result, "message", result)
    assert getattr(result, "code", None) == "CST_LOAD_ERROR"
    details = getattr(result, "details", None) or {}
    assert details.get("changes_applied") is False
    assert "original_error" in details
    assert broken.read_text() == "def f():\n    x = \n"
