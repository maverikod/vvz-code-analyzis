"""Tests for pre-scan ignore purge SQL batch building and non-ignored file listing."""

from __future__ import annotations

from code_analysis.core.file_watcher_pkg.ignore_pre_scan_purge import (
    build_ignore_purge_sql_batch,
    list_non_ignored_code_files_under_root,
)


def test_build_batch_starts_with_temp_table():
    """Verify test build batch starts with temp table."""
    ids = [
        "aaaaaaaa-bbbb-4ccc-dddd-000000000001",
        "aaaaaaaa-bbbb-4ccc-dddd-000000000002",
        "aaaaaaaa-bbbb-4ccc-dddd-000000000003",
    ]
    ops = build_ignore_purge_sql_batch("proj-1", ids)
    assert ops[0][0].startswith("DROP TABLE IF EXISTS")
    assert "CREATE TEMP TABLE" in ops[1][0]
    assert "TEXT NOT NULL PRIMARY KEY" in ops[1][0]
    assert any("duplicate_occurrences" in x[0] for x in ops)
    assert any("DELETE FROM files WHERE id IN" in x[0] for x in ops)


def test_build_batch_postgres_uses_uuid_temp_column():
    """PostgreSQL: temp purge ids must be UUID so IN (SELECT id FROM temp) matches uuid columns."""
    ops = build_ignore_purge_sql_batch(
        "00000000-0000-0000-0000-000000000001",
        ["aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"],
        use_uuid_temp_table=True,
    )
    assert "UUID NOT NULL PRIMARY KEY" in ops[1][0]


def test_build_ignore_purge_batch_skips_fts_when_disabled():
    """Verify test build ignore purge batch skips fts when disabled."""
    ops = build_ignore_purge_sql_batch(
        "proj-1",
        ["aaaaaaaa-bbbb-4ccc-dddd-000000000001"],
        include_code_content_fts=False,
    )
    assert not any("code_content_fts" in x[0] for x in ops)
    assert not any("rowid" in x[0] for x in ops)


def test_list_non_ignored_prunes_explicit_subtree(tmp_path):
    """Verify test list non ignored prunes explicit subtree."""
    root = tmp_path / "proj"
    root.mkdir()
    vis = root / "visible.py"
    vis.write_text("x=1\n", encoding="utf-8")
    subtree = root / "skip_sub"
    subtree.mkdir()
    (subtree / "secret.py").write_text("y=1\n", encoding="utf-8")
    patterns = ["**/skip_sub/**"]
    paths = list_non_ignored_code_files_under_root(root, patterns)
    names = {p.name for p in paths}
    assert "visible.py" in names
    assert "secret.py" not in names


def test_list_non_ignored_keeps_exception_pattern_inside_ignored_dir(tmp_path):
    """Verify test list non ignored keeps exception pattern inside ignored dir."""
    root = tmp_path / "proj"
    root.mkdir()
    keep = root / "src" / "generated" / "keep.py"
    keep.parent.mkdir(parents=True, exist_ok=True)
    keep.write_text("x=1\n", encoding="utf-8")
    blocked = keep.parent / "drop.py"
    blocked.write_text("x=2\n", encoding="utf-8")

    paths = list_non_ignored_code_files_under_root(
        root,
        ["**/src/generated/**"],
        ignore_exception_patterns=["**/src/generated/keep.py"],
    )
    as_set = {p.resolve() for p in paths}
    assert keep.resolve() in as_set
    assert blocked.resolve() not in as_set
