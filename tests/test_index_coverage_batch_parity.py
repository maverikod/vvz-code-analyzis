"""
Parity: batched IndexCoverageService coverage pre-filter vs the old per-file
``check_path`` loop (bug 0c124699).

``filter_grep_candidates_with_reasons`` used to call ``check_path`` once per
candidate, each doing up to 3 sequential DB round-trips (files row lookup,
code_content count, latest cst_hash) - ~1700 execute() calls for 577 files.
It now classifies the whole candidate set with a handful of multi-row
queries (see ``IndexCoverageService._batch_check_paths``). This test proves
the batched path produces byte-for-byte identical per-file verdicts to the
old per-file ``check_path`` loop, while issuing far fewer ``execute()`` calls.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from code_analysis.core.index_coverage import IndexCoverageService

PROJECT_ID = "11111111-1111-1111-1111-111111111111"


class _FakeProject:
    """Stand-in for the ``Project`` object ``get_project`` returns."""

    def __init__(self, root_path: str) -> None:
        """Store the resolved project root used for path matching."""
        self.root_path = root_path


class _FixtureDriver:
    """In-memory driver covering exactly the SQL shapes IndexCoverageService issues.

    Dispatches on substring/param-membership rather than full SQL parsing -
    both the old per-file queries and the new batched queries only ever
    filter ``files``/``code_content``/``cst_trees`` by an equality or
    membership check on the same bind values, so one matcher serves both
    shapes and keeps the two code paths honestly comparable.
    """

    def __init__(
        self,
        files: List[Dict[str, Any]],
        code_content_counts: Dict[str, int],
        cst_rows: List[Dict[str, Any]],
    ) -> None:
        """Store fixture rows and reset call counters."""
        self.files = files
        self.code_content_counts = code_content_counts
        self.cst_rows = cst_rows
        self.execute_calls: List[tuple] = []

    def execute(self, sql: str, params: Optional[tuple] = None) -> Dict[str, Any]:
        """Route a query to the matching in-memory fixture table."""
        self.execute_calls.append((sql, params))
        params = params or ()
        s = " ".join(sql.split())

        if s.startswith("SELECT * FROM files WHERE project_id = ?"):
            project_id = params[0]
            bind_rest = set(params[1:])
            matched = [
                r
                for r in self.files
                if r["project_id"] == project_id
                and not r.get("deleted")
                and (
                    r.get("relative_path") in bind_rest or r.get("path") in bind_rest
                )
            ]
            return {"data": matched}

        if "FROM code_content" in s:
            if "GROUP BY file_id" in s:
                ids = params
                rows = [
                    {"file_id": fid, "c": self.code_content_counts.get(fid, 0)}
                    for fid in ids
                    if self.code_content_counts.get(fid, 0) > 0
                ]
                return {"data": rows}
            file_id = params[0]
            return {"data": [{"c": self.code_content_counts.get(file_id, 0)}]}

        if "FROM cst_trees" in s:
            if "ROW_NUMBER()" in s:
                id_set = set(params)
                by_file: Dict[str, Dict[str, Any]] = {}
                for row in self.cst_rows:
                    if row["file_id"] not in id_set:
                        continue
                    best = by_file.get(row["file_id"])
                    if best is None or row["file_mtime"] > best["file_mtime"]:
                        by_file[row["file_id"]] = row
                return {
                    "data": [
                        {"file_id": fid, "cst_hash": row["cst_hash"]}
                        for fid, row in by_file.items()
                    ]
                }
            file_id = params[0]
            candidates = [r for r in self.cst_rows if r["file_id"] == file_id]
            if not candidates:
                return {"data": []}
            best = max(candidates, key=lambda r: r["file_mtime"])
            return {"data": [{"cst_hash": best["cst_hash"]}]}

        raise AssertionError(f"unexpected SQL in fixture driver: {s!r}")


def _hash_of(text: str) -> str:
    """Return sha256 hex digest matching IndexCoverageService's disk-hash."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.fixture
