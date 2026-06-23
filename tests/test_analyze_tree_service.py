"""
End-to-end test for the analyze_tree shared core + service.

Uses a fake DB (canned rows keyed by table) and real on-disk temp files so the
disk-enumeration, checksum staleness gate, module resolution, mode, and formatter
layers are exercised together without a live database.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from pathlib import Path

from code_analysis.commands.analyze_tree import staleness as st
from code_analysis.commands.analyze_tree.formatters import format_output
from code_analysis.commands.analyze_tree.service import analyze_tree_json
from code_analysis.core.tree_lifecycle.checksum import compute_content_checksum

PROJECT_ID = "11111111-1111-4111-8111-111111111111"


class FakeDB:
    """Minimal DatabaseClient stand-in: returns canned rows by SQL table."""

    def __init__(self, tables):
        self._tables = tables

    def execute(self, sql, params=None):
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
        pass


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _build_project(root: Path):
    _write(root, "pkg/sub/a.py", "from pkg.core.exc import E\nimport os\nx = 1\n")
    _write(root, "pkg/sub/b.py", "from pkg.sub.a import Y\ny = 2\n")
    _write(root, "pkg/core/exc.py", "class E(Exception):\n    pass\n")
    _write(root, "pkg/caller.py", "from pkg.sub.a import Y\n")

    a_sha = compute_content_checksum((root / "pkg/sub/a.py").read_text())
    files = [
        {"id": "1", "path": str(root / "pkg/sub/a.py"), "relative_path": "pkg/sub/a.py",
         "tree_checksum": a_sha},  # sha_match
        {"id": "2", "path": str(root / "pkg/sub/b.py"), "relative_path": "pkg/sub/b.py",
         "tree_checksum": "STALEHASH"},  # rebuilt (R2)
        {"id": "3", "path": str(root / "pkg/core/exc.py"), "relative_path": "pkg/core/exc.py",
         "tree_checksum": "x"},
        {"id": "4", "path": str(root / "pkg/caller.py"), "relative_path": "pkg/caller.py",
         "tree_checksum": "x"},
    ]
    imports = [
        {"file_id": "1", "module": "pkg.core.exc", "name": "E", "import_type": "from"},
        {"file_id": "1", "module": None, "name": "os", "import_type": "import"},
        {"file_id": "1", "module": "pkg.sub.b", "name": "X", "import_type": "from"},
        {"file_id": "2", "module": "pkg.sub.a", "name": "Y", "import_type": "from"},
        {"file_id": "4", "module": "pkg.sub.a", "name": "Y", "import_type": "from"},
    ]
    return FakeDB({"files": files, "imports": imports, "leases": []})


def test_boundary_end_to_end(tmp_path):
    db = _build_project(tmp_path)
    data = analyze_tree_json(
        db=db,
        project_id=PROJECT_ID,
        project_root=tmp_path,
        roots=["pkg/sub/"],
        mode="package_boundary",
        include_stdlib=False,
        with_verdict=True,
        limit=50000,
    )
    assert data["mode"] == "package_boundary"
    assert data["roots"] == ["pkg/sub"]
    assert data["internal_files"] == ["pkg/sub/a.py", "pkg/sub/b.py"]

    # staleness gate (R2): a.py matches, b.py diverged → rebuilt
    counts = data["staleness"]["counts"]
    assert counts[st.SHA_MATCH] == 1
    assert counts[st.REBUILT] == 1
    assert "pkg/sub/b.py" in data["staleness"]["rebuilt"]

    # outbound project leak resolved to a real path (not a bare stem)
    targets = {b["target"] for b in data["outbound"]["project"]}
    assert "pkg/core/exc.py" in targets
    # intra-subtree edge a→b is not outbound
    assert "pkg/sub/b.py" not in targets

    # inbound: external caller resolves to the internal target path
    inbound = {i["importer"]: i["targets"] for i in data["inbound"]}
    assert inbound == {"pkg/caller.py": ["pkg/sub/a.py"]}

    # verdict: exceptions module → pull_in
    verdicts = {v["target"]: v["verdict"] for v in data["verdict"]}
    assert verdicts["pkg/core/exc.py"] == "pull_in"


def test_staleness_rebuilt_and_skipped_active_session(tmp_path):
    """N-1 (in motion): a file whose on-disk content diverges from its DB
    tree_checksum lands in staleness.rebuilt; if an active edit-session lease
    holds it, it lands in skipped_active_session instead — and analysis still
    succeeds either way."""
    _write(tmp_path, "pkg/sub/a.py", "x = 1\n")  # real content, real sha
    _write(tmp_path, "pkg/sub/b.py", "y = 2\n")
    a_sha = compute_content_checksum((tmp_path / "pkg/sub/a.py").read_text())
    files = [
        # a.py: DB checksum matches disk -> sha_match
        {"id": "1", "path": str(tmp_path / "pkg/sub/a.py"), "relative_path": "pkg/sub/a.py", "tree_checksum": a_sha},
        # b.py: DB checksum diverges from disk -> rebuilt (unless a lease holds it)
        {"id": "2", "path": str(tmp_path / "pkg/sub/b.py"), "relative_path": "pkg/sub/b.py", "tree_checksum": "DIVERGED"},
    ]

    # No lease: b.py diverged -> rebuilt
    db = FakeDB({"files": files, "imports": [], "leases": []})
    data = analyze_tree_json(
        db=db, project_id=PROJECT_ID, project_root=tmp_path, roots=["pkg/sub/"],
        mode="package_boundary", include_stdlib=False, with_verdict=False, limit=50000,
    )
    counts = data["staleness"]["counts"]
    assert counts[st.SHA_MATCH] == 1 and counts[st.REBUILT] == 1
    assert "pkg/sub/b.py" in data["staleness"]["rebuilt"]
    assert data["internal_files"] == ["pkg/sub/a.py", "pkg/sub/b.py"]  # analysis still succeeds

    # Active edit-session lease on b.py: diverged -> skipped_active_session (not rebuilt)
    db2 = FakeDB({"files": files, "imports": [], "leases": [{"file_path": "pkg/sub/b.py"}]})
    data2 = analyze_tree_json(
        db=db2, project_id=PROJECT_ID, project_root=tmp_path, roots=["pkg/sub/"],
        mode="package_boundary", include_stdlib=False, with_verdict=False, limit=50000,
    )
    c2 = data2["staleness"]["counts"]
    assert c2[st.SKIPPED_ACTIVE_SESSION] == 1 and c2[st.REBUILT] == 0
    assert "pkg/sub/b.py" in data2["staleness"]["skipped_active_session"]


def test_cycles_end_to_end(tmp_path):
    db = _build_project(tmp_path)
    # add b→? no; a→b? a imports pkg.sub.b, b imports pkg.sub.a → cycle
    data = analyze_tree_json(
        db=db, project_id=PROJECT_ID, project_root=tmp_path, roots=["pkg/sub/"],
        mode="cycles", include_stdlib=False, with_verdict=False, limit=50000,
    )
    assert data["cycles_found"] == 1
    assert set(data["cycles"][0]) == {"pkg/sub/a.py", "pkg/sub/b.py"}


def test_dead_code_end_to_end(tmp_path):
    # Sub-tree pkg/sub with two functions; one is dead (no callers), one is live.
    _write(tmp_path, "pkg/sub/a.py", "def live_fn():\n    return 1\n\ndef dead_fn():\n    return 2\n")
    _write(tmp_path, "pkg/other.py", "x = 1\n")
    files = [
        {"id": "1", "path": str(tmp_path / "pkg/sub/a.py"), "relative_path": "pkg/sub/a.py", "tree_checksum": "x"},
        {"id": "2", "path": str(tmp_path / "pkg/other.py"), "relative_path": "pkg/other.py", "tree_checksum": "x"},
    ]
    functions = [
        {"file_id": "1", "name": "live_fn", "line": 1, "end_line": 2},
        {"file_id": "1", "name": "dead_fn", "line": 4, "end_line": 5},
    ]
    # live_fn is called from a production file outside the sub-tree; dead_fn never.
    usages = [{"target_name": "live_fn", "file_id": "2"}]
    db = FakeDB({"files": files, "functions": functions, "usages": usages, "imports": [], "leases": []})

    data = analyze_tree_json(
        db=db, project_id=PROJECT_ID, project_root=tmp_path, roots=["pkg/sub/"],
        mode="dead_code", include_stdlib=False, with_verdict=False, limit=50000,
    )
    assert data["mode"] == "dead_code"
    s = data["summary"]
    assert s["total_symbols"] == 2
    assert s["live"] == 1 and s["unused"] == 1
    by_name = {r["name"]: r["classification"] for r in data["symbols"]}
    assert by_name == {"live_fn": "live", "dead_fn": "unused"}
    assert [r["name"] for r in data["removable"]] == ["dead_fn"]


def test_dot_and_markdown_formats(tmp_path):
    db = _build_project(tmp_path)
    data = analyze_tree_json(
        db=db, project_id=PROJECT_ID, project_root=tmp_path, roots=["pkg/sub/"],
        mode="dependencies", include_stdlib=False, with_verdict=False, limit=50000,
    )
    dot = format_output(dict(data), "dot")
    assert dot["format"] == "dot"
    assert dot["dot"].startswith("digraph analyze_tree {")

    md = format_output(dict(data), "markdown")
    assert md["format"] == "markdown"
    assert "analyze_tree" in md["markdown"]
