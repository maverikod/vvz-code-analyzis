"""
Contract tests for analyze_tree mode=dead_code (TZ-CA-DEADCODE-VERIFY-001).

R-1: Every top-level, symbol, and summary field is present; format=json.
R-4: note is non-empty; summary.removable_count == len(removable).
R-5: staleness block present in dead_code output with counts + rebuilt/
     skipped_active_session lists (cross-checks TZ-CA-STALENESS-TESTS-001).

R-2 and R-3 are already covered at unit level in test_analyze_tree_modes.py
(test_dead_code_classification + the D-1 shape assert).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path

import pytest

from code_analysis.commands.analyze_tree.formatters import format_output
from code_analysis.commands.analyze_tree.service import analyze_tree_json
from code_analysis.core.tree_lifecycle.checksum import compute_content_checksum

PROJECT_ID = "22222222-2222-4222-8222-222222222222"

# Field lists from spec TZ-CA-DEADCODE-VERIFY-001 § target_under_test.output_contract
TOP_LEVEL_FIELDS = (
    "mode",
    "roots",
    "staleness",
    "symbols",
    "removable",
    "summary",
    "note",
    "format",
)
SYMBOL_FIELDS = (
    "name",
    "kind",
    "class_name",
    "file",
    "line",
    "classification",
    "production_callers",
    "test_callers",
    "importers",
)
SUMMARY_FIELDS = (
    "total_symbols",
    "live",
    "test_only",
    "import_only",
    "unused",
    "removable_count",
)


class FakeDB:
    """Minimal DatabaseClient stand-in: returns canned rows keyed by SQL table."""

    def __init__(self, tables):
        """Initialize the instance."""
        self._tables = tables

    def execute(self, sql, params=None):
        """Execute the command."""
        if "FROM imports" in sql:
            key = "imports"
        elif "FROM usages" in sql:
            key = "usages"
        elif "FROM classes" in sql:
            key = "classes"
        elif "FROM methods" in sql:
            key = "methods"
        elif "FROM functions" in sql:
            key = "functions"
        elif "file_advisory_lock_leases" in sql:
            key = "leases"
        else:
            key = "files"
        return {"data": list(self._tables.get(key, []))}

    def disconnect(self):
        """Return disconnect."""
        pass


def _write(root: Path, rel: str, content: str) -> None:
    """Return write."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _build_four_class_project(root: Path) -> FakeDB:
    """
    Fixture with one symbol of each classification bucket plus a D-1 analog:

    live_fn        — production caller in pkg/prod_caller.py
    test_only_fn   — only called by tests/test_a.py  (D-1 shape)
    import_only_fn — imported by pkg/consumer.py but never called
    orphan_fn      — defined, never referenced anywhere
    """
    _write(
        root,
        "pkg/sub/a.py",
        (
            "def live_fn(): pass\n"
            "def test_only_fn(): pass\n"
            "def import_only_fn(): pass\n"
            "def orphan_fn(): pass\n"
        ),
    )
    _write(root, "pkg/prod_caller.py", "from pkg.sub.a import live_fn\nlive_fn()\n")
    _write(
        root, "tests/test_a.py", "from pkg.sub.a import test_only_fn\ntest_only_fn()\n"
    )
    _write(root, "pkg/consumer.py", "from pkg.sub.a import import_only_fn\n")

    files = [
        {
            "id": "1",
            "path": str(root / "pkg/sub/a.py"),
            "relative_path": "pkg/sub/a.py",
            "tree_checksum": "x",
        },
        {
            "id": "2",
            "path": str(root / "pkg/prod_caller.py"),
            "relative_path": "pkg/prod_caller.py",
            "tree_checksum": "x",
        },
        {
            "id": "3",
            "path": str(root / "tests/test_a.py"),
            "relative_path": "tests/test_a.py",
            "tree_checksum": "x",
        },
        {
            "id": "4",
            "path": str(root / "pkg/consumer.py"),
            "relative_path": "pkg/consumer.py",
            "tree_checksum": "x",
        },
    ]
    functions = [
        {"file_id": "1", "name": "live_fn", "line": 1, "end_line": 1},
        {"file_id": "1", "name": "test_only_fn", "line": 2, "end_line": 2},
        {"file_id": "1", "name": "import_only_fn", "line": 3, "end_line": 3},
        {"file_id": "1", "name": "orphan_fn", "line": 4, "end_line": 4},
    ]
    usages = [
        {"target_name": "live_fn", "file_id": "2"},
        {"target_name": "test_only_fn", "file_id": "3"},
    ]
    imports = [
        {
            "file_id": "2",
            "name": "live_fn",
            "module": "pkg.sub.a",
            "import_type": "from",
        },
        {
            "file_id": "3",
            "name": "test_only_fn",
            "module": "pkg.sub.a",
            "import_type": "from",
        },
        {
            "file_id": "4",
            "name": "import_only_fn",
            "module": "pkg.sub.a",
            "import_type": "from",
        },
    ]
    return FakeDB(
        {
            "files": files,
            "functions": functions,
            "usages": usages,
            "imports": imports,
            "leases": [],
        }
    )