def coverage_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Build project_root + candidate files + a matching fixture driver.

    Returns (project_root, candidates, make_driver) where make_driver()
    returns a fresh _FixtureDriver over the same fixture data (each variant
    of the code under test gets its own driver + call counter).
    """
    project_root = tmp_path / "proj"
    project_root.mkdir()
    now = time.time()

    # 1. unsupported extension - no DB row needed.
    (project_root / "unsupported.bin").write_bytes(b"\x00\x01")

    # 2. not present in the files table at all.
    (project_root / "not_indexed.py").write_text("x = 1\n", encoding="utf-8")

    # 3. files row exists, but code_content has zero rows for it.
    (project_root / "missing_content.py").write_text("x = 2\n", encoding="utf-8")

    # 4. files row + code_content exist, but the file is gone from disk.
    vanished_rel = "vanished.py"

    # 5. disk mtime newer than the DB's last_modified.
    disk_newer_path = project_root / "disk_newer.py"
    disk_newer_path.write_text("x = 3\n", encoding="utf-8")
    disk_newer_mtime = disk_newer_path.stat().st_mtime

    # 6. cst_hash matches the current disk content -> indexed_current.
    hash_match_text = "x = 4\n"
    hash_match_path = project_root / "hash_match.py"
    hash_match_path.write_text(hash_match_text, encoding="utf-8")
    hash_match_mtime = hash_match_path.stat().st_mtime

    # 7. hash differs/missing, but db_mtime >= disk mtime -> indexed_current.
    mtime_only_path = project_root / "mtime_only_current.py"
    mtime_only_path.write_text("x = 5\n", encoding="utf-8")
    mtime_only_mtime = mtime_only_path.stat().st_mtime

    candidates = [
        "unsupported.bin",
        "not_indexed.py",
        "missing_content.py",
        vanished_rel,
        "disk_newer.py",
        "hash_match.py",
        "mtime_only_current.py",
    ]

    files = [
        {
            "id": "f-missing-content",
            "project_id": PROJECT_ID,
            "relative_path": "missing_content.py",
            "path": "missing_content.py",
            "deleted": False,
            "last_modified": now + 3600,
        },
        {
            "id": "f-vanished",
            "project_id": PROJECT_ID,
            "relative_path": vanished_rel,
            "path": vanished_rel,
            "deleted": False,
            "last_modified": now + 3600,
        },
        {
            "id": "f-disk-newer",
            "project_id": PROJECT_ID,
            "relative_path": "disk_newer.py",
            "path": "disk_newer.py",
            "deleted": False,
            "last_modified": disk_newer_mtime - 3600,  # strictly older than disk
        },
        {
            "id": "f-hash-match",
            "project_id": PROJECT_ID,
            "relative_path": "hash_match.py",
            "path": "hash_match.py",
            "deleted": False,
            # not older than disk (so the mtime-newer branch is skipped) and
            # the cst_hash below matches the disk content -> indexed_current.
            "last_modified": hash_match_mtime + 3600,
        },
        {
            "id": "f-mtime-only",
            "project_id": PROJECT_ID,
            "relative_path": "mtime_only_current.py",
            "path": "mtime_only_current.py",
            "deleted": False,
            "last_modified": mtime_only_mtime + 3600,  # in the future -> "not older than disk"
        },
    ]
    code_content_counts = {
        "f-missing-content": 0,
        "f-vanished": 1,
        "f-disk-newer": 1,
        "f-hash-match": 1,
        "f-mtime-only": 1,
    }
    cst_rows = [
        {"file_id": "f-vanished", "file_mtime": now, "cst_hash": "irrelevant"},
        {"file_id": "f-disk-newer", "file_mtime": now, "cst_hash": "irrelevant"},
        {"file_id": "f-hash-match", "file_mtime": now, "cst_hash": _hash_of(hash_match_text)},
        {"file_id": "f-mtime-only", "file_mtime": now, "cst_hash": "stale-hash-does-not-match"},
    ]

    def make_driver() -> _FixtureDriver:
        """Return a fresh fixture driver + call counter over the same data."""
        return _FixtureDriver(
            files=[dict(r) for r in files],
            code_content_counts=dict(code_content_counts),
            cst_rows=[dict(r) for r in cst_rows],
        )

    fake_project = _FakeProject(root_path=str(project_root))
    monkeypatch.setattr(
        "code_analysis.core.index_coverage.get_project",
        lambda driver, project_id: fake_project,
    )
    monkeypatch.setattr(
        "code_analysis.core.database_driver_pkg.domain.files.get_project",
        lambda driver, project_id: fake_project,
    )

    return project_root, candidates, make_driver


def test_batched_classification_matches_per_file_check_path(coverage_fixture) -> None:
    """Same per-path verdicts; drastically fewer execute() calls."""
    project_root, candidates, make_driver = coverage_fixture

    old_driver = make_driver()
    old_service = IndexCoverageService(old_driver, PROJECT_ID, project_root)
    old_reasons = {rel: old_service.check_path(rel) for rel in candidates}

    new_driver = make_driver()
    new_service = IndexCoverageService(new_driver, PROJECT_ID, project_root)
    new_kept, new_reasons = new_service.filter_grep_candidates_with_reasons(
        candidates, skip_indexed_unchanged=True, indexed_only=False
    )

    assert set(new_reasons.keys()) == set(old_reasons.keys())
    for rel in candidates:
        old_cov = old_reasons[rel]
        new_cov = new_reasons[rel]
        assert new_cov.as_dict() == old_cov.as_dict(), rel

    expected_reasons = {
        "unsupported.bin": "unsupported_format",
        "not_indexed.py": "not_indexed",
        "missing_content.py": "missing_content",
        "vanished.py": "changed_since_index",
        "disk_newer.py": "changed_since_index",
        "hash_match.py": "indexed_current",
        "mtime_only_current.py": "indexed_current",
    }
    for rel, expected_reason in expected_reasons.items():
        assert old_reasons[rel].reason == expected_reason, rel
        assert new_reasons[rel].reason == expected_reason, rel

    # skip_indexed_unchanged=True drops indexed+unchanged (indexed_current) paths.
    expected_kept = {
        rel
        for rel, cov in old_reasons.items()
        if not (cov.indexed and cov.unchanged) and cov.reason != "deleted"
    }
    assert set(new_kept) == expected_kept

    old_call_count = len(old_driver.execute_calls)
    new_call_count = len(new_driver.execute_calls)
    # Old per-file check_path loop, one execute() per short-circuit point:
    #   not_indexed(1) + missing_content(2) + vanished(2) + disk_newer(2)
    #   + hash_match(3) + mtime_only_current(3) = 13, for 6 supported candidates.
    assert old_call_count == 13
    # New: one files lookup + one code_content group-by + one cst_trees group-by,
    # regardless of how many candidates are in the batch.
    assert new_call_count <= 3
    assert new_call_count < old_call_count


def test_batched_classification_handles_indexed_only_and_empty_candidates(
    coverage_fixture,
) -> None:
    """indexed_only filtering and an empty candidate list behave like check_path."""
    project_root, candidates, make_driver = coverage_fixture

    driver = make_driver()
    service = IndexCoverageService(driver, PROJECT_ID, project_root)
    kept, reasons = service.filter_grep_candidates_with_reasons(
        candidates, skip_indexed_unchanged=False, indexed_only=True
    )
    # indexed_only keeps only indexed-and-changed paths.
    assert set(kept) == {"disk_newer.py", "vanished.py"}
    assert set(reasons.keys()) == set(candidates)

    empty_driver = make_driver()
    empty_service = IndexCoverageService(empty_driver, PROJECT_ID, project_root)
    empty_kept, empty_reasons = empty_service.filter_grep_candidates_with_reasons(
        [], skip_indexed_unchanged=True, indexed_only=False
    )
    assert empty_kept == []
    assert empty_reasons == {}
    assert empty_driver.execute_calls == []
