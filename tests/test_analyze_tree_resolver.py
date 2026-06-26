"""
Unit tests for the analyze_tree module→path resolver.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from code_analysis.commands.analyze_tree.resolver import (
    ModulePathResolver,
    is_stdlib_module,
)

PROJECT_FILES = [
    "code_analysis/core/exceptions.py",
    "code_analysis/core/uuid_validation.py",
    "code_analysis/core/cst_tree/builder.py",
    "code_analysis/core/cst_tree/__init__.py",
    "code_analysis/commands/analyze_tree/service.py",
]


def test_resolves_from_import_to_module_file():
    """Verify test resolves from import to module file."""
    r = ModulePathResolver(PROJECT_FILES)
    res = r.resolve(
        module="code_analysis.core.exceptions",
        name="ValidationError",
        import_type="from",
    )
    assert res.kind == "project"
    assert res.rel_path == "code_analysis/core/exceptions.py"


def test_resolves_via_trailing_suffix_without_top_package():
    # Import written as `core.exceptions` (top package not on the dotted name).
    """Verify test resolves via trailing suffix without top package."""
    r = ModulePathResolver(PROJECT_FILES)
    res = r.resolve(module="core.exceptions", name="E", import_type="from")
    assert res.kind == "project"
    assert res.rel_path == "code_analysis/core/exceptions.py"


def test_resolves_package_init():
    """Verify test resolves package init."""
    r = ModulePathResolver(PROJECT_FILES)
    res = r.resolve(module="code_analysis.core.cst_tree", name="x", import_type="from")
    # Prefers the submodule-or-package file; cst_tree resolves to its __init__.py
    assert res.kind == "project"
    assert res.rel_path == "code_analysis/core/cst_tree/__init__.py"


def test_plain_import_uses_name():
    """Verify test plain import uses name."""
    r = ModulePathResolver(PROJECT_FILES)
    res = r.resolve(
        module=None, name="code_analysis.core.uuid_validation", import_type="import"
    )
    assert res.kind == "project"
    assert res.rel_path == "code_analysis/core/uuid_validation.py"


def test_stdlib_classification():
    """Verify test stdlib classification."""
    r = ModulePathResolver(PROJECT_FILES)
    res = r.resolve(module=None, name="os", import_type="import")
    assert res.kind == "stdlib"
    assert res.rel_path is None
    assert is_stdlib_module("os.path") is True


def test_third_party_classification():
    """Verify test third party classification."""
    r = ModulePathResolver(PROJECT_FILES)
    res = r.resolve(module="libcst", name="Module", import_type="from")
    assert res.kind == "third_party"
    assert res.rel_path is None


def test_tie_break_prefers_importer_top_dir():
    """Verify test tie break prefers importer top dir."""
    files = ["a/util.py", "b/util.py"]
    r = ModulePathResolver(files)
    res = r.resolve(
        module=None, name="util", import_type="import", importer_rel="b/main.py"
    )
    assert res.rel_path == "b/util.py"