def _call_dead_code(db: FakeDB, root: Path) -> dict:
    """Return call dead code."""
    return analyze_tree_json(
        db=db,
        project_id=PROJECT_ID,
        project_root=root,
        roots=["pkg/sub/"],
        mode="dead_code",
        include_stdlib=False,
        with_verdict=False,
        limit=50000,
    )


# ---------------------------------------------------------------------------
# R-1: full output contract
# ---------------------------------------------------------------------------


def test_dead_code_full_contract(tmp_path):
    """R-1: every top-level, per-symbol, and summary field is present; format=json."""
    db = _build_four_class_project(tmp_path)
    data = format_output(_call_dead_code(db, tmp_path), "json")

    for field in TOP_LEVEL_FIELDS:
        assert field in data, f"missing top-level field: {field!r}"
    assert data["format"] == "json"
    assert data["mode"] == "dead_code"

    assert data["symbols"], "symbols list must be non-empty for this fixture"
    for sym in data["symbols"]:
        for field in SYMBOL_FIELDS:
            assert (
                field in sym
            ), f"missing symbol field {field!r} on symbol {sym.get('name')!r}"

    summary = data["summary"]
    for field in SUMMARY_FIELDS:
        assert field in summary, f"missing summary field: {field!r}"


# ---------------------------------------------------------------------------
# R-4: note field + removable_count invariant
# ---------------------------------------------------------------------------


def test_dead_code_note_and_removable_count(tmp_path):
    """R-4: note is present and non-empty; removable_count == len(removable)."""
    db = _build_four_class_project(tmp_path)
    data = _call_dead_code(db, tmp_path)

    assert data.get("note"), "note field must be present and non-empty"
    assert data["summary"]["removable_count"] == len(data["removable"])


# ---------------------------------------------------------------------------
# R-5: staleness block in dead_code output
# ---------------------------------------------------------------------------


def test_dead_code_staleness_rebuilt(tmp_path):
    """R-5 (rebuilt path): staleness block present; diverged file lands in rebuilt."""
    _write(tmp_path, "pkg/sub/a.py", "def fn(): pass\n")
    _write(tmp_path, "pkg/sub/b.py", "def gn(): pass\n")
    a_sha = compute_content_checksum((tmp_path / "pkg/sub/a.py").read_text())
    files = [
        {
            "id": "1",
            "path": str(tmp_path / "pkg/sub/a.py"),
            "relative_path": "pkg/sub/a.py",
            "tree_checksum": a_sha,
        },
        {
            "id": "2",
            "path": str(tmp_path / "pkg/sub/b.py"),
            "relative_path": "pkg/sub/b.py",
            "tree_checksum": "STALE",
        },
    ]
    db = FakeDB(
        {"files": files, "functions": [], "usages": [], "imports": [], "leases": []}
    )
    data = analyze_tree_json(
        db=db,
        project_id=PROJECT_ID,
        project_root=tmp_path,
        roots=["pkg/sub/"],
        mode="dead_code",
        include_stdlib=False,
        with_verdict=False,
        limit=50000,
    )

    stale = data["staleness"]
    assert "counts" in stale
    assert "rebuilt" in stale
    assert "skipped_active_session" in stale

    counts = stale["counts"]
    assert counts.get("sha_match") == 1
    assert counts.get("rebuilt") == 1
    assert "pkg/sub/b.py" in stale["rebuilt"]
    assert stale["skipped_active_session"] == []


def test_dead_code_staleness_skipped_active_session(tmp_path):
    """R-5 (session path): diverged file held by an edit-session lease lands in
    skipped_active_session, not rebuilt."""
    _write(tmp_path, "pkg/sub/a.py", "def fn(): pass\n")
    _write(tmp_path, "pkg/sub/b.py", "def gn(): pass\n")
    a_sha = compute_content_checksum((tmp_path / "pkg/sub/a.py").read_text())
    files = [
        {
            "id": "1",
            "path": str(tmp_path / "pkg/sub/a.py"),
            "relative_path": "pkg/sub/a.py",
            "tree_checksum": a_sha,
        },
        {
            "id": "2",
            "path": str(tmp_path / "pkg/sub/b.py"),
            "relative_path": "pkg/sub/b.py",
            "tree_checksum": "STALE",
        },
    ]
    db = FakeDB(
        {
            "files": files,
            "functions": [],
            "usages": [],
            "imports": [],
            "leases": [{"file_path": "pkg/sub/b.py"}],
        }
    )
    data = analyze_tree_json(
        db=db,
        project_id=PROJECT_ID,
        project_root=tmp_path,
        roots=["pkg/sub/"],
        mode="dead_code",
        include_stdlib=False,
        with_verdict=False,
        limit=50000,
    )

    stale = data["staleness"]
    counts = stale["counts"]
    assert counts.get("skipped_active_session") == 1
    assert counts.get("rebuilt") == 0
    assert "pkg/sub/b.py" in stale["skipped_active_session"]
    assert stale["rebuilt"] == []
